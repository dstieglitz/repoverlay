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
