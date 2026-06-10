"""Database layer — NeonDB (PostgreSQL via psycopg2)."""

import os
import secrets
import string
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import bcrypt
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")


@contextmanager
def _conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()


# ── password helpers ──────────────────────────────────────────────────────────

def _hash(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def _verify(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode(), h.encode())


# ── user helpers ──────────────────────────────────────────────────────────────

def _row_to_user(row) -> dict:
    uid, name, email, class_, curriculum, tier, avatar_url = row
    return {
        "uid": uid,
        "name": name,
        "email": email,
        "class": class_,
        "curriculum": curriculum,
        "tier": tier,
        "avatar_url": avatar_url,
    }


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_user(name: str, email: str, password: str, class_: str, curriculum: str) -> dict | None:
    """Returns user dict or None if email taken."""
    hashed = _hash(password)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT uid FROM users WHERE email=%s", (email,))
            if cur.fetchone():
                return None
            cur.execute(
                "INSERT INTO users (name,email,password,class,curriculum) "
                "VALUES (%s,%s,%s,%s,%s) RETURNING uid,name,email,class,curriculum,tier,avatar_url",
                (name, email, hashed, class_, curriculum),
            )
            row = cur.fetchone()
            conn.commit()
    return _row_to_user(row)


def authenticate_user(email: str, password: str) -> dict | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT uid,name,email,class,curriculum,tier,avatar_url,password "
                "FROM users WHERE email=%s",
                (email,),
            )
            row = cur.fetchone()
    if not row:
        return None
    *user_fields, stored_hash = row
    if not stored_hash or not _verify(password, stored_hash):
        return None
    return _row_to_user(user_fields)


def get_or_create_google_user(google_id: str, email: str, name: str, avatar_url: str) -> dict:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT uid,name,email,class,curriculum,tier,avatar_url "
                "FROM users WHERE google_id=%s OR email=%s",
                (google_id, email),
            )
            row = cur.fetchone()
            if row:
                cur.execute(
                    "UPDATE users SET google_id=%s,avatar_url=%s,last_login=NOW() "
                    "WHERE uid=%s",
                    (google_id, avatar_url, row[0]),
                )
                conn.commit()
                return _row_to_user(row)
            cur.execute(
                "INSERT INTO users (name,email,google_id,avatar_url,class,curriculum) "
                "VALUES (%s,%s,%s,%s,'SSC','NCTB') "
                "RETURNING uid,name,email,class,curriculum,tier,avatar_url",
                (name, email, google_id, avatar_url),
            )
            row = cur.fetchone()
            conn.commit()
    return _row_to_user(row)


def get_user_by_id(uid: int) -> dict | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT uid,name,email,class,curriculum,tier,avatar_url FROM users WHERE uid=%s",
                (uid,),
            )
            row = cur.fetchone()
    return _row_to_user(row) if row else None


def update_user_profile(uid: int, name: str, class_: str, curriculum: str) -> dict | None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET name=%s,class=%s,curriculum=%s WHERE uid=%s "
                "RETURNING uid,name,email,class,curriculum,tier,avatar_url",
                (name, class_, curriculum, uid),
            )
            row = cur.fetchone()
            conn.commit()
    return _row_to_user(row) if row else None


def update_password(email: str, new_password: str) -> bool:
    hashed = _hash(new_password)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET password=%s WHERE email=%s", (hashed, email))
            updated = cur.rowcount > 0
            conn.commit()
    return updated


# ── OTP ───────────────────────────────────────────────────────────────────────

def _gen_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def create_otp(email: str, purpose: str = "reset") -> str:
    code = _gen_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE otp_codes SET used=TRUE WHERE email=%s AND purpose=%s AND used=FALSE",
                (email, purpose),
            )
            cur.execute(
                "INSERT INTO otp_codes (email,code,purpose,expires_at) VALUES (%s,%s,%s,%s)",
                (email, code, purpose, expires_at),
            )
            conn.commit()
    return code


def verify_otp(email: str, code: str, purpose: str = "reset") -> bool:
    now = datetime.now(timezone.utc)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM otp_codes "
                "WHERE email=%s AND code=%s AND purpose=%s AND used=FALSE AND expires_at>%s",
                (email, code, purpose, now),
            )
            row = cur.fetchone()
            if not row:
                return False
            cur.execute("UPDATE otp_codes SET used=TRUE WHERE id=%s", (row[0],))
            conn.commit()
    return True


def user_exists(email: str) -> bool:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE email=%s", (email,))
            return cur.fetchone() is not None


# ── chat history ──────────────────────────────────────────────────────────────

def create_session(uid: int, subject: str, curriculum: str, title: str = "") -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_sessions (uid,title,subject,curriculum) "
                "VALUES (%s,%s,%s,%s) RETURNING id",
                (uid, title or f"{subject} session", subject, curriculum),
            )
            sid = cur.fetchone()[0]
            conn.commit()
    return sid


def save_message(session_id: int, role: str, content: str, sources: list | None = None):
    import json
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO chat_messages (session_id,role,content,sources) VALUES (%s,%s,%s,%s)",
                (session_id, role, content, json.dumps(sources) if sources else None),
            )
            conn.commit()


def get_sessions(uid: int) -> list[dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,title,subject,curriculum,created_at FROM chat_sessions "
                "WHERE uid=%s ORDER BY created_at DESC LIMIT 30",
                (uid,),
            )
            rows = cur.fetchall()
    return [
        {"id": r[0], "title": r[1], "subject": r[2], "curriculum": r[3],
         "created_at": r[4].isoformat()}
        for r in rows
    ]


def get_messages(session_id: int) -> list[dict]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role,content,sources,created_at FROM chat_messages "
                "WHERE session_id=%s ORDER BY created_at ASC",
                (session_id,),
            )
            rows = cur.fetchall()
    return [
        {"role": r[0], "content": r[1], "sources": r[2], "created_at": r[3].isoformat()}
        for r in rows
    ]
