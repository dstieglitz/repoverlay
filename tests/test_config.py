"""Tests for config module."""

import pytest
import yaml

from repoverlay.config import ConfigError, find_config, load_config, validate_config


class TestValidateConfig:
    """Tests for validate_config function."""

    def test_valid_config(self, sample_config):
        """Valid config parses correctly."""
        result = validate_config(sample_config)
        assert result == sample_config

    def test_missing_version(self, sample_config):
        """Missing version errors."""
        del sample_config["version"]
        with pytest.raises(ConfigError, match="Missing required field: version"):
            validate_config(sample_config)

    def test_wrong_version(self, sample_config):
        """Wrong version errors."""
        sample_config["version"] = 2
        with pytest.raises(ConfigError, match="Unsupported config version: 2"):
            validate_config(sample_config)

    def test_missing_repo(self, sample_config):
        """Missing repo errors."""
        del sample_config["overlay"]["repo"]
        with pytest.raises(ConfigError, match="Missing required field: overlay.repo"):
            validate_config(sample_config)

    def test_missing_mappings_allowed(self, sample_config):
        """Missing mappings is allowed (generates from all files)."""
        del sample_config["overlay"]["mappings"]
        result = validate_config(sample_config)
        assert "mappings" not in result["overlay"]

    def test_empty_mappings_allowed(self, sample_config):
        """Empty mappings list is allowed."""
        sample_config["overlay"]["mappings"] = []
        result = validate_config(sample_config)
        assert result["overlay"]["mappings"] == []

    def test_mappings_not_a_list(self, sample_config):
        """Mappings must be a list if provided."""
        sample_config["overlay"]["mappings"] = "not a list"
        with pytest.raises(ConfigError, match="mappings must be a list"):
            validate_config(sample_config)

    def test_missing_overlay(self, sample_config):
        """Missing overlay section errors."""
        del sample_config["overlay"]
        with pytest.raises(ConfigError, match="Missing required field: overlay"):
            validate_config(sample_config)

    def test_absolute_dst_path(self, sample_config):
        """Absolute destination path errors."""
        sample_config["overlay"]["mappings"][0]["dst"] = "/etc/secrets"
        with pytest.raises(ConfigError, match="Destination must be relative"):
            validate_config(sample_config)

    def test_mapping_missing_src(self, sample_config):
        """Mapping missing src errors."""
        del sample_config["overlay"]["mappings"][0]["src"]
        with pytest.raises(ConfigError, match="Missing required field: mappings"):
            validate_config(sample_config)

    def test_mapping_missing_dst(self, sample_config):
        """Mapping missing dst errors."""
        del sample_config["overlay"]["mappings"][0]["dst"]
        with pytest.raises(ConfigError, match="Missing required field: mappings"):
            validate_config(sample_config)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_yaml(self, tmp_path, sample_config):
        """Valid YAML file loads correctly."""
        config_path = tmp_path / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = load_config(config_path)
        assert result["version"] == 1
        assert result["overlay"]["repo"] == sample_config["overlay"]["repo"]

    def test_invalid_yaml(self, tmp_path):
        """Invalid YAML errors."""
        config_path = tmp_path / ".repoverlay.yaml"
        config_path.write_text("{ invalid yaml [")

        with pytest.raises(ConfigError, match="Invalid config"):
            load_config(config_path)

    def test_empty_file(self, tmp_path):
        """Empty file errors."""
        config_path = tmp_path / ".repoverlay.yaml"
        config_path.write_text("")

        with pytest.raises(ConfigError, match="Invalid config: empty file"):
            load_config(config_path)


class TestFindConfig:
    """Tests for find_config function."""

    def test_config_in_current_dir(self, tmp_path):
        """Finds config in current directory."""
        config_path = tmp_path / ".repoverlay.yaml"
        config_path.write_text("version: 1")

        result = find_config(tmp_path)
        assert result == config_path

    def test_config_in_parent_dir(self, tmp_path):
        """Finds config in parent directory."""
        config_path = tmp_path / ".repoverlay.yaml"
        config_path.write_text("version: 1")

        subdir = tmp_path / "sub" / "dir"
        subdir.mkdir(parents=True)

        result = find_config(subdir)
        assert result == config_path

    def test_config_not_found(self, tmp_path):
        """Errors when config not found."""
        subdir = tmp_path / "sub"
        subdir.mkdir()

        with pytest.raises(ConfigError, match="No .repoverlay.yaml found"):
            find_config(subdir)
