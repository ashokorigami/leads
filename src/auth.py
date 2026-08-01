"""Accounts and sessions.

Passwords use stdlib scrypt — no extra dependency, and the cost parameters are
stored alongside the hash so they can be raised later without invalidating
anyone's password. Session tokens are stored HASHED: a leaked database dump
does not hand over live sessions.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from config import db

# ~100ms per hash on this box. Raise N, not the others, if that gets cheap.
_N, _R, _P, _DKLEN, _SALT = 2 ** 14, 8, 1, 32, 16

SESSION_DAYS = 30
COOKIE = "origami_session"


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(_SALT)
    dk = hashlib.scrypt(pw.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt_hex, hash_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
    except (ValueError, TypeError):
        return False
    # compare_digest, not ==, so a wrong password cannot be found byte by byte.
    return hmac.compare_digest(dk.hex(), hash_hex)


def create_user(email: str, name: str, password: str, role: str = "admin") -> int:
    with db() as c, c.cursor() as cur:
        cur.execute(
            """INSERT INTO users (email, name, password_hash, role)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (email) DO UPDATE
                 SET name = EXCLUDED.name,
                     password_hash = EXCLUDED.password_hash,
                     role = EXCLUDED.role
               RETURNING id""",
            (email.strip().lower(), name, hash_password(password), role))
        return cur.fetchone()[0]


def set_password(email: str, password: str) -> bool:
    with db() as c, c.cursor() as cur:
        cur.execute("UPDATE users SET password_hash=%s WHERE email=%s",
                    (hash_password(password), email.strip().lower()))
        return cur.rowcount == 1


def login(email: str, password: str) -> str | None:
    """Returns a fresh session token, or None. Never says WHICH half was wrong."""
    with db() as c, c.cursor() as cur:
        cur.execute("SELECT id, password_hash, active FROM users WHERE email=%s",
                    (email.strip().lower(),))
        row = cur.fetchone()
    if not row:
        # Burn the same time as a real check so timing does not reveal whether
        # the address exists.
        verify_password(password, hash_password("decoy"))
        return None
    uid, stored, active = row
    if not active or not verify_password(password, stored):
        return None

    token = secrets.token_urlsafe(32)
    with db() as c, c.cursor() as cur:
        cur.execute(
            """INSERT INTO sessions (token_hash, user_id, expires_at)
               VALUES (%s, %s, %s)""",
            (hashlib.sha256(token.encode()).hexdigest(), uid,
             datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)))
        cur.execute("UPDATE users SET last_login = now() WHERE id=%s", (uid,))
    return token


def current_user(token: str | None) -> dict | None:
    if not token:
        return None
    with db() as c, c.cursor() as cur:
        cur.execute(
            """SELECT u.id, u.email, u.name, u.role
               FROM sessions s JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = %s AND s.expires_at > now() AND u.active""",
            (hashlib.sha256(token.encode()).hexdigest(),))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("UPDATE sessions SET last_seen = now() WHERE token_hash=%s",
                    (hashlib.sha256(token.encode()).hexdigest(),))
    return dict(zip(("id", "email", "name", "role"), row))


def logout(token: str | None) -> None:
    if not token:
        return
    with db() as c, c.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE token_hash=%s",
                    (hashlib.sha256(token.encode()).hexdigest(),))


def purge_expired() -> int:
    with db() as c, c.cursor() as cur:
        cur.execute("DELETE FROM sessions WHERE expires_at < now()")
        return cur.rowcount
