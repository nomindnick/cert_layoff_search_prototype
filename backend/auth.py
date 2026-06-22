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
