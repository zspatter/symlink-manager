# Symlink Manager

A Python-based, idempotent symlink deployment engine designed to manage environment configurations, batch scripts, and dotfiles. It operates by reading a centralized JSON configuration and mapping atomic files from a host repository to target directories.

## Architecture & Integration

This tool is designed to be used as a **Git Submodule** inside a parent repository. The manager is completely blind to your personal files and relies strictly on the Current Working Directory (CWD) to locate configurations and payload files. 

### Expected Parent Directory Structure

When executed, the scripts expect the parent directory to look like this:

```text
parent-repo/
├── config.json           # Your local configurations (Git-ignored here)
├── manifest.json         # Routing logic for variant files
├── core/                 # Universal files deployed to all variants
├── variants/             # Variant-specific files
└── symlink-manager/      # THIS SUBMODULE
    └── scripts/          
```

## Setup & Configuration

To use this manager, you must create a `config.json` and a `manifest.json` in the root of your parent repository. 

### `config.json`
Defines the target deployment directories and toggles for global inclusion.

```json
{
    "my_environment": {
        "target_dir": "C:/Path/To/Target/Directory",
        "include_core": true,
        "include_builds": true,
        "variant_folder": "variants/my_environment"
    }
}
```

### `manifest.json`
Acts as the routing table for files in your `variants/` directory.

```json
{
    "specific_script.txt": [
        "my_environment",
        "another_environment"
    ]
}
```

## Execution Pipeline

Run these scripts from the root of your **parent repository**.

*   **Deploy Links:** `python symlink-manager/scripts/deploy.py <variant_key>`
*   **Remove Links (Teardown):** `python symlink-manager/scripts/deploy.py <variant_key> --remove`
*   **Format & Sanitize:** `python symlink-manager/scripts/format_skyrim_batch.py`
*   **Audit & Generate Docs:** `python symlink-manager/scripts/maintain_repo.py`
*   **Full Pipeline (Format -> Audit -> Deploy):** `python symlink-manager/scripts/build.py <variant_key>`

*Note: The engine aggressively protects real files. It will not overwrite existing non-symlink files in the target directory.*