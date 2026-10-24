from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any


PASSWORD_ITERATIONS = 240_000
SESSION_LIFETIME_SECONDS = 24 * 60 * 60


def password_hash(password: str, salt_hex: str, iterations: int = PASSWORD_ITERATIONS) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return digest.hex()


def new_password_record(password: str, must_change: bool = False) -> dict[str, Any]:
    salt = secrets.token_bytes(16).hex()
    return {
        "username": "admin",
        "password_salt": salt,
        "password_hash": password_hash(password, salt),
        "password_iterations": PASSWORD_ITERATIONS,
        "must_change_password": must_change,
    }


def verify_password(password: str, auth_config: dict[str, Any]) -> bool:
    try:
        candidate = password_hash(
            password,
            str(auth_config["password_salt"]),
            int(auth_config.get("password_iterations", PASSWORD_ITERATIONS)),
        )
        return hmac.compare_digest(candidate, str(auth_config["password_hash"]))
    except (KeyError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class AdminSession:
    token: str
    csrf_token: str
    expires_at: float


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, AdminSession] = {}
        self._lock = threading.Lock()

    def create(self) -> AdminSession:
        session = AdminSession(
            token=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(24),
            expires_at=time.time() + SESSION_LIFETIME_SECONDS,
        )
        with self._lock:
            self._remove_expired()
            self._sessions[session.token] = session
        return session

    def get(self, token: str | None) -> AdminSession | None:
        if not token:
            return None
        with self._lock:
            self._remove_expired()
            return self._sessions.get(token)

    def remove(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def keep_only(self, token: str) -> None:
        with self._lock:
            current = self._sessions.get(token)
            self._sessions.clear()
            if current and current.expires_at > time.time():
                self._sessions[token] = current

    def _remove_expired(self) -> None:
        now = time.time()
        expired = [token for token, session in self._sessions.items() if session.expires_at <= now]
        for token in expired:
            self._sessions.pop(token, None)
