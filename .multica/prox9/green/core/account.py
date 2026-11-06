"""
账号注册 / 登录（盐 + PBKDF2）
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import uuid
from typing import Any, Dict, Optional

from storage.db import AccountRepository, AuthSessionRepository, CharacterRepository, LegacyRepository, ChronicleRepository

USERNAME_RE = re.compile(r"^[一-鿿A-Za-z0-9_]{2,16}$")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


def register(username: str, password: str, *, display_name: Optional[str] = None) -> Dict[str, Any]:
    username = (username or "").strip()
    password = password or ""
    if not USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名需 2–16 位中文/字母/数字/下划线"}
    if len(password) < 6:
        return {"ok": False, "error": "密码至少 6 位"}
    if AccountRepository.get_by_username(username):
        return {"ok": False, "error": "该用户名已存在，请直接登录"}
    salt = uuid.uuid4().hex[:16]
    ph = _hash_password(password, salt)
    uid = AccountRepository.create(username, ph, salt)
    if not uid:
        return {"ok": False, "error": "注册失败（用户名冲突）"}
    return {"ok": True, "user_id": uid, "username": username, "display_name": display_name or username}


def login(username: str, password: str) -> Dict[str, Any]:
    username = (username or "").strip()
    acc = AccountRepository.get_by_username(username)
    if not acc:
        return {"ok": False, "error": "账号不存在，请先注册"}
    ph = _hash_password(password or "", acc["salt"])
    if not hmac.compare_digest(ph, acc["password_hash"]):
        return {"ok": False, "error": "密码错误"}
    AccountRepository.touch_login(acc["user_id"])
    return {"ok": True, "user_id": acc["user_id"], "username": acc["username"]}


def bind_session(token: str, user_id: str, character_id: str, name: str) -> None:
    AuthSessionRepository.save(token, user_id, character_id, name)
