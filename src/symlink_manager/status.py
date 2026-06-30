"""Read-only inspection of a profile's links (the status / doctor view).

Resolves a profile's links for the current (or overridden) host and classifies
each one's on-disk state, without touching the filesystem. Also lints the
resolved set for conflicts (multiple sources pointing at one target).
"""
from enum import Enum, auto
from pathlib import Path

from .config import ConfigError, load_config, select_variant
from .profiles import get_profile_type, current_host_context


class LinkState(Enum):
    OK = auto()              # symlink that points at our source
    MISSING = auto()         # target absent (not deployed)
    BROKEN = auto()          # dangling symlink
    WRONG_TARGET = auto()    # symlink pointing somewhere other than our source
    BLOCKED = auto()         # a real (non-symlink) file occupies the target
    MISSING_SOURCE = auto()  # the repo source file does not exist


STATE_LABELS = {
    LinkState.OK: "Linked",
    LinkState.MISSING: "Not deployed",
    LinkState.BROKEN: "Broken link",
    LinkState.WRONG_TARGET: "Wrong target",
    LinkState.BLOCKED: "Blocked (real file)",
    LinkState.MISSING_SOURCE: "Missing source",
}

STATE_GLYPHS = {
    LinkState.OK: "[ok]",
    LinkState.MISSING: "[--]",
    LinkState.BROKEN: "[!!]",
    LinkState.WRONG_TARGET: "[!!]",
    LinkState.BLOCKED: "[!!]",
    LinkState.MISSING_SOURCE: "[!!]",
}

# States that signal something is wrong on disk (as opposed to OK or the benign
# "not deployed yet"). Their presence makes status report failure for CI gating.
PROBLEM_STATES = frozenset({
    LinkState.BROKEN,
    LinkState.WRONG_TARGET,
    LinkState.BLOCKED,
    LinkState.MISSING_SOURCE,
})


def link_status(source_path, target_path):
    """Returns the current LinkState of a (source, target) pair. Read-only."""
    if not source_path.exists():
        return LinkState.MISSING_SOURCE

    if target_path.is_symlink():
        if not target_path.exists():
            return LinkState.BROKEN
        try:
            if target_path.resolve() == source_path.resolve():
                return LinkState.OK
        except OSError:
            pass
        return LinkState.WRONG_TARGET

    if target_path.exists():
        return LinkState.BLOCKED
    return LinkState.MISSING


def duplicate_targets(link_specs):
    """Maps each target hit by more than one source to the offending sources."""
    by_target = {}
    for source, target in link_specs:
        by_target.setdefault(target, []).append(source)
    return {target: sources for target, sources in by_target.items() if len(sources) > 1}


def _summary(stats):
    border = "-" * 50
    lines = ["", border, " STATUS SUMMARY".center(50), border]
    active = {state: count for state, count in stats.items() if count > 0}
    if not active:
        lines.append("  No links resolved for this host.")
    else:
        for state, count in active.items():
            lines.append(f" {STATE_LABELS[state]:<21}: {count}")
    lines.append(border)
    return "\n".join(lines)


def run_status(variant_key, repo_root=None, platform_override=None, host_override=None):
    """Reports the current link state for a profile (read-only).

    Returns a process-style exit code: 0 when every link is OK or simply not yet
    deployed, 1 if configuration failed, any link is in a problem state (see
    ``PROBLEM_STATES``), or sources collide on a target.
    """
    repo_root = repo_root or Path.cwd()
    context = current_host_context(platform_override, host_override)

    try:
        master_config = load_config(repo_root)
        profile = select_variant(master_config, variant_key)
        profile_type = get_profile_type(profile)
        link_specs = profile_type.resolve_links(profile, variant_key, repo_root, context)
    except ConfigError as e:
        print(f"  [!] ERROR: {e}")
        return 1

    type_name = profile.get("type", "skyrim_batch")
    print(f"  [*] Status: {variant_key} ({type_name}) - {len(link_specs)} link(s) "
          f"[{context.platform}/{context.host}]\n")

    stats = {state: 0 for state in LinkState}
    for source, target in link_specs:
        state = link_status(source, target)
        stats[state] += 1
        print(f"  {STATE_GLYPHS[state]} {STATE_LABELS[state]:<20} {target}")

    conflicts = duplicate_targets(link_specs)
    if conflicts:
        print()
        for target, sources in conflicts.items():
            names = ", ".join(s.name for s in sources)
            print(f"  [!] CONFLICT: multiple sources link to {target} ({names})")

    print(_summary(stats))
    problems = any(stats[state] for state in PROBLEM_STATES) or bool(conflicts)
    return 1 if problems else 0
