# `repoverlay migrate`

Move a file between the main repo and the overlay repo. Direction is detected automatically based on where the file lives.

```bash
repoverlay migrate <file> [--to DEST] [--encrypt] [--purge-history] [--dry-run]
```

## Arguments & Flags

| Argument/Flag | Description |
|------|-------------|
| `file` | File to migrate (path relative to cwd or absolute) |
| `--to DEST` | Override destination path; defaults to the same relative path in the target repo |
| `--encrypt`, `-e` | Encrypt when moving into the overlay (also auto-triggered by `encrypt_patterns`) |
| `--purge-history` | Rewrite source repo history to remove the file (requires `git-filter-repo`) |
| `--dry-run`, `-n` | Preview changes without executing |

---

## Main Repo → Overlay

Moving a file from your main repo into the overlay:

```bash
# Move terraform.tfvars into the overlay
repoverlay migrate terraform/terraform.tfvars

# Move and encrypt a secret
repoverlay migrate secrets/db-password.yaml --encrypt

# Move to a different path in the overlay
repoverlay migrate local/path/config.yaml --to config/production.yaml

# Remove the file from main repo git history after migrating
repoverlay migrate terraform/terraform.tfvars --purge-history
```

**What it does:**

1. Copies the file into the overlay repo (or encrypts it there)
2. Removes the original file and creates a symlink in its place
3. Removes the file from the main repo's git index (if tracked)
4. Stages the file in the overlay repo
5. Updates state and git exclude files

---

## Overlay → Main Repo

Moving a file from the overlay back into the main repo:

```bash
# Promote an overlay file back into the main repo
repoverlay migrate .repoverlay/repo/config/feature-flags.yaml
```

**What it does:**

1. Copies (or decrypts) the file into the main repo
2. Removes the file from the overlay repo's git index
3. Removes any symlinks in the main repo that pointed to it
4. Updates state

---

## Purging History

Use `--purge-history` to rewrite git history in the source repo after migration. This permanently removes the file from all commits.

!!! warning "Requires `git-filter-repo`"
    `--purge-history` requires [`git-filter-repo`](https://github.com/newren/git-filter-repo) to be installed.

!!! danger "Destructive operation"
    History rewriting affects all branches and requires a force-push. Coordinate with your team before using this on shared repositories.

```bash
pip install git-filter-repo
repoverlay migrate terraform/terraform.tfvars --purge-history
```

---

## Difference from `import`

[`import`](import.md) is designed specifically for moving files into the overlay from the main repo. `migrate` is bidirectional and adds support for history rewriting. Use `import` for the common case; use `migrate` when you need the extra flexibility.
