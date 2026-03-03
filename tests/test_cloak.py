"""Tests for cloak and decloak commands."""

import os
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from repoverlay import sops
from repoverlay.output import Output
from repoverlay.overlay import (
    OverlayError,
    cloak_overlay,
    decloak_overlay,
    get_decoded_dir,
    get_repo_dir,
)
from repoverlay.state import read_state, write_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path):
    """Set up a standard test environment with one encrypted file, already decloaked.

    Layout:
        root_dir/
            .repoverlay/
                repo/
                    secrets.yaml.enc   <- encrypted file
                decoded/
                    secrets.yaml       <- decrypted file
            secrets.yaml               <- symlink -> .repoverlay/decoded/secrets.yaml

    State: encrypted_files entry with cloaked=False (or absent).
    """
    root_dir = tmp_path / "main"
    root_dir.mkdir()
    overlay_dir = root_dir / ".repoverlay"
    overlay_dir.mkdir()
    repo_dir = overlay_dir / "repo"
    repo_dir.mkdir()
    decoded_dir = overlay_dir / "decoded"
    decoded_dir.mkdir()

    enc_file = repo_dir / "secrets.yaml.enc"
    enc_file.write_text("SOPS-encrypted content")

    dec_file = decoded_dir / "secrets.yaml"
    dec_file.write_text("plaintext content")

    # Symlink: root_dir/secrets.yaml -> .repoverlay/decoded/secrets.yaml
    symlink_path = root_dir / "secrets.yaml"
    rel_target = os.path.relpath(dec_file, symlink_path.parent)
    symlink_path.symlink_to(rel_target)

    enc_hash = sops.file_hash(enc_file)
    dec_hash = sops.file_hash(dec_file)

    write_state(root_dir, {
        "symlinks": ["secrets.yaml"],
        "created_directories": [],
        "encrypted_files": {
            "secrets.yaml.enc": {
                "decoded_path": "secrets.yaml",
                "symlink_dst": "secrets.yaml",
                "last_encrypted_hash": enc_hash,
                "last_decoded_hash": dec_hash,
                "cloaked": False,
            }
        },
    })

    return {
        "root_dir": root_dir,
        "repo_dir": repo_dir,
        "decoded_dir": decoded_dir,
        "enc_file": enc_file,
        "dec_file": dec_file,
        "symlink_path": symlink_path,
    }


@pytest.fixture()
def env_cloaked(env):
    """Same as `env` but with the repo already in cloaked state.

    Symlink: root_dir/secrets.yaml -> .repoverlay/repo/secrets.yaml.enc
    No decoded file present.
    State: cloaked=True.
    """
    root_dir = env["root_dir"]
    repo_dir = env["repo_dir"]
    enc_file = env["enc_file"]
    symlink_path = env["symlink_path"]
    dec_file = env["dec_file"]

    # Remove decoded file
    dec_file.unlink()

    # Repoint symlink to encrypted file
    symlink_path.unlink()
    rel_target = os.path.relpath(enc_file, symlink_path.parent)
    symlink_path.symlink_to(rel_target)

    # Update state
    state = read_state(root_dir)
    state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] = True
    write_state(root_dir, state)

    env["dec_file"] = None  # no longer present
    return env


def _make_output():
    stream = StringIO()
    err_stream = StringIO()
    return Output(no_color=True, stream=stream, err_stream=err_stream), stream, err_stream


# ---------------------------------------------------------------------------
# cloak_overlay tests
# ---------------------------------------------------------------------------


class TestCloakOverlay:

    def test_cloak_removes_decoded_file(self, env):
        """Cloaking removes the decrypted file from decoded dir."""
        output, _, _ = _make_output()
        cloak_overlay(env["root_dir"], output=output)
        assert not env["dec_file"].exists()

    def test_cloak_symlink_points_to_encrypted_file(self, env):
        """After cloaking, symlink points to the .enc file in repo/."""
        output, _, _ = _make_output()
        cloak_overlay(env["root_dir"], output=output)

        symlink_path = env["symlink_path"]
        assert symlink_path.is_symlink()
        target = Path(os.readlink(symlink_path))
        # Resolve relative symlink
        resolved = (symlink_path.parent / target).resolve()
        assert resolved == env["enc_file"].resolve()

    def test_cloak_symlink_name_has_no_enc_suffix(self, env):
        """The symlink name itself does not have the .enc suffix."""
        output, _, _ = _make_output()
        cloak_overlay(env["root_dir"], output=output)
        assert env["symlink_path"].name == "secrets.yaml"  # no .enc

    def test_cloak_updates_state_cloaked_flag(self, env):
        """State is updated to mark files as cloaked."""
        output, _, _ = _make_output()
        cloak_overlay(env["root_dir"], output=output)

        state = read_state(env["root_dir"])
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is True

    def test_cloak_is_idempotent(self, env_cloaked):
        """Cloaking an already-cloaked repo is a no-op."""
        output, stdout, _ = _make_output()
        cloak_overlay(env_cloaked["root_dir"], output=output)
        assert "already cloaked" in stdout.getvalue()

    def test_cloak_no_encrypted_files(self, tmp_path):
        """Cloaking with no tracked encrypted files is safe."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        (root_dir / ".repoverlay" / "repo").mkdir(parents=True)
        write_state(root_dir, {"symlinks": [], "created_directories": [], "encrypted_files": {}})

        output, stdout, _ = _make_output()
        cloak_overlay(root_dir, output=output)
        assert "nothing to cloak" in stdout.getvalue().lower()

    def test_cloak_raises_if_repo_not_cloned(self, tmp_path):
        """Raises OverlayError if overlay repo doesn't exist."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        (root_dir / ".repoverlay").mkdir()

        output, _, _ = _make_output()
        with pytest.raises(OverlayError, match="not cloned"):
            cloak_overlay(root_dir, output=output)

    def test_cloak_warns_if_encrypted_file_missing(self, env):
        """Warns (does not raise) when the .enc file is missing from repo."""
        env["enc_file"].unlink()
        output, _, err = _make_output()
        cloak_overlay(env["root_dir"], output=output)
        assert "not found" in err.getvalue()

    def test_cloak_dry_run_makes_no_changes(self, env):
        """Dry-run shows what would happen without changing anything."""
        output, stdout, _ = _make_output()
        cloak_overlay(env["root_dir"], dry_run=True, output=output)

        # Files unchanged
        assert env["dec_file"].exists()
        symlink_target = Path(os.readlink(env["symlink_path"]))
        resolved = (env["symlink_path"].parent / symlink_target).resolve()
        assert resolved == env["dec_file"].resolve()  # still points to decoded

        # Output mentions dry-run
        assert "[dry-run]" in stdout.getvalue()
        assert "secrets.yaml" in stdout.getvalue()

        # State unchanged
        state = read_state(env["root_dir"])
        assert not state["encrypted_files"]["secrets.yaml.enc"].get("cloaked", False)

    def test_cloak_aborts_if_decoded_files_have_changes(self, env):
        """Cloaking aborts when decoded files have been modified since last decrypt."""
        # Modify the decoded file to simulate user edits
        dec_file = env["decoded_dir"] / "secrets.yaml"
        dec_file.write_text("modified plaintext content")

        output, _, err = _make_output()
        with pytest.raises(OverlayError, match="Uncommitted changes"):
            cloak_overlay(env["root_dir"], output=output)

        # Decoded file should still exist (not deleted)
        assert dec_file.exists()
        # Symlink should still point to decoded file (unchanged)
        symlink_path = env["symlink_path"]
        resolved = (symlink_path.parent / Path(os.readlink(symlink_path))).resolve()
        assert resolved == dec_file.resolve()
        # State should still show uncloaked
        state = read_state(env["root_dir"])
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is False
        # Error message should mention the file
        assert "secrets.yaml" in err.getvalue()

    def test_cloak_succeeds_when_decoded_files_unchanged(self, env):
        """Cloaking succeeds when decoded files have NOT been modified."""
        output, _, _ = _make_output()
        # env fixture writes matching hashes, so no changes detected
        cloak_overlay(env["root_dir"], output=output)
        assert not env["dec_file"].exists()

    def test_cloak_multiple_files(self, tmp_path):
        """Cloaks multiple encrypted files in one pass."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        overlay = root_dir / ".repoverlay"
        overlay.mkdir()
        repo_dir = overlay / "repo"
        repo_dir.mkdir()
        decoded_dir = overlay / "decoded"
        decoded_dir.mkdir()

        # Two encrypted files
        for name in ("alpha.yaml", "beta.yaml"):
            enc = repo_dir / f"{name}.enc"
            enc.write_text("encrypted")
            dec = decoded_dir / name
            dec.write_text("plain")
            link = root_dir / name
            link.symlink_to(os.path.relpath(dec, link.parent))

        write_state(root_dir, {
            "symlinks": ["alpha.yaml", "beta.yaml"],
            "created_directories": [],
            "encrypted_files": {
                "alpha.yaml.enc": {
                    "decoded_path": "alpha.yaml",
                    "symlink_dst": "alpha.yaml",
                    "last_encrypted_hash": sops.file_hash(repo_dir / "alpha.yaml.enc"),
                    "last_decoded_hash": sops.file_hash(decoded_dir / "alpha.yaml"),
                    "cloaked": False,
                },
                "beta.yaml.enc": {
                    "decoded_path": "beta.yaml",
                    "symlink_dst": "beta.yaml",
                    "last_encrypted_hash": sops.file_hash(repo_dir / "beta.yaml.enc"),
                    "last_decoded_hash": sops.file_hash(decoded_dir / "beta.yaml"),
                    "cloaked": False,
                },
            },
        })

        output, stdout, _ = _make_output()
        cloak_overlay(root_dir, output=output)

        assert "Cloaked 2 file(s)" in stdout.getvalue()
        state = read_state(root_dir)
        for key in ("alpha.yaml.enc", "beta.yaml.enc"):
            assert state["encrypted_files"][key]["cloaked"] is True
        assert not (decoded_dir / "alpha.yaml").exists()
        assert not (decoded_dir / "beta.yaml").exists()


# ---------------------------------------------------------------------------
# decloak_overlay tests
# ---------------------------------------------------------------------------


class TestDecloakOverlay:

    def _config(self, repo_dir):
        return {"version": 1, "overlay": {"repo": str(repo_dir)}}

    def _mock_decrypt(self, plaintext="decrypted content"):
        """Return a side_effect that writes a file when decrypt_file is called."""
        def _side_effect(src, dst, sops_config=None):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(plaintext)
        return _side_effect

    def test_decloak_creates_decoded_file(self, env_cloaked):
        """Decloaking creates the decrypted file in decoded/."""
        root_dir = env_cloaked["root_dir"]
        decoded_dir = env_cloaked["decoded_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=self._mock_decrypt()):
            with patch.object(sops, "file_hash", return_value="sha256:new"):
                decloak_overlay(root_dir, config, output=output)

        assert (decoded_dir / "secrets.yaml").exists()

    def test_decloak_symlink_points_to_decoded_file(self, env_cloaked):
        """After decloaking, symlink points to the decoded file."""
        root_dir = env_cloaked["root_dir"]
        decoded_dir = env_cloaked["decoded_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=self._mock_decrypt()):
            with patch.object(sops, "file_hash", return_value="sha256:new"):
                decloak_overlay(root_dir, config, output=output)

        symlink_path = env_cloaked["symlink_path"]
        assert symlink_path.is_symlink()
        resolved = (symlink_path.parent / Path(os.readlink(symlink_path))).resolve()
        assert resolved == (decoded_dir / "secrets.yaml").resolve()

    def test_decloak_updates_state_cloaked_flag(self, env_cloaked):
        """State cloaked flag is set to False after decloaking."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=self._mock_decrypt()):
            with patch.object(sops, "file_hash", return_value="sha256:new"):
                decloak_overlay(root_dir, config, output=output)

        state = read_state(root_dir)
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is False

    def test_decloak_updates_hashes_in_state(self, env_cloaked):
        """State hashes are refreshed after decloaking."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=self._mock_decrypt()):
            with patch.object(sops, "file_hash", return_value="sha256:refreshed"):
                decloak_overlay(root_dir, config, output=output)

        state = read_state(root_dir)
        meta = state["encrypted_files"]["secrets.yaml.enc"]
        assert meta["last_encrypted_hash"] == "sha256:refreshed"
        assert meta["last_decoded_hash"] == "sha256:refreshed"

    def test_decloak_is_idempotent(self, env):
        """Decloaking an already-decloaked repo is a no-op."""
        root_dir = env["root_dir"]
        config = self._config(env["repo_dir"])

        output, stdout, _ = _make_output()
        with patch.object(sops, "decrypt_file") as mock_decrypt:
            decloak_overlay(root_dir, config, output=output)
            mock_decrypt.assert_not_called()

        assert "already decloaked" in stdout.getvalue()

    def test_decloak_specific_file_by_decoded_path(self, tmp_path):
        """Decloak only one file when a specific decoded path is given."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        overlay = root_dir / ".repoverlay"
        overlay.mkdir()
        repo_dir = overlay / "repo"
        repo_dir.mkdir()
        decoded_dir = overlay / "decoded"
        decoded_dir.mkdir()

        for name in ("alpha.yaml", "beta.yaml"):
            enc = repo_dir / f"{name}.enc"
            enc.write_text("encrypted")
            link = root_dir / name
            link.symlink_to(os.path.relpath(enc, link.parent))

        write_state(root_dir, {
            "symlinks": ["alpha.yaml", "beta.yaml"],
            "created_directories": [],
            "encrypted_files": {
                "alpha.yaml.enc": {
                    "decoded_path": "alpha.yaml",
                    "symlink_dst": "alpha.yaml",
                    "last_encrypted_hash": sops.file_hash(repo_dir / "alpha.yaml.enc"),
                    "cloaked": True,
                },
                "beta.yaml.enc": {
                    "decoded_path": "beta.yaml",
                    "symlink_dst": "beta.yaml",
                    "last_encrypted_hash": sops.file_hash(repo_dir / "beta.yaml.enc"),
                    "cloaked": True,
                },
            },
        })

        config = {"version": 1, "overlay": {"repo": str(repo_dir)}}
        output, stdout, _ = _make_output()

        def _side_effect(src, dst, sops_config=None):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("decrypted")

        with patch.object(sops, "decrypt_file", side_effect=_side_effect):
            with patch.object(sops, "file_hash", return_value="sha256:x"):
                decloak_overlay(root_dir, config, file="alpha.yaml", output=output)

        state = read_state(root_dir)
        assert state["encrypted_files"]["alpha.yaml.enc"]["cloaked"] is False
        assert state["encrypted_files"]["beta.yaml.enc"]["cloaked"] is True

        # Only alpha symlink was relinked
        assert (decoded_dir / "alpha.yaml").exists()
        assert not (decoded_dir / "beta.yaml").exists()

    def test_decloak_specific_file_by_encrypted_path(self, env_cloaked):
        """Decloak accepts the encrypted path (e.g. secrets.yaml.enc) as file arg."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, stdout, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=self._mock_decrypt()):
            with patch.object(sops, "file_hash", return_value="sha256:x"):
                decloak_overlay(root_dir, config, file="secrets.yaml.enc", output=output)

        state = read_state(root_dir)
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is False

    def test_decloak_raises_for_unknown_file(self, env_cloaked):
        """Raises OverlayError when the specified file is not tracked."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with pytest.raises(OverlayError, match="not found"):
            decloak_overlay(root_dir, config, file="nonexistent.yaml", output=output)

    def test_decloak_raises_on_sops_not_available(self, env_cloaked):
        """Raises OverlayError when SOPS is not installed."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=sops.SopsNotAvailableError("no sops")):
            with pytest.raises(OverlayError, match="no sops"):
                decloak_overlay(root_dir, config, output=output)

    def test_decloak_raises_on_decryption_error(self, env_cloaked):
        """Raises OverlayError when decryption fails."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=sops.SopsDecryptionError("bad key")):
            with pytest.raises(OverlayError, match="bad key"):
                decloak_overlay(root_dir, config, output=output)

    def test_decloak_no_encrypted_files(self, tmp_path):
        """Decloaking with no tracked encrypted files is safe."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        (root_dir / ".repoverlay" / "repo").mkdir(parents=True)
        write_state(root_dir, {"symlinks": [], "created_directories": [], "encrypted_files": {}})

        config = {"version": 1, "overlay": {"repo": str(root_dir / ".repoverlay" / "repo")}}
        output, stdout, _ = _make_output()
        decloak_overlay(root_dir, config, output=output)
        assert "nothing to decloak" in stdout.getvalue().lower()

    def test_decloak_raises_if_repo_not_cloned(self, tmp_path):
        """Raises OverlayError if overlay repo doesn't exist."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        (root_dir / ".repoverlay").mkdir()
        config = {"version": 1, "overlay": {"repo": "git@github.com:org/repo.git"}}

        output, _, _ = _make_output()
        with pytest.raises(OverlayError, match="not cloned"):
            decloak_overlay(root_dir, config, output=output)

    def test_decloak_dry_run_makes_no_changes(self, env_cloaked):
        """Dry-run shows what would happen without making any changes."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])
        symlink_path = env_cloaked["symlink_path"]
        enc_file = env_cloaked["enc_file"]

        output, stdout, _ = _make_output()
        with patch.object(sops, "decrypt_file") as mock_decrypt:
            decloak_overlay(root_dir, config, dry_run=True, output=output)
            mock_decrypt.assert_not_called()

        # Symlink still points to encrypted file
        resolved = (symlink_path.parent / Path(os.readlink(symlink_path))).resolve()
        assert resolved == enc_file.resolve()

        # State unchanged
        state = read_state(root_dir)
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is True

        # Output mentions dry-run
        assert "[dry-run]" in stdout.getvalue()


# ---------------------------------------------------------------------------
# Round-trip tests: cloak then decloak
# ---------------------------------------------------------------------------


class TestCloakDecloakRoundTrip:

    def _config(self, repo_dir):
        return {"version": 1, "overlay": {"repo": str(repo_dir)}}

    def test_cloak_then_decloak_restores_symlink(self, env):
        """Cloaking then decloaking leaves the project in its original state."""
        root_dir = env["root_dir"]
        repo_dir = env["repo_dir"]
        decoded_dir = env["decoded_dir"]
        symlink_path = env["symlink_path"]
        dec_file = env["dec_file"]
        config = self._config(repo_dir)

        original_content = dec_file.read_text()

        # Cloak
        output, _, _ = _make_output()
        cloak_overlay(root_dir, output=output)

        assert not dec_file.exists()
        assert symlink_path.is_symlink()

        # Decloak
        output2, _, _ = _make_output()

        def _side_effect(src, dst, sops_config=None):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(original_content)

        with patch.object(sops, "decrypt_file", side_effect=_side_effect):
            with patch.object(sops, "file_hash", return_value="sha256:restored"):
                decloak_overlay(root_dir, config, output=output2)

        assert dec_file.exists()
        assert dec_file.read_text() == original_content
        resolved = (symlink_path.parent / Path(os.readlink(symlink_path))).resolve()
        assert resolved == dec_file.resolve()

        state = read_state(root_dir)
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is False

    def test_double_cloak_is_safe(self, env):
        """Cloaking twice does not corrupt state."""
        root_dir = env["root_dir"]
        output, _, _ = _make_output()

        cloak_overlay(root_dir, output=output)
        cloak_overlay(root_dir, output=output)

        state = read_state(root_dir)
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is True

    def test_double_decloak_is_safe(self, env_cloaked):
        """Decloaking twice does not corrupt state."""
        root_dir = env_cloaked["root_dir"]
        config = self._config(env_cloaked["repo_dir"])

        def _side_effect(src, dst, sops_config=None):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text("plain")

        output, _, _ = _make_output()
        with patch.object(sops, "decrypt_file", side_effect=_side_effect):
            with patch.object(sops, "file_hash", return_value="sha256:x"):
                decloak_overlay(root_dir, config, output=output)
                decloak_overlay(root_dir, config, output=output)

        state = read_state(root_dir)
        assert state["encrypted_files"]["secrets.yaml.enc"]["cloaked"] is False


# ---------------------------------------------------------------------------
# CLI integration tests
# ---------------------------------------------------------------------------


class TestCloakDecloakCLI:

    def _run_cmd(self, argv, root_dir):
        """Run the CLI with the given argv list, returning exit code and captured output."""
        import sys
        from io import StringIO
        from repoverlay.cli import main
        from repoverlay.config import find_config

        stream = StringIO()
        err_stream = StringIO()

        old_argv = sys.argv
        try:
            sys.argv = ["repoverlay"] + argv
            with patch("repoverlay.cli.find_config") as mock_find:
                mock_find.return_value = root_dir / ".repoverlay.yaml"
                (root_dir / ".repoverlay.yaml").write_text(
                    "version: 1\noverlay:\n  repo: git@github.com:org/repo.git\n"
                )
                from repoverlay.config import load_config
                with patch("repoverlay.cli.load_config") as mock_load:
                    mock_load.return_value = {
                        "version": 1,
                        "overlay": {"repo": str(root_dir / ".repoverlay" / "repo")},
                    }
                    from repoverlay.output import Output, set_output
                    output = Output(no_color=True, stream=stream, err_stream=err_stream)
                    set_output(output)
                    with patch("repoverlay.cli.Output", return_value=output):
                        exit_code = main()
        finally:
            sys.argv = old_argv

        return exit_code, stream.getvalue(), err_stream.getvalue()

    def test_cloak_command_exits_zero(self, env):
        """'repoverlay cloak' exits 0 on success."""
        root_dir = env["root_dir"]
        exit_code, stdout, _ = self._run_cmd(["cloak"], root_dir)
        assert exit_code == 0

    def test_decloak_command_exits_zero(self, env_cloaked):
        """'repoverlay decloak' exits 0 on success."""
        root_dir = env_cloaked["root_dir"]
        with patch.object(sops, "decrypt_file") as mock_decrypt:
            def _side_effect(src, dst, sops_config=None):
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text("plain")
            mock_decrypt.side_effect = _side_effect
            with patch.object(sops, "file_hash", return_value="sha256:x"):
                exit_code, stdout, _ = self._run_cmd(["decloak"], root_dir)
        assert exit_code == 0

    def test_cloak_dry_run_flag(self, env):
        """'repoverlay cloak --dry-run' shows dry-run output without changes."""
        root_dir = env["root_dir"]
        exit_code, stdout, _ = self._run_cmd(["cloak", "--dry-run"], root_dir)
        assert exit_code == 0
        assert "[dry-run]" in stdout
        assert env["dec_file"].exists()  # unchanged

    def test_decloak_dry_run_flag(self, env_cloaked):
        """'repoverlay decloak --dry-run' shows dry-run output without changes."""
        root_dir = env_cloaked["root_dir"]
        with patch.object(sops, "decrypt_file") as mock_decrypt:
            exit_code, stdout, _ = self._run_cmd(["decloak", "--dry-run"], root_dir)
            mock_decrypt.assert_not_called()
        assert exit_code == 0
        assert "[dry-run]" in stdout

    def test_cloak_exits_one_on_error(self, tmp_path):
        """'repoverlay cloak' exits 1 when overlay is not cloned."""
        root_dir = tmp_path / "main"
        root_dir.mkdir()
        (root_dir / ".repoverlay").mkdir()  # overlay dir exists but no repo/ inside
        write_state(root_dir, {
            "symlinks": [],
            "created_directories": [],
            "encrypted_files": {"bad.enc": {"decoded_path": "bad", "symlink_dst": "bad", "cloaked": False}},
        })
        exit_code, _, _ = self._run_cmd(["cloak"], root_dir)
        assert exit_code == 1
