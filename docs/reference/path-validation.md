# Path Validation

Destination paths specified in `mappings` and paths derived from overlay files are validated before symlinks are created.

## Rules

Destination paths must:

- Be **relative** (no leading `/`)
- Not contain `..` (no directory traversal)
- Not be inside `.git/`
- Not overwrite protected files: `.repoverlay.yaml`, `.repoverlayignore`, or `.repoverlay/`
- Not be **duplicated** within the same config
- Not **overlap** with other destinations (e.g., `config` and `config/secrets`)

## Examples of Invalid Paths

| Path | Reason |
|------|--------|
| `/etc/secrets` | Absolute path |
| `../sibling-repo/config` | Contains `..` |
| `.git/config` | Inside `.git/` |
| `.repoverlay.yaml` | Protected file |
| `config` and `config/secrets` | Overlapping paths |

## Validation Errors

Validation errors are reported before any changes are made:

```
Error: invalid destination path '../other-repo/secrets' - paths must be relative and cannot contain '..'
Error: duplicate destination 'terraform/terraform.tfvars' in mappings
```
