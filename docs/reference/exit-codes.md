# Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success — all operations completed without errors |
| `1` | Error — operation failed |
| `2` | Partial success — some operations completed, but warnings were raised (e.g., files skipped due to conflicts) |

## Using Exit Codes in Scripts

```bash
repoverlay clone
if [ $? -eq 2 ]; then
    echo "Some files were skipped — check for conflicts"
fi

# Or use set -e to fail on any non-zero exit
set -e
repoverlay clone   # exits script on error
```

## Exit Code 2 Scenarios

Exit code `2` is returned when repoverlay completes partially:

- One or more destination files already existed and were skipped
- One or more SOPS decryptions failed (overlay still cloned, affected files skipped)

Check the output for warning messages to understand what was skipped.
