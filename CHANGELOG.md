# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## 0.2.0

### Added

- `symlink-build` now accepts `--dry-run`, `--backup`, `--platform`, and `--host`
  (previously only `--remove`), so the full pipeline can be previewed and
  simulated for other hosts. A dry run skips the mutating format/audit stages and
  previews the deploy only.
- Profile schema validation: `config.json` and each profile must be a JSON
  object (a clear error otherwise, instead of a confusing downstream failure),
  and commands warn on unrecognized profile keys to catch typos (e.g.
  `targett_dir`). Unknown keys are ignored, not fatal.
- `symlink-status --json` emits the report as a single JSON object on stdout
  (`ok`, `counts`, `links`, `conflicts`, …) with diagnostics routed to stderr,
  so status is easy to consume from scripts/CI. The exit code is unchanged.
- Linting/typing: `ruff` and `mypy` configured (`pip install -e ".[lint]"`) and
  run as a CI job.
- Relative symlinks: `--relative` on `deploy`/`build`/`adopt`, or `"relative":
  true` on a profile, stores links relative to each target's directory (portable
  when the tree is relocated). Falls back to absolute if no relative path exists
  (e.g. different Windows drives).

### Changed

- Host matching (`hosts`) is now case-insensitive, matching platform matching.
  `platform.node()` casing varies by OS, so a config `hosts` entry no longer has
  to match the exact case.
- A malformed `config.json` or `manifest.json` now reports a clean error (and a
  non-zero exit) instead of a raw `JSONDecodeError` traceback.
- `deploy` and `adopt` now run the duplicate-target lint that `status` already
  had: when two sources resolve to one target, they print a `CONFLICT` warning
  before acting (`deploy` remains last-writer-wins). The lint now lives in the
  engine and is shared by all three commands.
- Documented teardown scope: `--remove` deletes whatever symlink occupies a
  managed target (real files stay protected). See USAGE.md.

### Fixed

- Removal now surfaces the OS error message when a symlink can't be unlinked,
  instead of silently counting it in the summary only.
- **Exit codes**: `symlink-deploy`, `symlink-adopt`, `symlink-status`, and
  `symlink-build` now exit non-zero when configuration fails or a link ends in an
  error state, so scripts and CI can gate on them. Previously a failed run still
  exited `0`. `symlink-status` exits non-zero when any link is broken, points at
  the wrong target, is blocked by a real file, has a missing source, or when
  sources collide on a target; a not-yet-deployed link is not an error.
- **Windows directory links**: directory sources now pass
  `target_is_directory=True` to `os.symlink`, which previously produced a broken
  file-symlink on Windows (no-op on POSIX).

## 0.1.0

Initial release.

- Installable `symlink_manager` package (`src/` layout) with console entry points.
- Profile types bundle a formatter with a source→target resolver:
  - **`skyrim_batch`** - batch-file formatting + flat broadcast into one
    `target_dir`, with an optional `source_root` to silo a domain's files.
  - **`dotfiles`** - verbatim deployment with explicit per-file targets and
    platform/host conditional links (`platforms`/`hosts`; a link value may be a
    string, an object, or a list of candidates with first-match-wins).
- Idempotent, real-file-protecting symlink engine that creates missing target
  parent directories and surfaces OS errors per link.
- Commands: `symlink-build`, `symlink-deploy` (`--remove` / `--backup`),
  `symlink-adopt`, `symlink-format`, `symlink-status`, `symlink-audit`; plus
  `python -m symlink_manager <command>`.
- `--dry-run`, `--platform`, and `--host` flags for previewing and simulating
  other hosts.
- pytest suite (111 tests).
