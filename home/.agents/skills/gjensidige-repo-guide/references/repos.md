# Gjensidige Repository Glossary

Full reference for the repos in [SKILL.md](../SKILL.md). All repos live under the
`gjensidige/` GitHub org. Team-owned repos are described as patterns; confirm the actual
name for your team before acting.

## Contents

- [GAP application platform](#gap-application-platform)
- [Kubernetes platform](#kubernetes-platform)
- [Azure infrastructure](#azure-infrastructure)
- [GitHub & CI/CD plumbing](#github--cicd-plumbing)
- [Access management](#access-management)
- [Shared applications](#shared-applications)
- [Team-owned repo patterns](#team-owned-repo-patterns)

## GAP application platform

### `gjensidige/argocd`
**Purpose:** Declarative GitOps configuration for Gjensidige's ArgoCD instances, and the
per-team namespace configuration published to Gappynator.
**Use when:** Registering a new application for continuous deployment to Kubernetes,
modifying deployment settings (sync policy, notifications), or changing a namespace's
resource quota, addons, instrumentation or workload identity groups.
**Key concepts:** Applications defined as Jsonnet files per cluster/team. Projects define
team boundaries. Namespace configuration lives in
`configurations/<env>/teams/team_<github-team-slug>.json` as
`cluster -> namespaces -> namespace` with `resource_quota`, `addons`, `instrumentation`
and `workload_identity` (`default` groups for every identity in the namespace, `apps.<app>`
for one application). See `configurations/README.md`.
**Structure:** `applications/<cluster-name>/team-<team>/<app>/application.jsonnet`
**Environments:** TEST (argocd.testgjensidige.io), PROD (argocd.gjensidige.io).
Standard GAP clusters are `apps-int-test` and `apps-int-prod`.
**Slack:** #team-platform
**Related skills:** `gap` from gjensidige/gap-api (`gap argocd add`, `gap credential wi add`),
`gap-clone-app` (copies an existing app's setup), `gap-app-onboarding` (registers apps
end-to-end).

### `gjensidige/gappynator`
**Purpose:** Kubernetes operator for the GAP CRDs (`apiVersion: gap.io/v1`). `Application`
is reconciled into Deployments, probes, network policies, observability, secret-store
integration, and volumes. `Identity` gives workloads that are not an `Application` (for
example CronJobs) a workload identity: a ServiceAccount and Key Vault secrets.
**Use when:** A team's manifests use `Application` or `Identity` resources and you need the
full set of available CRD fields, defaults, and validation rules.
**Key concepts:** Env vars / `envFrom` / probes accept standard Kubernetes YAML as input
in the CRD spec. Workload identity groups come from the namespace configuration in
`argocd`.

## Kubernetes platform

### `gjensidige/terraform-aks`
**Purpose:** Terraform for all AKS clusters in Gjensidige Application Platform (GAP).
**Use when:** Creating a new Kubernetes namespace (provisioning) or managing
cluster-level settings. Resource quotas, instrumentation and workload identity groups are
configured in `argocd` instead.
**Key actions:**
- Create namespace: edit `namespaces.<cluster>.<env>.tfvars` → add an entry to the
  `namespaces` object.
- Namespace addons are set here (for example `java-key-store`, `ca-bundle`, `jwt-config`,
  `confluent-cloud-config`). Keep `ca-bundle`, `java-key-store` and `jwt-config` in sync
  with the namespace's `addons` in `argocd`, which publishes them to Gappynator.
**Docs:** gap.gjensidige.io (namespace onboarding, cluster overview)
**Slack:** #gap

## Azure infrastructure

### `gjensidige/terraform-hub-firewall`
**Purpose:** Manage Azure Hub Firewall rules (application L7 and network L3/L4 rules).
**Use when:** Opening firewall rules between Azure networks, on-prem, or external services.
**Key concepts:**
- Application rules (L7, FQDN-based) preferred over network rules (L3/L4).
- IP Groups define VNets/subnets as reusable references.
- Policies: base (platform-wide) and child (per source group).
- Collection groups categorize rules by traffic source.
**Best practices:** Use FQDN over IP; use application rules for HTTP/S; check existing
collection groups before creating new ones.

### `gjensidige/terraform-hub-application-gateway`
**Purpose:** Manage the Azure Hub Application Gateway (the shared L7 entry point — WAF,
listeners, backend pools, routing rules).
**Use when:** Exposing a service through the hub gateway, or adjusting WAF / routing
configuration on it.

### `gjensidige/terraform-common-aad`
**Purpose:** Provision common Azure AD resources (groups and app registrations).
**Use when:** Creating a new Azure AD security group or registering an Azure AD application
(for OAuth/OIDC).
**Key actions:**
- AD Groups: add an `azuread_group` resource to `aad_groups.tf`.
- AD Apps: add an entry to the `applications` local map in `variables.tf`.
**Environments:** Separate test/prod directories.

### `gjensidige/terraform-platform-postgresql-services`
**Purpose:** Provision PostgreSQL Flexible Servers managed by platform operations.
**Use when:** Creating a new PostgreSQL database or managing database access (tier2/tier3
groups).
**Key actions:** Edit `provision_databases.tfvars` in your team folder → add the database
to the instance's `databases` block.
**Access tiers:**
- Default (tier2): team-level access.
- `enable_cotr`: CRUD operations (tier3).
- `enable_redr`: read-only access (tier3).
**Constraints:** DB names ~15 chars recommended; use underscores, not hyphens.

### `gjensidige/terraform-azure-onboarding`
**Purpose:** Onboard new teams to Azure (subscriptions, resource groups, access packages).
**Use when:** A new team needs Azure resources — creates subscription access, resource
groups, approver assignments, and DBA groups.
**Key config:** A module per team with environment, subscription_code, team_name,
cost_center, resource_groups.
**Note:** The `team_name` here is the canonical team identifier other repos and skills must
match exactly. Onboard the team here before onboarding apps to GAP.
**Docs:** Confluence — Azure Onboarding

### `gjensidige/terraform-publicdata`
**Purpose:** Provision Public Data CDN in Azure.
**Use when:** Hosting static/public files via CDN (e.g. design-system assets, public
documents).

## GitHub & CI/CD plumbing

### `gjensidige/terraform-github-repo-credentials`
**Purpose:** Mount OIDC-based credentials into repos as GitHub Actions secrets.
**Use when:** A repo needs to push container images to ACR, run Terraform against Azure,
or authenticate to Azure from GitHub Actions.
**Three mechanisms:**
1. `repos-container-registry-push/` → ACR push (secret:
   `AZURE_CONTAINER_REGISTRY_CLIENT_ID`).
2. `repos-terraform/` → IaC with state-storage access (secrets: `AZURE_*_IAC_CLIENT_ID`,
   `*_SUBSCRIPTION_ID`).
3. `repos-azure-oidc/` → Generic Azure auth (read-only / non-IaC).
**Shared GitHub tokens:** `repos-github-token/common/tokens_*.json` define org-wide tokens
(the `repositorySecretName` is the secret name created on consuming repos);
`repos-github-token/teams/team_*.json` grant them to apps via `"common": [...]`. The
internal definition name differs from the exposed secret name — resolve the secret name
from `repositorySecretName`.
**All use OIDC** — no static secrets to rotate.
**Related skill:** `gap-app-onboarding` Step 7.

### `gjensidige/terraform-github-config`
**Purpose:** GitHub organization settings as code (teams, labels, rulesets, Actions
permissions, runner groups).
**Use when:** Adding a GitHub team, modifying org-wide security rulesets, managing outside
collaborators, or configuring allowed GitHub Actions.
**Key actions:**
- Add team: edit `config/teams.tfvars`.
- Teams integrate with Azure AD groups.
**Provider:** `integrations/github` ~> 6.5.0

## Access management

### `gjensidige/itsec-iam-selfservice`
**Purpose:** Self-service configuration for IBM Security Verify Access (ISVA) / WebSEAL —
junctions, ACLs, groups, firewall rules.
**Use when:** Configuring reverse-proxy junctions, managing access control lists, or setting
up RBAC for web applications behind WebSEAL.
**Key concepts:**
- Junctions: connection points between apps and access control. File path:
  `junctions/<env>/<site>/<team>/<junction-name>.yaml`. The `<site>` is the WebSEAL host
  (e.g. `www.gjensidige.no`, `services.gjensidige.no`, `connect.gjensidige.com`; test
  equivalents use `testgjensidige`). Junction filename derives from `junction_point`: strip
  the leading `/`, replace remaining `/` with `!`.
- ACLs: permissions for users/groups. Referenced ACLs must already exist in the same
  env/domain.
- Groups: logical user collections.
- Teams own their `junctions/.../team-<name>` directories (CODEOWNERS) and self-merge.
**Related skill:** `gap-app-onboarding` Step 8 covers creating a WebSEAL junction as part of
app onboarding.

## Shared applications

Org-wide shared application repos (not team-specific infrastructure).

### `gjensidige/application-portal`
**Purpose:** Customer-facing portal (gjensidige.no logged-in area) — Spring Boot + React.
**Use when:** Modifying routing for SPAs on the customer portal, managing site contexts
(privat/bedrift/megler), or updating frontend micro-app loading.
**Key concepts:** Sites (customer contexts), Filters (request middleware), Routing
Definitions (JSON in `backend/src/main/resources/routing/`).

### `gjensidige/application-portal-internal`
**Purpose:** Internal application portal for serving internal tools/applications.
**Use when:** Adding or managing internally-facing applications.

## Team-owned repo patterns

These differ per team. Discover the concrete repo before acting.

### `<team>-kubernetes-manifests`
**Purpose:** A team's Kubernetes manifests for its applications.
**Use when:** Deploying or configuring your team's apps (resource limits, ingress, secrets,
alerts).
**Structure (varies):** Commonly `apps/<app>/{common.jsonnet, <env>/app.jsonnet,
<env>/params.json}` with Jsonnet templates; some teams use Gappynator `Application`
resources instead. `params.json` is typically updated by CI on release.
**Find it:** In `argocd`, open a sibling app under `applications/<cluster>/team-<team>/` and
read its `repoURL`.

### `<team>-reusable-workflows`
**Purpose:** A team's shared GitHub Actions reusable workflows (e.g. release pipelines).
**Find it:** Look in an existing app repo's `.github/workflows/` for a
`uses: gjensidige/<team>-reusable-workflows/.github/workflows/<file>@<ref>` reference.
**Default building blocks** (for teams without a reusable workflow):
- `gjensidige/docker-build-scan-push-action` — build, scan, push image to ACR.
- `gjensidige/gap-workflow-dispatch-action` — dispatch a release event to the manifests
  repo.

### team application repos
**Purpose:** The source code for a team's services.
**Find it:** Org repo search, or follow references from the team's manifests repo.
