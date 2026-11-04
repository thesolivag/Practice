"""Telegram-approved browser pairing. Only hashes of codes and session tokens are stored.

Pairing is separate from account creation: every resulting session belongs to the
Telegram user who issued its code. Global tables always carry explicit user guards.
"""
import base64
import hashlib
import hmac
import os
import re
import secrets
import time

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse
import pymysql.cursors
import db

COOKIE = "slk_session"
CODE_TTL = 5 * 60
SESSION_TTL = 30 * 86400
MAX_SESSIONS = 10
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_for(token):
    return hmac.new(token.encode(), b"slk-session-csrf-v1", hashlib.sha256).hexdigest()


def _now():
    return int(time.time())


def _origin(request):
    configured = os.environ.get("APP_ORIGIN", "").strip().rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _check_origin(request, extension=False):
    origin = request.headers.get("origin", "")
    if extension and (not origin or re.fullmatch(r"chrome-extension://[a-p]{32}", origin)):
        return
    if origin != _origin(request):
        raise HTTPException(403, "Open this action from your connected app.")


def _client(value):
    if value not in ("browser", "extension"):
        raise HTTPException(422, "Choose browser or extension.")
    return value


def _code(value):
    text = re.sub(r"[\s-]", "", str(value or "")).upper()
    if not re.fullmatch(r"[A-Z2-7]{26}", text):
        raise HTTPException(401, "Pairing code is invalid, expired, or already used.")
    return text


def _database(fn, *args):
    try:
        return fn(*args)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Sign-in storage is unavailable. Please try again.") from None


def _limit(key, limit, period):
    now = _now()
    bucket = now // period
    k = digest(f"{key}:{bucket}")
    db.execute("INSERT INTO auth_rate_limits (k, attempts, expires_at) VALUES (%s, 1, %s) "
               "ON DUPLICATE KEY UPDATE attempts=attempts+1", (k, now + period * 2))
    rows = db.query("SELECT attempts FROM auth_rate_limits WHERE k=%s", (k,))
    if not rows or rows[0]["attempts"] > limit:
        raise HTTPException(429, "Too many sign-in attempts. Please wait a few minutes.")


def _cleanup():
    now = _now()
    db.execute("DELETE FROM web_auth_codes WHERE expires_at < %s", (now - 86400,))
    db.execute("DELETE FROM browser_sessions WHERE expires_at < %s", (now - 86400,))
    db.execute("DELETE FROM auth_rate_limits WHERE expires_at < %s", (now,))


def issue_code(uid, client="browser"):
    client = _client(client)
    _limit("issue:" + str(uid), 5, 15 * 60)
    _cleanup()
    raw = base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")
    now = _now()
    conn = db.connect()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute("INSERT IGNORE INTO app_users (user_id) VALUES (%s)", (int(uid),))
            cur.execute("SELECT user_id FROM app_users WHERE user_id=%s FOR UPDATE", (int(uid),))
            cur.fetchone()
            cur.execute("UPDATE web_auth_codes SET used_at=%s WHERE user_id=%s AND client=%s AND used_at IS NULL",
                        (now, int(uid), client))
            cur.execute("INSERT INTO web_auth_codes (code_hash, user_id, client, created_at, expires_at, used_at) "
                        "VALUES (%s,%s,%s,%s,%s,NULL)", (digest(raw), int(uid), client, now, now + CODE_TTL))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"code": "-".join(raw[i:i+4] for i in range(0, len(raw), 4)),
            "client": client, "expires_at": now + CODE_TTL}


def consume_code(raw, client, name):
    """Row lock and session creation share one transaction: concurrent redeems have one winner."""
    raw = _code(raw)
    client = _client(client)
    name = re.sub(r"[\x00-\x1f\x7f]", "", str(name or "Connected browser"))[:80]
    token = secrets.token_urlsafe(32)
    sid = secrets.token_hex(16)
    conn = db.connect()
    try:
        conn.begin()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            # Discover identity without locking the code, then always acquire the
            # account lock before code locks (same order as issue_code).
            cur.execute("SELECT user_id FROM web_auth_codes WHERE code_hash=%s", (digest(raw),))
            identity = cur.fetchone()
            if not identity:
                raise HTTPException(401, "Pairing code is invalid, expired, or already used.")
            uid = int(identity["user_id"])
            cur.execute("SELECT user_id FROM app_users WHERE user_id=%s FOR UPDATE", (uid,))
            if not cur.fetchone():
                raise HTTPException(401, "Pairing code is invalid, expired, or already used.")
            cur.execute("SELECT user_id, client, expires_at, used_at FROM web_auth_codes "
                        "WHERE code_hash=%s FOR UPDATE", (digest(raw),))
            row = cur.fetchone()
            now = _now()
            if (not row or int(row["user_id"]) != uid or row["used_at"] is not None
                    or row["expires_at"] <= now or row["client"] != client):
                raise HTTPException(401, "Pairing code is invalid, expired, or already used.")
            # Locking read observes sessions committed while we waited for the
            # account lock, even under MySQL REPEATABLE READ snapshot isolation.
            cur.execute("SELECT id FROM browser_sessions "
                        "WHERE user_id=%s AND revoked_at IS NULL AND expires_at>%s FOR UPDATE", (uid, now))
            if len(cur.fetchall()) >= MAX_SESSIONS:
                raise HTTPException(409, "Disconnect an existing browser in Telegram before connecting another.")
            cur.execute("UPDATE web_auth_codes SET used_at=%s WHERE code_hash=%s AND used_at IS NULL",
                        (now, digest(raw)))
            if cur.rowcount != 1:
                raise HTTPException(401, "Pairing code is invalid, expired, or already used.")
            cur.execute("INSERT INTO browser_sessions "
                        "(id, token_hash, user_id, client, name, created_at, expires_at, revoked_at) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,NULL)",
                        (sid, digest(token), uid, client, name, now, now + SESSION_TTL))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return {"user": {"id": uid}, "token": token, "csrf": csrf_for(token),
            "session_id": sid, "expires_at": now + SESSION_TTL, "auth_method": client}


def resolve_user(request):
    """Resolve only a cookie/Bearer session; caller keeps existing Telegram validation and tenancy scope."""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        client = "extension"
    else:
        token = request.cookies.get(COOKIE, "")
        client = "browser"
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise HTTPException(403, "Sign in through Telegram or connect this browser.")
    rows = _database(db.query, "SELECT id, user_id, client, expires_at FROM browser_sessions "
                     "WHERE token_hash=%s AND revoked_at IS NULL AND expires_at>%s", (digest(token), _now()))
    if not rows or rows[0]["client"] != client:
        raise HTTPException(403, "This browser session expired or was disconnected. Connect it again in Telegram.")
    row = rows[0]
    if client == "browser" and request.method not in SAFE_METHODS:
        _check_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf_for(token)):
            raise HTTPException(403, "Refresh the page and try again.")
    request.state.auth_method = client
    request.state.session_id = row["id"]
    request.state.session_expires_at = row["expires_at"]
    request.state.csrf = csrf_for(token)
    return {"id": int(row["user_id"]), "auth_method": client}


def register_routes(app, validate_telegram):
    """validate_telegram is app.validate_init_data; avoids circular imports and reused browser identity."""
    def telegram(request):
        init = request.headers.get("x-telegram-init-data", "")
        authorization = request.headers.get("authorization", "")
        if not init and authorization.lower().startswith("tma "):
            init = authorization[4:]
        try:
            user = validate_telegram(init, os.environ.get("TELEGRAM_BOT_TOKEN", ""), "*")
        except ValueError:
            raise HTTPException(403, "Open this action inside the Telegram Mini App.") from None
        return user

    @app.post("/api/auth/pair-code")
    def pair_code(request: Request, body: dict = Body(default={})):
        user = telegram(request)
        result = _database(issue_code, user["id"], body.get("client", "browser"))
        return JSONResponse(result, headers={"Cache-Control": "no-store"})

    @app.post("/api/auth/redeem")
    def redeem(request: Request, body: dict = Body(...)):
        client = _client(body.get("client", "browser"))
        _check_origin(request, extension=client == "extension")
        ip = request.client.host if request.client else "unknown"
        _database(_limit, "redeem:" + ip, 20, 5 * 60)
        result = _database(consume_code, body.get("code"), client, body.get("name"))
        token = result.pop("token")
        if client == "extension":
            result["token"] = token
        response = JSONResponse(result, headers={"Cache-Control": "no-store"})
        if client == "browser":
            response.set_cookie(COOKIE, token, max_age=SESSION_TTL, secure=True, httponly=True,
                                samesite="strict", path="/")
        return response

    @app.get("/api/auth/session")
    def session(request: Request):
        if request.headers.get("x-telegram-init-data") or request.headers.get("authorization", "").lower().startswith("tma "):
            return JSONResponse({"user": telegram(request), "auth_method": "telegram", "csrf": None},
                                headers={"Cache-Control": "no-store"})
        user = resolve_user(request)
        return JSONResponse({"user": user, "auth_method": request.state.auth_method,
                             "csrf": request.state.csrf, "expires_at": request.state.session_expires_at,
                             "session_id": request.state.session_id}, headers={"Cache-Control": "no-store"})

    @app.get("/api/auth/sessions")
    def sessions(request: Request):
        user = telegram(request)
        return _database(db.query, "SELECT id, client, name, created_at, expires_at FROM browser_sessions "
                         "WHERE user_id=%s AND revoked_at IS NULL AND expires_at>%s ORDER BY created_at DESC LIMIT 100",
                         (user["id"], _now()))

    @app.delete("/api/auth/sessions/{session_id}")
    def revoke(session_id: str, request: Request):
        user = telegram(request)
        _database(db.execute, "UPDATE browser_sessions SET revoked_at=%s WHERE id=%s AND user_id=%s AND revoked_at IS NULL",
                  (_now(), session_id, user["id"]))
        return {"ok": True}

    @app.post("/api/auth/logout")
    def logout(request: Request):
        user = resolve_user(request)
        _database(db.execute, "UPDATE browser_sessions SET revoked_at=%s WHERE id=%s AND user_id=%s",
                  (_now(), request.state.session_id, user["id"]))
        response = JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})
        response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")
        return response
