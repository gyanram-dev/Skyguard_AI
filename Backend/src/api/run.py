"""Server entrypoint: python -m src.api.run (uvicorn programmatically)."""

from __future__ import annotations

import os


def main() -> None:
    """Serve the SkyGuard API (development defaults; see reports/api/)."""
    import uvicorn

    uvicorn.run("src.api.app:app",
                host=os.environ.get("SKYGUARD_HOST", "127.0.0.1"),
                port=int(os.environ.get("SKYGUARD_PORT", "8000")),
                reload=False, log_level="info")


if __name__ == "__main__":
    main()
