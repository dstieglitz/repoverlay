"""Test fixtures for repoverlay."""

import subprocess

import pytest


@pytest.fixture
def tmp_overlay_repo(tmp_path):
    """Local git repo acting as remote overlay."""
    repo = tmp_path / "overlay-origin"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)

    # Configure git user for commits
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Create test files
    (repo / "secrets").mkdir()
    (repo / "secrets" / "db.yaml").write_text("password: secret")
    (repo / ".env.production").write_text("API_KEY=xxx")

    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture
def tmp_main_repo(tmp_path):
    """Local git repo acting as main project."""
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    return repo


@pytest.fixture
def sample_config(tmp_overlay_repo):
    """Minimal valid config."""
    return {
        "version": 1,
        "overlay": {
            "repo": str(tmp_overlay_repo),
            "mappings": [
                {"src": "secrets", "dst": "config/secrets"},
                {"src": ".env.production", "dst": ".env"},
            ],
        },
    }
