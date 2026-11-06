# 查看 AI 通道配置状态（不打印密钥明文）
from pathlib import Path

p = Path(r"D:\codex\xiuxian\.env")
print("env_exists", p.exists())
if p.exists():
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k == "LLM_API_KEY":
            print(f"{k}={'set(len=%d)' % len(v) if v else 'empty'}")
        else:
            print(f"{k}={'set' if v else 'empty'} ({v if k in ('LLM_API_BASE','LLM_MODEL','USE_CCSWITCH','ALLOW_LOCAL_AI','AI_REQUIRED') else ''})")
import config

print("runtime ai_available", config.ai_available())
print("runtime USE_CCSWITCH", config.USE_CCSWITCH)
print("runtime LLM_API_BASE", config.LLM_API_BASE)
print("runtime LLM_MODEL", config.LLM_MODEL)
print("runtime ALLOW_LOCAL_AI", config.ALLOW_LOCAL_AI)
print("runtime AI_REQUIRED", config.AI_REQUIRED)
