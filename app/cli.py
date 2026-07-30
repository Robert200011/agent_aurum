"""Command-line entry points for development and operational bootstrap."""

from __future__ import annotations

import argparse
import asyncio
import sys

import uvicorn

from app.config import get_settings
from app.db.bootstrap import grant_application_privileges
from app.db.session import get_engine, get_session_factory
from app.services.admin import bootstrap_admin


async def _bootstrap_admin() -> None:
    await bootstrap_admin(get_session_factory(), get_settings())
    await get_engine().dispose()


async def _grant_app_role() -> None:
    await grant_application_privileges(get_settings())


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="aurum-agent")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("bootstrap-admin")
    subcommands.add_parser("grant-app-role")
    serve = subcommands.add_parser("serve")
    serve.add_argument("--host", default=settings.server_host)
    serve.add_argument("--port", default=settings.server_port, type=int)
    args = parser.parse_args()

    if args.command == "bootstrap-admin":
        asyncio.run(_bootstrap_admin())
    elif args.command == "grant-app-role":
        asyncio.run(_grant_app_role())
    elif args.command == "serve":
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            loop=(
                "app.main:windows_selector_loop_factory"
                if sys.platform == "win32"
                else "auto"
            ),
        )
