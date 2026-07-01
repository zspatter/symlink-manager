"""Unit tests for the generic formatting orchestration (format_tree + helpers)."""
from symlink_manager import formatting
from symlink_manager.formatters import SkyrimBatchFormatter


# ---------------------------------------------------------------------------
# is_critical_error (error-severity routing)
# ---------------------------------------------------------------------------

class TestIsCriticalError:
    def test_no_active_variant_is_always_critical(self, tmp_path):
        target = tmp_path / "variants" / "other" / "x.txt"
        assert formatting.is_critical_error(target, tmp_path, None) is True

    def test_core_file_is_critical(self, tmp_path):
        target = tmp_path / "core" / "x.txt"
        assert formatting.is_critical_error(target, tmp_path, "nolvus") is True

    def test_active_variant_file_is_critical(self, tmp_path):
        target = tmp_path / "variants" / "nolvus" / "x.txt"
        assert formatting.is_critical_error(target, tmp_path, "nolvus") is True

    def test_inactive_variant_file_is_not_critical(self, tmp_path):
        target = tmp_path / "variants" / "other" / "x.txt"
        assert formatting.is_critical_error(target, tmp_path, "nolvus") is False


# ---------------------------------------------------------------------------
# FormatStatus + format_tree (integration over a temp repo)
# ---------------------------------------------------------------------------

class TestFormatStatus:
    def test_expected_members(self):
        names = {s.name for s in formatting.FormatStatus}
        assert names == {"UNCHANGED", "MODIFIED", "ERROR", "IGNORED"}


class TestFormatTreeIntegration:
    def test_formats_messy_file_and_archives_a_copy(self, tmp_path):
        core = tmp_path / "core"
        core.mkdir()
        messy = core / "spells.txt"
        messy.write_text(
            "; Spells\nplayer.addspell FireBall 1 ; (0000000F) 'Fire Ball'\n",
            encoding="utf-8",
        )

        assert formatting.format_tree(tmp_path, SkyrimBatchFormatter()) is True

        result = messy.read_text(encoding="utf-8")
        assert "Spells" in result          # header preserved
        assert "Fire Ball" in result       # comment sanitized, FormID stripped
        assert "(0000000F)" not in result

        archived = list((tmp_path / "archive" / "core").glob("spells_*.txt"))
        assert len(archived) == 1          # original mirrored into archive/

    def test_clean_file_is_left_unchanged(self, tmp_path):
        core = tmp_path / "core"
        core.mkdir()
        target = core / "spells.txt"
        target.write_text("; Spells\nplayer.addspell FireBall 1 ; Fire Ball\n", encoding="utf-8")

        # First pass normalizes the file; second pass must be a no-op (idempotent).
        formatting.format_tree(tmp_path, SkyrimBatchFormatter())
        normalized = target.read_text(encoding="utf-8")
        formatting.format_tree(tmp_path, SkyrimBatchFormatter())
        assert target.read_text(encoding="utf-8") == normalized

    def test_identity_formatter_leaves_files_untouched(self, tmp_path):
        from symlink_manager.formatters import IdentityFormatter

        core = tmp_path / "core"
        core.mkdir()
        target = core / "raw.txt"
        original = "; not Skyrim\nrandom content   \n\n\n"
        target.write_text(original, encoding="utf-8")

        assert formatting.format_tree(tmp_path, IdentityFormatter()) is True
        assert target.read_text(encoding="utf-8") == original   # byte-for-byte

    def test_no_files_to_process_is_success(self, tmp_path, capsys):
        assert formatting.format_tree(tmp_path, SkyrimBatchFormatter()) is True
        assert "No text files found" in capsys.readouterr().out


class _RaisingFormatter:
    """A formatter that always fails, to exercise error-severity routing."""

    def format(self, text: str) -> str:
        raise ValueError("boom")


class TestFormatTreeErrorSeverity:
    def test_error_in_critical_file_halts(self, tmp_path, capsys):
        core = tmp_path / "core"
        core.mkdir()
        (core / "x.txt").write_text("data", encoding="utf-8")

        assert formatting.format_tree(tmp_path, _RaisingFormatter()) is False
        assert "FATAL ERROR" in capsys.readouterr().out

    def test_error_in_inactive_variant_is_tolerated(self, tmp_path, capsys):
        variant = tmp_path / "variants" / "other"
        variant.mkdir(parents=True)
        (variant / "x.txt").write_text("data", encoding="utf-8")

        # The failing file belongs to an *inactive* variant, so the sweep survives.
        assert formatting.format_tree(tmp_path, _RaisingFormatter(), active_variant="nolvus") is True
        out = capsys.readouterr().out
        assert "WARNING" in out and "Ignored Errors" in out
