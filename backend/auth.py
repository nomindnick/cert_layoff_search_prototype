"""Per-person magic-link token auth (PLAN.md section 9).

Tokens are bearer links — they are simultaneously auth, the analytics user id,
and the share signal. They are seeded from ``settings.ACCESS_TOKENS`` in the
form ``tok:Display Name,tok2:Name2``. A token may arrive via the
``X-Access-Token`` header, a ``?k=`` query param, or a ``k`` cookie (the SPA
persists it to localStorage and sends the header on every /api call).

In ``ENV=development`` the default token ``demo`` works out of the box.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from backend.config import settings


def _parse_tokens(raw: str) -> dict[str, str]:
    """Parse ``tok:Name,tok2:Name2`` into {token: display_name}. Tolerant of
    stray whitespace, blank entries, and missing names (falls back to token)."""
    out: dict[str, str] = {}
    for entry in (raw or "").split(","):
        entry = entry.strip()
        if not entry:
            continue
        tok, _, name = entry.partition(":")
        tok = tok.strip()
        if not tok:
            continue
        out[tok] = name.strip() or tok
    return out


# Parsed once at import; ACCESS_TOKENS is a deploy-time env var.
TOKENS: dict[str, str] = _parse_tokens(settings.ACCESS_TOKENS)


def _parse_admins(raw: str) -> set[str]:
    """Parse ``tok,tok2`` (names optional, ignored) into a set of admin tokens."""
    out: set[str] = set()
    for entry in (raw or "").split(","):
        tok = entry.strip().partition(":")[0].strip()
        if tok:
            out.add(tok)
    return out


# Admin tokens are a SUBSET of TOKENS — being a valid user never implies admin.
ADMINS: set[str] = _parse_admins(settings.ADMIN_TOKENS)


def current_token(request: Request) -> str | None:
    """Return the raw token presented on the request (header > query > cookie),
    regardless of validity. Used for analytics enrichment."""
    tok = request.headers.get("X-Access-Token")
    if not tok:
        tok = request.query_params.get("k")
    if not tok:
        tok = request.cookies.get("k")
    tok = (tok or "").strip()
    return tok or None


def get_user(request: Request) -> str | None:
    """Return the display name for a valid token, else None."""
    tok = current_token(request)
    if tok is None:
        return None
    return TOKENS.get(tok)


def require_user(request: Request) -> str:
    """FastAPI dependency: return the valid token string or raise 401.

    Returns the *token* (the analytics user id), not the display name — routers
    that need the name can call get_user(request).
    """
    tok = current_token(request)
    if tok is None or tok not in TOKENS:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing access token — ask Nick for a link.",
        )
    return tok


def is_admin(request: Request) -> bool:
    """True when the presented token is both valid and listed in ADMIN_TOKENS."""
    tok = current_token(request)
    return bool(tok) and tok in TOKENS and tok in ADMINS


def require_admin(request: Request) -> str:
    """FastAPI dependency for the admin surface: a valid token that is also in
    ADMIN_TOKENS. 401 for a bad token, 403 for a valid-but-not-admin one.

    The 403 message names ADMIN_TOKENS on purpose — the likeliest cause is the
    env var being unset on the deploy, and a silent 404 would make that look
    like a routing bug.
    """
    tok = require_user(request)
    if tok not in ADMINS:
        raise HTTPException(
            status_code=403,
            detail="This page is admin-only (token not listed in ADMIN_TOKENS).",
        )
    return tok
