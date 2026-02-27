# Getting Started

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

---

## Quick Start

### Option A — Pass the URL directly (no config file needed)

```bash
repoverlay clone git@github.com:yourorg/config-prod.git
```

repoverlay creates `.repoverlay.yaml` automatically and symlinks all files from the overlay at their original paths. Edit the config afterward to add mappings or other options.

### Option B — Create `.repoverlay.yaml` first, then clone

**1. Create a `.repoverlay.yaml` in your infrastructure project:**

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

**2. Clone the overlay and create symlinks:**

```bash
repoverlay clone
```

**3. Your project now has symlinks to the configuration files:**

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

---

## Day-to-Day Workflow

```bash
# Pull the latest config changes and re-sync symlinks
repoverlay pull

# Check overlay status
repoverlay status

# Move a file from your main repo into the overlay
repoverlay import terraform/terraform.tfvars

# Commit overlay changes
repoverlay commit -m "Update database config"

# Push overlay changes
repoverlay push
```

---

## Next Steps

- [Configure `.repoverlay.yaml`](configuration/repoverlay-yaml.md) — add mappings, refs, and more
- [Import files](commands/import.md) — move existing files into the overlay
- [Encrypt secrets with SOPS](sops/overview.md) — keep sensitive config encrypted at rest
- [IntelliJ integration](integrations/intellij.md) — see overlay file status in your IDE
