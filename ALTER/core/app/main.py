"""Vercel FastAPI entrypoint.

Keep this import aligned with ``api/index.py`` so production mounts every ALTER
router rather than only the legacy base API.
"""

from alter_core.main import app

__all__ = ["app"]
