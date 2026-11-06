"""F17 LLM 超时可配置：默认值/env 覆盖/钳制/非法回退 + httpx 透传 + 探针独立口径。

config 常量在导入时冻结，env 覆盖类断言走子进程独立导入（零污染，不 reload）；
进程内只断言绑定值与透传行为，monkeypatch 全部自动恢复。
"""
import os

os.environ["ALLOW_LOCAL_AI"] = "1"
os.environ["AI_REQUIRED"] = "0"
os.environ["NPC_TICK_INTERVAL"] = "0"

import inspect
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _config_timeout_in_subprocess(raw):
    """在干净子进程里导入 config，读 LLM_TIMEOUT_SECONDS。raw=None 表示不设置。"""
    env = dict(os.environ)
    env.pop("LLM_TIMEOUT_SECONDS", None)
    if raw is not None:
        env["LLM_TIMEOUT_SECONDS"] = raw
    out = subprocess.run(
        [sys.executable, "-c", "import config; print(config.LLM_TIMEOUT_SECONDS)"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    return float(out.stdout.strip())


def test_default_timeout_is_12():
    assert _config_timeout_in_subprocess(None) == 12.0


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("45", 45.0),      # env 覆盖生效
        ("7.5", 7.5),      # 小数可
        ("2", 5.0),        # 下限钳制
        ("999", 120.0),    # 上限钳制
        ("abc", 12.0),     # 非法回退默认
        ("", 12.0),        # 空串回退默认
        ("nan", 12.0),     # NaN 回退默认
        ("inf", 12.0),     # Inf 回退默认
    ],
)
def test_env_override_and_clamp(raw, expected):
    assert _config_timeout_in_subprocess(raw) == expected


def test_signature_defaults_bind_config_value():
    import config
    from ai import gateway, router

    for fn in (gateway._chat_json, gateway._chat_text, gateway._router_data, router.invoke):
        default = inspect.signature(fn).parameters["timeout"].default
        assert default == config.LLM_TIMEOUT_SECONDS, fn.__qualname__


def test_anthropic_default_binds_config_value():
    """login-latency-fix D1.3：CCSwitch 路径默认超时与主通道一致（LLM_TIMEOUT_SECONDS）。"""
    import config
    from ai import gateway

    assert inspect.signature(gateway._anthropic_chat_json).parameters["timeout"].default == config.LLM_TIMEOUT_SECONDS


class _FakeResp:
    status_code = 200
    text = ""

    def __init__(self, content):
        self._content = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def _capture_httpx(monkeypatch, content):
    import httpx

    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["timeout"] = timeout
        seen["url"] = url
        return _FakeResp(content)

    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_chat_json_default_timeout_reaches_httpx(monkeypatch):
    import config
    from ai import gateway

    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    seen = _capture_httpx(monkeypatch, '{"line": "通"}')
    data = gateway._chat_json("任意提示")
    assert data == {"line": "通"}
    assert seen["timeout"] == config.LLM_TIMEOUT_SECONDS


def test_chat_json_explicit_timeout_passthrough(monkeypatch):
    from ai import gateway

    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(gateway, "log_ai_call", lambda **kw: None)
    seen = _capture_httpx(monkeypatch, '{"line": "通"}')
    gateway._chat_json("任意提示", timeout=12.0)
    assert seen["timeout"] == 12.0


def test_chat_text_default_timeout_reaches_httpx(monkeypatch):
    import config
    from ai import gateway

    monkeypatch.setattr(gateway, "LLM_API_KEY", "test-key")
    seen = _capture_httpx(monkeypatch, "一段文本")
    text = gateway._chat_text("任意提示")
    assert text == "一段文本"
    assert seen["timeout"] == config.LLM_TIMEOUT_SECONDS


def test_probe_keeps_own_short_timeout(monkeypatch):
    """健康探针口径独立：仍以 12.0 调 _chat_json，不随主通道默认放大。"""
    from ai import gateway
    from storage.db import WorldStateRepository

    recorded = {}

    def fake_chat_json(prompt, timeout=None):
        recorded["timeout"] = timeout
        return {"line": "通了"}

    monkeypatch.setattr(gateway, "_chat_json", fake_chat_json)
    monkeypatch.setattr(gateway, "ai_available", lambda: True)
    monkeypatch.setattr(WorldStateRepository, "get", staticmethod(lambda key: {}))
    monkeypatch.setattr(WorldStateRepository, "set", staticmethod(lambda key, value: None))

    result = gateway.probe_ai_channel(force=True)
    assert result["ok"] is True
    assert recorded["timeout"] == 12.0
