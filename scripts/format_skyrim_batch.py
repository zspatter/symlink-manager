import re
import shutil
from datetime import datetime
from pathlib import Path

# ==============================================================================
# Configuration & Constants
# ==============================================================================

TARGET_WIDTH = 65
HEADER_WIDTH = 100
VERBOSE = False

# ==============================================================================
# Text Formatting & Sanitization Tools
# ==============================================================================

def is_skyrim_command(text_line):
    """Checks if a string begins with a standard, unambiguous Skyrim batch command."""
    if not text_line: 
        return False
        
    words = text_line.split()
    first_word = text_line.split()[0].lower()

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
        
        command = command.ljust(TARGET_WIDTH) if len(command) < TARGET_WIDTH else command + " "
        line_str = f"{command}; {comment}"
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
# File System & OS Operations
# ==============================================================================

def get_target_files(base_dir):
    """Discovers all text files in the target directory structure."""
    targets = [base_dir / "core", base_dir / "builds", base_dir / "variants"]
    files = []
    for t in targets:
        if t.exists():
            files.extend(t.glob("**/*.txt"))
    return files

def archive_file(file_path, base_dir, archive_root, timestamp):
    """Mirrors the active directory structure inside the archive folder."""
    rel_path = file_path.relative_to(base_dir)
    script_archive_dir = archive_root / rel_path.parent
    script_archive_dir.mkdir(parents=True, exist_ok=True)

    archive_filename = f"{file_path.stem}_{timestamp}{file_path.suffix}"
    archive_path = script_archive_dir / archive_filename

    shutil.copy2(file_path, archive_path)
    print(f"  -> Archived: archive/{rel_path.parent}/{archive_filename}")

def process_single_file(file_path, base_dir, archive_root, timestamp):
    """Reads, formats, checks idempotency, and safely handles OS errors."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            original_text = f.read()

        lines = original_text.strip().splitlines()
        formatted_lines = process_lines(lines)
        new_text = "\n".join(formatted_lines) + "\n"
        rel_path = file_path.relative_to(base_dir)
        
        if original_text == new_text:
            if VERBOSE:
                print(f"  [-] Skipped (Unchanged): {rel_path.name}")
            return "unchanged", None

        print(f"\nProcessing: {rel_path}")
        archive_file(file_path, base_dir, archive_root, timestamp)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_text)
            
        print(f"  [+] Formatted: {rel_path.name}")
        return "modified", None
        
    except Exception as e:
        return "error", str(e)
    
def build_summary(total_files, stats):
    border = "-" * 50
    
    summary_lines = [
        "", # Leading newline
        border,
        " FORMATTING SUMMARY".center(50),
        border,
        f" Total Files Scanned : {total_files}",
        f" Skipped (Unchanged) : {stats['unchanged']}",
        f" Modified & Archived : {stats['modified']}"
    ]
    
    if stats["ignored"] > 0:
        summary_lines.append(f" Ignored Errors      : {stats['ignored']}")
        
    summary_lines.append(border)
    
    return "\n".join(summary_lines)

def format_repository(active_variant=None):
    """Main execution loop. Returns True if successful, False if a critical error occurs."""
    # The script will act on the directory from which it was called
    base_dir = Path.cwd()
    archive_root = base_dir / "archive"
    
    files_to_process = get_target_files(base_dir)
    total_files = len(files_to_process)

    if not files_to_process:
        print("  [*] No text files found to process.")
        return True

    now = datetime.now()
    print_time = now.strftime("%H:%M:%S")
    file_time = now.strftime("%Y-%m-%d_%H.%M.%S")
    
    print(f"  [*] Sweep initiated at {print_time}\n")
    
    stats = {"unchanged": 0, "modified": 0, "error": 0, "ignored": 0}

    for file_path in files_to_process:
        status, err_msg = process_single_file(file_path, base_dir, archive_root, file_time)
        
        if status == "error":
            is_critical = True 
            if active_variant and "variants" in file_path.parts:
                try:
                    rel_var_path = file_path.relative_to(base_dir / "variants")
                    file_variant_folder = rel_var_path.parts[0]
                    if file_variant_folder != active_variant:
                        is_critical = False
                except ValueError:
                    pass
            
            if is_critical:
                print(f"\n[!] FATAL ERROR: Formatting failed on critical file -> {file_path.name}")
                print(f"    Reason: {err_msg}")
                return False
            else:
                print(f"\n[~] WARNING: Ignored error in non-critical file -> {file_path.name}")
                stats["ignored"] += 1
        else:
            stats[status] += 1

    print(build_summary(total_files, stats))
    
    return True

if __name__ == "__main__":
    format_repository()