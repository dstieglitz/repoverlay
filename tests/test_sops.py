"""Tests for SOPS encryption/decryption module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repoverlay import sops


class TestSopsAvailability:
    """Tests for SOPS availability checking."""

    def test_is_sops_available_when_installed(self):
        """Returns True when SOPS is installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert sops.is_sops_available() is True
            mock_run.assert_called_once()

    def test_is_sops_available_when_not_installed(self):
        """Returns False when SOPS is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert sops.is_sops_available() is False

    def test_is_sops_available_when_command_fails(self):
        """Returns False when SOPS command fails."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert sops.is_sops_available() is False


class TestEncryptedFileDetection:
    """Tests for encrypted file detection."""

    def test_is_encrypted_file_enc_suffix(self):
        """Detects .enc suffix."""
        assert sops.is_encrypted_file("config.yaml.enc") is True
        assert sops.is_encrypted_file("secrets/db.yaml.enc") is True

    def test_is_encrypted_file_encoded_suffix(self):
        """Detects .encoded suffix."""
        assert sops.is_encrypted_file("config.yaml.encoded") is True

    def test_is_encrypted_file_encrypted_suffix(self):
        """Detects .encrypted suffix."""
        assert sops.is_encrypted_file("terraform.tfstate.encrypted") is True
        assert sops.is_encrypted_file("secrets/db.yaml.encrypted") is True

    def test_is_encrypted_file_not_encrypted(self):
        """Returns False for non-encrypted files."""
        assert sops.is_encrypted_file("config.yaml") is False
        assert sops.is_encrypted_file("README.md") is False
        assert sops.is_encrypted_file("secrets.enc.bak") is False

    def test_is_encrypted_file_path_object(self):
        """Works with Path objects."""
        assert sops.is_encrypted_file(Path("config.yaml.enc")) is True
        assert sops.is_encrypted_file(Path("config.yaml")) is False


class TestDetectInputType:
    """Tests for input type detection."""

    def test_detect_yaml_enc(self):
        """Detects yaml from .yaml.enc files."""
        assert sops._detect_input_type(Path("config.yaml.enc")) == "yaml"
        assert sops._detect_input_type(Path("path/to/config.yaml.enc")) == "yaml"

    def test_detect_yml_enc(self):
        """Detects yaml from .yml.enc files."""
        assert sops._detect_input_type(Path("config.yml.enc")) == "yaml"

    def test_detect_yaml_encrypted(self):
        """Detects yaml from .yaml.encrypted files."""
        assert sops._detect_input_type(Path("config.yaml.encrypted")) == "yaml"

    def test_detect_json(self):
        """Detects json from .json.enc files."""
        assert sops._detect_input_type(Path("config.json.enc")) == "json"

    def test_detect_dotenv(self):
        """Detects dotenv from .env.enc files."""
        assert sops._detect_input_type(Path(".env.enc")) == "dotenv"
        assert sops._detect_input_type(Path("secrets.env.enc")) == "dotenv"

    def test_detect_ini(self):
        """Detects ini from .ini.enc files."""
        assert sops._detect_input_type(Path("config.ini.enc")) == "ini"

    def test_no_detection_for_unknown(self):
        """Returns None for unknown file types."""
        assert sops._detect_input_type(Path("secrets.enc")) is None
        assert sops._detect_input_type(Path("data.txt.enc")) is None

    def test_case_insensitive(self):
        """Detection is case-insensitive."""
        assert sops._detect_input_type(Path("config.YAML.enc")) == "yaml"
        assert sops._detect_input_type(Path("config.YML.encrypted")) == "yaml"
        assert sops._detect_input_type(Path("config.JSON.enc")) == "json"


class TestDecodedPath:
    """Tests for decoded path generation."""

    def test_get_decoded_path_enc(self):
        """Strips .enc suffix."""
        assert sops.get_decoded_path("config.yaml.enc") == "config.yaml"
        assert sops.get_decoded_path("secrets/db.yaml.enc") == "secrets/db.yaml"

    def test_get_decoded_path_encoded(self):
        """Strips .encoded suffix."""
        assert sops.get_decoded_path("config.yaml.encoded") == "config.yaml"

    def test_get_decoded_path_encrypted(self):
        """Strips .encrypted suffix."""
        assert sops.get_decoded_path("terraform.tfstate.encrypted") == "terraform.tfstate"

    def test_get_decoded_path_no_suffix(self):
        """Returns unchanged if no encryption suffix."""
        assert sops.get_decoded_path("config.yaml") == "config.yaml"


class TestSopsConfigPath:
    """Tests for SOPS config path detection."""

    def test_get_sops_config_from_config_option(self, tmp_path):
        """Uses custom path from config."""
        # Create custom sops config location
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        sops_yaml = custom_dir / ".sops.yaml"
        sops_yaml.write_text("keys: []")

        config = {"overlay": {"sops_config": "custom/.sops.yaml"}}
        result = sops.get_sops_config_path(tmp_path, config)
        assert result == sops_yaml

    def test_get_sops_config_default_location(self, tmp_path):
        """Finds .sops.yaml in .config/ directory."""
        config_dir = tmp_path / ".config"
        config_dir.mkdir()
        sops_yaml = config_dir / ".sops.yaml"
        sops_yaml.write_text("keys: []")

        result = sops.get_sops_config_path(tmp_path)
        assert result == sops_yaml

    def test_get_sops_config_root_location(self, tmp_path):
        """Falls back to root .sops.yaml."""
        sops_yaml = tmp_path / ".sops.yaml"
        sops_yaml.write_text("keys: []")

        result = sops.get_sops_config_path(tmp_path)
        assert result == sops_yaml

    def test_get_sops_config_not_found(self, tmp_path):
        """Returns None if no .sops.yaml found."""
        result = sops.get_sops_config_path(tmp_path)
        assert result is None


class TestFileHash:
    """Tests for file hashing."""

    def test_file_hash(self, tmp_path):
        """Computes correct SHA256 hash."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        result = sops.file_hash(test_file)
        assert result.startswith("sha256:")
        # Known hash for "hello world"
        assert "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9" in result

    def test_file_hash_different_content(self, tmp_path):
        """Different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        assert sops.file_hash(file1) != sops.file_hash(file2)


class TestScanEncryptedFiles:
    """Tests for scanning encrypted files."""

    def test_scan_finds_enc_files(self, tmp_path):
        """Finds .enc files."""
        (tmp_path / "config.yaml.enc").write_text("encrypted")
        (tmp_path / "secrets" / "db.yaml.enc").parent.mkdir()
        (tmp_path / "secrets" / "db.yaml.enc").write_text("encrypted")

        result = sops.scan_encrypted_files(tmp_path)
        assert len(result) == 2
        assert Path("config.yaml.enc") in result
        assert Path("secrets/db.yaml.enc") in result

    def test_scan_skips_git_directory(self, tmp_path):
        """Skips .git directory."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config.enc").write_text("encrypted")

        result = sops.scan_encrypted_files(tmp_path)
        assert len(result) == 0

    def test_scan_finds_encoded_files(self, tmp_path):
        """Finds .encoded files."""
        (tmp_path / "config.yaml.encoded").write_text("encrypted")

        result = sops.scan_encrypted_files(tmp_path)
        assert len(result) == 1
        assert Path("config.yaml.encoded") in result


class TestDecryptFile:
    """Tests for file decryption."""

    def test_decrypt_file_sops_not_available(self, tmp_path):
        """Raises error when SOPS not installed."""
        src = tmp_path / "config.yaml.enc"
        dst = tmp_path / "config.yaml"
        src.write_text("encrypted")

        with patch.object(sops, "is_sops_available", return_value=False):
            with pytest.raises(sops.SopsNotAvailableError):
                sops.decrypt_file(src, dst)

    def test_decrypt_file_success(self, tmp_path):
        """Successfully decrypts file."""
        src = tmp_path / "config.yaml.enc"
        dst = tmp_path / "decoded" / "config.yaml"
        src.write_text("encrypted")

        with patch.object(sops, "is_sops_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                sops.decrypt_file(src, dst)

                # Check subprocess was called correctly
                args = mock_run.call_args[0][0]
                assert "sops" in args
                assert "--decrypt" in args

    def test_decrypt_file_key_not_found(self, tmp_path):
        """Raises error when keys unavailable."""
        src = tmp_path / "config.yaml.enc"
        dst = tmp_path / "config.yaml"
        src.write_text("encrypted")

        with patch.object(sops, "is_sops_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="failed to get the data key required to decrypt"
                )
                with pytest.raises(sops.SopsDecryptionError) as exc_info:
                    sops.decrypt_file(src, dst)
                assert "failed to get the data key" in str(exc_info.value)


class TestEncryptFile:
    """Tests for file encryption."""

    def test_encrypt_file_sops_not_available(self, tmp_path):
        """Raises error when SOPS not installed."""
        src = tmp_path / "config.yaml"
        dst = tmp_path / "config.yaml.enc"
        src.write_text("plain")

        with patch.object(sops, "is_sops_available", return_value=False):
            with pytest.raises(sops.SopsNotAvailableError):
                sops.encrypt_file(src, dst)

    def test_encrypt_file_success(self, tmp_path):
        """Successfully encrypts file."""
        src = tmp_path / "config.yaml"
        dst = tmp_path / "repo" / "config.yaml.enc"
        src.write_text("plain")

        with patch.object(sops, "is_sops_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                sops.encrypt_file(src, dst)

                args = mock_run.call_args[0][0]
                assert "sops" in args
                assert "--encrypt" in args

    def test_encrypt_file_no_matching_rules(self, tmp_path):
        """Raises error when no matching creation rules."""
        src = tmp_path / "config.yaml"
        dst = tmp_path / "config.yaml.enc"
        src.write_text("plain")

        with patch.object(sops, "is_sops_available", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="no matching creation rules"
                )
                with pytest.raises(sops.SopsEncryptionError) as exc_info:
                    sops.encrypt_file(src, dst)
                assert "creation rules" in str(exc_info.value)


class TestDecryptAllFiles:
    """Tests for bulk decryption."""

    def test_decrypt_all_no_encrypted_files(self, tmp_path):
        """Returns empty dict when no encrypted files."""
        repo_dir = tmp_path / "repo"
        decoded_dir = tmp_path / "decoded"
        repo_dir.mkdir()

        result = sops.decrypt_all_files(repo_dir, decoded_dir)
        assert result == {}

    def test_decrypt_all_sops_not_available(self, tmp_path):
        """Raises error when SOPS not installed."""
        repo_dir = tmp_path / "repo"
        decoded_dir = tmp_path / "decoded"
        repo_dir.mkdir()
        (repo_dir / "config.yaml.enc").write_text("encrypted")

        with patch.object(sops, "is_sops_available", return_value=False):
            with pytest.raises(sops.SopsNotAvailableError):
                sops.decrypt_all_files(repo_dir, decoded_dir)

    def test_decrypt_all_success(self, tmp_path):
        """Successfully decrypts all files."""
        repo_dir = tmp_path / "repo"
        decoded_dir = tmp_path / "decoded"
        repo_dir.mkdir()
        enc_file = repo_dir / "config.yaml.enc"
        enc_file.write_text("encrypted")

        with patch.object(sops, "is_sops_available", return_value=True):
            with patch.object(sops, "decrypt_file") as mock_decrypt:
                result = sops.decrypt_all_files(repo_dir, decoded_dir)

                assert "config.yaml.enc" in result
                assert result["config.yaml.enc"]["decoded_path"] == "config.yaml"
                mock_decrypt.assert_called_once()


class TestDetectDecodedChanges:
    """Tests for detecting changes to decoded files."""

    def test_detect_deleted_file(self, tmp_path):
        """Detects deleted decoded files."""
        decoded_dir = tmp_path / "decoded"
        repo_dir = tmp_path / "repo"
        decoded_dir.mkdir()
        repo_dir.mkdir()

        encrypted_state = {
            "config.yaml.enc": {
                "decoded_path": "config.yaml",
                "last_encrypted_hash": "sha256:abc123"
            }
        }

        changed = sops.detect_decoded_changes(decoded_dir, repo_dir, encrypted_state)
        assert "config.yaml.enc" in changed

    def test_detect_unchanged_file(self, tmp_path):
        """No changes when file matches encrypted source."""
        decoded_dir = tmp_path / "decoded"
        repo_dir = tmp_path / "repo"
        decoded_dir.mkdir()
        repo_dir.mkdir()

        # Create decoded and encrypted files with same content
        (decoded_dir / "config.yaml").write_text("content")
        (repo_dir / "config.yaml.enc").write_text("encrypted")

        encrypted_state = {
            "config.yaml.enc": {
                "decoded_path": "config.yaml",
                "last_encrypted_hash": "sha256:abc123"
            }
        }

        with patch("subprocess.run") as mock_run:
            # Mock decryption returning same content
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"content"
            )
            changed = sops.detect_decoded_changes(decoded_dir, repo_dir, encrypted_state)
            assert len(changed) == 0


class TestReEncryptChangedFiles:
    """Tests for re-encryption of changed files."""

    def test_re_encrypt_updates_files(self, tmp_path):
        """Re-encrypts modified decoded files."""
        decoded_dir = tmp_path / "decoded"
        repo_dir = tmp_path / "repo"
        decoded_dir.mkdir()
        repo_dir.mkdir()

        (decoded_dir / "config.yaml").write_text("modified content")
        (repo_dir / "config.yaml.enc").write_text("old encrypted")

        encrypted_state = {
            "config.yaml.enc": {
                "decoded_path": "config.yaml",
                "last_encrypted_hash": "sha256:old"
            }
        }

        with patch.object(sops, "encrypt_file") as mock_encrypt:
            with patch.object(sops, "file_hash", return_value="sha256:new"):
                updated = sops.re_encrypt_changed_files(
                    decoded_dir,
                    repo_dir,
                    ["config.yaml.enc"],
                    encrypted_state
                )

                assert "config.yaml.enc" in updated
                mock_encrypt.assert_called_once()
                # Check hash was updated
                assert encrypted_state["config.yaml.enc"]["last_encrypted_hash"] == "sha256:new"

    def test_re_encrypt_skips_deleted(self, tmp_path):
        """Skips re-encryption of deleted decoded files."""
        decoded_dir = tmp_path / "decoded"
        repo_dir = tmp_path / "repo"
        decoded_dir.mkdir()
        repo_dir.mkdir()

        encrypted_state = {
            "config.yaml.enc": {
                "decoded_path": "config.yaml",
                "last_encrypted_hash": "sha256:old"
            }
        }

        with patch.object(sops, "encrypt_file") as mock_encrypt:
            updated = sops.re_encrypt_changed_files(
                decoded_dir,
                repo_dir,
                ["config.yaml.enc"],
                encrypted_state
            )

            assert len(updated) == 0
            mock_encrypt.assert_not_called()


class TestReDecryptIfChanged:
    """Tests for re-decryption when encrypted source changes."""

    def test_re_decrypt_when_source_changed(self, tmp_path):
        """Re-decrypts when encrypted source hash differs."""
        decoded_dir = tmp_path / "decoded"
        repo_dir = tmp_path / "repo"
        decoded_dir.mkdir()
        repo_dir.mkdir()

        enc_file = repo_dir / "config.yaml.enc"
        enc_file.write_text("new encrypted content")

        encrypted_state = {
            "config.yaml.enc": {
                "decoded_path": "config.yaml",
                "last_encrypted_hash": "sha256:old"
            }
        }

        with patch.object(sops, "decrypt_file") as mock_decrypt:
            with patch.object(sops, "file_hash", return_value="sha256:new"):
                re_decrypted = sops.re_decrypt_if_changed(
                    repo_dir, decoded_dir, encrypted_state
                )

                assert "config.yaml.enc" in re_decrypted
                mock_decrypt.assert_called_once()
                # Check hash was updated
                assert encrypted_state["config.yaml.enc"]["last_encrypted_hash"] == "sha256:new"

    def test_no_re_decrypt_when_unchanged(self, tmp_path):
        """No re-decryption when hash matches."""
        decoded_dir = tmp_path / "decoded"
        repo_dir = tmp_path / "repo"
        decoded_dir.mkdir()
        repo_dir.mkdir()

        enc_file = repo_dir / "config.yaml.enc"
        enc_file.write_text("encrypted content")
        current_hash = sops.file_hash(enc_file)

        encrypted_state = {
            "config.yaml.enc": {
                "decoded_path": "config.yaml",
                "last_encrypted_hash": current_hash
            }
        }

        with patch.object(sops, "decrypt_file") as mock_decrypt:
            re_decrypted = sops.re_decrypt_if_changed(
                repo_dir, decoded_dir, encrypted_state
            )

            assert len(re_decrypted) == 0
            mock_decrypt.assert_not_called()


class TestConfigValidation:
    """Tests for SOPS config validation in repoverlay config."""

    def test_valid_sops_config(self):
        """Valid sops_config passes validation."""
        from repoverlay.config import validate_config

        config = {
            "version": 1,
            "overlay": {
                "repo": "git@github.com:org/config.git",
                "sops_config": ".config/.sops.yaml"
            }
        }
        result = validate_config(config)
        assert result["overlay"]["sops_config"] == ".config/.sops.yaml"

    def test_sops_config_must_be_string(self):
        """sops_config must be a string."""
        from repoverlay.config import validate_config, ConfigError

        config = {
            "version": 1,
            "overlay": {
                "repo": "git@github.com:org/config.git",
                "sops_config": 123
            }
        }
        with pytest.raises(ConfigError) as exc_info:
            validate_config(config)
        assert "sops_config must be a string" in str(exc_info.value)

    def test_sops_config_must_be_relative(self):
        """sops_config must be relative path."""
        from repoverlay.config import validate_config, ConfigError

        config = {
            "version": 1,
            "overlay": {
                "repo": "git@github.com:org/config.git",
                "sops_config": "/absolute/path/.sops.yaml"
            }
        }
        with pytest.raises(ConfigError) as exc_info:
            validate_config(config)
        assert "must be relative" in str(exc_info.value)

    def test_valid_encrypt_patterns(self):
        """Valid encrypt_patterns passes validation."""
        from repoverlay.config import validate_config

        config = {
            "version": 1,
            "overlay": {
                "repo": "git@github.com:org/config.git",
                "encrypt_patterns": ["secrets/**", "**/*.secret.yaml"]
            }
        }
        result = validate_config(config)
        assert result["overlay"]["encrypt_patterns"] == ["secrets/**", "**/*.secret.yaml"]

    def test_encrypt_patterns_must_be_list(self):
        """encrypt_patterns must be a list."""
        from repoverlay.config import validate_config, ConfigError

        config = {
            "version": 1,
            "overlay": {
                "repo": "git@github.com:org/config.git",
                "encrypt_patterns": "secrets/**"
            }
        }
        with pytest.raises(ConfigError) as exc_info:
            validate_config(config)
        assert "encrypt_patterns must be a list" in str(exc_info.value)

    def test_encrypt_patterns_items_must_be_strings(self):
        """encrypt_patterns items must be strings."""
        from repoverlay.config import validate_config, ConfigError

        config = {
            "version": 1,
            "overlay": {
                "repo": "git@github.com:org/config.git",
                "encrypt_patterns": ["secrets/**", 123]
            }
        }
        with pytest.raises(ConfigError) as exc_info:
            validate_config(config)
        assert "encrypt_patterns[1]" in str(exc_info.value)


class TestSyncEncryptedFiles:
    """Integration tests for sync behavior with encrypted files."""

    def test_sync_does_not_recreate_unchanged_encrypted_symlinks(self, tmp_path):
        """Sync should not remove/recreate encrypted file symlinks when nothing changed."""
        from repoverlay.overlay import sync_overlay, get_repo_dir, get_decoded_dir
        from repoverlay.state import write_state
        from repoverlay.output import Output
        from io import StringIO

        # Set up directory structure
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        overlay_dir = root_dir / ".repoverlay"
        overlay_dir.mkdir()
        repo_dir = overlay_dir / "repo"
        repo_dir.mkdir()
        decoded_dir = overlay_dir / "decoded"
        decoded_dir.mkdir()

        # Create encrypted file and decoded version
        (repo_dir / "secrets.yaml.enc").write_text("encrypted content")
        (decoded_dir / "secrets.yaml").write_text("decrypted content")

        # Create the symlink (correct relative path from root_dir/secrets.yaml to decoded file)
        symlink_path = root_dir / "secrets.yaml"
        symlink_target = ".repoverlay/decoded/secrets.yaml"
        symlink_path.symlink_to(symlink_target)

        # Write state with encrypted file tracked
        write_state(root_dir, {
            "symlinks": ["secrets.yaml"],
            "created_directories": [],
            "encrypted_files": {
                "secrets.yaml.enc": {
                    "decoded_path": "secrets.yaml",
                    "symlink_dst": "secrets.yaml",
                    "last_encrypted_hash": sops.file_hash(repo_dir / "secrets.yaml.enc"),
                }
            }
        })

        config = {
            "version": 1,
            "overlay": {"repo": str(repo_dir)}
        }

        # Capture output
        stdout = StringIO()
        output = Output(no_color=True, stream=stdout)

        # Mock SOPS functions
        with patch.object(sops, "is_sops_available", return_value=True):
            with patch.object(sops, "scan_encrypted_files", return_value=[Path("secrets.yaml.enc")]):
                exit_code = sync_overlay(root_dir, config, output=output)

        # Check that the symlink was NOT removed and recreated
        output_text = stdout.getvalue()
        assert "- secrets.yaml" not in output_text  # Not removed
        assert "+ secrets.yaml (decrypted)" not in output_text  # Not recreated
        assert exit_code == 0

    def test_encrypted_files_excluded_from_mappings_even_on_decrypt_failure(self, tmp_path):
        """Encrypted files should not be symlinked as regular files even if decryption fails."""
        from repoverlay.overlay import sync_overlay
        from repoverlay.state import write_state, read_state
        from repoverlay.output import Output
        from io import StringIO

        # Set up directory structure
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        overlay_dir = root_dir / ".repoverlay"
        overlay_dir.mkdir()
        repo_dir = overlay_dir / "repo"
        repo_dir.mkdir()

        # Create encrypted file (no decoded version - simulating failed decryption)
        (repo_dir / "secrets.yaml.enc").write_text("encrypted content")
        # Also create a regular file
        (repo_dir / "config.yaml").write_text("regular content")

        # Write initial state (no encrypted files tracked yet)
        write_state(root_dir, {
            "symlinks": [],
            "created_directories": [],
            "encrypted_files": {}
        })

        config = {
            "version": 1,
            "overlay": {"repo": str(repo_dir)}
        }

        stdout = StringIO()
        stderr = StringIO()
        output = Output(no_color=True, stream=stdout, err_stream=stderr)

        # Mock SOPS - make decryption fail
        with patch.object(sops, "is_sops_available", return_value=True):
            with patch.object(sops, "decrypt_file", side_effect=sops.SopsDecryptionError("No keys")):
                with patch.object(sops, "get_sops_config_path", return_value=None):
                    exit_code = sync_overlay(root_dir, config, output=output)

        # Check that encrypted file was NOT symlinked as a regular file
        assert not (root_dir / "secrets.yaml.enc").exists()
        # But regular file should be symlinked
        assert (root_dir / "config.yaml").is_symlink()
        # Should have warning about decryption failure
        assert "No keys" in stderr.getvalue()
        assert exit_code == 2  # Warning exit code

    def test_sync_preserves_encrypted_files_state(self, tmp_path):
        """Sync should preserve encrypted_files in state across runs."""
        from repoverlay.overlay import sync_overlay
        from repoverlay.state import write_state, read_state
        from repoverlay.output import Output
        from io import StringIO

        # Set up directory structure
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        overlay_dir = root_dir / ".repoverlay"
        overlay_dir.mkdir()
        repo_dir = overlay_dir / "repo"
        repo_dir.mkdir()
        decoded_dir = overlay_dir / "decoded"
        decoded_dir.mkdir()

        # Create encrypted file and decoded version
        enc_file = repo_dir / "secrets.yaml.enc"
        enc_file.write_text("encrypted content")
        (decoded_dir / "secrets.yaml").write_text("decrypted content")

        # Create the symlink (correct relative path)
        symlink_path = root_dir / "secrets.yaml"
        symlink_path.symlink_to(".repoverlay/decoded/secrets.yaml")

        original_hash = sops.file_hash(enc_file)

        # Write state with encrypted file tracked
        write_state(root_dir, {
            "symlinks": ["secrets.yaml"],
            "created_directories": [],
            "encrypted_files": {
                "secrets.yaml.enc": {
                    "decoded_path": "secrets.yaml",
                    "symlink_dst": "secrets.yaml",
                    "last_encrypted_hash": original_hash,
                }
            }
        })

        config = {
            "version": 1,
            "overlay": {"repo": str(repo_dir)}
        }

        output = Output(no_color=True, stream=StringIO())

        with patch.object(sops, "is_sops_available", return_value=True):
            with patch.object(sops, "scan_encrypted_files", return_value=[Path("secrets.yaml.enc")]):
                sync_overlay(root_dir, config, output=output)

        # Check that encrypted_files state was preserved
        state = read_state(root_dir)
        assert "secrets.yaml.enc" in state["encrypted_files"]
        assert state["encrypted_files"]["secrets.yaml.enc"]["last_encrypted_hash"] == original_hash
