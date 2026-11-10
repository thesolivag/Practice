"""OAuth tokens + settings storage for the cTrader client.

Tokens are read from the DB `settings` table (keys ctrader_access_token, ctrader_refresh_token,
ctrader_token_expiry = unix seconds) when available, else from env CTRADER_ACCESS_TOKEN /
CTRADER_REFRESH_TOKEN. Refreshed tokens are written back to the DB (the refresh call invalidates
the previous refresh token, so without a DB the new pair is only kept in memory for this process).

CLI (one-time setup, see ctrader/README.md):
    python -m ctrader.tokens auth-url --redirect-uri https://example.com/callback
    python -m ctrader.tokens exchange --code CODE --redirect-uri https://example.com/callback
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
from contextlib import contextmanager

AUTH_URI = "https://openapi.ctrader.com/apps/auth"
TOKEN_URI = "https://openapi.ctrader.com/apps/token"
REFRESH_MARGIN_S = 3 * 24 * 3600  # refresh when < 3 days left


class MemorySettings:
    """Fallback settings store (no DB): env-seeded, process-local."""

    def __init__(self, initial=None):
        self.d = dict(initial or {})

    def get(self, k, default=None):
        return self.d.get(k, default)

    def set(self, k, v):
        self.d[k] = None if v is None else str(v)


class DbSettings:
    """Owner settings on dedicated connections, safe beside threaded news and alert jobs."""

    def __init__(self, db):
        self.db = db

    def get(self, k, default=None):
        from slk import tenancy
        with tenancy.scope(None):
            conn = self.db.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT v FROM settings WHERE k=%s", (k,))
                    row = cur.fetchone()
                return row["v"] if row and row["v"] is not None else default
            finally:
                conn.close()

    def set(self, k, v):
        from slk import tenancy
        with tenancy.scope(None):
            conn = self.db.connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)",
                                (k, None if v is None else str(v)))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()


def default_settings(strict=True):
    """DbSettings when DATABASE_URL is set, else MemorySettings. With strict=True an unusable DB
    raises (so the kill switch is never silently skipped); strict=False falls back to memory."""
    if os.environ.get("DATABASE_URL"):
        try:
            from slk import db  # optional dependency, see CONTRACT.md
            store = DbSettings(db)
            store.get("kill_switch", "off")
            return store
        except Exception as e:
            if strict:
                raise
            print(f"warning: DB settings unavailable ({type(e).__name__}); using env tokens only")
    return MemorySettings()


def load_tokens(settings):
    if isinstance(settings, DbSettings):
        # One statement observes a coherent committed token pair. Three separate
        # reads could straddle another runner's atomic rotation.
        from slk import tenancy
        with tenancy.scope(None):
            conn = settings.db.connect()
            try:
                return _read_pair(conn)
            finally:
                conn.close()
    return {
        "access_token": settings.get("ctrader_access_token") or os.environ.get("CTRADER_ACCESS_TOKEN"),
        "refresh_token": settings.get("ctrader_refresh_token") or os.environ.get("CTRADER_REFRESH_TOKEN"),
        "expiry": _to_float(settings.get("ctrader_token_expiry")),
    }


def needs_refresh(tokens, now=None):
    exp = tokens.get("expiry")
    if not exp:
        return False  # unknown expiry: refresh only on an auth failure
    return exp - (now or time.time()) < REFRESH_MARGIN_S


def _to_float(v):
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _token_request(params, http_get=None):
    if http_get is None:
        import requests
        http_get = lambda url, params: requests.get(url, params=params, timeout=30,  # noqa: E731
                                                    headers={"Accept": "application/json"}).json()
    data = http_get(TOKEN_URI, params)
    if not data.get("accessToken") or data.get("errorCode"):
        raise RuntimeError(f"token request failed: {data.get('errorCode')} {data.get('description')}")
    return data


def refresh_tokens(settings=None, refresh_token=None, client_id=None, client_secret=None, http_get=None):
    """OAuth refresh. Stores new access/refresh token + expiry in settings; returns the tokens dict."""
    settings = settings if settings is not None else default_settings()
    if isinstance(settings, DbSettings):
        # Observe before waiting: another runner may rotate this pair while we wait.
        observed = load_tokens(settings)
        return _refresh_db(settings, observed, refresh_token, client_id, client_secret, http_get)
    refresh_token = refresh_token or load_tokens(settings)["refresh_token"]
    if not refresh_token:
        raise RuntimeError("no refresh token (CTRADER_REFRESH_TOKEN / settings.ctrader_refresh_token)")
    data = _token_request({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id or os.environ["CTRADER_CLIENT_ID"],
        "client_secret": client_secret or os.environ["CTRADER_CLIENT_SECRET"],
    }, http_get)
    return _store(settings, data)


def _store(settings, data):
    if isinstance(settings, DbSettings):
        with _oauth_lock(settings) as conn:
            return _persist_pair(conn, data, _read_pair(conn))
    expiry = int(time.time() + int(data.get("expiresIn") or 0)) if data.get("expiresIn") else None
    settings.set("ctrader_access_token", data["accessToken"])
    if data.get("refreshToken"):
        settings.set("ctrader_refresh_token", data["refreshToken"])
    if expiry:
        settings.set("ctrader_token_expiry", expiry)
    return {"access_token": data["accessToken"], "refresh_token": data.get("refreshToken"), "expiry": expiry}



TOKEN_LOCK = "slk:ctrader:oauth-refresh:v1"
TOKEN_KEYS = ("ctrader_access_token", "ctrader_refresh_token", "ctrader_token_expiry")


@contextmanager
def _oauth_lock(settings):
    """A separate connection owns this server-side lock across HTTP and persistence.

    This is deliberately not the market-feed lease, which callers may already own.
    A busy/unavailable DB never permits an unlocked refresh or env-only fallback.
    """
    from slk import tenancy
    with tenancy.scope(None):
        conn = settings.db.connect()
        acquired = False
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT GET_LOCK(%s,60) AS acquired", (TOKEN_LOCK,))
                row = cur.fetchone()
                acquired = bool(row and row.get("acquired") == 1)
            if not acquired:
                raise RuntimeError("cTrader token refresh is busy; retry on the next run")
            yield conn
        finally:
            if acquired:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT RELEASE_LOCK(%s)", (TOKEN_LOCK,))
                except Exception:
                    pass  # Closing the dedicated connection also releases its named lock.
            conn.close()


def _read_pair(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT k,v FROM settings WHERE k IN (%s,%s,%s)", TOKEN_KEYS)
        values = {r["k"]: r["v"] for r in cur.fetchall()}
    return {"access_token": values.get(TOKEN_KEYS[0]) or os.environ.get("CTRADER_ACCESS_TOKEN"),
            "refresh_token": values.get(TOKEN_KEYS[1]) or os.environ.get("CTRADER_REFRESH_TOKEN"),
            "expiry": _to_float(values.get(TOKEN_KEYS[2]))}


def _persist_pair(conn, data, previous):
    """One commit publishes all three fields, so readers never see a partial pair."""
    expiry = int(time.time() + int(data["expiresIn"])) if data.get("expiresIn") else None
    result = {"access_token": data["accessToken"],
              "refresh_token": data.get("refreshToken") or previous.get("refresh_token"), "expiry": expiry}
    values = [(TOKEN_KEYS[0], result["access_token"]), (TOKEN_KEYS[1], result["refresh_token"]),
              (TOKEN_KEYS[2], str(expiry) if expiry is not None else None)]
    try:
        conn.begin()
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO settings (k,v) VALUES (%s,%s) ON DUPLICATE KEY UPDATE v=VALUES(v)", values)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return result


def _refresh_db(settings, observed, requested, client_id, client_secret, http_get):
    with _oauth_lock(settings) as conn:
        current = _read_pair(conn)
        changed = ((current["access_token"], current["refresh_token"]) !=
                   (observed["access_token"], observed["refresh_token"]))
        stale_argument = bool(requested and requested != current["refresh_token"])
        usable = current["access_token"] and (not current["expiry"] or current["expiry"] > time.time())
        if usable and (changed or stale_argument):
            return current
        # The DB pair wins over a stale explicit refresh token, even when access expired.
        refresh = current["refresh_token"] or requested
        if not refresh:
            raise RuntimeError("no cTrader refresh token is configured")
        try:
            if not (client_id and client_secret):
                from slk.runtime_config import credentials
                configured_id,configured_secret=credentials(settings)
                client_id,client_secret=configured_id,configured_secret
            if not (client_id and client_secret):
                raise RuntimeError("Broker application credentials are not configured")
            data = _token_request({"grant_type": "refresh_token", "refresh_token": refresh,
                                   "client_id": client_id, "client_secret": client_secret}, http_get)
        except Exception:
            # HTTP exceptions may embed query parameters containing OAuth secrets.
            raise RuntimeError("cTrader token refresh failed") from None
        return _persist_pair(conn, data, current)

def auth_url(client_id, redirect_uri, scope="trading"):
    q = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri, "scope": scope})
    return f"{AUTH_URI}?{q}"


def exchange_code(code, redirect_uri, client_id, client_secret, http_get=None):
    return _token_request({
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "client_secret": client_secret,
    }, http_get)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m ctrader.tokens")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("auth-url")
    a.add_argument("--redirect-uri", required=True)
    e = sub.add_parser("exchange")
    e.add_argument("--code", required=True)
    e.add_argument("--redirect-uri", required=True)
    e.add_argument("--save-db", action="store_true", help="also write tokens to DB settings")
    sub.add_parser("refresh", help="refresh now and store in DB settings")
    args = ap.parse_args(argv)
    cid = os.environ.get("CTRADER_CLIENT_ID")
    if not cid:
        sys.exit("set CTRADER_CLIENT_ID (and CTRADER_CLIENT_SECRET) in the environment")
    if args.cmd == "auth-url":
        print(auth_url(cid, args.redirect_uri))
    elif args.cmd == "exchange":
        data = exchange_code(args.code, args.redirect_uri, cid, os.environ["CTRADER_CLIENT_SECRET"])
        if args.save_db:
            _store(default_settings(), data)
        # Printed on purpose: this is the one-time, local, interactive setup step.
        print(json.dumps({k: data.get(k) for k in ("accessToken", "refreshToken", "expiresIn", "tokenType")}, indent=1))
    else:
        t = refresh_tokens()
        print(f"refreshed; expires at {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(t['expiry'] or 0))}")


if __name__ == "__main__":
    main()
