# Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — all operations completed without errors |
| `1` | Error — operation failed |
| `2` | Partial success — the command completed, but raised warnings that need attention (e.g., a mapping source was missing) |

## Using Exit Codes in Scripts

```bash
repoverlay sync
if [ $? -eq 2 ]; then
    echo "Sync completed with warnings — check the output"
fi

# Or use set -e to fail on any non-zero exit
set -e
repoverlay clone   # exits script on error
```

## Exit Code 2 Scenarios

Exit code `2` is returned when a command completes but raises warnings. Which warnings count depends on the command.

### `clone`

- One or more mapping sources were not found in the overlay (those mappings are skipped)

Destinations that already exist are skipped with a warning but do **not** change the exit code. SOPS decryption failures during `clone` are errors (exit code `1`).

### `sync`, `pull`, `checkout`, `merge`

`pull`, `checkout`, and `merge` run `sync` afterwards and return its exit code.

- One or more mapping sources were not found in the overlay (those mappings are skipped)
- New encrypted files were found but SOPS is not installed
- One or more SOPS decryptions or re-decryptions failed (affected files skipped)
- The cloned repo's remote URL doesn't match `overlay.repo` in the config
- One or more destinations match a `.gitignore` pattern
- One or more managed symlinks were replaced by regular files (rerun with `--force` to recreate them)

Destinations that already exist are skipped with a warning but do **not** change the exit code.

Check the output for warning messages to understand what was skipped.
