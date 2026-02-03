"""Tests for ignore module."""

import pytest

from repoverlay.ignore import (
    filter_mappings,
    load_ignore_patterns,
    should_ignore,
)


class TestLoadIgnorePatterns:
    """Tests for load_ignore_patterns function."""

    def test_load_patterns(self, tmp_path):
        """Loads patterns from file."""
        ignore_file = tmp_path / ".repoverlayignore"
        ignore_file.write_text("*.txt\nsecrets/\n")

        patterns = load_ignore_patterns(tmp_path)
        assert patterns == ["*.txt", "secrets/"]

    def test_skip_comments(self, tmp_path):
        """Skips comment lines."""
        ignore_file = tmp_path / ".repoverlayignore"
        ignore_file.write_text("# This is a comment\n*.txt\n# Another comment\n")

        patterns = load_ignore_patterns(tmp_path)
        assert patterns == ["*.txt"]

    def test_skip_blank_lines(self, tmp_path):
        """Skips blank lines."""
        ignore_file = tmp_path / ".repoverlayignore"
        ignore_file.write_text("*.txt\n\n\nsecrets/\n")

        patterns = load_ignore_patterns(tmp_path)
        assert patterns == ["*.txt", "secrets/"]

    def test_missing_file(self, tmp_path):
        """Returns empty list if file doesn't exist."""
        patterns = load_ignore_patterns(tmp_path)
        assert patterns == []

    def test_empty_file(self, tmp_path):
        """Returns empty list if file is empty."""
        ignore_file = tmp_path / ".repoverlayignore"
        ignore_file.write_text("")

        patterns = load_ignore_patterns(tmp_path)
        assert patterns == []


class TestShouldIgnore:
    """Tests for should_ignore function."""

    def test_simple_glob(self):
        """Matches simple glob patterns."""
        assert should_ignore("README.md", ["README.md"])
        assert should_ignore("test.txt", ["*.txt"])
        assert not should_ignore("test.py", ["*.txt"])

    def test_question_mark(self):
        """Matches ? wildcard."""
        assert should_ignore("test1.txt", ["test?.txt"])
        assert not should_ignore("test12.txt", ["test?.txt"])

    def test_char_class(self):
        """Matches character class [seq]."""
        assert should_ignore("test1.txt", ["test[123].txt"])
        assert not should_ignore("test4.txt", ["test[123].txt"])

    def test_recursive_pattern(self):
        """Matches ** recursive patterns."""
        assert should_ignore("a/b/c/test.txt", ["**/test.txt"])
        assert should_ignore("test.txt", ["**/test.txt"])

    def test_nested_pattern(self):
        """Matches nested directory patterns."""
        assert should_ignore("a/test/b.txt", ["**/test/**"])
        assert not should_ignore("a/testing/b.txt", ["**/test/**"])

    def test_filename_match(self):
        """Matches filename regardless of path."""
        assert should_ignore("path/to/README.md", ["README.md"])
        assert should_ignore("deep/nested/path/README.md", ["README.md"])


class TestFilterMappings:
    """Tests for filter_mappings function."""

    def test_filter_by_pattern(self):
        """Filters mappings based on patterns."""
        mappings = [
            {"src": "secrets/db.yaml", "dst": "config/db.yaml"},
            {"src": "README.md", "dst": "README.md"},
            {"src": ".env", "dst": ".env"},
        ]
        patterns = ["README.md"]

        result = filter_mappings(mappings, patterns)

        assert len(result) == 2
        assert result[0]["src"] == "secrets/db.yaml"
        assert result[1]["src"] == ".env"

    def test_no_patterns(self):
        """Returns all mappings if no patterns."""
        mappings = [
            {"src": "a", "dst": "a"},
            {"src": "b", "dst": "b"},
        ]

        result = filter_mappings(mappings, [])
        assert result == mappings

    def test_all_filtered(self):
        """Returns empty list if all filtered."""
        mappings = [
            {"src": "README.md", "dst": "README.md"},
        ]
        patterns = ["*.md"]

        result = filter_mappings(mappings, patterns)
        assert result == []
