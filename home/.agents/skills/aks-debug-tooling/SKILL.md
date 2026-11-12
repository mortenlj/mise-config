---
name: aks-debug-tooling
description: 'Recipes for inspecting AKS clusters and running pods without modifying or restarting them. USE WHEN: you cannot reach a cluster-internal resource directly (DNS, connectivity, Azure Blob access from inside the cluster); you need to inspect a running application pod''s process/network state in-place; you need a standing debug pod with network utilities; you need to observe network flows/drops with hubble observe. Covers the system-debug platform-debug pod, ephemeral debug containers, and Hubble network observability via cilium-agent. All actions here are read-only and non-destructive.'
---

# AKS Debug Tooling

Read-only, non-destructive cluster inspection recipes. Safe to run without confirmation.

## Standing debug pod (`platform-debug`)

Every cluster has `deployment/platform-debug` in namespace `system-debug` — a standing pod
with common network/debug utilities. Use it for cluster-internal checks (DNS, connectivity,
Azure Blob access, etc.) when you can't reach a resource directly:

```bash
kubectl exec -it deploy/platform-debug -n system-debug --context <name> -- <cmd>
```

Examples:

```bash
# DNS resolution inside the cluster
kubectl exec deploy/platform-debug -n system-debug --context <name> -- nslookup loki-gateway.system-loki.svc

# HTTP reachability of an in-cluster service
kubectl exec deploy/platform-debug -n system-debug --context <name> -- curl -sv http://mimir-distributed-gateway.system-mimir.svc/ready
```

> **Azure Blob note:** storage accounts are reachable only via private endpoint, not from a
> laptop. Perform blob operations (`az storage blob ...`, `azcopy`) from the debug pod. Add
> `--num-results '*'` to `az storage blob list` — it truncates at 5000 results by default.
> In shell loops like `while read ... done < file`, redirect the `azcopy`/`az` command's stdin
> from `/dev/null` — otherwise it consumes the rest of the manifest from stdin and silently
> skips most items.

## Ephemeral debug container (inspect a running app pod in place)

To debug a running application pod **without** exec'ing into the app container or restarting
it, attach an ephemeral debug container. It shares the target pod's namespaces (network, PID)
so you can inspect the app's process/network state without modifying it:

```bash
kubectl debug -it <pod> -n <namespace> --context <name> \
  --image="gjensidige.azurecr.io/platform/debug@sha256:f0efb274fd1e0a7f2c5cbc6f2c38341f62c491fc4e1f4101fe59a7846d890936" \
  --custom=<(echo '{"securityContext":{"readOnlyRootFilesystem":true,"runAsNonRoot":false,"runAsUser":10001}}') \
  --profile=restricted
```

## Hubble network observability (`hubble observe`)

Don't use the local `hubble` CLI against `hubble-relay` — it requires a port-forward plus
per-cluster mTLS certs that break on every blue/green cluster upgrade (new Cilium CA). Instead,
exec into the `cilium-agent` pod on the relevant node: it runs its own local Hubble server on a
Unix socket, so `hubble observe` works instantly with zero TLS/config, on any cluster:

```bash
kubectl exec -n kube-system <cilium-pod> --context <name> -- hubble observe --namespace <ns> --verdict DROPPED --last 100
```

Find the right `cilium-agent` pod:

```bash
# resolve the node a workload runs on, then find that node's cilium pod
kubectl get pod <pod> -n <namespace> --context <name> -o jsonpath='{.spec.nodeName}'
kubectl get pods -n kube-system -l k8s-app=cilium --context <name> --field-selector spec.nodeName=<node> -o name
```

Caveat: results are scoped to that node only (flows visible to that node's agent) — pick the
node hosting the workload you care about rather than guessing.

## Command form (aks-mcp readonly mode)

Place the read verb immediately after `kubectl`, then pass flags:

```bash
kubectl get pods -n <namespace> --context <name>   # not: kubectl --context <name> get pods
```
