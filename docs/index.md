# repoverlay

> Clone overlay repositories and create symlinks for secrets/config management.

**repoverlay** helps manage environment-specific configuration that lives in a separate repository from your infrastructure code. It clones a configuration overlay repo and creates symlinks to map files into your project, letting you share infrastructure code while keeping configuration separate.

## The Problem

Infrastructure projects often use multiple tools—Terraform, Ansible, Helm, Helmfile, shell scripts—each with their own configuration files. You want to share the infrastructure code across teams or environments, but the configuration is environment-specific.

Common approaches fall short:

| Approach | Drawbacks |
|----------|-----------|
| Config in same repo | Can't share infra code without leaking environment details |
| Copy files manually | Error-prone, no version control, configs drift |
| Template everything | Complex, every tool has different templating |
| Monorepo with directories | Still exposes all environments to everyone with access |
| Git submodules | Awkward workflow, detached HEAD issues, nested repos |

## The repoverlay Approach

Keep environment-specific configuration in a separate repository and symlink it into your infrastructure code. This cleanly separates *what* you're deploying from *where* and *how* it's configured.

- **Share infrastructure code** — The same Terraform modules, Helm charts, and scripts work across environments
- **Isolate configuration** — Each environment's config lives in its own repo with appropriate access controls
- **Tool-agnostic** — Works with any tool that reads files: Terraform tfvars, Ansible inventories, Helm values, .env files, shell configs
- **Version controlled** — Full git history for configuration changes, separate from infrastructure changes
- **Simple workflow** — No templating, no variable interpolation, just files where tools expect them

## Typical Setup

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

## Use Cases

- Separate Terraform tfvars, Ansible inventories, and Helm values from shared infrastructure code
- Use the same infrastructure repo across multiple environments (prod, staging, dev)
- Keep environment-specific configuration in access-controlled repos
- Manage configuration for projects using multiple IaC tools
- Optionally combine with [SOPS](https://github.com/getsops/sops) for encrypted secrets within configuration

## Quick Navigation

<div class="grid cards" markdown>

- :material-rocket-launch: **[Getting Started](getting-started.md)**

    Install repoverlay and set up your first overlay in minutes

- :material-file-cog: **[Configuration](configuration/repoverlay-yaml.md)**

    Reference for `.repoverlay.yaml` and `.repoverlayignore`

- :material-console: **[Commands](commands/clone.md)**

    Full command reference for clone, sync, import, migrate, and more

- :material-lock: **[SOPS Integration](sops/overview.md)**

    Encrypt secrets in your overlay with SOPS

</div>
