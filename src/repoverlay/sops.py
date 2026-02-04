"""SOPS encryption/decryption operations for repoverlay."""

import hashlib
import shutil
import subprocess
from pathlib import Path
from typing import Any


class SopsError(Exception):
    """Raised when SOPS operations fail."""
    pass


class SopsNotAvailableError(SopsError):
    """Raised when SOPS CLI is not installed."""
    pass


class SopsDecryptionError(SopsError):
    """Raised when decryption fails."""
    pass


class SopsEncryptionError(SopsError):
    """Raised when encryption fails."""
    pass


# File extensions that indicate SOPS-encrypted files
ENCRYPTED_EXTENSIONS = (".enc", ".encoded", ".encrypted")

# Default SOPS config location in overlay repo
DEFAULT_SOPS_CONFIG_PATH = ".config/.sops.yaml"


def is_sops_available() -> bool:
    """Check if SOPS CLI is installed and available.

    Returns:
        True if SOPS is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["sops", "--version"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def is_encrypted_file(path: str | Path) -> bool:
    """Check if a file is SOPS-encrypted based on its extension.

    Args:
        path: Path to check (can be string or Path)

    Returns:
        True if file has .enc or .encoded suffix
    """
    path_str = str(path)
    return any(path_str.endswith(ext) for ext in ENCRYPTED_EXTENSIONS)


def get_decoded_path(encrypted_path: str | Path) -> str:
    """Get the decoded filename by stripping encryption suffix.

    Args:
        encrypted_path: Path to encrypted file

    Returns:
        Path string with encryption suffix removed

    Example:
        get_decoded_path("config.yaml.enc") -> "config.yaml"
    """
    path_str = str(encrypted_path)
    for ext in ENCRYPTED_EXTENSIONS:
        if path_str.endswith(ext):
            return path_str[:-len(ext)]
    return path_str


def get_sops_config_path(repo_dir: Path, config: dict[str, Any] | None = None) -> Path | None:
    """Find the SOPS config file (.sops.yaml) in the overlay repo.

    Args:
        repo_dir: Path to the overlay repository
        config: Optional repoverlay config dict with sops_config key

    Returns:
        Path to .sops.yaml if found, None otherwise
    """
    # Check config for custom path
    if config and "overlay" in config:
        custom_path = config["overlay"].get("sops_config")
        if custom_path:
            sops_path = repo_dir / custom_path
            if sops_path.exists():
                return sops_path

    # Try default location
    default_path = repo_dir / DEFAULT_SOPS_CONFIG_PATH
    if default_path.exists():
        return default_path

    # Try root .sops.yaml
    root_path = repo_dir / ".sops.yaml"
    if root_path.exists():
        return root_path

    return None


def _detect_input_type(path: Path) -> str | None:
    """Detect the input type for SOPS based on filename.

    SOPS needs --input-type when the file extension doesn't indicate the format.
    For example, 'config.yaml.enc' needs --input-type yaml.

    Args:
        path: Path to the encrypted file

    Returns:
        Input type string ('yaml', 'json', etc.) or None if not detected
    """
    # Get the filename without the encryption suffix
    name = str(path)
    for ext in ENCRYPTED_EXTENSIONS:
        if name.endswith(ext):
            name = name[:-len(ext)]
            break

    # Check for known file types
    name_lower = name.lower()
    if name_lower.endswith(('.yaml', '.yml')):
        return 'yaml'
    elif name_lower.endswith('.json'):
        return 'json'
    elif name_lower.endswith('.env'):
        return 'dotenv'
    elif name_lower.endswith('.ini'):
        return 'ini'

    return None


def decrypt_file(
    src: Path,
    dst: Path,
    sops_config: Path | None = None,
) -> None:
    """Decrypt a single SOPS-encrypted file.

    Args:
        src: Path to encrypted source file
        dst: Path to write decrypted output
        sops_config: Optional path to .sops.yaml

    Raises:
        SopsNotAvailableError: If SOPS CLI is not installed
        SopsDecryptionError: If decryption fails
    """
    if not is_sops_available():
        raise SopsNotAvailableError(
            "SOPS is not installed. Install it with:\n"
            "  brew install sops      # macOS\n"
            "  apt install sops       # Debian/Ubuntu\n"
            "  choco install sops     # Windows"
        )

    # Build command
    cmd = ["sops", "--decrypt"]
    if sops_config:
        cmd.extend(["--config", str(sops_config)])

    # Detect input type from filename (e.g., config.yaml.enc -> yaml)
    input_type = _detect_input_type(src)
    if input_type:
        cmd.extend(["--input-type", input_type])
        cmd.extend(["--output-type", input_type])

    cmd.extend(["--output", str(dst), str(src)])

    # Ensure parent directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip()
        hint = "\nHint: Are you using the correct credentials/profile?"
        raise SopsDecryptionError(f"Failed to decrypt {src}:\n{error_msg}{hint}")


def encrypt_file(
    src: Path,
    dst: Path,
    sops_config: Path | None = None,
) -> None:
    """Encrypt a single file with SOPS.

    Args:
        src: Path to plaintext source file
        dst: Path to write encrypted output
        sops_config: Optional path to .sops.yaml

    Raises:
        SopsNotAvailableError: If SOPS CLI is not installed
        SopsEncryptionError: If encryption fails
    """
    if not is_sops_available():
        raise SopsNotAvailableError(
            "SOPS is not installed. Install it with:\n"
            "  brew install sops      # macOS\n"
            "  apt install sops       # Debian/Ubuntu\n"
            "  choco install sops     # Windows"
        )

    # Build command
    cmd = ["sops", "--encrypt"]
    if sops_config:
        cmd.extend(["--config", str(sops_config)])
    cmd.extend(["--output", str(dst), str(src)])

    # Ensure parent directory exists
    dst.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        error_msg = result.stderr.strip()
        if "no matching creation rules" in error_msg.lower():
            raise SopsEncryptionError(
                f"Cannot encrypt {src}: no matching creation rules in .sops.yaml.\n"
                "Ensure your .sops.yaml has rules that match this file path."
            )
        raise SopsEncryptionError(f"Failed to encrypt {src}: {error_msg}")


def file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to file

    Returns:
        Hash string in format "sha256:hexdigest"
    """
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"


def scan_encrypted_files(repo_dir: Path) -> list[Path]:
    """Scan repository for SOPS-encrypted files.

    Args:
        repo_dir: Path to the overlay repository

    Returns:
        List of paths to encrypted files (relative to repo_dir)
    """
    encrypted_files = []
    for path in repo_dir.rglob("*"):
        if path.is_file() and is_encrypted_file(path):
            # Skip .git directory
            try:
                rel_path = path.relative_to(repo_dir)
                if rel_path.parts[0] != ".git":
                    encrypted_files.append(rel_path)
            except ValueError:
                pass
    return encrypted_files


def decrypt_all_files(
    repo_dir: Path,
    decoded_dir: Path,
    sops_config: Path | None = None,
) -> dict[str, dict[str, str]]:
    """Decrypt all encrypted files from repo to decoded directory.

    Args:
        repo_dir: Path to the overlay repository
        decoded_dir: Path to directory for decrypted files
        sops_config: Optional path to .sops.yaml

    Returns:
        Dict mapping encrypted paths to their metadata:
        {
            "file.enc": {
                "decoded_path": "file",
                "last_encrypted_hash": "sha256:..."
            }
        }

    Raises:
        SopsError: If any decryption fails (rolls back on error)
    """
    encrypted_files = scan_encrypted_files(repo_dir)

    if not encrypted_files:
        return {}

    # Verify SOPS is available before starting
    if not is_sops_available():
        raise SopsNotAvailableError(
            "SOPS is not installed. Install it with:\n"
            "  brew install sops      # macOS\n"
            "  apt install sops       # Debian/Ubuntu\n"
            "  choco install sops     # Windows"
        )

    result: dict[str, dict[str, str]] = {}
    decrypted_files: list[Path] = []  # Track for rollback

    try:
        for enc_path in encrypted_files:
            src = repo_dir / enc_path
            decoded_name = get_decoded_path(str(enc_path))
            dst = decoded_dir / decoded_name

            decrypt_file(src, dst, sops_config)
            decrypted_files.append(dst)

            result[str(enc_path)] = {
                "decoded_path": decoded_name,
                "last_encrypted_hash": file_hash(src),
            }

    except SopsError:
        # Rollback: remove already decrypted files
        for f in decrypted_files:
            if f.exists():
                f.unlink()
        raise

    return result


def detect_decoded_changes(
    decoded_dir: Path,
    repo_dir: Path,
    encrypted_state: dict[str, dict[str, str]],
    sops_config: Path | None = None,
) -> list[str]:
    """Detect which decoded files have been modified.

    Compares decoded files against what would be produced by re-decrypting
    the encrypted source.

    Args:
        decoded_dir: Path to decoded files directory
        repo_dir: Path to the overlay repository
        encrypted_state: State dict from encrypted_files
        sops_config: Optional path to .sops.yaml

    Returns:
        List of encrypted file paths (str) whose decoded versions changed
    """
    changed = []

    for enc_path_str, metadata in encrypted_state.items():
        decoded_path_str = metadata["decoded_path"]
        decoded_file = decoded_dir / decoded_path_str

        if not decoded_file.exists():
            # Decoded file was deleted - consider as changed
            changed.append(enc_path_str)
            continue

        # Get current decoded content
        current_content = decoded_file.read_bytes()

        # Decrypt encrypted source to temp location and compare
        enc_src = repo_dir / enc_path_str
        if not enc_src.exists():
            continue

        # Decrypt to memory via stdout
        cmd = ["sops", "--decrypt"]
        if sops_config:
            cmd.extend(["--config", str(sops_config)])
        cmd.append(str(enc_src))

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            original_content = result.stdout
            if current_content != original_content:
                changed.append(enc_path_str)

    return changed


def re_encrypt_changed_files(
    decoded_dir: Path,
    repo_dir: Path,
    changed_files: list[str],
    encrypted_state: dict[str, dict[str, str]],
    sops_config: Path | None = None,
) -> list[str]:
    """Re-encrypt modified decoded files back to the repo.

    Args:
        decoded_dir: Path to decoded files directory
        repo_dir: Path to the overlay repository
        changed_files: List of encrypted file paths that changed
        encrypted_state: State dict from encrypted_files
        sops_config: Optional path to .sops.yaml

    Returns:
        List of encrypted file paths that were updated

    Raises:
        SopsEncryptionError: If encryption fails
    """
    updated = []

    for enc_path_str in changed_files:
        metadata = encrypted_state.get(enc_path_str)
        if not metadata:
            continue

        decoded_path_str = metadata["decoded_path"]
        decoded_file = decoded_dir / decoded_path_str
        enc_dst = repo_dir / enc_path_str

        if not decoded_file.exists():
            # File was deleted - we don't automatically delete encrypted files
            continue

        encrypt_file(decoded_file, enc_dst, sops_config)
        updated.append(enc_path_str)

        # Update hash in state
        metadata["last_encrypted_hash"] = file_hash(enc_dst)

    return updated


def re_decrypt_if_changed(
    repo_dir: Path,
    decoded_dir: Path,
    encrypted_state: dict[str, dict[str, str]],
    sops_config: Path | None = None,
) -> list[str]:
    """Re-decrypt files whose encrypted source has changed.

    Checks if encrypted files have been updated (e.g., after git pull)
    and re-decrypts them.

    Args:
        repo_dir: Path to the overlay repository
        decoded_dir: Path to decoded files directory
        encrypted_state: State dict from encrypted_files
        sops_config: Optional path to .sops.yaml

    Returns:
        List of encrypted file paths that were re-decrypted
    """
    re_decrypted = []

    for enc_path_str, metadata in encrypted_state.items():
        enc_src = repo_dir / enc_path_str
        if not enc_src.exists():
            continue

        # Check if encrypted file changed
        current_hash = file_hash(enc_src)
        if current_hash != metadata.get("last_encrypted_hash"):
            # Re-decrypt
            decoded_path_str = metadata["decoded_path"]
            dst = decoded_dir / decoded_path_str
            decrypt_file(enc_src, dst, sops_config)

            # Update hash
            metadata["last_encrypted_hash"] = current_hash
            re_decrypted.append(enc_path_str)

    return re_decrypted
