"""Generic file-tree formatting: discovery, idempotency, archiving, and writing.

This orchestration is domain-agnostic. The per-file text transform is supplied
as a :class:`~symlink_manager.formatters.base.Formatter`, so the same walk drives
Skyrim batch normalization, a dotfile no-op, or anything else.

It does assume the repo's ``core/``, ``builds/``, ``variants/`` layout for file
discovery and for variant-aware error severity; only profiles that opt into
formatting (currently ``skyrim_batch``) ever run it.
"""
import shutil
from datetime import datetime
from enum import Enum, auto

VERBOSE = False


class FormatStatus(Enum):
    UNCHANGED = auto()
    MODIFIED = auto()
    ERROR = auto()
    IGNORED = auto()


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

def process_single_file(file_path, base_dir, archive_root, timestamp, formatter):
    """Reads, formats, checks idempotency, and safely handles OS errors."""
    try:
        with open(file_path, encoding='utf-8') as f:
            original_text = f.read()

        new_text = formatter.format(original_text)
        rel_path = file_path.relative_to(base_dir)

        if original_text == new_text:
            if VERBOSE:
                print(f"  [-] Skipped (Unchanged): {rel_path.name}")
            return FormatStatus.UNCHANGED, None

        print(f"\nProcessing: {rel_path}")
        archive_file(file_path, base_dir, archive_root, timestamp)

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_text)

        print(f"  [+] Formatted: {rel_path.name}")
        return FormatStatus.MODIFIED, None

    except Exception as e:
        return FormatStatus.ERROR, str(e)

def build_summary(total_files, stats):
    border = "-" * 50

    summary_lines = [
        "",  # Leading newline
        border,
        " FORMATTING SUMMARY".center(50),
        border,
        f" Total Files Scanned : {total_files}",
        f" Skipped (Unchanged) : {stats[FormatStatus.UNCHANGED]}",
        f" Modified & Archived : {stats[FormatStatus.MODIFIED]}"
    ]

    if stats[FormatStatus.IGNORED] > 0:
        summary_lines.append(f" Ignored Errors      : {stats[FormatStatus.IGNORED]}")

    summary_lines.append(border)

    return "\n".join(summary_lines)

def is_critical_error(file_path, base_dir, active_variant):
    """A formatting error is non-critical only when it lands in an inactive variant.

    Errors in core/builds files (or when no variant is active) always halt the
    pipeline. Errors inside a *different* variant's folder are tolerated so a
    deploy to one modlist isn't blocked by an unrelated variant's bad file.
    """
    if not active_variant or "variants" not in file_path.parts:
        return True
    try:
        variant_folder = file_path.relative_to(base_dir / "variants").parts[0]
    except ValueError:
        return True
    return variant_folder == active_variant

def format_tree(base_dir, formatter, active_variant=None):
    """Formats every text file under ``base_dir`` with ``formatter``.

    Returns True if successful, False if a critical error occurs.
    """
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

    stats = {status: 0 for status in FormatStatus}

    for file_path in files_to_process:
        status, err_msg = process_single_file(file_path, base_dir, archive_root, file_time, formatter)

        if status is FormatStatus.ERROR:
            if is_critical_error(file_path, base_dir, active_variant):
                print(f"\n[!] FATAL ERROR: Formatting failed on critical file -> {file_path.name}")
                print(f"    Reason: {err_msg}")
                return False

            print(f"\n[~] WARNING: Ignored error in non-critical file -> {file_path.name}")
            stats[FormatStatus.IGNORED] += 1
        else:
            stats[status] += 1

    print(build_summary(total_files, stats))

    return True
