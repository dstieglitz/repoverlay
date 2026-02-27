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

Infrastructure projects often use multiple tools — Terraform, Ansible, Helm, Helmfile, shell scripts — each with their own configuration files. You want to share the infrastructure code across teams or environments, but the configuration is environment-specific.

Common approaches don't work well:

| Approach | Drawbacks |
|----------|-----------|
| Config in same repo | Can't share infra code without leaking environment details |
| Copy files manually | Error-prone, no version control, configs drift |
| Template everything | Complex, every tool has different templating |
| Monorepo with directories | Still exposes all environments to everyone with access |
| Git submodules | Awkward workflow, detached HEAD issues, nested repos |

**The repoverlay approach:** Keep environment-specific configuration in a separate repository and symlink it into your infrastructure code. This cleanly separates *what* you're deploying from *where* and *how* it's configured.

## Getting Started

```bash
pip install repoverlay
```

**Option A — pass the URL directly:**

```bash
repoverlay clone git@github.com:yourorg/config-prod.git
```

repoverlay creates `.repoverlay.yaml` automatically and symlinks all files from the overlay at their original paths.

**Option B — create `.repoverlay.yaml` first:**

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  mappings:
    - src: terraform.tfvars
      dst: terraform/terraform.tfvars
    - src: ansible/inventory
      dst: ansible/inventory
```

```bash
repoverlay clone
```

**Requirements:** Python 3.9+

---

For full documentation see the [docs](docs/) directory or the hosted docs site.
