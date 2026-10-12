"""LeakWatch CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__
from .db import SessionLocal, engine
from .persistence import init_db, seed_default_domains
from .worker import run_watch_cycle


def cmd_run_once(_: argparse.Namespace) -> int:
    stats = asyncio.run(run_watch_cycle({}))
    print(stats)
    return 0


def cmd_init_db(_: argparse.Namespace) -> int:
    async def _run() -> None:
        await init_db(engine)
        async with SessionLocal() as session:
            await seed_default_domains(session)
            await session.commit()

    asyncio.run(_run())
    print("database initialised")
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(f"leakwatch {__version__}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    # Imported lazily so the heavy FastAPI/uvicorn stack is only loaded when
    # the API server is actually needed.
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "leakwatch.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leakwatch", description="Credential Leak Monitor")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run-once", help="run a single watch cycle and print stats").set_defaults(
        func=cmd_run_once
    )
    sub.add_parser("init-db", help="create tables and seed default domains").set_defaults(
        func=cmd_init_db
    )
    serve = sub.add_parser("serve", help="run the FastAPI API server")
    serve.add_argument("--host", default="127.0.0.1", help="bind host")
    serve.add_argument("--port", type=int, default=8000, help="bind port")
    serve.add_argument("--reload", action="store_true", help="auto-reload on file changes")
    serve.set_defaults(func=cmd_serve)
    sub.add_parser("version", help="print version").set_defaults(func=cmd_version)
    return parser


def cli() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.version:
        sys.exit(cmd_version(args))
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(func(args))


if __name__ == "__main__":
    cli()
