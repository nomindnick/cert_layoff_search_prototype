"""Deterministic report generation for the cert-layoff search app.

Assembles the house-style "Layoff Decision Summaries" report from the served,
already de-identified decision records held by the Store. No LLM is involved:
the report is a GROUP BY over ``summary_style_holding`` paragraphs, rendered in
the frozen-taxonomy section order with the traditional "District (ALJ)" cite.

Public surface:
    build_report(store, params) -> {"html", "n_holdings", "title", "groups"}
    to_pdf(html) -> bytes   (xhtml2pdf / pisa, import-guarded)
"""

from .generate import build_report, to_pdf

__all__ = ["build_report", "to_pdf"]
