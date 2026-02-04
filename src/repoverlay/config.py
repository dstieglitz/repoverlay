"""Configuration loading and validation."""

from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Raised when config is invalid or not found."""
    pass


def find_config(start_dir: Path | None = None) -> Path:
    """Find .repoverlay.yaml by searching upward from start_dir.

    Args:
        start_dir: Directory to start search from. Defaults to cwd.

    Returns:
        Path to the config file.

    Raises:
        ConfigError: If no config file found.
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    while True:
        config_path = current / ".repoverlay.yaml"
        if config_path.exists():
            return config_path

        parent = current.parent
        if parent == current:
            # Reached filesystem root
            raise ConfigError("No .repoverlay.yaml found")
        current = parent


def load_config(config_path: Path) -> dict[str, Any]:
    """Load and validate config from YAML file.

    Args:
        config_path: Path to the config file.

    Returns:
        Validated config dict.

    Raises:
        ConfigError: If config is invalid.
    """
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid config: {e}")

    if config is None:
        raise ConfigError("Invalid config: empty file")

    return validate_config(config)


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate config structure and values.

    Args:
        config: Raw config dict.

    Returns:
        Validated config dict.

    Raises:
        ConfigError: If config is invalid.
    """
    if not isinstance(config, dict):
        raise ConfigError("Invalid config: expected mapping")

    # Check version
    if "version" not in config:
        raise ConfigError("Missing required field: version")

    if config["version"] != 1:
        raise ConfigError(f"Unsupported config version: {config['version']}")

    # Check overlay section
    if "overlay" not in config:
        raise ConfigError("Missing required field: overlay")

    overlay = config["overlay"]
    if not isinstance(overlay, dict):
        raise ConfigError("Invalid config: overlay must be a mapping")

    if "repo" not in overlay:
        raise ConfigError("Missing required field: overlay.repo")

    # Mappings are optional - if not provided, all files in overlay will be used
    if "mappings" in overlay:
        mappings = overlay["mappings"]
        if not isinstance(mappings, list):
            raise ConfigError("Invalid config: mappings must be a list")

        # Validate each mapping
        for i, mapping in enumerate(mappings):
            if not isinstance(mapping, dict):
                raise ConfigError(f"Invalid mapping at index {i}: expected mapping")

            if "src" not in mapping:
                raise ConfigError(f"Missing required field: mappings[{i}].src")

            if "dst" not in mapping:
                raise ConfigError(f"Missing required field: mappings[{i}].dst")

            dst = mapping["dst"]
            if dst.startswith("/"):
                raise ConfigError(f"Destination must be relative: {dst}")

    # Validate sops_config (optional string, relative path)
    if "sops_config" in overlay:
        sops_config = overlay["sops_config"]
        if not isinstance(sops_config, str):
            raise ConfigError("Invalid config: sops_config must be a string")
        if sops_config.startswith("/"):
            raise ConfigError(f"sops_config must be relative path: {sops_config}")

    # Validate encrypt_patterns (optional list of glob strings)
    if "encrypt_patterns" in overlay:
        encrypt_patterns = overlay["encrypt_patterns"]
        if not isinstance(encrypt_patterns, list):
            raise ConfigError("Invalid config: encrypt_patterns must be a list")
        for i, pattern in enumerate(encrypt_patterns):
            if not isinstance(pattern, str):
                raise ConfigError(f"Invalid encrypt_patterns[{i}]: must be a string")

    return config
