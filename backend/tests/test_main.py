"""Tests for the CLI entrypoint."""

from __future__ import annotations

import pytest

from leakwatch import __version__
from leakwatch.main import build_parser, cmd_version


def test_version_command(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    args = parser.parse_args(["version"])
    assert cmd_version(args) == 0
    out = capsys.readouterr().out
    assert __version__ in out


def test_top_level_version_flag() -> None:
    parser = build_parser()
    args = parser.parse_args(["--version"])
    assert args.version is True


def test_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    args = parser.parse_args([])
    assert not hasattr(args, "func")
