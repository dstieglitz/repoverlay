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

    def test_log_command(self, tmp_main_repo, sample_config):
        """Log command shows overlay commit log."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "log"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_log_with_args(self, tmp_main_repo, sample_config):
        """Log command passes arguments to git."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Use -1 to limit output to one commit
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "log", "--", "-1"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_log_without_clone_errors(self, tmp_main_repo, sample_config):
        """Log command errors if overlay not cloned."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "log"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_merge_command(self, tmp_main_repo, tmp_overlay_repo):
        """Merge command merges a branch and syncs symlinks."""
        # Use config without explicit mappings so new files get symlinks
        config = {
            "version": 1,
            "overlay": {"repo": str(tmp_overlay_repo)},
        }
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create a feature branch with a new file
        subprocess.run(
            ["git", "checkout", "-b", "feature"],
            cwd=repo_dir, capture_output=True,
        )
        new_file = repo_dir / "feature.yaml"
        new_file.write_text("feature: true")
        subprocess.run(["git", "add", "feature.yaml"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add feature file"],
            cwd=repo_dir, capture_output=True,
        )

        # Go back to the default branch
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=repo_dir, capture_output=True,
        )

        # Merge the feature branch via repoverlay
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "merge", "feature"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        # The new file should exist in repo after merge
        assert new_file.exists()
        assert new_file.read_text() == "feature: true"

        # Symlink should have been created by sync
        symlink = tmp_main_repo / "feature.yaml"
        assert symlink.is_symlink()

    def test_merge_syncs_symlinks(self, tmp_main_repo, tmp_overlay_repo):
        """Merge creates symlinks for nested files added in the merged branch."""
        config = {
            "version": 1,
            "overlay": {"repo": str(tmp_overlay_repo)},
        }
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create a feature branch with nested files
        subprocess.run(
            ["git", "checkout", "-b", "feature-nested"],
            cwd=repo_dir, capture_output=True,
        )
        nested = repo_dir / "config" / "new" / "settings.yaml"
        nested.parent.mkdir(parents=True)
        nested.write_text("new_setting: true")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add nested config"],
            cwd=repo_dir, capture_output=True,
        )

        # Back to default branch
        subprocess.run(
            ["git", "checkout", "-"],
            cwd=repo_dir, capture_output=True,
        )

        # Merge
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "merge", "feature-nested"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        # Nested symlink should be created
        symlink = tmp_main_repo / "config" / "new" / "settings.yaml"
        assert symlink.is_symlink()
        assert symlink.read_text() == "new_setting: true"

    def test_merge_without_clone_errors(self, tmp_main_repo, sample_config):
        """Merge command errors if overlay not cloned."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "merge", "somebranch"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

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


class TestCommitCommand:
    """Tests for commit command."""

    def test_commit_with_all_flag(self, tmp_main_repo, sample_config):
        """Commit -a stages and commits modified files."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Modify a file in the overlay repo (repo is in .repoverlay/repo/)
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        secrets_file = repo_dir / "secrets" / "db.yaml"
        secrets_file.write_text("password: new_secret")

        # Commit with -a flag (should auto-stage the modified file)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "commit", "-a", "-m", "update secret"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "complete" in result.stdout.lower()

        # Verify the commit was made
        log_result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "update secret" in log_result.stdout

    def test_commit_all_flag_long_form(self, tmp_main_repo, sample_config):
        """Commit --all stages and commits modified files."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Modify a file in the overlay repo (repo is in .repoverlay/repo/)
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        secrets_file = repo_dir / "secrets" / "db.yaml"
        secrets_file.write_text("password: another_secret")

        # Commit with --all flag
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "commit", "--all", "-m", "another update"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "complete" in result.stdout.lower()

    def test_push_to_local_nonbare_repo(self, tmp_main_repo, tmp_overlay_repo):
        """Push to local non-bare repo works via pull mechanism."""
        # tmp_overlay_repo is a non-bare repo (has working directory)
        # Configure repoverlay to use it
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
                "mappings": [
                    {"src": "secrets", "dst": "config/secrets"},
                ],
            },
        }
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Modify a file in the overlay repo
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        secrets_file = repo_dir / "secrets" / "db.yaml"
        secrets_file.write_text("password: pushed_secret")

        # Commit the change
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "commit", "-a", "-m", "test push"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Push should succeed (via pull into remote)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "push"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "complete" in result.stdout.lower()

        # Verify the change was pushed to the origin repo
        origin_file = tmp_overlay_repo / "secrets" / "db.yaml"
        assert origin_file.read_text() == "password: pushed_secret"

        # Verify status doesn't show unpushed commits (tracking refs updated)
        status_result = subprocess.run(
            ["git", "status", "-sb"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        # Should not show "ahead" if tracking refs are properly updated
        assert "ahead" not in status_result.stdout


class TestAddCommand:
    """Tests for add command."""

    def test_add_file_from_outside_repo(self, tmp_main_repo, sample_config):
        """Add command copies files from outside overlay repo into it."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create a file outside the overlay repo but inside the project
        external_file = tmp_main_repo / "myconfig" / "settings.yaml"
        external_file.parent.mkdir(parents=True)
        external_file.write_text("key: value")

        # Add the external file
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(external_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "Copied to overlay" in result.stdout

        # Verify the file was copied into the overlay repo
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        copied_file = repo_dir / "myconfig" / "settings.yaml"
        assert copied_file.exists()
        assert copied_file.read_text() == "key: value"

        # Verify the file was staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "myconfig/settings.yaml" in status_result.stdout

    def test_add_file_already_in_repo(self, tmp_main_repo, sample_config):
        """Add command stages files that are already in the overlay repo."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create a new file directly in the overlay repo
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        new_file = repo_dir / "newfile.txt"
        new_file.write_text("new content")

        # Add the file using its path inside the repo
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(new_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "staged" in result.stdout.lower()

        # Verify the file was staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "newfile.txt" in status_result.stdout

    def test_add_file_completely_outside_project(self, tmp_main_repo, sample_config, tmp_path):
        """Add command uses basename for files outside the project entirely."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create a file completely outside the project
        external_file = tmp_path / "outside" / "external.yaml"
        external_file.parent.mkdir(parents=True)
        external_file.write_text("external: data")

        # Add the external file
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(external_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Verify the file was copied using just the basename
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        copied_file = repo_dir / "external.yaml"
        assert copied_file.exists()
        assert copied_file.read_text() == "external: data"

    def test_add_repo_relative_path(self, tmp_main_repo, sample_config):
        """Add command works with repo-relative paths (from status output)."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create a nested file structure in the repo (simulating existing tracked file)
        nested_file = repo_dir / "terraform" / "aws" / "main.tf"
        nested_file.parent.mkdir(parents=True)
        nested_file.write_text("# initial content")

        # Commit the initial file
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=repo_dir,
            capture_output=True,
        )

        # Modify the file (simulating user editing a tracked file)
        nested_file.write_text("# modified content")

        # Add using repo-relative path (like from 'repoverlay status' output)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", "terraform/aws/main.tf"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "staged" in result.stdout.lower()

        # Verify file is staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "M  terraform/aws/main.tf" in status_result.stdout

    def test_add_modified_file_in_repo(self, tmp_main_repo, sample_config):
        """Add command stages modified files that exist in repo."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Modify an existing file from the overlay (secrets/db.yaml from fixture)
        secrets_file = repo_dir / "secrets" / "db.yaml"
        secrets_file.write_text("password: modified_secret")

        # Add using repo-relative path
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", "secrets/db.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Verify file is staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "secrets/db.yaml" in status_result.stdout


class TestResetCommand:
    """Tests for reset command."""

    def test_reset_specific_file(self, tmp_main_repo, sample_config):
        """Reset command unstages specific files."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create and stage a new file
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        new_file = repo_dir / "staged.txt"
        new_file.write_text("staged content")

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(new_file)],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Verify file is staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "A  staged.txt" in status_result.stdout

        # Reset the file
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "reset", "staged.txt"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "unstaged" in result.stdout.lower()

        # Verify file is no longer staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "A  staged.txt" not in status_result.stdout
        # File should now be untracked
        assert "?? staged.txt" in status_result.stdout

    def test_reset_all_files(self, tmp_main_repo, sample_config):
        """Reset command without args unstages all files."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create and stage multiple new files
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        file1 = repo_dir / "file1.txt"
        file2 = repo_dir / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(file1), str(file2)],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Reset all
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "reset"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "unstaged" in result.stdout.lower()

        # Verify no files are staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        # Files should be untracked, not staged
        assert "A " not in status_result.stdout
        assert "?? file1.txt" in status_result.stdout
        assert "?? file2.txt" in status_result.stdout

    def test_reset_with_absolute_path_outside_repo(self, tmp_main_repo, sample_config):
        """Reset command handles absolute paths outside repo."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create a file outside repo, add it (which copies it in)
        external_file = tmp_main_repo / "external" / "data.yaml"
        external_file.parent.mkdir(parents=True)
        external_file.write_text("key: value")

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(external_file)],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Verify file is staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "external/data.yaml" in status_result.stdout

        # Reset using the original absolute path (outside repo)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "reset", str(external_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "unstaged" in result.stdout.lower()

        # Verify file is no longer staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "A  external/data.yaml" not in status_result.stdout

    def test_reset_ignores_head_argument(self, tmp_main_repo, sample_config):
        """Reset command ignores HEAD if passed (git muscle memory)."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create and stage a file
        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        new_file = repo_dir / "test.txt"
        new_file.write_text("content")

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(new_file)],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Reset with HEAD argument (like `git reset HEAD file`)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "reset", "HEAD", "test.txt"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Verify file is unstaged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "A  test.txt" not in status_result.stdout

    def test_reset_encrypted_file_by_original_path(self, tmp_main_repo, sample_config):
        """Reset finds .enc file when given original filename."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create and stage an encrypted file directly (simulating what add --encrypt does)
        enc_file = repo_dir / "secrets.yml.enc"
        enc_file.write_text("encrypted: content")

        subprocess.run(
            ["git", "add", "secrets.yml.enc"],
            cwd=repo_dir,
            capture_output=True,
        )

        # Verify file is staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "secrets.yml.enc" in status_result.stdout

        # Reset using original filename (without .enc)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "reset", "secrets.yml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # Verify .enc file is unstaged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "A  secrets.yml.enc" not in status_result.stdout

    def test_reset_repo_relative_path(self, tmp_main_repo, sample_config):
        """Reset command works with repo-relative paths (from status output)."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create a nested file structure and stage it
        nested_file = repo_dir / "terraform" / "aws" / "main.tf"
        nested_file.parent.mkdir(parents=True)
        nested_file.write_text("# terraform config")

        subprocess.run(
            ["git", "add", "terraform/aws/main.tf"],
            cwd=repo_dir,
            capture_output=True,
        )

        # Verify file is staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "terraform/aws/main.tf" in status_result.stdout

        # Reset using repo-relative path (like from status output)
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "reset", "terraform/aws/main.tf"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "unstaged" in result.stdout.lower()

        # Verify file is no longer staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "A  terraform/aws/main.tf" not in status_result.stdout


class TestAddEncryptPatterns:
    """Tests for add command with encrypt_patterns."""

    def test_add_detects_secret_file_by_pattern(self, tmp_main_repo, tmp_overlay_repo):
        """Add command should detect files matching encrypt_patterns."""
        # Create config with encrypt_patterns
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
                "mappings": [],
                "encrypt_patterns": ["**/secrets.yml", "**/secrets.yaml"],
            },
        }
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        # Create a secrets file outside the repo
        secrets_file = tmp_main_repo / "ansible" / "environments" / "all" / "secrets.yml"
        secrets_file.parent.mkdir(parents=True)
        secrets_file.write_text("password: supersecret")

        # Add the file - should auto-detect as needing encryption
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(secrets_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )

        # Check if it detected encryption (will fail without SOPS, but that's OK)
        # The key is whether it TRIED to encrypt
        print("stdout:", result.stdout)
        print("stderr:", result.stderr)

        # If SOPS is not installed, it should error about SOPS not installed
        # If SOPS is installed but no config, it should error about encryption
        # Either way, it should NOT just add as plain text silently
        assert ("SOPS" in result.stderr or
                "encrypt" in result.stderr.lower() or
                "Encrypted" in result.stdout or
                "encrypted" in result.stdout.lower())

    def test_add_symlink_to_decoded_file_stages_enc(self, tmp_path, tmp_overlay_repo):
        """Add on a symlink pointing to .repoverlay/decoded/ should stage the .enc file, not create nested dirs."""
        import json

        # Resolve tmp_path to avoid macOS /var -> /private/var symlink mismatch
        # which masks the bug by making relative_to(root_dir) fail on the resolved path
        tmp_main_repo = (tmp_path / "main-resolved").resolve()
        tmp_main_repo.mkdir()
        subprocess.run(["git", "init"], cwd=tmp_main_repo, check=True, capture_output=True)

        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo.resolve()),
            },
        }
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(config))

        # Clone the overlay
        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"
        decoded_dir = tmp_main_repo / ".repoverlay" / "decoded"

        # Simulate a previously imported encrypted file:
        # 1. Create the .enc file in the repo
        enc_file = repo_dir / "secrets.yaml.enc"
        enc_file.write_text("ENC[AES256,data:encrypted]")
        subprocess.run(["git", "add", "secrets.yaml.enc"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add encrypted file"],
            cwd=repo_dir,
            capture_output=True,
        )

        # 2. Create the decoded file
        decoded_dir.mkdir(parents=True, exist_ok=True)
        decoded_file = decoded_dir / "secrets.yaml"
        decoded_file.write_text("password: original")

        # 3. Create symlink in project root pointing to decoded file
        symlink_path = tmp_main_repo / "secrets.yaml"
        rel_symlink = os.path.relpath(decoded_file, symlink_path.parent)
        symlink_path.symlink_to(rel_symlink)

        # 4. Write state as if import --encrypt had been run
        state_path = tmp_main_repo / ".repoverlay" / "state.json"
        state = {
            "symlinks": ["secrets.yaml"],
            "created_directories": [],
            "encrypted_files": {
                "secrets.yaml.enc": {
                    "decoded_path": "secrets.yaml",
                    "symlink_dst": "secrets.yaml",
                    "last_encrypted_hash": "sha256:fakehash",
                }
            },
        }
        state_path.write_text(json.dumps(state, indent=2))

        # Now modify the decoded file through the symlink
        symlink_path.write_text("password: modified")

        # Modify the .enc file too (simulating what re-encryption would do)
        enc_file.write_text("ENC[AES256,data:re-encrypted]")

        # Run repoverlay add using the absolute path of the symlink.
        # This bypasses the first-pass relative ".enc" check and triggers
        # resolve() to follow the symlink into .repoverlay/decoded/.
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "add", str(symlink_path)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "staged" in result.stdout.lower()

        # Verify: the .enc file should be staged, NOT a file under .repoverlay/
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "secrets.yaml.enc" in status_result.stdout
        # Must NOT have created nested .repoverlay dir inside the repo
        assert ".repoverlay" not in status_result.stdout
        assert not (repo_dir / ".repoverlay").exists()


class TestImport:
    """Tests for import command with absolute and relative paths."""

    def _setup_overlay(self, tmp_main_repo, tmp_overlay_repo):
        """Clone overlay into tmp_main_repo and return repo_dir."""
        config = {
            "version": 1,
            "overlay": {
                "repo": str(tmp_overlay_repo),
            },
        }
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )
        return tmp_main_repo / ".repoverlay" / "repo"

    def test_import_relative_path(self, tmp_main_repo, tmp_overlay_repo):
        """Import with a relative path copies file to overlay and creates symlink."""
        repo_dir = self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        # Create a file in the main repo
        target = tmp_main_repo / "settings.yaml"
        target.write_text("key: value")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", "settings.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "imported" in result.stdout.lower()

        # File should now be a symlink
        assert target.is_symlink()
        # File should exist in overlay repo
        assert (repo_dir / "settings.yaml").exists()
        assert (repo_dir / "settings.yaml").read_text() == "key: value"

    def test_import_absolute_path(self, tmp_main_repo, tmp_overlay_repo):
        """Import with an absolute path copies file to overlay and creates symlink."""
        repo_dir = self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        # Create a file in the main repo
        target = tmp_main_repo / "settings.yaml"
        target.write_text("key: value")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", str(target)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "imported" in result.stdout.lower()

        # File should now be a symlink
        assert target.is_symlink()
        # File should exist in overlay repo
        assert (repo_dir / "settings.yaml").exists()
        assert (repo_dir / "settings.yaml").read_text() == "key: value"

    def test_import_nested_relative_path(self, tmp_main_repo, tmp_overlay_repo):
        """Import with a nested relative path preserves directory structure."""
        repo_dir = self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        # Create a nested file in the main repo
        target = tmp_main_repo / "config" / "app" / "settings.yaml"
        target.parent.mkdir(parents=True)
        target.write_text("nested: true")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", "config/app/settings.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        assert target.is_symlink()
        assert (repo_dir / "config" / "app" / "settings.yaml").exists()
        assert (repo_dir / "config" / "app" / "settings.yaml").read_text() == "nested: true"

    def test_import_nested_absolute_path(self, tmp_main_repo, tmp_overlay_repo):
        """Import with a nested absolute path preserves directory structure."""
        repo_dir = self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        # Create a nested file in the main repo
        target = tmp_main_repo / "config" / "app" / "settings.yaml"
        target.parent.mkdir(parents=True)
        target.write_text("nested: true")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", str(target)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        assert target.is_symlink()
        assert (repo_dir / "config" / "app" / "settings.yaml").exists()
        assert (repo_dir / "config" / "app" / "settings.yaml").read_text() == "nested: true"

    def test_import_dry_run(self, tmp_main_repo, tmp_overlay_repo):
        """Import with --dry-run previews changes without executing."""
        self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        target = tmp_main_repo / "settings.yaml"
        target.write_text("key: value")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", "--dry-run", "settings.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # File should NOT be a symlink
        assert not target.is_symlink()
        assert target.read_text() == "key: value"

    def test_import_file_outside_project_errors(self, tmp_main_repo, tmp_overlay_repo, tmp_path):
        """Import rejects files outside the project root."""
        self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        external_file = tmp_path / "outside" / "file.yaml"
        external_file.parent.mkdir(parents=True)
        external_file.write_text("external: true")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", str(external_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1

    def test_import_already_in_overlay_skips(self, tmp_main_repo, tmp_overlay_repo):
        """Import skips files that already exist in the overlay repo."""
        repo_dir = self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        # .env.production already exists in overlay from fixture
        target = tmp_main_repo / ".env.production"
        # The file is already a symlink from clone
        if target.is_symlink():
            target.unlink()
        target.write_text("API_KEY=yyy")

        # Create the file in overlay repo too (simulating it already being there)
        (repo_dir / ".env.production").write_text("API_KEY=xxx")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", ".env.production"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        # Should warn about skipping (warnings go to stderr), not error
        combined = result.stdout.lower() + result.stderr.lower()
        assert "skip" in combined or "already exists" in combined

    def test_import_tracked_file_removes_from_index(self, tmp_main_repo, tmp_overlay_repo):
        """Import of a git-tracked file removes it from the main repo index."""
        repo_dir = self._setup_overlay(tmp_main_repo, tmp_overlay_repo)

        # Create and track a file in main repo
        target = tmp_main_repo / "tracked.yaml"
        target.write_text("tracked: true")

        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=tmp_main_repo, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=tmp_main_repo, capture_output=True,
        )
        subprocess.run(["git", "add", "tracked.yaml"], cwd=tmp_main_repo, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add tracked"],
            cwd=tmp_main_repo, capture_output=True,
        )

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "import", "tracked.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

        # File should be a symlink now
        assert target.is_symlink()

        # Should be removed from main repo index
        ls_result = subprocess.run(
            ["git", "ls-files", "tracked.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert "tracked.yaml" not in ls_result.stdout


class TestRestore:
    """Tests for restore command with absolute and relative paths."""

    def _setup_overlay_with_staged_file(self, tmp_main_repo, sample_config):
        """Clone overlay and stage a modified file. Returns (repo_dir, file_path)."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create and commit a file
        test_file = repo_dir / "testfile.txt"
        test_file.write_text("original content")
        subprocess.run(["git", "add", "testfile.txt"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add testfile"],
            cwd=repo_dir, capture_output=True,
        )

        # Modify and stage the file
        test_file.write_text("modified content")
        subprocess.run(["git", "add", "testfile.txt"], cwd=repo_dir, capture_output=True)

        return repo_dir, test_file

    def test_restore_staged_relative_path(self, tmp_main_repo, sample_config):
        """Restore --staged with relative path unstages the file."""
        repo_dir, _ = self._setup_overlay_with_staged_file(tmp_main_repo, sample_config)

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "restore", "--staged", "testfile.txt"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "unstaged" in result.stdout.lower()

        # File should no longer be staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        # Should show as modified (unstaged) not staged
        assert "M  testfile.txt" not in status_result.stdout  # not staged
        assert " M testfile.txt" in status_result.stdout  # unstaged modification

    def test_restore_staged_absolute_path(self, tmp_main_repo, sample_config):
        """Restore --staged with absolute path unstages the file."""
        repo_dir, test_file = self._setup_overlay_with_staged_file(tmp_main_repo, sample_config)

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "restore", "--staged", str(test_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "unstaged" in result.stdout.lower()

        # File should no longer be staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "M  testfile.txt" not in status_result.stdout
        assert " M testfile.txt" in status_result.stdout

    def test_restore_unstaged_changes_relative_path(self, tmp_main_repo, sample_config):
        """Restore without --staged discards working tree changes (relative path)."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create and commit a file
        test_file = repo_dir / "testfile.txt"
        test_file.write_text("original content")
        subprocess.run(["git", "add", "testfile.txt"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add testfile"],
            cwd=repo_dir, capture_output=True,
        )

        # Modify but don't stage
        test_file.write_text("modified content")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "restore", "testfile.txt"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "restored" in result.stdout.lower()

        # File should be back to original content
        assert test_file.read_text() == "original content"

    def test_restore_unstaged_changes_absolute_path(self, tmp_main_repo, sample_config):
        """Restore without --staged discards working tree changes (absolute path)."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create and commit a file
        test_file = repo_dir / "testfile.txt"
        test_file.write_text("original content")
        subprocess.run(["git", "add", "testfile.txt"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add testfile"],
            cwd=repo_dir, capture_output=True,
        )

        # Modify but don't stage
        test_file.write_text("modified content")

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "restore", str(test_file)],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
        assert "restored" in result.stdout.lower()

        # File should be back to original content
        assert test_file.read_text() == "original content"

    def test_restore_staged_encrypted_file_by_original_name(self, tmp_main_repo, sample_config):
        """Restore --staged with original filename resolves to .enc file."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create and commit an encrypted file
        enc_file = repo_dir / "secrets.yaml.enc"
        enc_file.write_text("ENC[original]")
        subprocess.run(["git", "add", "secrets.yaml.enc"], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add encrypted"],
            cwd=repo_dir, capture_output=True,
        )

        # Modify and stage
        enc_file.write_text("ENC[modified]")
        subprocess.run(["git", "add", "secrets.yaml.enc"], cwd=repo_dir, capture_output=True)

        # Restore using the name without .enc suffix
        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "restore", "--staged", "secrets.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        # File should no longer be staged
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "M  secrets.yaml.enc" not in status_result.stdout

    def test_restore_nested_relative_path(self, tmp_main_repo, sample_config):
        """Restore --staged with nested relative path."""
        config_path = tmp_main_repo / ".repoverlay.yaml"
        config_path.write_text(yaml.dump(sample_config))

        subprocess.run(
            [sys.executable, "-m", "repoverlay", "clone"],
            cwd=tmp_main_repo,
            capture_output=True,
        )

        repo_dir = tmp_main_repo / ".repoverlay" / "repo"

        # Create nested file
        nested_file = repo_dir / "config" / "app" / "settings.yaml"
        nested_file.parent.mkdir(parents=True)
        nested_file.write_text("original: true")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "add nested"],
            cwd=repo_dir, capture_output=True,
        )

        # Modify and stage
        nested_file.write_text("modified: true")
        subprocess.run(["git", "add", "."], cwd=repo_dir, capture_output=True)

        result = subprocess.run(
            [sys.executable, "-m", "repoverlay", "restore", "--staged", "config/app/settings.yaml"],
            cwd=tmp_main_repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"

        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        assert "M  config/app/settings.yaml" not in status_result.stdout
