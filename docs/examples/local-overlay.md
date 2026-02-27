# Example: Local Directory Overlay

You can use a local directory instead of a remote Git repository. This is useful for:

- Testing configuration changes before committing
- Development environments where config lives on a shared filesystem
- Air-gapped environments without network access
- Quickly prototyping a new overlay structure

## Simplest Case — No Mappings

```yaml
version: 1
overlay:
  repo: ../config-local
```

All files in `config-local/` are symlinked into your project at their original paths.

## With Explicit Mappings

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

## Directory Structure

```
projects/
├── infra-repo/
│   └── .repoverlay.yaml  # repo: ../config-local
└── config-local/
    ├── terraform.tfvars
    └── secrets.yaml
```

```bash
# From infra-repo, create symlinks to sibling config directory
cd projects/infra-repo
repoverlay clone

# Result: symlinks point to copied files in .repoverlay/repo/
```

## Behavior Notes

- If the local path is a **git repository**, it will be cloned (preserving git history)
- If the local path is a **plain directory**, it will be copied
- For plain directories, the `ref` field is ignored
- `repoverlay push` detects local non-bare repos and syncs changes correctly — no manual handling needed

## Syncing After Changes

If you add new files to the local config directory and want to pick them up:

```bash
# Add mappings to .repoverlay.yaml, then:
repoverlay sync
```

Or if using no mappings (auto-link all):

```bash
repoverlay sync
```

## Use Case: Testing Before Committing

Keep a local working copy of config that you iterate on, then push to the remote overlay when ready:

```yaml
# .repoverlay.yaml (development)
version: 1
overlay:
  repo: ../config-dev-local    # local, unversioned
```

When satisfied, switch to the remote:

```yaml
# .repoverlay.yaml (production)
version: 1
overlay:
  repo: git@github.com:yourorg/config-prod.git
```
