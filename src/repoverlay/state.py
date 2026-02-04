"""State file management."""

import json
from pathlib import Path
from typing import Any


def get_state_path(root_dir: Path) -> Path:
    """Get path to state file.

    Args:
        root_dir: Root directory containing .repoverlay/

    Returns:
        Path to state.json
    """
    return root_dir / ".repoverlay" / "state.json"


def read_state(root_dir: Path) -> dict[str, Any]:
    """Read state from state.json.

    Args:
        root_dir: Root directory containing .repoverlay/

    Returns:
        State dict, or empty default if file doesn't exist.

    State schema:
        {
            "symlinks": [...],
            "created_directories": [...],
            "encrypted_files": {
                "terraform.tfvars.enc": {
                    "decoded_path": "terraform.tfvars",
                    "symlink_dst": "terraform/terraform.tfvars",
                    "last_encrypted_hash": "sha256:abc123..."
                }
            }
        }
    """
    state_path = get_state_path(root_dir)

    if not state_path.exists():
        return {"symlinks": [], "created_directories": [], "encrypted_files": {}}

    with open(state_path) as f:
        state = json.load(f)
        # Ensure encrypted_files key exists for backwards compatibility
        if "encrypted_files" not in state:
            state["encrypted_files"] = {}
        return state


def write_state(root_dir: Path, state: dict[str, Any]) -> None:
    """Write state to state.json.

    Args:
        root_dir: Root directory containing .repoverlay/
        state: State dict to write.
    """
    state_path = get_state_path(root_dir)

    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)

    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
