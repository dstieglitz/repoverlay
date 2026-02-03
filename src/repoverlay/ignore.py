"""Ignore file handling for .repoverlayignore."""

import fnmatch
from pathlib import Path


def load_ignore_patterns(root_dir: Path) -> list[str]:
    """Load ignore patterns from .repoverlayignore file.

    Args:
        root_dir: Root directory containing .repoverlayignore

    Returns:
        List of glob patterns (empty if file doesn't exist)
    """
    ignore_path = root_dir / ".repoverlayignore"

    if not ignore_path.exists():
        return []

    patterns = []
    with open(ignore_path) as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            patterns.append(line)

    return patterns


def should_ignore(path: str, patterns: list[str]) -> bool:
    """Check if a path should be ignored based on patterns.

    Args:
        path: Path to check (relative path from overlay root)
        patterns: List of glob patterns

    Returns:
        True if path matches any pattern
    """
    for pattern in patterns:
        if _matches_pattern(path, pattern):
            return True
    return False


def _matches_pattern(path: str, pattern: str) -> bool:
    """Check if path matches a single pattern.

    Supports:
    - * matches any characters except /
    - ** matches any characters including /
    - ? matches single character
    - [seq] matches any character in seq

    Args:
        path: Path to check
        pattern: Glob pattern

    Returns:
        True if path matches pattern
    """
    # Handle ** patterns (matches across directories)
    if "**" in pattern:
        # Convert ** to match anything including /
        # Split pattern on ** and check each segment
        parts = pattern.split("**")
        if len(parts) == 2:
            prefix, suffix = parts
            prefix = prefix.rstrip("/")
            suffix = suffix.lstrip("/")

            # Check all possible positions
            if not prefix and not suffix:
                # Pattern is just **
                return True

            if not prefix:
                # Pattern starts with **
                # Match suffix at end of any path segment
                if fnmatch.fnmatch(path, f"*{suffix}"):
                    return True
                # Or match in any subdirectory
                path_parts = path.split("/")
                for i in range(len(path_parts)):
                    subpath = "/".join(path_parts[i:])
                    if fnmatch.fnmatch(subpath, suffix.lstrip("/")):
                        return True
                return False

            if not suffix:
                # Pattern ends with **
                return path.startswith(prefix) or fnmatch.fnmatch(path, prefix)

            # Pattern has ** in middle
            # Check if prefix matches start and suffix matches end
            if fnmatch.fnmatch(path, f"{prefix}*{suffix}"):
                return True
            # Check intermediate directories
            path_parts = path.split("/")
            for i in range(len(path_parts)):
                pre = "/".join(path_parts[:i])
                post = "/".join(path_parts[i:])
                if (not prefix or fnmatch.fnmatch(pre, prefix.rstrip("/"))):
                    if fnmatch.fnmatch(post, suffix.lstrip("/")):
                        return True
            return False

    # Standard fnmatch for simple patterns
    # Match against full path
    if fnmatch.fnmatch(path, pattern):
        return True

    # Also match against filename only for patterns without /
    if "/" not in pattern:
        filename = path.split("/")[-1]
        if fnmatch.fnmatch(filename, pattern):
            return True

    return False


def filter_mappings(
    mappings: list[dict], patterns: list[str]
) -> list[dict]:
    """Filter mappings based on ignore patterns.

    Args:
        mappings: List of mapping dicts with src/dst keys
        patterns: List of ignore patterns

    Returns:
        Filtered list of mappings (those not ignored)
    """
    return [m for m in mappings if not should_ignore(m["src"], patterns)]
