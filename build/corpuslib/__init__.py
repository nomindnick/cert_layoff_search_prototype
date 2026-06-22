"""Vendored corpus data-access layer for the offline build pipeline.

Copied from cert_layoff_playground/corpuslib so the build/ scripts have a
self-contained loader + de-identifier with no dependency on the playground
repo. Only the build pipeline imports this package (via sys.path); the served
backend never touches corpuslib (it reads pre-built pickles + records.json).

Exports the loader entry points the build scripts need.
"""

from .corpus import (
    corpus_paths,
    load_decisions,
    load_gold_holdings,
    load_taxonomy,
)

__all__ = [
    "corpus_paths",
    "load_decisions",
    "load_gold_holdings",
    "load_taxonomy",
]
