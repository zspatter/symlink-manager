"""Unit tests for the pure Skyrim-batch transforms and the formatter wrappers."""
from symlink_manager.formatters import skyrim_batch as fmt
from symlink_manager.formatters import IdentityFormatter, SkyrimBatchFormatter

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
        lines = ["; player.additem X 1"]
        result = fmt.process_lines(lines)
        assert result[1] == "; player.additem X 1"

    def test_bare_trailing_semicolon_produces_no_blank_comment(self):
        # A line with a trailing ';' but no comment text must not keep a dangling "; ".
        result = fmt.process_lines(["player.additem X 1 ;"])
        assert result == [EMPTY_HEADER, "player.additem X 1", EMPTY_HEADER]

    def test_formid_only_comment_is_dropped_entirely(self):
        # A comment that cleans to nothing leaves the bare command, no "; ".
        result = fmt.process_lines(["player.additem X 1 ; (0000000F)"])
        assert result == [EMPTY_HEADER, "player.additem X 1", EMPTY_HEADER]

    def test_disabled_command_with_empty_comment_is_clean(self):
        result = fmt.process_lines(["; player.additem X 1 ;"])
        assert result[1] == "; player.additem X 1"


# ---------------------------------------------------------------------------
# Formatter wrappers
# ---------------------------------------------------------------------------

class TestFormatters:
    def test_identity_returns_input_unchanged(self):
        text = "; nothing\nplayer.additem X 1\n"
        assert IdentityFormatter().format(text) == text

    def test_skyrim_formatter_matches_process_lines(self):
        text = "player.additem Gold001 100 ; (0000000F) 'Gold'\n"
        expected = "\n".join(fmt.process_lines(text.strip().splitlines())) + "\n"
        assert SkyrimBatchFormatter().format(text) == expected
        assert expected.endswith("\n")
