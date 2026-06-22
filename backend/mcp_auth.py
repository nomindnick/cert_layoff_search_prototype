"""OAuth 2.1 authorization-server bridge for the MCP connector.

claude.ai's custom connector expects the MCP server to be an OAuth 2.1
authorization + resource server (Dynamic Client Registration, /authorize,
/token, PKCE, audience-bound tokens). The mcp SDK auto-mounts all of those
endpoints when given an ``OAuthAuthorizationServerProvider``; this module is
that provider, bridged to the app's existing per-person magic-link tokens:

  * the consent page (/oauth/consent) asks the user for the access token she
    already has — validated against ``backend.auth.TOKENS`` — and the issued
    OAuth identity (``subject``) IS that magic-link token, so her MCP activity
    logs under the same analytics user id as the web app;
  * clients, authorization codes, and tokens persist in the analytics database
    (Postgres on Railway) so a redeploy doesn't force her to reconnect.

Only active when ``settings.PUBLIC_BASE_URL`` is set (see backend/config.py).
"""

from __future__ import annotations

import html
import json
import logging
import secrets
import time

from sqlalchemy import Column, Float, MetaData, String, Table, Text, delete, select
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from backend import auth as magic_auth
from backend.config import settings
from backend.db import engine

logger = logging.getLogger(__name__)

# --- Policy ---------------------------------------------------------------- #
SCOPE = "corpus.read"
ACCESS_TTL = 3600              # 1h access tokens
REFRESH_TTL = 30 * 24 * 3600   # 30d refresh tokens
CODE_TTL = 300                 # 5min authorization codes
PENDING_TTL = 600              # 10min to complete the consent page

BASE = settings.PUBLIC_BASE_URL.rstrip("/")
RESOURCE = f"{BASE}/mcp" if BASE else ""

# --- Storage (shares the analytics DB engine; portable sqlite/postgres) ---- #
_md = MetaData()


def _tbl(name: str) -> Table:
    # key -> JSON blob (+ expiry for codes/tokens/pending; clients don't expire)
    return Table(
        name,
        _md,
        Column("key", String(255), primary_key=True),
        Column("data", Text, nullable=False),
        Column("kind", String(16)),         # 'access' | 'refresh' (tokens only)
        Column("grant_id", String(64)),      # links the access+refresh pair (tokens)
        Column("expires_at", Float),         # epoch seconds; NULL = no expiry
    )


oauth_clients = _tbl("oauth_clients")
oauth_pending = _tbl("oauth_pending")
oauth_codes = _tbl("oauth_codes")
oauth_tokens = _tbl("oauth_tokens")


def create_all() -> None:
    """Create the oauth_* tables if missing. Idempotent; call at startup."""
    _md.create_all(engine)


def _put(table, key, data, *, kind=None, grant_id=None, expires_at=None):
    # upsert-by-delete-then-insert (portable; volumes are tiny)
    with engine.begin() as conn:
        conn.execute(delete(table).where(table.c.key == key))
        conn.execute(
            table.insert().values(
                key=key, data=data, kind=kind, grant_id=grant_id, expires_at=expires_at
            )
        )


def _consume(table, key) -> str | None:
    """Atomically delete a row and return its data iff THIS call removed it.

    Makes single-use (authorization codes) race-safe: concurrent redemptions of
    the same code serialize on the DELETE — exactly one sees rowcount==1.
    """
    with engine.begin() as conn:
        res = conn.execute(
            delete(table).where(table.c.key == key).returning(table.c.data, table.c.expires_at)
        )
        row = res.first()
    if row is None:
        return None
    data, expires_at = row
    if expires_at is not None and expires_at < time.time():
        return None
    return data


def _get(table, key, *, kind=None):
    with engine.connect() as conn:
        stmt = select(table.c.data, table.c.expires_at, table.c.kind).where(table.c.key == key)
        row = conn.execute(stmt).first()
    if row is None:
        return None
    data, expires_at, row_kind = row
    if kind is not None and row_kind != kind:
        return None
    if expires_at is not None and expires_at < time.time():
        _delete(table, key)  # opportunistic GC of the expired row
        return None
    return data


def _delete(table, key):
    with engine.begin() as conn:
        conn.execute(delete(table).where(table.c.key == key))


# --- Provider -------------------------------------------------------------- #
class MagicLinkOAuthProvider:
    """OAuthAuthorizationServerProvider bridging OAuth to magic-link tokens."""

    # -- Dynamic client registration --
    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        raw = _get(oauth_clients, client_id)
        return OAuthClientInformationFull.model_validate_json(raw) if raw else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _put(oauth_clients, client_info.client_id, client_info.model_dump_json())

    # -- Authorize: stash the request, redirect to our consent page --
    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        rid = secrets.token_urlsafe(24)
        pending = {
            "client_id": client.client_id,
            "redirect_uri": str(params.redirect_uri),
            "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
            "code_challenge": params.code_challenge,
            "state": params.state,
            "scopes": params.scopes or [SCOPE],
            "resource": params.resource,
        }
        _put(oauth_pending, rid, json.dumps(pending), expires_at=time.time() + PENDING_TTL)
        return f"{BASE}/oauth/consent?rid={rid}"

    # -- Authorization codes --
    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        raw = _get(oauth_codes, authorization_code)
        if not raw:
            return None
        ac = AuthorizationCode.model_validate_json(raw)
        if ac.client_id != client.client_id:
            return None
        return ac

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        # Single-use, race-safe: only the caller that wins the atomic delete
        # proceeds; a concurrent replay of the same code gets invalid_grant.
        if _consume(oauth_codes, authorization_code.code) is None:
            raise TokenError("invalid_grant", "authorization code already used or expired")
        return self._issue(client.client_id, authorization_code.scopes,
                           authorization_code.subject, authorization_code.resource)

    # -- Refresh tokens (rotating) --
    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        raw = _get(oauth_tokens, refresh_token, kind="refresh")
        if not raw:
            return None
        rt = RefreshToken.model_validate_json(raw)
        if rt.client_id != client.client_id:
            return None
        return rt

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        # Rotate the whole grant: revoke the old access+refresh pair, then mint a
        # new one (so the prior access token can't outlive the rotated refresh).
        self._revoke_grant(refresh_token.token)
        granted = scopes or refresh_token.scopes
        return self._issue(client.client_id, granted, refresh_token.subject, RESOURCE)

    # -- Access tokens --
    async def load_access_token(self, token: str) -> AccessToken | None:
        raw = _get(oauth_tokens, token, kind="access")
        if not raw:
            return None
        at = AccessToken.model_validate_json(raw)
        # Audience binding (RFC 8707): only honor tokens minted for THIS server.
        if RESOURCE and at.resource and at.resource != RESOURCE:
            return None
        return at

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        # Revoke the full grant (both the access and refresh token), per spec.
        self._revoke_grant(token.token)

    # -- helpers --
    def _revoke_grant(self, token_str: str) -> None:
        with engine.begin() as conn:
            row = conn.execute(
                select(oauth_tokens.c.grant_id).where(oauth_tokens.c.key == token_str)
            ).first()
            gid = row[0] if row else None
            if gid:
                conn.execute(delete(oauth_tokens).where(oauth_tokens.c.grant_id == gid))
            else:
                conn.execute(delete(oauth_tokens).where(oauth_tokens.c.key == token_str))

    def _issue(self, client_id, scopes, subject, resource) -> OAuthToken:
        now = int(time.time())
        gid = secrets.token_urlsafe(16)
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        at = AccessToken(
            token=access, client_id=client_id, scopes=scopes,
            expires_at=now + ACCESS_TTL, resource=resource or RESOURCE, subject=subject,
        )
        rt = RefreshToken(
            token=refresh, client_id=client_id, scopes=scopes,
            expires_at=now + REFRESH_TTL, subject=subject,
        )
        _put(oauth_tokens, access, at.model_dump_json(), kind="access",
             grant_id=gid, expires_at=now + ACCESS_TTL)
        _put(oauth_tokens, refresh, rt.model_dump_json(), kind="refresh",
             grant_id=gid, expires_at=now + REFRESH_TTL)
        return OAuthToken(
            access_token=access, token_type="Bearer", expires_in=ACCESS_TTL,
            refresh_token=refresh, scope=" ".join(scopes),
        )


provider = MagicLinkOAuthProvider()


def build_auth_settings() -> AuthSettings:
    return AuthSettings(
        issuer_url=BASE,
        resource_server_url=RESOURCE,
        client_registration_options=ClientRegistrationOptions(
            enabled=True, valid_scopes=[SCOPE], default_scopes=[SCOPE]
        ),
        revocation_options=RevocationOptions(enabled=True),
        required_scopes=[SCOPE],
    )


# --- Consent page (the magic-link login bridge) ---------------------------- #
_FORM = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect to Cert Layoff Search</title>
<style>
 body{{font-family:Inter,system-ui,sans-serif;background:#f7f5f2;color:#1c1917;
   display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
 .card{{background:#fff;max-width:420px;width:90%;padding:32px;border-radius:14px;
   box-shadow:0 1px 3px rgba(0,0,0,.08),0 8px 24px rgba(0,0,0,.06)}}
 h1{{font-size:19px;margin:0 0 6px}} p{{color:#57534e;font-size:14px;line-height:1.5;margin:0 0 18px}}
 label{{font-size:13px;font-weight:600;display:block;margin-bottom:6px}}
 input{{width:100%;box-sizing:border-box;padding:11px 12px;border:1px solid #d6d3d1;
   border-radius:9px;font-size:14px;font-family:ui-monospace,monospace}}
 button{{margin-top:18px;width:100%;padding:11px;border:0;border-radius:9px;background:#1c1917;
   color:#fff;font-size:14px;font-weight:600;cursor:pointer}}
 .err{{color:#b91c1c;font-size:13px;margin-top:10px}}
</style></head><body><div class="card">
 <h1>Connect your Claude to the corpus</h1>
 <p>Paste the access token from your personal link to authorize this connection.
    It's the <code>k=</code> value Nick sent you.</p>
 <form method="post" action="/oauth/consent">
  <input type="hidden" name="rid" value="{rid}">
  <label for="token">Access token</label>
  <input id="token" name="token" autocomplete="off" autofocus placeholder="e.g. zLh_aIB1ZCmjnklN">
  {error}
  <button type="submit">Authorize</button>
 </form>
</div></body></html>"""


def _form(rid: str, error: str = "") -> HTMLResponse:
    # Escape everything interpolated into HTML. rid is a server-minted token and
    # is gated behind an oauth_pending lookup, but escape regardless (no footgun
    # if rid ever becomes user-influenced).
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ""
    return HTMLResponse(_FORM.format(rid=html.escape(rid, quote=True), error=err_html))


async def consent_get(request: Request) -> HTMLResponse:
    rid = request.query_params.get("rid", "")
    if not rid or _get(oauth_pending, rid) is None:
        return HTMLResponse("<h1>This authorization link has expired.</h1>"
                            "<p>Start the connection again from Claude.</p>", status_code=400)
    return _form(rid)


async def consent_post(request: Request):
    form = await request.form()
    rid = (form.get("rid") or "").strip()
    token = (form.get("token") or "").strip()

    raw = _get(oauth_pending, rid)
    if not raw:
        return HTMLResponse("<h1>This authorization link has expired.</h1>"
                            "<p>Start the connection again from Claude.</p>", status_code=400)
    pending = json.loads(raw)

    if token not in magic_auth.TOKENS:
        return _form(rid, "That access token isn’t recognized. Check the link Nick sent you.")

    code = secrets.token_urlsafe(32)
    ac = AuthorizationCode(
        code=code,
        scopes=pending["scopes"],
        expires_at=time.time() + CODE_TTL,
        client_id=pending["client_id"],
        code_challenge=pending["code_challenge"],
        redirect_uri=pending["redirect_uri"],
        redirect_uri_provided_explicitly=pending["redirect_uri_provided_explicitly"],
        resource=pending.get("resource"),
        subject=token,  # the magic-link token IS the OAuth identity
    )
    _put(oauth_codes, code, ac.model_dump_json(), expires_at=time.time() + CODE_TTL)
    _delete(oauth_pending, rid)

    redirect_to = construct_redirect_uri(pending["redirect_uri"], code=code, state=pending.get("state"))
    return RedirectResponse(redirect_to, status_code=302)


def consent_routes() -> list[Route]:
    return [
        Route("/oauth/consent", consent_get, methods=["GET"]),
        Route("/oauth/consent", consent_post, methods=["POST"]),
    ]
