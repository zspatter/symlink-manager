# Usage

In-depth reference for the `symlink-manager` commands. For the overview, setup,
and configuration schema, see the [README](README.md).

Every command runs from the root of your parent repository (or pass
`--repo-root <path>`), and each is also available as
`python -m symlink_manager <command> ...` when the console scripts aren't on your
`PATH`.

## Concepts

- **Profile** - a named entry in `config.json`. Its `type` (`skyrim_batch` or
  `dotfiles`) decides whether files are formatted and how sources map to targets.
- **Host context** - conditional dotfile links are selected by the running
  platform (normalized to `windows` / `macos` / `linux`) and hostname
  (`platform.node()`). `--platform` / `--host` override these for previews.
- **Real-file protection** - the engine never overwrites a non-symlink file at a
  target; it reports it as *protected* and skips it. `--backup` overrides this.
- **Missing parents** - a target's parent directories are created automatically
  on deploy (e.g. `~/.config/nvim/`).
- **Teardown scope** - `--remove` deletes whatever *symlink* currently occupies a
  managed target, including a stale one that points elsewhere (so renaming a
  source and tearing down again still cleans up). Real files are always protected
  and left in place, so a symlink you placed by hand at a managed path will be
  removed - keep unrelated links out of your configured target paths.
- **Target conflicts** - if two sources resolve to the same target, `deploy`,
  `adopt`, and `status` print a `CONFLICT` warning. `deploy` is last-writer-wins;
  `status` treats a conflict as a failure (non-zero exit).
- **Config validation** - `config.json` and each profile must be a JSON object
  (otherwise the command fails with a clear message), and a profile key the
  active type doesn't recognize (e.g. a misspelled `target_dir`) prints a
  warning. Unrecognized keys are ignored, never fatal.

`deploy`, `status`, and `adopt` work on any profile. `format`, `audit`, and
`build` only do anything for *formatting* profile types (`skyrim_batch` today):
for other types they are a no-op, and `build` is equivalent to `deploy`.

---

## `symlink-deploy <profile>`

Create (or with `--remove`, tear down) the profile's symlinks.

| Flag | Effect |
| --- | --- |
| `--remove` | Remove the profile's links instead of creating them. |
| `--backup` | Rename a blocking real file to `<name>.<timestamp>.bak`, then link. |
| `--dry-run` | Preview without touching the filesystem. |
| `--platform <p>` | Override the platform (`windows`/`macos`/`linux`) for selection. |
| `--host <h>` | Override the hostname for selection. |
| `--repo-root <path>` | Act on this repo root instead of the current directory. |

```bash
symlink-deploy nolvus                              # link a Skyrim modlist's batch files
symlink-deploy dotfiles --dry-run                  # preview what this host would get
symlink-deploy dotfiles --backup                   # onboard a machine that already has the files
symlink-deploy dotfiles --remove                   # tear the links down
symlink-deploy dotfiles --dry-run --platform linux # preview the selection as if on linux
```

## `symlink-build <profile>`

The full pipeline for formatting domains: **format → audit → deploy**. For a
`dotfiles` profile (which doesn't format) this is equivalent to `symlink-deploy`.

| Flag | Effect |
| --- | --- |
| `--remove` | Skip format/audit and remove links. |
| `--dry-run` | Preview the deploy without touching the filesystem; also skips the mutating format/audit stages. |
| `--backup` | Rename a blocking real file to `<name>.<timestamp>.bak`, then link. |
| `--platform <p>` / `--host <h>` | Override the platform/hostname for link selection. |
| `--repo-root <path>` | Act on this repo root. |

```bash
symlink-build nolvus            # format the batch tree, regenerate manifest.md, then deploy
symlink-build nolvus --dry-run  # preview the deploy only (no formatting, no links written)
```

## `symlink-status <profile>`

Read-only report of every resolved link's current state, plus a duplicate-target
lint. States: **Linked**, **Not deployed**, **Broken** (dangling symlink),
**Wrong target**, **Blocked** (real file), **Missing source**.

| Flag | Effect |
| --- | --- |
| `--json` | Emit the report as a JSON object on stdout (diagnostics go to stderr). |
| `--platform <p>` / `--host <h>` | Inspect the selection for another host. |
| `--repo-root <path>` | Act on this repo root. |

Exit status is `0` when every link is OK or simply not deployed, and `1` when
any link is broken/wrong-target/blocked/missing-source or two sources collide on
one target - so `symlink-status` doubles as a CI health gate. With `--json`,
stdout carries only the report (`variant`, `type`, `platform`, `host`, `ok`,
`counts`, `links`, `conflicts`), making it easy to consume from scripts.

```bash
symlink-status dotfiles                  # what's linked / missing / broken here
symlink-status dotfiles --platform macos # what a mac would resolve
symlink-status dotfiles --json | jq .ok  # machine-readable; false if anything is wrong
```

## `symlink-adopt <profile>`

The inverse of deploy: for each link whose repo source is missing but whose
target is a real file on this machine, move the file **into** the repo (at the
source path) and link it back. Use it to capture existing config into version
control.

| Flag | Effect |
| --- | --- |
| `--dry-run` | Preview what would be adopted. |
| `--platform <p>` / `--host <h>` | Restrict to another host's selection. |
| `--repo-root <path>` | Act on this repo root. |

```bash
symlink-adopt dotfiles --dry-run   # show which machine files would be captured
symlink-adopt dotfiles             # move them into the repo and link back
```

## `symlink-format <profile>`

Run only the formatting stage of a `skyrim_batch` profile (align commands,
normalize headers/comments) in place - no deploy. Profiles whose type doesn't
format are a no-op.

| Flag | Effect |
| --- | --- |
| `--repo-root <path>` | Act on this repo root. |

```bash
symlink-format nolvus   # normalize the batch files without deploying
```

## `symlink-audit`

Audit a Skyrim domain's `manifest.json` against the physical `variants/` tree
(reporting ghost entries and undocumented files) and regenerate `manifest.md`.
If no `manifest.json` exists at the source root, it reports nothing to do - it
will not scaffold one.

| Flag | Effect |
| --- | --- |
| `--source-root <dir>` | Domain subdirectory holding `manifest.json`/`variants/` (default: repo root). |
| `--repo-root <path>` | Act on this repo root. |

```bash
symlink-audit --source-root skyrim
```

---

## Workflows

**Onboard a new machine (capture what's already there):**
```bash
# 1. add the files' links entries to config.json, then:
symlink-adopt dotfiles --dry-run   # confirm what will be captured
symlink-adopt dotfiles             # move them into the repo + link back
```

**Re-deploy onto a machine that already has the files:**
```bash
symlink-deploy dotfiles --dry-run --backup   # confirm what gets backed up
symlink-deploy dotfiles --backup             # back up blockers (.bak) and link
```

**Add one new dotfile:**
```bash
mv ~/.gitconfig dotfiles/git/.gitconfig      # move the real file into the repo
# add "dotfiles/git/.gitconfig": "~/.gitconfig" to the dotfiles profile, then:
symlink-deploy dotfiles
```

**Check health across a fleet (from any one machine):**
```bash
symlink-status dotfiles                 # this host
symlink-status dotfiles --platform linux --host server-01
```
