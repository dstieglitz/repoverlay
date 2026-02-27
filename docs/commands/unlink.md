# `repoverlay unlink`

Remove all symlinks created by repoverlay and optionally clean up the cloned overlay directory.

```bash
repoverlay unlink [--remove-repo] [--force] [--dry-run]
```

## Flags

| Flag | Description |
|------|-------------|
| `--remove-repo` | Also remove the `.repoverlay/` directory (cloned repo, decoded secrets, state) |
| `--force`, `-f` | Proceed even if there are uncommitted changes in the overlay repo |
| `--dry-run`, `-n` | Preview changes without executing |

## Behavior

By default, `unlink` removes all symlinks that repoverlay is tracking (those recorded in `.repoverlay/state.json`). The cloned overlay repo at `.repoverlay/repo/` is left in place.

Use `--remove-repo` to perform a full cleanup:

```bash
repoverlay unlink --remove-repo
```

This removes:

- All managed symlinks
- `.repoverlay/repo/` — the cloned overlay
- `.repoverlay/decoded/` — decrypted secret files
- `.repoverlay/state.json` — repoverlay state

!!! warning "Uncommitted overlay changes"
    If the overlay repo has uncommitted changes, `unlink --remove-repo` will fail to protect against data loss. Use `--force` to override this check, or commit/stash changes first.

## IntelliJ

When `--remove-repo` is used and a `.idea/vcs.xml` exists, repoverlay automatically removes the overlay VCS root from IntelliJ's configuration.

## After Unlinking

The main repo's `.git/info/exclude` entries added by repoverlay are also cleaned up, so previously excluded symlink paths are no longer ignored.
