"""Tests for state module."""

from repoverlay.state import get_state_path, read_state, write_state


class TestState:
    """Tests for state management."""

    def test_get_state_path(self, tmp_path):
        """State path is correct."""
        result = get_state_path(tmp_path)
        assert result == tmp_path / ".repoverlay" / "state.json"

    def test_write_state(self, tmp_path):
        """Write state file."""
        state = {"symlinks": ["config/secrets", ".env"]}
        write_state(tmp_path, state)

        state_path = get_state_path(tmp_path)
        assert state_path.exists()
        assert "config/secrets" in state_path.read_text()

    def test_read_state(self, tmp_path):
        """Read state file."""
        state = {"symlinks": ["config/secrets", ".env"]}
        write_state(tmp_path, state)

        result = read_state(tmp_path)
        assert result == state

    def test_read_missing_state(self, tmp_path):
        """Missing state file returns empty default."""
        result = read_state(tmp_path)
        assert result == {"symlinks": [], "created_directories": []}

    def test_write_creates_directory(self, tmp_path):
        """Write creates .repoverlay directory if needed."""
        state = {"symlinks": []}
        write_state(tmp_path, state)

        assert (tmp_path / ".repoverlay").is_dir()
