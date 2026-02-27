# Git Passthrough Commands

repoverlay provides passthrough commands for common git operations that run in the context of the **overlay repository** rather than your main repo.

## Command Reference

| Command | Description |
|---------|-------------|
| `repoverlay status` | Show overlay repo status |
| `repoverlay fetch` | Fetch from overlay remote |
| `repoverlay pull [--rebase\|--merge\|--ff-only]` | Pull updates, then sync symlinks |
| `repoverlay push` | Push overlay changes |
| `repoverlay diff [args]` | Show overlay diff |
| `repoverlay log [args]` | Show overlay commit log |
| `repoverlay add [-e] <files>` | Stage files in overlay (`-e`/`--encrypt` to encrypt with SOPS) |
| `repoverlay restore [-S] <files>` | Restore files in overlay (`-S`/`--staged` to unstage) |
| `repoverlay reset [files]` | Unstage files from overlay (defaults to all staged) |
| `repoverlay commit [-a] -m "msg"` | Commit overlay changes (`-a` stages modified files) |
| `repoverlay checkout [-b] <ref>` | Checkout ref (or create branch with `-b`), then sync symlinks |
| `repoverlay merge <branch>` | Merge branch, then sync symlinks |
| `repoverlay repair` | Rebuild state from filesystem |

## Syncing After Pull / Checkout / Merge

`repoverlay pull`, `repoverlay checkout`, and `repoverlay merge` automatically call `sync` after the git operation completes. This ensures your symlinks stay up to date when the overlay repo contents change.

## Staging and Encrypting Files

Use `repoverlay add` to stage files in the overlay. Pass `-e` / `--encrypt` to encrypt a file with SOPS before staging:

```bash
# Stage a plaintext file
repoverlay add terraform/terraform.tfvars

# Encrypt and stage a secrets file
repoverlay add --encrypt secrets/database.yaml
```

## Committing Changes

```bash
# Commit staged changes
repoverlay commit -m "Update production database config"

# Stage all modified tracked files and commit
repoverlay commit -a -m "Update all modified config files"
```

## Pushing to Local Repositories

When your overlay points to a local non-bare repository (a normal working directory rather than a bare `.git` repo), `repoverlay push` automatically handles the complexity of pushing to a checked-out branch.

Instead of failing with git's "refusing to update checked out branch" error, repoverlay detects this situation and uses a pull-based sync:

```bash
$ repoverlay push
Remote is a local non-bare repo with 'main' checked out.
Pulling changes into remote to keep working directory in sync...
Push complete (via pull into remote).
```

This keeps both the overlay clone and the origin repository in sync, with working directories updated correctly.

## Repairing State

If `.repoverlay/state.json` becomes out of sync with the filesystem (e.g., after manual changes), use `repair` to rebuild it:

```bash
repoverlay repair
```

## Global Flags

These flags work with all repoverlay commands:

| Flag | Description |
|------|-------------|
| `--quiet`, `-q` | Suppress informational output |
| `--no-color` | Disable colored output |
| `--version` | Show version and exit |
| `--help` | Show help |
