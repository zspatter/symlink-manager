"""Skyrim batch-file formatter: aligns commands, normalizes headers/comments.

The public surface for the engine is :class:`SkyrimBatchFormatter`; the module
level functions are the pure transforms it composes (kept module level so they
stay individually unit-testable).
"""
import re

# ==============================================================================
# Configuration & Constants
# ==============================================================================

TARGET_WIDTH = 65
HEADER_WIDTH = 100

# ==============================================================================
# Text Formatting & Sanitization Tools
# ==============================================================================

def is_skyrim_command(text_line):
    """Checks if a string begins with a standard, unambiguous Skyrim batch command."""
    words = text_line.split()
    if not words:
        return False

    first_word = words[0].lower()

    safe_commands = {
        "bat", "setav", "modav", "forceav", "addperk", "addspell",
        "addshout", "prid", "equipitem", "setstage", "setgs",
        "completequest", "resetquest", "coc", "tmm", "sqs"
    }

    if first_word.startswith("player.") or first_word in safe_commands:
        return True

    if first_word == "set" and len(words) >= 4 and words[2].lower() == "to":
        return True

    return False

def clean_comment(comment_text):
    """Removes FormID residue and surrounding quotes from an inline comment."""
    text = comment_text.strip()
    text = re.sub(r'^\(?[0-9a-fA-F]{8}\)?\s*', '', text)

    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1].strip()
    elif len(text) >= 1 and text[0] in ("'", '"'):
        text = text[1:].strip()

    return text.strip()

def format_header_line(header_text):
    """Generates a single, centered header line padded with equal signs."""
    if header_text:
        return "; " + f" {header_text.title()} ".center(HEADER_WIDTH - 2, '=')
    return "; " + ("=" * (HEADER_WIDTH - 2))

def format_command_line(process_str, is_disabled):
    """Aligns a command and its comment to the target width."""
    if ";" in process_str and not process_str.startswith(";"):
        parts = process_str.split(";", 1)
        command = parts[0].strip()
        comment = clean_comment(parts[1])

        if comment:
            command = command.ljust(TARGET_WIDTH) if len(command) < TARGET_WIDTH else command + " "
            line_str = f"{command}; {comment}"
        else:
            # No real comment left (empty, or FormID/quote residue that cleaned
            # to nothing): emit the bare command, never a dangling "; ".
            line_str = command
        return f"; {line_str}" if is_disabled else line_str

    if is_disabled:
        return f"; {process_str}"

    if not process_str.startswith(";"):
        return process_str

    text_content = process_str[1:].lstrip()
    return f"; {text_content}" if text_content else ";"

def append_header_safely(formatted_lines, header_text):
    """Handles header insertion while resolving duplicates and style collisions."""
    header_line = format_header_line(header_text)
    empty_separator = format_header_line("")

    if not header_text:
        if formatted_lines and formatted_lines[-1].startswith("; =") and formatted_lines[-1].endswith("="):
            return
    else:
        if formatted_lines and formatted_lines[-1] == empty_separator:
            formatted_lines.pop()

    formatted_lines.append(header_line)

def finalize_document_structure(formatted_lines):
    """Enforces maximum one consecutive blank line and appends the EOF footer."""
    final_lines = []

    for line in formatted_lines:
        if not line:
            if final_lines and final_lines[-1] != "":
                final_lines.append("")
        else:
            final_lines.append(line)

    footer_str = "; " + ("=" * (HEADER_WIDTH - 2))

    while final_lines and (final_lines[-1] == "" or final_lines[-1] == footer_str):
        final_lines.pop()

    if final_lines:
        final_lines.append(footer_str)

    return final_lines

def process_lines(lines):
    """Traffic cop: Iterates through lines, checks state, and routes to formatters."""
    formatted = []
    prev_blank = True
    first_content_found = False

    for line in lines:
        trimmed = line.strip()

        if not trimmed or trimmed == ";":
            formatted.append("")
            prev_blank = True
            continue

        is_disabled = False
        process_str = trimmed

        if trimmed.startswith(";"):
            potential_cmd = trimmed[1:].strip()
            if is_skyrim_command(potential_cmd):
                process_str = potential_cmd
                is_disabled = True

        is_header = False
        header_text = ""

        fenced_match = re.match(r'^;\s*=+(.*?)=+\s*$', trimmed)
        if fenced_match:
            is_header = True
            header_text = fenced_match.group(1).strip()
        elif trimmed.startswith(";") and not is_disabled and prev_blank:
            is_header = True
            header_text = trimmed[1:].strip()

        if not first_content_found:
            first_content_found = True
            if not is_header:
                formatted.append(format_header_line(""))

        if is_header:
            append_header_safely(formatted, header_text)
        else:
            formatted.append(format_command_line(process_str, is_disabled))

        prev_blank = False

    return finalize_document_structure(formatted)

# ==============================================================================
# Formatter
# ==============================================================================

class SkyrimBatchFormatter:
    """Wraps the line transforms above into the :class:`Formatter` contract."""

    def format(self, text: str) -> str:
        return "\n".join(process_lines(text.strip().splitlines())) + "\n"
