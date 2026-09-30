"""Server entrypoint: python -m src.api.run (uvicorn programmatically)."""

from __future__ import annotations

import os


def _load_env_file() -> None:
    """Load a .env file when python-dotenv is present.

    The .env file is a convenience, not a requirement: every setting has a
    default. A missing optional dependency must never stop the server from
    starting (it previously raised ModuleNotFoundError before uvicorn ran).
    """
    try:
        from dotenv import load_dotenv
    except ModuleNotFoundError:
        print("python-dotenv not installed: skipping .env load "
              "(environment variables and defaults still apply)")
        return
    load_dotenv(os.environ.get("SKYGUARD_ENV_FILE", ".env"), override=False)


def main() -> None:
    """Serve the SkyGuard API (development defaults; see reports/api/).

    Hosting platforms that inject PORT take precedence; SKYGUARD_PORT
    overrides only when PORT is absent; 8000 remains the local default.
    """
    import uvicorn

    _load_env_file()
    port = int(os.environ.get("PORT") or os.environ.get("SKYGUARD_PORT", "8000"))
    uvicorn.run("src.api.app:app",
                host=os.environ.get("SKYGUARD_HOST", "127.0.0.1"),
                port=port,
                reload=False, log_level="info")


if __name__ == "__main__":
    main()
