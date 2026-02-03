"""Tests for git exclude management."""

import pytest

from repoverlay.exclude import (
    BEGIN_MARKER,
    END_MARKER,
    get_exclude_path,
    remove_managed_section,
    update_exclude_file,
)


class TestUpdateExcludeFile:
    """Tests for update_exclude_file function."""

    def test_creates_exclude_file(self, tmp_path):
        """Creates exclude file if it doesn't exist."""
        # Create .git/info directory
        (tmp_path / ".git" / "info").mkdir(parents=True)

        update_exclude_file(tmp_path, [".env", "config/secrets"])

        exclude_path = get_exclude_path(tmp_path)
        assert exclude_path.exists()
        content = exclude_path.read_text()
        assert BEGIN_MARKER in content
        assert END_MARKER in content
        assert ".env" in content
        assert "config/secrets" in content

    def test_preserves_existing_content(self, tmp_path):
        """Preserves existing content outside managed section."""
        (tmp_path / ".git" / "info").mkdir(parents=True)
        exclude_path = get_exclude_path(tmp_path)
        exclude_path.write_text("# My custom excludes\n*.log\n")

        update_exclude_file(tmp_path, [".env"])

        content = exclude_path.read_text()
        assert "# My custom excludes" in content
        assert "*.log" in content
        assert ".env" in content

    def test_updates_existing_managed_section(self, tmp_path):
        """Updates existing managed section."""
        (tmp_path / ".git" / "info").mkdir(parents=True)

        update_exclude_file(tmp_path, [".env"])
        update_exclude_file(tmp_path, [".env", "new-file"])

        content = get_exclude_path(tmp_path).read_text()
        # Should only have one managed section
        assert content.count(BEGIN_MARKER) == 1
        assert "new-file" in content

    def test_includes_repoverlay_files(self, tmp_path):
        """Always includes repoverlay config files."""
        (tmp_path / ".git" / "info").mkdir(parents=True)

        update_exclude_file(tmp_path, [])

        content = get_exclude_path(tmp_path).read_text()
        assert ".repoverlay.yaml" in content
        assert ".repoverlayignore" in content
        assert ".repoverlay/" in content


class TestRemoveManagedSection:
    """Tests for remove_managed_section function."""

    def test_removes_managed_section(self, tmp_path):
        """Removes the managed section."""
        (tmp_path / ".git" / "info").mkdir(parents=True)
        exclude_path = get_exclude_path(tmp_path)

        # Create file with managed section
        content = f"""# Custom
*.log

{BEGIN_MARKER}
.repoverlay/
.env
{END_MARKER}
"""
        exclude_path.write_text(content)

        remove_managed_section(tmp_path)

        new_content = exclude_path.read_text()
        assert BEGIN_MARKER not in new_content
        assert END_MARKER not in new_content
        assert ".repoverlay/" not in new_content
        assert "*.log" in new_content

    def test_handles_missing_file(self, tmp_path):
        """Handles missing exclude file gracefully."""
        (tmp_path / ".git" / "info").mkdir(parents=True)

        # Should not raise
        remove_managed_section(tmp_path)
