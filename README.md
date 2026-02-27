# repoverlay

Clone overlay repositories and create symlinks for secrets/config management.

## Overview

`repoverlay` helps manage environment-specific configuration that lives in a separate repository from your infrastructure code. It clones a configuration overlay repo and creates symlinks to map files into your project, letting you share infrastructure code while keeping configuration separate.

**Use cases:**
- Separate Terraform tfvars, Ansible inventories, and Helm values from shared infrastructure code
- Use the same infrastructure repo across multiple environments (prod, staging, dev)
- Keep environment-specific configuration in access-controlled repos
- Manage configuration for projects using multiple IaC tools (Terraform, Ansible, Helm, Helmfile, shell scripts)
- Optionally combine with [SOPS](https://github.com/getsops/sops) for encrypted secrets within configuration

## Why repoverlay?

**The problem:** Infrastructure projects often use multiple tools—Terraform, Ansible, Helm, Helmfile, shell scripts—each with their own configuration files. You want to share the infrastructure code across teams or environments, but the configuration is environment-specific.

Common approaches don't work well:

| Approach | Drawbacks |
|----------|-----------|
| Config in same repo | Can't share infra code without leaking environment details |
| Copy files manually | Error-prone, no version control, configs drift |
| Template everything | Complex, every tool has different templating |
| Monorepo with directories | Still exposes all environments to everyone with access |
| Git submodules | Awkward workflow, detached HEAD issues, nested repos |

**The repoverlay approach:** Keep environment-specific configuration in a separate repository and symlink it into your infrastructure code. This cleanly separates *what* you're deploying from *where* and *how* it's configured.

- **Share infrastructure code** - The same Terraform modules, Helm charts, and scripts work across environments
- **Isolate configuration** - Each environment's config lives in its own repo with appropriate access controls
- **Tool-agnostic** - Works with any tool that reads files: Terraform tfvars, Ansible inventories, Helm values, .env files, shell configs
- **Version controlled** - Full git history for configuration changes, separate from infrastructure changes
- **Simple workflow** - No templating, no variable interpolation, just files where tools expect them

**Typical setup:**

```
your-org/
├── infra-repo/                    # Shared infrastructure code
│   ├── .repoverlay.yaml           # Points to config-repo
│   ├── terraform/
│   │   ├── main.tf
│   │   └── terraform.tfvars -> ../../.repoverlay/repo/terraform.tfvars
│   ├── ansible/
│   │   ├── playbooks/
│   │   └── inventory -> ../../.repoverlay/repo/ansible/inventory
│   └── helm/
│       └── values.yaml -> ../../.repoverlay/repo/helm/values.yaml
│
└── config-prod-repo/              # Environment-specific configuration
    ├── terraform.tfvars
    ├── ansible/inventory
    └── helm/values.yaml
```

Teams working on production use `config-prod-repo`. Teams working on staging use `config-staging-repo`. The infrastructure code stays the same—only the overlay changes.

## Installation

```bash
pip install repoverlay
```

Or install from source:

```bash
git clone https://github.com/user/repoverlay.git
cd repoverlay
pip install -e .
```

**Requirements:** Python 3.9+

## Quick Start

**Option A — pass the URL directly (no config file needed):**

```bash
repoverlay clone git@github.com:yourorg/config-prod.git
```

repoverlay creates `.repoverlay.yaml` automatically and symlinks all files from the overlay at their original paths. Edit the config afterward to add mappings or other options.

**Option B — create `.repoverlay.yaml` first, then clone:**

1. Create a `.repoverlay.yaml` in your infrastructure project:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  ref: main  # optional branch/tag
  mappings:
    - src: terraform.tfvars
      dst: terraform/terraform.tfvars
    - src: ansible/inventory
      dst: ansible/inventory
    - src: helm/values.yaml
      dst: helm/values.yaml
```

2. Clone the overlay and create symlinks:

```bash
repoverlay clone
```

3. Your project now has symlinks to the configuration files:

```
infra-project/
├── .repoverlay.yaml
├── .repoverlay/
│   └── repo/           # cloned config overlay
├── terraform/
│   ├── main.tf
│   └── terraform.tfvars -> ../.repoverlay/repo/terraform.tfvars
├── ansible/
│   ├── playbooks/
│   └── inventory -> ../.repoverlay/repo/ansible/inventory
└── helm/
    ├── Chart.yaml
    └── values.yaml -> ../.repoverlay/repo/helm/values.yaml
```

## Encryption Patterns

`encrypt_patterns` is an optional list of glob patterns in `.repoverlay.yaml` that controls which files are automatically encrypted with SOPS when added to the overlay. Without this, you must pass `--encrypt` explicitly on every `repoverlay add` or `repoverlay import` call.

## SOPS Configuration

See https://github.com/getsops/sops?tab=readme-ov-file#2usage

### Configuration

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  sops_config: .config/.sops.yaml   # optional, see SOPS Integration below
  encrypt_patterns:
    - "secrets/**"
    - "**/*.secret.yaml"
    - "**/*.env"
    - "credentials.json"
```

### Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `secrets/**` | All files anywhere under `secrets/` |
| `**/*.secret.yaml` | Any `.secret.yaml` file at any depth |
| `**/*.env` | Any `.env` file at any depth |
| `credentials.json` | Exactly `credentials.json` at the repo root |
| `config/db.*` | Any file named `db.*` directly inside `config/` |

- `*` matches any characters except `/`
- `**` matches across directory boundaries (any depth)
- `?` matches a single character
- Patterns are matched against the file's path relative to the overlay repo root

### Behavior

When `encrypt_patterns` is configured, any file whose path matches is encrypted automatically — no `--encrypt` flag needed:

```bash
# Without encrypt_patterns: must opt in
repoverlay add --encrypt secrets/database.yaml

# With encrypt_patterns: ["secrets/**"] — auto-encrypted
repoverlay add secrets/database.yaml

# Files that don't match are added as plaintext
repoverlay add terraform/terraform.tfvars
```

The same patterns apply to `repoverlay import`:

```bash
# Auto-encrypted because path matches "secrets/**"
repoverlay import secrets/database.yaml

# Plaintext because path doesn't match any pattern
repoverlay import ansible/inventory
```

### Example: Separating Secrets from Config

A common setup encrypts only sensitive files while keeping other config in plaintext:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  encrypt_patterns:
    - "secrets/**"
    - "**/*.key"
    - "**/*.pem"
    - "vault-password"
```

With this config:
- `secrets/db-password.yaml` → encrypted as `secrets/db-password.yaml.enc`
- `ansible/inventory` → added as plaintext
- `tls/server.key` → encrypted as `tls/server.key.enc`
- `vault-password` → encrypted as `vault-password.enc`

Encrypted files appear in the overlay repo with a `.enc` suffix. When you clone or sync, they are automatically decrypted into `.repoverlay/decoded/` and symlinked as plaintext into your project.

## Commands

### `repoverlay clone`

Clone the overlay repository and create symlinks.

```bash
repoverlay clone [URL] [--force] [--dry-run]
```

| Argument/Flag | Description |
|------|-------------|
| `URL` | Git URL or local path of overlay repo. Creates `.repoverlay.yaml` if none exists |
| `--force`, `-f` | Overwrite existing `.repoverlay/repo/` and destination files |
| `--dry-run`, `-n` | Preview changes without executing |
| `--intellij` | Configure IntelliJ IDEA to track overlay repo as VCS root |

Files that already exist in your project are skipped with a warning. Use `--force` to overwrite them.

#### Cloning without a config file

If no `.repoverlay.yaml` exists, you can pass a URL directly and repoverlay will create one for you:

```bash
repoverlay clone git@github.com:yourorg/config-prod.git
```

This creates a minimal `.repoverlay.yaml` in the current directory:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
```

All files from the overlay repo are then symlinked into your project at their original paths (no explicit mappings). You can edit `.repoverlay.yaml` afterward to add mappings, `encrypt_patterns`, or other options, then run `repoverlay sync` to apply the changes.

If a `.repoverlay.yaml` already exists, the URL argument is ignored and the existing config is used.

### `repoverlay sync`

Recreate symlinks after config changes. Use after modifying mappings or pulling overlay updates.

```bash
repoverlay sync [--force] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Overwrite existing destination files |
| `--dry-run`, `-n` | Preview changes without executing |
| `--intellij` | Configure IntelliJ IDEA to track overlay repo as VCS root |

Files that already exist in your project are skipped with a warning. Use `--force` to overwrite them.

### `repoverlay unlink`

Remove all symlinks and clean up.

```bash
repoverlay unlink [--remove-repo] [--force] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--remove-repo` | Also remove `.repoverlay/` directory |
| `--force`, `-f` | Proceed even with uncommitted overlay changes |
| `--dry-run`, `-n` | Preview changes without executing |

### `repoverlay cloak`

Remove all decrypted secret files from `.repoverlay/decoded/` and replace their symlinks with ones pointing directly to the encrypted files in `.repoverlay/repo/`. The symlink names remain unchanged (no `.enc` suffix), so existing tool paths continue to work—but the plaintext content is gone from disk.

```bash
repoverlay cloak [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--dry-run`, `-n` | Preview changes without executing |

**Before cloaking:**
```
secrets.yaml -> .repoverlay/decoded/secrets.yaml   (plaintext on disk)
```

**After cloaking:**
```
secrets.yaml -> .repoverlay/repo/secrets.yaml.enc  (only encrypted bytes on disk)
```

This is useful when stepping away from a machine, checking in code on a shared screen, or any situation where you want to ensure plaintext secrets are not present on disk without losing access to the overlay structure.

---

### `repoverlay decloak`

Reverse `cloak`: decrypt encrypted files back to `.repoverlay/decoded/` and restore symlinks to point to the decrypted versions. Optionally decloak a single file.

```bash
repoverlay decloak [file] [--dry-run]
```

| Argument/Flag | Description |
|------|-------------|
| `file` | Specific file to decloak (decoded path e.g. `secrets.yaml`, or encrypted path e.g. `secrets.yaml.enc`). Defaults to all tracked files |
| `--dry-run`, `-n` | Preview changes without executing |

**Examples:**
```bash
# Decloak everything
repoverlay decloak

# Decloak a single secret by its decoded name
repoverlay decloak secrets/database.yaml

# Decloak a single secret by its encrypted name
repoverlay decloak secrets/database.yaml.enc

# Preview what would happen
repoverlay decloak --dry-run
```

---

### `repoverlay list`

List files in the overlay repository. Encrypted files are marked with `(encrypted)`.

```bash
repoverlay list
```

Example output:
```
ansible/inventory
helm/values.yaml
secrets.yaml.enc (encrypted)
terraform.tfvars
```

### `repoverlay import`

Move files from the main repo into the overlay repo in one step. This replaces the manual workflow of copying a file, `git rm`-ing it, adding it to the overlay, and syncing.

```bash
repoverlay import <files...> [--encrypt] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--encrypt`, `-e` | Encrypt files with SOPS before importing |
| `--dry-run`, `-n` | Preview changes without executing |

**What it does for each file:**
1. Copies the file into the overlay repo (preserving directory structure)
2. Removes it from the main repo's git index (if tracked)
3. Replaces the original with a symlink to the overlay copy
4. Stages the file in the overlay repo
5. Updates state and git exclude files

**Examples:**

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

Files matching `encrypt_patterns` in `.repoverlay.yaml` are automatically encrypted, even without `--encrypt`.

Untracked files (not in the main repo's git index) are imported normally — the `git rm` step is simply skipped for them.

### `repoverlay migrate`

Move a file between the main repo and the overlay repo. Direction is detected automatically based on where the file lives.

```bash
repoverlay migrate <file> [--to DEST] [--encrypt] [--purge-history] [--dry-run]
```

| Argument/Flag | Description |
|------|-------------|
| `file` | File to migrate (path relative to cwd or absolute) |
| `--to DEST` | Override destination path; defaults to the same relative path in the target repo |
| `--encrypt`, `-e` | Encrypt when moving into the overlay (also auto-triggered by `encrypt_patterns`) |
| `--purge-history` | Rewrite source repo history to remove the file (requires `git-filter-repo`) |
| `--dry-run`, `-n` | Preview changes without executing |

**Moving a file from the main repo into the overlay (main → overlay):**

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

What it does:
1. Copies the file into the overlay repo (or encrypts it there)
2. Removes the original file and creates a symlink in its place
3. Removes the file from the main repo's git index (if tracked)
4. Stages the file in the overlay repo
5. Updates state and git exclude files

**Moving a file from the overlay back into the main repo (overlay → main):**

```bash
# Promote an overlay file back into the main repo
repoverlay migrate .repoverlay/repo/config/feature-flags.yaml
```

What it does:
1. Copies (or decrypts) the file into the main repo
2. Removes the file from the overlay repo's git index
3. Removes any symlinks in the main repo that pointed to it
4. Updates state

**Difference from `import`:**

`import` is designed for moving files *into* the overlay from the main repo. `migrate` is bidirectional—it can also move files from the overlay back into the main repo, and supports optional history rewriting.

### Git Passthrough Commands

Run git commands in the overlay repository:

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
| `repoverlay import [-e] <files>` | Import files from main repo into overlay (see below) |
| `repoverlay migrate <file>` | Move a file between main repo and overlay (see below) |
| `repoverlay commit [-a] -m "msg"` | Commit overlay changes (`-a` stages modified files) |
| `repoverlay checkout [-b] <ref>` | Checkout ref (or create branch with `-b`), then sync symlinks |
| `repoverlay merge <branch>` | Merge branch, then sync symlinks |
| `repoverlay repair` | Rebuild state from filesystem |
| `repoverlay cloak` | Remove plaintext secrets from disk, relink to encrypted files |
| `repoverlay decloak [file]` | Decrypt secrets and restore symlinks to plaintext files |

#### Push to Local Repositories

When your overlay points to a local non-bare repository (a normal working directory rather than a bare `.git` repo), `repoverlay push` automatically handles the complexity of pushing to a checked-out branch.

Instead of failing with git's "refusing to update checked out branch" error, repoverlay detects this situation and uses a pull-based sync:

```bash
$ repoverlay push
Remote is a local non-bare repo with 'main' checked out.
Pulling changes into remote to keep working directory in sync...
Push complete (via pull into remote).
```

This keeps both the overlay clone and the origin repository in sync, with working directories updated correctly.

### Global Flags

| Flag | Description |
|------|-------------|
| `--quiet`, `-q` | Suppress informational output |
| `--no-color` | Disable colored output |
| `--version` | Show version and exit |
| `--help` | Show help |

## Configuration

### `.repoverlay.yaml`

```yaml
version: 1
overlay:
  repo: git@github.com:user/secrets-repo.git
  ref: main  # optional: branch, tag, or commit
  mappings:
    - src: path/in/overlay
      dst: path/in/project
    - src: .env.production
      dst: .env
```

| Field | Required | Description |
|-------|----------|-------------|
| `version` | Yes | Must be `1` |
| `overlay.repo` | Yes | Git URL or local path of overlay repository |
| `overlay.ref` | No | Branch, tag, or commit to checkout |
| `overlay.mappings` | No | List of source/destination mappings. If omitted, all files in the overlay are symlinked using their original paths |
| `overlay.sops_config` | No | Path to `.sops.yaml` in overlay repo (default: `.config/.sops.yaml` or `.sops.yaml`) |
| `overlay.encrypt_patterns` | No | List of glob patterns for auto-encrypting files on `repoverlay add` |
| `mappings[].src` | Yes | Path in overlay repo |
| `mappings[].dst` | Yes | Path in main repo (must be relative) |

**Without mappings:** When `mappings` is omitted, repoverlay symlinks all files from the overlay repository into your project using the same relative paths:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
```

If the overlay repo contains `terraform/terraform.tfvars` and `ansible/inventory`, symlinks will be created at those exact paths in your project.

### `.repoverlayignore`

Optional file to exclude overlay files from symlink creation:

```
# Ignore overlay's README
README.md

# Ignore all .example files
*.example

# Ignore test directories
**/test/**
```

**Pattern syntax:**
- `*` matches any characters except `/`
- `**` matches any characters including `/`
- `?` matches single character
- `[seq]` matches any character in seq
- Lines starting with `#` are comments
- Blank lines are ignored

## Conflict Handling

When a destination file already exists in your main repository (e.g., both repos have a `README.md`), repoverlay **skips** that file with a warning instead of failing:

```
Warning: Skipping README.md - destination already exists (use --force to overwrite)
```

This allows you to:
- Keep your main repo's version of common files like `README.md`
- Overlay only the files that don't conflict
- Use `--force` to overwrite if you want the overlay version

**Skipped files are not tracked** in repoverlay's state, so they won't be removed by `unlink` or managed by `sync`.

If you want to explicitly exclude certain overlay files (rather than relying on conflicts), add them to `.repoverlayignore`.

## Path Validation

Destination paths are validated:

- Must be relative (no leading `/`)
- Cannot contain `..`
- Cannot be in `.git/`
- Cannot overwrite `.repoverlay.yaml`, `.repoverlayignore`, or `.repoverlay/`
- Cannot have duplicates
- Cannot overlap (e.g., `config` and `config/secrets`)

## IntelliJ IDEA Integration

When working in IntelliJ IDEA (or other JetBrains IDEs), symlinked files from the overlay won't show version control status by default because they live in a different git repository. Use the `--intellij` flag to register the overlay as an additional VCS root:

```bash
repoverlay clone --intellij
```

This updates `.idea/vcs.xml` to include `.repoverlay/repo` as a git root, allowing IntelliJ to:
- Show git status for symlinked overlay files
- Track changes, diffs, and history for configuration files
- Commit overlay changes directly from the IDE

The `--intellij` flag is also available on `sync`:

```bash
repoverlay sync --intellij
```

When you run `repoverlay unlink --remove-repo`, the VCS root is automatically removed from IntelliJ's configuration.

**Note:** This only works if your project has a `.idea/` directory (i.e., has been opened in IntelliJ).

## Git Integration

repoverlay automatically manages `.git/info/exclude` to prevent accidental commits of overlay files:

```
# BEGIN repoverlay managed - do not edit
.repoverlay.yaml
.repoverlayignore
.repoverlay/
config/secrets
.env
# END repoverlay managed
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Error |
| 2 | Partial success with warnings |

## Example: Multi-Tool Infrastructure Project

A typical infrastructure project using Terraform, Ansible, and Helm with environment-specific configuration:

1. **Config repo structure (`config-prod`):**
```
config-prod/
├── terraform.tfvars          # Terraform variables
├── backend.tfvars            # Terraform backend config
├── ansible/
│   ├── inventory             # Ansible inventory
│   └── group_vars/
│       └── all.yaml          # Ansible variables
└── helm/
    └── values.yaml           # Helm values
```

2. **Infrastructure repo `.repoverlay.yaml`:**
```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  mappings:
    - src: terraform.tfvars
      dst: terraform/terraform.tfvars
    - src: backend.tfvars
      dst: terraform/backend.tfvars
    - src: ansible/inventory
      dst: ansible/inventory
    - src: ansible/group_vars
      dst: ansible/group_vars
    - src: helm/values.yaml
      dst: helm/values.yaml
```

3. **Workflow:**
```bash
# Set up configuration for this environment
repoverlay clone

# Run your tools as normal - they find configs via symlinks
cd terraform && terraform apply
cd ../ansible && ansible-playbook -i inventory playbook.yaml
cd ../helm && helm upgrade myapp . -f values.yaml

# Update configuration
repoverlay pull    # Get latest config changes

# Switch environments by changing .repoverlay.yaml to point to config-staging
```

## SOPS Integration

repoverlay has built-in support for [SOPS](https://github.com/getsops/sops) encrypted files. Files ending in `.enc`, `.encoded`, or `.encrypted` are automatically detected, decrypted to a working directory, and symlinked as plaintext files. Changes are automatically re-encrypted on commit.

### How It Works

```
main-repo/
├── .repoverlay.yaml
├── .repoverlay/
│   ├── repo/                  # Cloned overlay (encrypted files)
│   │   ├── .config/
│   │   │   └── .sops.yaml     # SOPS configuration
│   │   └── secrets.yaml.enc   # Encrypted file
│   ├── decoded/               # Decrypted working copies
│   │   └── secrets.yaml       # Plaintext (git-ignored)
│   └── state.json
└── config/secrets.yaml -> ../.repoverlay/decoded/secrets.yaml
```

### Setup

1. **Install SOPS:**
   ```bash
   brew install sops      # macOS
   apt install sops       # Debian/Ubuntu
   ```

2. **Add `.sops.yaml` to your overlay repo** (in `.config/.sops.yaml` or root):
   ```yaml
   creation_rules:
     - path_regex: .*\.enc$
       kms: arn:aws:kms:us-west-2:123456789:key/abc-123
     # Or use age, pgp, etc.
     - path_regex: .*\.encrypted$
       age: age1xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

3. **Clone with automatic decryption:**
   ```bash
   repoverlay clone
   # Output:
   # Found SOPS config: .config/.sops.yaml
   # Decrypting SOPS-encrypted files...
   # Decrypted 2 file(s)
   #   + secrets.yaml (decrypted)
   ```

### Encrypting Files

**Option 1: Use `repoverlay import --encrypt` (recommended for files in the main repo):**
```bash
repoverlay import --encrypt path/to/secrets.yaml
```

This will encrypt the file, move it to the overlay, remove it from the main repo index, and create a symlink — all in one step.

**Option 2: Use `repoverlay add --encrypt` (for external files):**
```bash
repoverlay add --encrypt path/to/secrets.yaml
```

This will:
- Encrypt the file → `secrets.yaml.enc` in `.repoverlay/repo/`
- Copy plaintext to `.repoverlay/decoded/`
- Stage the encrypted file for commit

**Option 2: Configure auto-encryption patterns:**
```yaml
version: 1
overlay:
  repo: git@github.com:org/config.git
  sops_config: .config/.sops.yaml    # optional custom path
  encrypt_patterns:
    - "secrets/**"
    - "**/*.secret.yaml"
```

Files matching these patterns are automatically encrypted when added:
```bash
repoverlay add secrets/database.yaml  # auto-encrypted
```

### Workflow

```bash
# Clone - encrypted files are decrypted automatically
repoverlay clone

# Edit the decrypted file directly
vim config/secrets.yaml

# Commit - changes are re-encrypted automatically
repoverlay commit -m "Update database password"

# Push encrypted files to remote
repoverlay push

# Pull - updated encrypted files are re-decrypted
repoverlay pull
```

### Multiple Keys

Different files can use different encryption keys. SOPS stores key metadata inside each encrypted file, so it automatically uses the correct key for decryption. Your `.sops.yaml` creation rules determine which key is used when *encrypting* new files:

```yaml
creation_rules:
  - path_regex: terraform/.*\.enc$
    kms: arn:aws:kms:us-west-2:123:key/terraform-key
  - path_regex: ansible/.*\.enc$
    age: age1xxxxxxxxx
  - path_regex: .*
    pgp: FINGERPRINT
```

### Cloak / Decloak

When working with SOPS-encrypted files, decrypted plaintext is stored in `.repoverlay/decoded/`. Sometimes you want to remove that plaintext from disk—without losing the overlay structure—and restore it later.

```bash
# Remove plaintext from disk; symlinks now point to encrypted files
repoverlay cloak

# Restore plaintext; symlinks point back to .repoverlay/decoded/
repoverlay decloak

# Decloak just one file
repoverlay decloak secrets/database.yaml
```

**Cloaked state on disk:**
```
main-repo/
├── .repoverlay/
│   ├── repo/
│   │   └── secrets.yaml.enc   ← encrypted content
│   └── decoded/               ← empty (no plaintext)
└── secrets.yaml -> .repoverlay/repo/secrets.yaml.enc
```

**Decloaked state on disk:**
```
main-repo/
├── .repoverlay/
│   ├── repo/
│   │   └── secrets.yaml.enc
│   └── decoded/
│       └── secrets.yaml       ← plaintext here
└── secrets.yaml -> .repoverlay/decoded/secrets.yaml
```

The symlink name (`secrets.yaml`) is the same in both states—tools that read the file continue to work in the decloaked state, and the encrypted bytes are accessible through the symlink in the cloaked state.

Cloak/decloak state is tracked in `.repoverlay/state.json`. Both operations are idempotent—running them twice is safe.

### Troubleshooting

If decryption fails, repoverlay shows the SOPS error with a hint:

```
Warning: Cannot decrypt secrets.yaml.enc:
Failed to decrypt secrets.yaml.enc:
Error decrypting key: AccessDeniedException...
Hint: Are you using the correct credentials/profile?
```

Common issues:
- **Wrong AWS profile:** `AWS_PROFILE=myprofile repoverlay sync`
- **Missing age key:** Ensure `SOPS_AGE_KEY_FILE` is set or key is in `~/.config/sops/age/keys.txt`
- **No matching creation rules:** Check `.sops.yaml` path patterns match your files

## Example: Local Directory Overlay

You can use a local directory instead of a remote Git repository. This is useful for:
- Testing configuration changes before committing
- Development environments where config lives on a shared filesystem
- Air-gapped environments without network access

**Simplest case - no mappings:**

```yaml
version: 1
overlay:
  repo: ../config-local
```

All files in `config-local/` are symlinked into your project at their original paths.

**With explicit mappings:**

```yaml
version: 1
overlay:
  repo: /path/to/local/config-directory
  mappings:
    - src: terraform.tfvars
      dst: terraform/terraform.tfvars
    - src: .env
      dst: .env
```

**Workflow with local directories:**

```bash
# Directory structure
projects/
├── infra-repo/
│   └── .repoverlay.yaml  # repo: ../config-local
└── config-local/
    ├── terraform.tfvars
    └── secrets.yaml

# From infra-repo, create symlinks to sibling config directory
cd projects/infra-repo
repoverlay clone

# Result: symlinks point to copied files in .repoverlay/repo/
```

When using a local directory:
- If the path is a git repository, it will be cloned (preserving git history)
- If the path is a plain directory, it will be copied
- For plain directories, the `ref` field is ignored
- Use `repoverlay sync` if you add new files to the mappings
- `repoverlay push` works transparently—it detects local non-bare repos and syncs changes correctly

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=repoverlay
```

## License

MIT
