---
name: gjensidige-repo-guide
description: >
  Map of the Gjensidige GitHub repository landscape — find the correct repo for a
  platform, infrastructure, or application task. Use when a developer asks "which repo
  do I change for...", "where do I configure...", or "what repo owns..." and needs to:
  deploy an app to Kubernetes (GAP), register an app in ArgoCD, create or change an AKS
  namespace, open an Azure hub firewall rule, configure the hub application gateway,
  create an Azure AD group or app registration, provision a PostgreSQL database, onboard
  a team to Azure, set up GitHub Actions OIDC credentials (ACR push / Terraform / Azure),
  manage GitHub org settings (teams, rulesets, runners), configure ISVA/WebSEAL junctions
  and ACLs, or host static files on a CDN. Routes to the right repo and, where one exists,
  to the matching action skill (gap from gjensidige/gap-api, gap-app-onboarding,
  gap-clone-app, gap-ephemeral-environments, gap-redis-setup, gap-postgresql-database,
  gap-app-grafana-debugging).
---

# Gjensidige Repository Guide

A glossary and decision tree for navigating Gjensidige's GitHub repos. Use it to answer
"which repo do I need?" — then, where a dedicated **action skill** exists, hand off to it
instead of doing the work by hand.

This skill is **team-agnostic**. Repos owned by a single team (your `*-kubernetes-manifests`
repo, your application code, your team Terraform) are described as *patterns*, not by name —
discover the actual repo for your team from existing siblings or ask the user.

See [references/repos.md](references/repos.md) for the full glossary with structure, key
actions, environments, and Slack channels.

## How to use

1. Match the user's intent to a row in the decision tree below.
2. Open the linked repo (or the team-pattern repo) and confirm by looking at sibling
   entries — never invent conventions; copy what the repo already does.
3. If an **action skill** is listed, prefer invoking it over editing files manually.

## Decision tree

### Deploying / running applications (GAP)

| I need to… | Repo | Action skill |
|---|---|---|
| Onboard a new containerized app to GAP (workflow + manifests + ArgoCD + credentials) | spans 4–5 repos | **`gap-app-onboarding`** |
| Create a new app configured like an existing one | spans 4–5 repos (read-only, then the `gap` CLI) | **`gap-clone-app`** |
| Define / change an app's Kubernetes manifests | `<team>-kubernetes-manifests` (your team's repo) | — |
| Register an app in ArgoCD | `argocd` | **`gap`** (`gap argocd add`, in gjensidige/gap-api), or **`gap-clone-app`** when copying an existing app |
| Reconfigure an app in ArgoCD | `argocd` | — |
| Set up a PR-triggered ephemeral environment | `<team>-kubernetes-manifests` + app repo | **`gap-ephemeral-environments`** |
| Add Azure Cache for Redis to a GAP app | team Terraform + manifests | **`gap-redis-setup`** |
| Debug the GAP production runtime (metrics, traces, ingress) | — (Grafana) | **`gap-app-grafana-debugging`** |

### Kubernetes platform

| I need to… | Repo | Action skill |
|---|---|---|
| Create a new AKS namespace | `terraform-aks` (namespace provisioning; keep `addons` in sync with `argocd`) | — |
| Change a namespace's resource quota, addons or instrumentation | `argocd` — `configurations/<env>/teams/team_<github-team-slug>.json` | — |
| Grant an Entra ID group to an app's workload identity | `argocd` — same team file, `workload_identity` | **`gap`** (`gap credential wi add`, in gjensidige/gap-api) |
| Understand the `Application` and `Identity` CRDs (`apiVersion: gap.io/v1`) | `gappynator` | — |

### Azure infrastructure

| I need to… | Repo |
|---|---|
| Open a hub firewall rule (L7 FQDN or L3/L4) | `terraform-hub-firewall` |
| Configure the hub Application Gateway (WAF, listeners, routing) | `terraform-hub-application-gateway` |
| Create an Azure AD group or app registration (OAuth/OIDC) | `terraform-common-aad` |
| Provision a PostgreSQL Flexible Server database | `terraform-platform-postgresql-services` (action skill: **`gap-postgresql-database`**) |
| Onboard a new team to Azure (subscription, RGs, access packages) | `terraform-azure-onboarding` |
| Host static/public files on a CDN | `terraform-publicdata` |

### GitHub & CI/CD plumbing

| I need to… | Repo |
|---|---|
| Give a repo OIDC credentials (ACR push, Terraform, generic Azure auth) | `terraform-github-repo-credentials` |
| Manage GitHub org settings (teams, rulesets, Actions permissions, runner groups) | `terraform-github-config` |

### Access management (ISVA / WebSEAL)

| I need to… | Repo | Action skill |
|---|---|---|
| Configure WebSEAL junctions, ACLs, or groups | `itsec-iam-selfservice` | junction creation is covered by **`gap-app-onboarding`** Step 8 |

### Shared applications

Org-wide shared application repos (not team-specific infrastructure):

| I need to… | Repo |
|---|---|
| Change routing, site contexts, or micro-app loading on the customer portal (gjensidige.no logged-in area) | `application-portal` |
| Add or manage an internally-facing application/tool | `application-portal-internal` |

## Team-owned repo patterns

These vary per team — find your team's actual repo rather than assuming a name:

| Pattern | What it holds | How to find it |
|---|---|---|
| `<team>-kubernetes-manifests` | Your apps' Jsonnet/`Application` manifests | Look in `argocd` under `applications/<cluster>/team-<team>/` for the `repoURL` your apps point at |
| `<team>-reusable-workflows` | Shared GitHub Actions release workflows | Check an existing app repo's `.github/workflows/` for a `uses: gjensidige/<team>-reusable-workflows/...` reference |
| team application repos | Service source code | Org repo search, or sibling references in the manifests repo |

## Boundaries

- This skill **routes**; it does not perform changes. For multi-repo work, defer to the
  named action skill.
- Don't guess repo names or file conventions — confirm against existing entries in the repo.
- All Gjensidige repos require **signed commits** and PR review; commit with `git commit -S`
  and never use the GitHub content API (it produces unsigned commits that get rejected).
