"""Warning checks for repoverlay."""

import fnmatch
from pathlib import Path

from .output import Output


def check_gitignore_conflicts(
    root_dir: Path,
    destinations: list[str],
    output: Output,
) -> bool:
    """Check if any destinations match .gitignore patterns.

    Args:
        root_dir: Root directory of the repository
        destinations: List of destination paths
        output: Output handler

    Returns:
        True if any conflicts found
    """
    gitignore_path = root_dir / ".gitignore"

    if not gitignore_path.exists():
        return False

    patterns = _load_gitignore_patterns(gitignore_path)
    if not patterns:
        return False

    has_conflicts = False
    for dst in destinations:
        for pattern in patterns:
            if _matches_gitignore_pattern(dst, pattern):
                output.warning(f"Destination '{dst}' matches .gitignore pattern '{pattern}'")
                has_conflicts = True
                break

    return has_conflicts


def _load_gitignore_patterns(gitignore_path: Path) -> list[str]:
    """Load patterns from .gitignore file.

    Args:
        gitignore_path: Path to .gitignore

    Returns:
        List of patterns
    """
    patterns = []
    with open(gitignore_path) as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Skip negation patterns (not fully supported)
            if line.startswith("!"):
                continue
            patterns.append(line)
    return patterns


def _matches_gitignore_pattern(path: str, pattern: str) -> bool:
    """Check if path matches a gitignore pattern.

    Simplified matching - doesn't fully implement gitignore semantics.

    Args:
        path: Path to check
        pattern: Gitignore pattern

    Returns:
        True if path matches
    """
    # Remove leading slash (root-anchored pattern)
    if pattern.startswith("/"):
        pattern = pattern[1:]
        # For anchored patterns, match from start
        if fnmatch.fnmatch(path, pattern):
            return True
        return False

    # Remove trailing slash (directory pattern)
    if pattern.endswith("/"):
        pattern = pattern[:-1]

    # Check full path match
    if fnmatch.fnmatch(path, pattern):
        return True

    # Check filename match (unanchored patterns match anywhere)
    filename = path.split("/")[-1]
    if fnmatch.fnmatch(filename, pattern):
        return True

    # Check if pattern matches any component
    parts = path.split("/")
    for part in parts:
        if fnmatch.fnmatch(part, pattern):
            return True

    return False
