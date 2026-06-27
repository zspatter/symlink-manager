"""Unit tests for the pure formatting helpers in format_skyrim_batch.

These cover the side-effect-free text transforms, which form the safety net the
rest of the refactor leans on.
"""
import format_skyrim_batch as fmt

EMPTY_HEADER = "; " + "=" * (fmt.HEADER_WIDTH - 2)


# ---------------------------------------------------------------------------
# clean_comment
# ---------------------------------------------------------------------------

class TestCleanComment:
    def test_strips_parenthesized_formid(self):
        assert fmt.clean_comment("(0000A1B2) Adventurer Backpack") == "Adventurer Backpack"

    def test_strips_bare_formid(self):
        assert fmt.clean_comment("0000A1B2 Gold") == "Gold"

    def test_strips_matched_single_quotes(self):
        assert fmt.clean_comment("'Gold'") == "Gold"

    def test_strips_matched_double_quotes(self):
        assert fmt.clean_comment('"Gold"') == "Gold"

    def test_strips_dangling_leading_quote(self):
        assert fmt.clean_comment("'Unbalanced") == "Unbalanced"

    def test_strips_formid_then_quotes(self):
        assert fmt.clean_comment("(0000000F) 'Gold'") == "Gold"

    def test_collapses_surrounding_whitespace(self):
        assert fmt.clean_comment("   spaced   ") == "spaced"


# ---------------------------------------------------------------------------
# is_skyrim_command
# ---------------------------------------------------------------------------

class TestIsSkyrimCommand:
    def test_player_dot_prefix(self):
        assert fmt.is_skyrim_command("player.additem Gold001 100") is True

    def test_known_safe_command(self):
        assert fmt.is_skyrim_command("setav health 100") is True

    def test_coc_command(self):
        assert fmt.is_skyrim_command("coc whiterun") is True

    def test_set_to_form(self):
        assert fmt.is_skyrim_command("set MyGlobal to 5") is True

    def test_set_without_to_is_rejected(self):
        assert fmt.is_skyrim_command("set MyGlobal 5") is False

    def test_plain_prose_is_rejected(self):
        assert fmt.is_skyrim_command("Backpacks") is False

    def test_empty_string_is_rejected(self):
        assert fmt.is_skyrim_command("") is False

    def test_whitespace_only_is_rejected(self):
        # Guards against an IndexError on whitespace-only input.
        assert fmt.is_skyrim_command("   ") is False


# ---------------------------------------------------------------------------
# format_header_line
# ---------------------------------------------------------------------------

class TestFormatHeaderLine:
    def test_empty_header_is_full_rule(self):
        assert fmt.format_header_line("") == EMPTY_HEADER

    def test_titled_header(self):
        result = fmt.format_header_line("backpacks")
        assert result.startswith("; ")
        assert "Backpacks" in result          # title-cased
        assert result.endswith("=")
        assert len(result) == fmt.HEADER_WIDTH


# ---------------------------------------------------------------------------
# finalize_document_structure
# ---------------------------------------------------------------------------

class TestFinalizeDocumentStructure:
    def test_collapses_consecutive_blanks_and_appends_footer(self):
        result = fmt.finalize_document_structure(["a", "", "", "b", ""])
        assert result == ["a", "", "b", EMPTY_HEADER]

    def test_empty_input_stays_empty(self):
        assert fmt.finalize_document_structure([]) == []


# ---------------------------------------------------------------------------
# process_lines (end-to-end over the pure pipeline)
# ---------------------------------------------------------------------------

class TestProcessLines:
    def test_command_with_inline_comment_is_aligned_and_sanitized(self):
        lines = ["player.additem Gold001 100 ; (0000000F) 'Gold'"]
        result = fmt.process_lines(lines)

        expected_command = "player.additem Gold001 100".ljust(fmt.TARGET_WIDTH) + "; Gold"
        assert result == [EMPTY_HEADER, expected_command, EMPTY_HEADER]

    def test_leading_comment_becomes_section_header(self):
        lines = ["; Backpacks", "player.additem X 1"]
        result = fmt.process_lines(lines)

        expected_header = "; " + " Backpacks ".center(fmt.HEADER_WIDTH - 2, "=")
        assert result == [expected_header, "player.additem X 1", EMPTY_HEADER]

    def test_disabled_command_is_recommented(self):
        # A commented-out real command keeps its disabled marker rather than
        # being mistaken for a section header.
        lines = ["; player.additem X 1"]
        result = fmt.process_lines(lines)
        assert result[1] == "; player.additem X 1"


# ---------------------------------------------------------------------------
# is_critical_error (error-severity routing)
# ---------------------------------------------------------------------------

class TestIsCriticalError:
    def test_no_active_variant_is_always_critical(self, tmp_path):
        target = tmp_path / "variants" / "other" / "x.txt"
        assert fmt.is_critical_error(target, tmp_path, None) is True

    def test_core_file_is_critical(self, tmp_path):
        target = tmp_path / "core" / "x.txt"
        assert fmt.is_critical_error(target, tmp_path, "nolvus") is True

    def test_active_variant_file_is_critical(self, tmp_path):
        target = tmp_path / "variants" / "nolvus" / "x.txt"
        assert fmt.is_critical_error(target, tmp_path, "nolvus") is True

    def test_inactive_variant_file_is_not_critical(self, tmp_path):
        target = tmp_path / "variants" / "other" / "x.txt"
        assert fmt.is_critical_error(target, tmp_path, "nolvus") is False


# ---------------------------------------------------------------------------
# FormatStatus + format_repository (integration over a temp repo)
# ---------------------------------------------------------------------------

class TestFormatStatus:
    def test_expected_members(self):
        names = {s.name for s in fmt.FormatStatus}
        assert names == {"UNCHANGED", "MODIFIED", "ERROR", "IGNORED"}


class TestFormatRepositoryIntegration:
    def test_formats_messy_file_and_archives_a_copy(self, tmp_path, monkeypatch):
        core = tmp_path / "core"
        core.mkdir()
        messy = core / "spells.txt"
        messy.write_text(
            "; Spells\nplayer.addspell FireBall 1 ; (0000000F) 'Fire Ball'\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)  # format_repository acts on Path.cwd()

        assert fmt.format_repository() is True

        result = messy.read_text(encoding="utf-8")
        assert "Spells" in result          # header preserved
        assert "Fire Ball" in result       # comment sanitized, FormID stripped
        assert "(0000000F)" not in result

        archived = list((tmp_path / "archive" / "core").glob("spells_*.txt"))
        assert len(archived) == 1          # original mirrored into archive/

    def test_clean_file_is_left_unchanged(self, tmp_path, monkeypatch):
        core = tmp_path / "core"
        core.mkdir()
        target = core / "spells.txt"
        target.write_text("; Spells\nplayer.addspell FireBall 1 ; Fire Ball\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        # First pass normalizes the file; second pass must be a no-op (idempotent).
        fmt.format_repository()
        normalized = target.read_text(encoding="utf-8")
        fmt.format_repository()
        assert target.read_text(encoding="utf-8") == normalized
