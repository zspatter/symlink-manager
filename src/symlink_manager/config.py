"""Loading and validation of the master ``config.json``."""
import json

class ConfigError(Exception):
    """Raised when config.json is missing or does not define the variant."""

def load_config(repo_root):
    """Loads and parses the master config.json from the repo root."""
    config_path = repo_root / "config.json"
    if not config_path.exists():
        raise ConfigError(f"Master configuration file missing at {config_path.name}")
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def select_variant(master_config, variant_key):
    """Returns the config block for a single variant, raising if undefined."""
    if variant_key not in master_config:
        raise ConfigError(f"Variant '{variant_key}' is not defined in config.json.")
    return master_config[variant_key]
