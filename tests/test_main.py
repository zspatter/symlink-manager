"""Tests for the ``python -m symlink_manager`` subcommand dispatcher."""
import pytest

from symlink_manager import __main__
from symlink_manager.__main__ import COMMANDS, main


class TestDispatch:
    def test_routes_to_command_with_remaining_args(self, monkeypatch):
        seen = {}
        monkeypatch.setitem(COMMANDS, "status", lambda argv: seen.setdefault("argv", argv))
        main(["status", "home", "--repo-root", "."])
        assert seen["argv"] == ["home", "--repo-root", "."]

    def test_defaults_argv_to_sys_argv(self, monkeypatch):
        seen = {}
        monkeypatch.setitem(COMMANDS, "deploy", lambda argv: seen.setdefault("argv", argv))
        monkeypatch.setattr(__main__.sys, "argv", ["prog", "deploy", "nolvus"])
        main()  # argv=None -> read from sys.argv
        assert seen["argv"] == ["nolvus"]


class TestUsageErrors:
    def test_no_args_prints_usage_and_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 2
        assert "usage" in capsys.readouterr().out

    def test_unknown_command_exits_2(self, capsys):
        with pytest.raises(SystemExit) as exc:
            main(["frobnicate"])
        assert exc.value.code == 2
        assert "usage" in capsys.readouterr().out
