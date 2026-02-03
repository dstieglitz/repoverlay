"""Tests for CLI module."""

import os
import subprocess
import sys

import pytest
import yaml

from repoverlay import __version__


class TestCLI:
    """Tests for command-line interface."""

    def test_version_flag(self):
        """--version prints version and exits."""
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "--version"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert __version__ in result.stdout

    def test_clone_success(self, tmp_main_repo, sample_config):
        """repoverlay clone runs successfully."""
        # Write config file
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "successfully" in result.stdout

        # Verify symlinks created
        assert (tmp_main_repo / ".env").is_symlink()
        assert (tmp_main_repo / "config" / "secrets").is_symlink()

    def test_clone_no_config(self, tmp_path):
        """Error message when no config found."""
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "No .repoverlay.yaml found" in result.stderr

    def test_clone_from_subdirectory(self, tmp_main_repo, sample_config):
        """Clone works from subdirectory."""
        # Write config file
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Create and run from subdirectory
        subdir = tmp_main_repo / "sub" / "dir"
        subdir.mkdir(parents=True)

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=subdir,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Verify symlinks created in main repo
        assert (tmp_main_repo / ".env").is_symlink()

    def test_help(self):
        """Help shows usage information."""
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "clone" in result.stdout
        assert "sync" in result.stdout
        assert "unlink" in result.stdout

    def test_sync_command(self, tmp_main_repo, sample_config):
        """Sync command works after clone."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # First clone
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Then sync
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "sync"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "complete" in result.stdout.lower()

    def test_unlink_command(self, tmp_main_repo, sample_config):
        """Unlink command removes symlinks."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )
        assert (tmp_main_repo / ".env").is_symlink()

        # Unlink
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "unlink"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert not (tmp_main_repo / ".env").exists()

    def test_quiet_flag(self, tmp_main_repo, sample_config):
        """--quiet suppresses informational output."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "--quiet", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Output should be minimal/empty
        assert result.stdout.strip() == ""

    def test_dry_run_flag(self, tmp_main_repo, sample_config):
        """--dry-run previews changes without executing."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone", "--dry-run"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "dry-run" in result.stdout.lower()

        # Nothing should be created
        assert not (tmp_main_repo / ".repoverlay").exists()

    def test_force_flag(self, tmp_main_repo, sample_config):
        """--force overwrites existing."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone twice with --force
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone", "--force"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_status_command(self, tmp_main_repo, sample_config):
        """Status command shows git status of overlay repo."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "status"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should show git status output
        assert "branch" in result.stdout.lower() or "nothing to commit" in result.stdout.lower()

    def test_status_without_clone(self, tmp_main_repo, sample_config):
        """Status errors if not cloned."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "status"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not cloned" in result.stderr.lower()

    def test_no_color_flag(self, tmp_main_repo, sample_config):
        """--no-color disables colored output."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "--no-color", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        # Should not contain ANSI escape codes
        assert "\033[" not in result.stdout

    def test_no_color_env_var(self, tmp_main_repo, sample_config):
        """NO_COLOR env var disables colored output."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        env = os.environ.copy()
        env["NO_COLOR"] = "1"

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0
        # Should not contain ANSI escape codes
        assert "\033[" not in result.stdout

    def test_diff_command(self, tmp_main_repo, sample_config):
        """Diff command shows overlay diff."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "diff"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_diff_with_args(self, tmp_main_repo, sample_config):
        """Diff command passes arguments to git."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Use -- to separate repoverlay args from git args
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "diff", "--", "--stat"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_fetch_command(self, tmp_main_repo, sample_config):
        """Fetch command runs git fetch."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "fetch"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_unlink_with_remove_repo(self, tmp_main_repo, sample_config):
        """Unlink --remove-repo removes .repoverlay/."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )
        assert (tmp_main_repo / ".repoverlay").exists()

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "unlink", "--remove-repo"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert not (tmp_main_repo / ".repoverlay").exists()


class TestExitCode2:
    """Tests for exit code 2 (partial success with warnings)."""

    def test_sync_repo_url_mismatch(self, tmp_main_repo, tmp_overlay_repo, sample_config):
        """Sync returns exit code 2 on repo URL mismatch."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone first
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Change config to different URL (must be a git URL to trigger mismatch check)
        sample_config["overlay"]["repo"] = "git@github.com:different/repo.git"
        config_path.write_text(yaml.dump(sample_config))

        # Sync should warn and return exit code 2
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "sync"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert "mismatch" in result.stderr.lower()

    def test_sync_gitignore_conflict(self, tmp_main_repo, sample_config):
        """Sync returns exit code 2 on gitignore conflict."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Add .gitignore with pattern matching destination
        (tmp_main_repo / ".gitignore").write_text(".env\n")

        # Clone first
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Sync should warn about gitignore conflict
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "sync"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2
        assert ".gitignore" in result.stderr.lower() or "warning" in result.stderr.lower()
