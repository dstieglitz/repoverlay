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

## Commands

### `repoverlay clone`

Clone the overlay repository and create symlinks.

```bash
repoverlay clone [--force] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Overwrite existing `.repoverlay/repo/` and destinations |
| `--dry-run`, `-n` | Preview changes without executing |
| `--intellij` | Configure IntelliJ IDEA to track overlay repo as VCS root |

### `repoverlay sync`

Recreate symlinks after config changes. Use after modifying mappings or pulling overlay updates.

```bash
repoverlay sync [--force] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Overwrite existing destinations |
| `--dry-run`, `-n` | Preview changes without executing |
| `--intellij` | Configure IntelliJ IDEA to track overlay repo as VCS root |

### `repoverlay unlink`

Remove all symlinks and clean up.

```bash
repoverlay unlink [--remove-repo] [--dry-run]
```

| Flag | Description |
|------|-------------|
| `--remove-repo` | Also remove `.repoverlay/` directory |
| `--dry-run`, `-n` | Preview changes without executing |

### Git Passthrough Commands

Run git commands in the overlay repository:

| Command | Description |
|---------|-------------|
| `repoverlay status` | Show overlay repo status |
| `repoverlay fetch` | Fetch from overlay remote |
| `repoverlay pull` | Pull updates, then sync symlinks |
| `repoverlay push` | Push overlay changes |
| `repoverlay diff [args]` | Show overlay diff |
| `repoverlay add <files>` | Stage files in overlay |
| `repoverlay commit [-a] -m "msg"` | Commit overlay changes (`-a` stages modified files) |
| `repoverlay checkout <ref>` | Checkout ref, then sync symlinks |
| `repoverlay merge <branch>` | Merge branch, then sync symlinks |

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

## Example: SOPS for Sensitive Values

Combine repoverlay with [SOPS](https://github.com/getsops/sops) when configuration contains secrets:

```bash
# Config repo has encrypted files
# config-prod/terraform.tfvars.enc (contains DB passwords, API keys)

# Decrypt after clone
repoverlay clone
sops -d terraform/terraform.tfvars.enc > terraform/terraform.tfvars

# Edit and re-encrypt
sops terraform/terraform.tfvars.enc
repoverlay commit -m "Rotate database credentials"
repoverlay push
```

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
