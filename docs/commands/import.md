# `repoverlay import`

Move files from the main repo into the overlay repo in one step. This replaces the manual workflow of copying a file, `git rm`-ing it, adding it to the overlay, and syncing.

```bash
repoverlay import <files...> [--encrypt] [--dry-run]
```

## Flags

| Flag | Description |
|------|-------------|
| `--encrypt`, `-e` | Encrypt files with SOPS before importing |
| `--dry-run`, `-n` | Preview changes without executing |

## What It Does

For each file:

1. Copies the file into the overlay repo (preserving directory structure)
2. Removes it from the main repo's git index (if tracked)
3. Replaces the original with a symlink to the overlay copy
4. Stages the file in the overlay repo
5. Updates state and git exclude files

## Examples

```bash
# Import a single file
repoverlay import terraform/terraform.tfvars

# Import an entire directory
repoverlay import scripts/config/

# Import and encrypt sensitive files
repoverlay import secrets.yaml --encrypt

# Preview what would happen
repoverlay import terraform/terraform.tfvars --dry-run
```

## Auto-Encryption

Files matching `encrypt_patterns` in `.repoverlay.yaml` are automatically encrypted, even without `--encrypt`:

```yaml
overlay:
  encrypt_patterns:
    - "secrets/**"
    - "**/*.env"
```

```bash
# Auto-encrypted because the path matches "secrets/**"
repoverlay import secrets/database.yaml

# Plaintext because no pattern matches
repoverlay import terraform/terraform.tfvars
```

See [Encrypt Patterns](../sops/encrypt-patterns.md) for details.

## Untracked Files

Untracked files (not in the main repo's git index) are imported normally — the `git rm` step is simply skipped for them.

## Difference from `migrate`

`import` is designed for moving files **into** the overlay from the main repo. [`migrate`](migrate.md) is bidirectional — it can also move files from the overlay back into the main repo, and supports optional history rewriting.
