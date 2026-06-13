"""
FastAPI worker process (Phase 1 of the pywebview migration).

Runs the de-Qt'd Application_Logic layer behind a local HTTP API with SSE
progress. Owns the SQLite project DB, the parsers, fuzzy matching, AI calls and
indexing — all the heavy work that must never run in the UI process. Importable
and runnable standalone:

    uvicorn backend.app:app --port 8765            # dev
    python -m backend.app                          # binds 127.0.0.1:0, prints URL

No PyQt6 anywhere under backend/ (enforced by tests).
"""
