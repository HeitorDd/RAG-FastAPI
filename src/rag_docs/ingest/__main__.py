"""Permite `python -m rag_docs.ingest`."""

from __future__ import annotations

import sys

from rag_docs.ingest.cli import main

if __name__ == "__main__":
    sys.exit(main())
