"""POST /api/report — deterministic, anchored report (PLAN.md section 7).

Filters store holdings by the request params, groups by issue category, and
renders each ``summary_style_holding`` in the annual-volume house style. No LLM.
Returns HTML for preview, or a streamed PDF (via xhtml2pdf; 501 if the optional
dependency is unavailable).
"""

from __future__ import annotations

import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.auth import require_user
from backend.models import ReportRequest
from backend.reports.generate import build_report, to_pdf
from backend.store import store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["reports"])


def _params(req: ReportRequest) -> dict:
    return {
        "categories": req.categories or [],
        "year_start": req.year_start,
        "year_end": req.year_end,
        "district": req.district,
        "alj": req.alj,
    }


@router.post("/report")
def run_report(req: ReportRequest, _token: str = Depends(require_user)):
    params = _params(req)
    try:
        report = build_report(store, params)
    except Exception:
        logger.exception("report generation failed (params=%s)", params)
        raise HTTPException(status_code=500, detail="Failed to generate report")

    fmt = (req.format or "html").lower()
    if fmt == "pdf":
        try:
            pdf_bytes = to_pdf(report["html"])
        except Exception as exc:
            # to_pdf raises a clear error when xhtml2pdf is unavailable.
            logger.warning("PDF rendering unavailable: %s", exc)
            raise HTTPException(status_code=501, detail=f"PDF generation unavailable: {exc}")

        title = report.get("title") or "report"
        filename = "".join(c if c.isalnum() or c in "-_" else "_" for c in title) or "report"
        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
        )

    return {
        "html": report.get("html"),
        "n_holdings": report.get("n_holdings"),
        "title": report.get("title"),
    }
