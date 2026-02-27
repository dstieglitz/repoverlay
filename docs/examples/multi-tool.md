# Example: Multi-Tool Infrastructure Project

A typical infrastructure project using Terraform, Ansible, and Helm with environment-specific configuration.

## Config Repo Structure (`config-prod`)

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

## Infrastructure Repo `.repoverlay.yaml`

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

## Result After `repoverlay clone`

```
infra-repo/
├── .repoverlay.yaml
├── .repoverlay/
│   └── repo/                   # cloned config-prod
├── terraform/
│   ├── main.tf
│   ├── terraform.tfvars -> ../.repoverlay/repo/terraform.tfvars
│   └── backend.tfvars -> ../.repoverlay/repo/backend.tfvars
├── ansible/
│   ├── playbooks/
│   ├── inventory -> ../.repoverlay/repo/ansible/inventory
│   └── group_vars -> ../.repoverlay/repo/ansible/group_vars
└── helm/
    ├── Chart.yaml
    └── values.yaml -> ../.repoverlay/repo/helm/values.yaml
```

## Workflow

```bash
# Set up configuration for this environment
repoverlay clone

# Run your tools as normal — they find configs via symlinks
cd terraform && terraform apply
cd ../ansible && ansible-playbook -i inventory playbook.yaml
cd ../helm && helm upgrade myapp . -f values.yaml

# Pull the latest config changes
repoverlay pull

# Switch environments by changing .repoverlay.yaml to point to config-staging
```

## Switching Environments

Edit `.repoverlay.yaml` to point to a different config repo:

```yaml
overlay:
  repo: git@github.com:yourorg/config-staging.git  # changed
```

Then re-clone:

```bash
repoverlay unlink --remove-repo
repoverlay clone
```

Or if you want to manage multiple environments simultaneously, keep separate branches or clones of your infra repo, each with a different `.repoverlay.yaml`.

## Adding Secrets with SOPS

To add encrypted secrets to the config repo:

```yaml
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
  sops_config: .config/.sops.yaml
  encrypt_patterns:
    - "secrets/**"
    - "**/*.key"
  mappings:
    - src: terraform.tfvars
      dst: terraform/terraform.tfvars
    - src: secrets/db-password.yaml
      dst: config/db-password.yaml
```

```bash
# Import a secret from the main repo and encrypt it
repoverlay import secrets/db-password.yaml --encrypt

# Commit the encrypted secret to the overlay
repoverlay commit -m "Add database password"
repoverlay push
```
