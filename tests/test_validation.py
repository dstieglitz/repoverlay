"""Tests for validation module."""

import pytest

from repoverlay.validation import ValidationError, validate_mappings, validate_path


class TestValidatePath:
    """Tests for validate_path function."""

    def test_valid_path(self):
        """Valid paths pass validation."""
        validate_path("secrets/db.yaml")
        validate_path("config/nested/path")
        validate_path(".env")

    def test_dotdot_rejected(self):
        """Paths with .. are rejected."""
        with pytest.raises(ValidationError, match="cannot contain '..'"):
            validate_path("../secrets")

        with pytest.raises(ValidationError, match="cannot contain '..'"):
            validate_path("config/../secrets")

    def test_dst_absolute_rejected(self):
        """Absolute destination paths are rejected."""
        with pytest.raises(ValidationError, match="must be relative"):
            validate_path("/etc/secrets", is_dst=True)

    def test_dst_git_rejected(self):
        """Destination in .git/ is rejected."""
        with pytest.raises(ValidationError, match="cannot be in .git"):
            validate_path(".git/hooks/pre-commit", is_dst=True)

        with pytest.raises(ValidationError, match="cannot be in .git"):
            validate_path(".git", is_dst=True)

    def test_dst_repoverlay_rejected(self):
        """Destination in .repoverlay is rejected."""
        with pytest.raises(ValidationError, match="Cannot overwrite repoverlay"):
            validate_path(".repoverlay/state.json", is_dst=True)

        with pytest.raises(ValidationError, match="Cannot overwrite repoverlay"):
            validate_path(".repoverlay.yaml", is_dst=True)

        with pytest.raises(ValidationError, match="Cannot overwrite repoverlay"):
            validate_path(".repoverlayignore", is_dst=True)


class TestValidateMappings:
    """Tests for validate_mappings function."""

    def test_valid_mappings(self):
        """Valid mappings pass validation."""
        mappings = [
            {"src": "secrets", "dst": "config/secrets"},
            {"src": ".env", "dst": ".env"},
        ]
        validate_mappings(mappings)  # Should not raise

    def test_duplicate_dst_rejected(self):
        """Duplicate destinations are rejected."""
        mappings = [
            {"src": "a", "dst": "same"},
            {"src": "b", "dst": "same"},
        ]
        with pytest.raises(ValidationError, match="Duplicate destination"):
            validate_mappings(mappings)

    def test_overlapping_paths_rejected(self):
        """Overlapping paths are rejected."""
        mappings = [
            {"src": "config", "dst": "config"},
            {"src": "secrets", "dst": "config/secrets"},
        ]
        with pytest.raises(ValidationError, match="Overlapping paths"):
            validate_mappings(mappings)

    def test_non_overlapping_similar_paths(self):
        """Similar but non-overlapping paths are allowed."""
        mappings = [
            {"src": "config", "dst": "config"},
            {"src": "config2", "dst": "config2"},
        ]
        validate_mappings(mappings)  # Should not raise

    def test_deeply_nested_overlap(self):
        """Deeply nested overlapping paths are rejected."""
        mappings = [
            {"src": "a", "dst": "a/b/c"},
            {"src": "b", "dst": "a/b/c/d/e"},
        ]
        with pytest.raises(ValidationError, match="Overlapping paths"):
            validate_mappings(mappings)
