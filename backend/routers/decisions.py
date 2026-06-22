"""GET /api/decision/{oah_case_no} — full served record for the reader.

Returns the de-identified served record from records.json. The case number may
be passed with or without its leading ``N`` (filenames are stem-based without N,
but ``oah_case_no`` inside the record carries the N) — both forms are matched.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.auth import require_user
from backend.models import DecisionDetail, HoldingDetail
from backend.store import store

router = APIRouter(prefix="/api", tags=["decisions"])


def _resolve_record(case_no):
    """Look up a served record tolerating leading-N variance in either direction."""
    record = store.get_record(case_no)
    if record is None:
        cn = (case_no or "").strip()
        alt = cn[1:] if cn[:1].upper() == "N" else "N" + cn
        record = store.get_record(alt)
    return record


@router.get("/decision/{oah_case_no}", response_model=DecisionDetail)
def get_decision(oah_case_no: str, _token: str = Depends(require_user)):
    record = _resolve_record(oah_case_no)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    return DecisionDetail(**record)


@router.get("/holding/{holding_id}", response_model=HoldingDetail)
def get_holding(holding_id: str, _token: str = Depends(require_user)):
    """Full detail for one holding (arguments / facts / reasoning / authorities).

    holding_id is "<case_stem>:<idx>" (as emitted by the search index). Lets the
    search-result card fetch depth on demand without loading the whole decision.
    """
    case, sep, idx = holding_id.rpartition(":")
    if not sep or not case or not idx.isdigit():
        raise HTTPException(status_code=400, detail="Malformed holding id")
    record = _resolve_record(case)
    if record is None:
        raise HTTPException(status_code=404, detail="Decision not found")
    holdings = record.get("holdings") or []
    i = int(idx)
    holding = next((h for h in holdings if h.get("idx") == i), None)
    if holding is None and 0 <= i < len(holdings):
        holding = holdings[i]
    if holding is None:
        raise HTTPException(status_code=404, detail="Holding not found")
    return HoldingDetail(**holding)
