# Changelog

All notable changes to this project are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## Unreleased

### Fixed

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
