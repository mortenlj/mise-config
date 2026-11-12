---
name: azure-subscription-routing
description: 'Look up Azure subscription IDs and decide which subscription to investigate for Gjensidige and GMG AKS environments. USE WHEN: running az/azure-mcp/aks-mcp queries; needing a subscription ID for tools-prod/tools-test/apps-prod/apps-test/lab/gmg-prod/gmg-test; debugging shared networking, DNS, firewall, private endpoints, route tables, load balancers, or VNET peering (Hub subscriptions); investigating shared tooling or management-plane dependencies (Management subscriptions). DO NOT USE FOR: Kubernetes-side (kubectl) investigation — use the cluster context instead.'
---

# Azure Subscription Routing

Use the AKS **context** for Kubernetes-side investigation; use the subscription table
below for Azure-side (`az` / azure-mcp / aks-mcp) investigation.

## Routing Logic

- Start in the subscription that owns the affected cluster family or platform service.
- Expand to a **Hub** subscription for shared networking, DNS, firewall, private endpoint,
  route table, load balancer, or peering issues.
- Expand to a **Management** subscription for shared tooling, platform services, and
  management-plane dependencies.
- Expand to **Legacy** or **BI Dataplatform** only when the symptom clearly points there.

## Subscription Reference

| Group | Subscription | Subscription ID | Tenant | Use For |
|---|---|---|---|---|
| Gjensidige Test | Gjensidige Test Management | `6a9002a7-bdae-47e8-9523-e0f3fff9a472` | `9c644eac-5362-44db-8e9c-b2be20cee933` | `tools-test` and shared test management resources |
| Gjensidige Test | Gjensidige Test Modern | `2e93682c-15a2-4d44-bd12-38b5dca351cd` | `9c644eac-5362-44db-8e9c-b2be20cee933` | `apps-test`, `lab`, and test app resources |
| Gjensidige Test | Gjensidige Test Hub | `98665394-d016-4774-8b4b-ce4c774843cb` | `9c644eac-5362-44db-8e9c-b2be20cee933` | Shared test hub networking and connectivity |
| Gjensidige Test | Gjensidige Test Legacy | `d421342f-b70c-4a9e-b906-f6052c301af1` | `9c644eac-5362-44db-8e9c-b2be20cee933` | Legacy dependencies when relevant |
| Gjensidige Test | Gjensidige Test BI Dataplatform | `2a6255c7-4e5b-4547-9c71-cc92fce76c2a` | `9c644eac-5362-44db-8e9c-b2be20cee933` | BI and dataplatform dependencies when relevant |
| Gjensidige Prod | Gjensidige Production Management | `9dad2cca-4b60-4c83-95f5-d32a0ff8f0e1` | `80184e22-072c-440e-a8a9-22f52b82646d` | `tools-prod` and shared prod management resources |
| Gjensidige Prod | Gjensidige Production Modern | `8d5ce0ed-72d6-4a81-9a73-a1335a1b01f1` | `80184e22-072c-440e-a8a9-22f52b82646d` | `apps-prod` and prod app resources |
| Gjensidige Prod | Gjensidige Production Hub | `4570d9c1-81f0-439f-afd3-03cac2ae01b5` | `80184e22-072c-440e-a8a9-22f52b82646d` | Shared prod hub networking and connectivity |
| Gjensidige Prod | Gjensidige Production Legacy | `7e620b6a-0a6a-42b0-a300-9f382fd43100` | `80184e22-072c-440e-a8a9-22f52b82646d` | Legacy dependencies when relevant |
| Gjensidige Prod | Gjensidige Production BI Dataplatform | `a050c898-659f-43be-89d2-4119720bc771` | `80184e22-072c-440e-a8a9-22f52b82646d` | BI and dataplatform dependencies when relevant |
| GMG | GMG Apps Devtest | `1ab7b06a-acb7-48e8-899c-f6f441cb1ebe` | `3e82bd4c-f506-48c5-95df-6b6d6d97ed98` | `gmg-test` and GMG dev/test app resources |
| GMG | GMG Apps Production | `57abebb0-3e84-4e90-92b0-6f9b09df2bf0` | `3e82bd4c-f506-48c5-95df-6b6d6d97ed98` | `gmg-prod` and GMG prod app resources |
| GMG | GMG Hub Devtest | `8b70cbb1-8d41-4b56-b152-c517dc6694bc` | `3e82bd4c-f506-48c5-95df-6b6d6d97ed98` | GMG dev/test shared networking and hub resources |
| GMG | GMG Hub Production | `c8c1c92d-fdc1-4d93-af1e-b5a8c1fb66b5` | `3e82bd4c-f506-48c5-95df-6b6d6d97ed98` | GMG prod shared networking and hub resources |

## Tenants

| Tenant | ID | Clusters |
|---|---|---|
| Gjensidige Test | `9c644eac-5362-44db-8e9c-b2be20cee933` | `apps-test`, `lab`, `tools-test` |
| Gjensidige Prod | `80184e22-072c-440e-a8a9-22f52b82646d` | `apps-prod`, `tools-prod` |
| GMG | `3e82bd4c-f506-48c5-95df-6b6d6d97ed98` | `gmg-prod`, `gmg-test` |

## Command Form

Place the read verb immediately after `az`, then pass flags:

```bash
az aks list --subscription <id>          # not: az --subscription <id> aks list
```
