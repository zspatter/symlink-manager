"""Property-based tests for the Skyrim batch formatter (the one real parser).

Fuzzes the formatter to assert two invariants: it never raises on arbitrary
input, and formatting is idempotent (a formatted file reformats to itself).
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from symlink_manager.formatters.skyrim_batch import SkyrimBatchFormatter, process_lines

# Realistic batch-ish lines: printable ASCII (no embedded line breaks), salted
# with samples that hit the formatter's branches (commands, headers, comments).
_printable = st.text(st.characters(min_codepoint=32, max_codepoint=126), max_size=60)
_batch_line = st.one_of(
    _printable,
    st.sampled_from([
        "player.additem Gold001 100",
        "player.additem X 1 ; (0000000F) 'Gold'",
        "setav health 100",
        "set MyGlobal to 5",
        "; A Section Header",
        "; ===== Fenced Header =====",
        "; player.additem X 1",   # disabled command
        ";",
        "",
        "   ",
        "bat other_script",
    ]),
)
_batch_doc = st.lists(_batch_line, max_size=40)


@settings(deadline=None)
@given(st.text())
def test_process_lines_never_crashes_on_arbitrary_text(text):
    result = process_lines(text.splitlines())
    assert isinstance(result, list)


@settings(deadline=None)
@given(_batch_doc)
def test_formatter_is_idempotent(lines):
    formatter = SkyrimBatchFormatter()
    once = formatter.format("\n".join(lines))
    twice = formatter.format(once)
    assert once == twice


@settings(deadline=None)
@given(_batch_doc)
def test_formatted_output_is_well_formed(lines):
    # Whatever the input, output is newline-terminated and free of trailing
    # whitespace on any line.
    out = SkyrimBatchFormatter().format("\n".join(lines))
    assert out.endswith("\n")
    assert all(line == line.rstrip() for line in out.splitlines())
