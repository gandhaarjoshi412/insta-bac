"""Entrypoint script to execute the NoInsta server using Uvicorn."""

import argparse
import sys
import uvicorn

from app.core.config import settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NoInsta Backend Server Runner")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Bind host (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reloading for development")
    return parser.parse_args()


def main():
    args = parse_args()
    reload_enabled = args.reload or (settings.APP_ENV == "development")

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=reload_enabled,
        log_level="info",
        ws="websockets",
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    main()
