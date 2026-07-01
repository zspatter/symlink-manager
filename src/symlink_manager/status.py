"""Read-only inspection of a profile's links (the status / doctor view).

Resolves a profile's links for the current (or overridden) host and classifies
each one's on-disk state, without touching the filesystem. Also lints the
resolved set for conflicts (multiple sources pointing at one target).
"""
import contextlib
import json
import sys
from enum import Enum, auto
from pathlib import Path

from .config import ConfigError, load_config, select_variant
from .deploy import duplicate_targets, warn_duplicate_targets
from .profiles import current_host_context, get_profile_type, warn_unknown_keys


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


def _json_report(variant_key, profile, context, results, stats, conflicts, ok):
    """Builds the machine-readable status document (see ``run_status(as_json=True)``)."""
    return {
        "variant": variant_key,
        "type": profile.get("type", "skyrim_batch"),
        "platform": context.platform,
        "host": context.host,
        "ok": ok,
        "counts": {state.name: stats[state] for state in LinkState},
        "links": [
            {"source": str(source), "target": str(target), "state": state.name}
            for source, target, state in results
        ],
        "conflicts": [
            {"target": str(target), "sources": [str(s) for s in sources]}
            for target, sources in conflicts.items()
        ],
    }


def run_status(variant_key, repo_root=None, platform_override=None, host_override=None,
               as_json=False):
    """Reports the current link state for a profile (read-only).

    With ``as_json`` the report is emitted as a single JSON object on stdout and
    all diagnostics go to stderr, keeping stdout machine-parseable.

    Returns a process-style exit code: 0 when every link is OK or simply not yet
    deployed, 1 if configuration failed, any link is in a problem state (see
    ``PROBLEM_STATES``), or sources collide on a target.
    """
    repo_root = repo_root or Path.cwd()
    context = current_host_context(platform_override, host_override)

    # In JSON mode, keep resolution-phase diagnostics (warnings, notices) off the
    # stdout that must carry only JSON by redirecting them to stderr.
    diag = contextlib.redirect_stdout(sys.stderr) if as_json else contextlib.nullcontext()
    try:
        with diag:
            master_config = load_config(repo_root)
            profile = select_variant(master_config, variant_key)
            profile_type = get_profile_type(profile)
            warn_unknown_keys(profile, profile_type, variant_key)
            link_specs = profile_type.resolve_links(profile, variant_key, repo_root, context)
    except ConfigError as e:
        if as_json:
            print(json.dumps({"variant": variant_key, "error": str(e)}, indent=2))
        else:
            print(f"  [!] ERROR: {e}")
        return 1

    results = [(source, target, link_status(source, target)) for source, target in link_specs]
    stats = {state: 0 for state in LinkState}
    for _, _, state in results:
        stats[state] += 1
    conflicts = duplicate_targets(link_specs)
    problems = any(stats[state] for state in PROBLEM_STATES) or bool(conflicts)
    code = 1 if problems else 0

    if as_json:
        print(json.dumps(
            _json_report(variant_key, profile, context, results, stats, conflicts, ok=code == 0),
            indent=2))
        return code

    type_name = profile.get("type", "skyrim_batch")
    print(f"  [*] Status: {variant_key} ({type_name}) - {len(link_specs)} link(s) "
          f"[{context.platform}/{context.host}]\n")
    for _, target, state in results:
        print(f"  {STATE_GLYPHS[state]} {STATE_LABELS[state]:<20} {target}")
    warn_duplicate_targets(link_specs, blank_line_before=True)
    print(_summary(stats))
    return code
