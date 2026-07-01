"""Loading and validation of the master ``config.json``."""
import json

class ConfigError(Exception):
    """Raised when config.json is missing or does not define the variant."""

def load_json(path, description):
    """Reads and parses a JSON file, raising ConfigError on a syntax error.

    ``description`` names the file for the error message (e.g. "config.json").
    Keeps a malformed file from surfacing as a bare JSONDecodeError traceback.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"{description} is not valid JSON ({path}): {e}") from e

def load_config(repo_root):
    """Loads and parses the master config.json from the repo root."""
    config_path = repo_root / "config.json"
    if not config_path.exists():
        raise ConfigError(f"Master configuration file missing at {config_path.name}")
    return load_json(config_path, "config.json")

def select_variant(master_config, variant_key):
    """Returns the config block for a single variant, raising if undefined."""
    if variant_key not in master_config:
        raise ConfigError(f"Variant '{variant_key}' is not defined in config.json.")
    return master_config[variant_key]
