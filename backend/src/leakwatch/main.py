"""LeakWatch CLI entrypoint."""

from __future__ import annotations

import argparse
import asyncio
import sys

from . import __version__
from .worker import run_watch_cycle


def cmd_run_once(_: argparse.Namespace) -> int:
    stats = asyncio.run(run_watch_cycle({}))
    print(stats)
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    print(f"leakwatch {__version__}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leakwatch", description="Credential Leak Monitor")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run-once", help="run a single watch cycle and print stats").set_defaults(
        func=cmd_run_once
    )
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
