---
name: hubble-relay-local
description: "Use when: querying Cilium Hubble Relay locally, investigating policy-denied or dropped Kubernetes flows, configuring the local Hubble CLI through a proxied Hubble Relay, checking Cilium NetworkPolicy drops, or aggregating recent Hubble flows."
---

# Local Hubble Relay

Use the locally installed `hubble` CLI with its built-in Kubernetes Relay port
forward. Do not create diagnostic Pods, run `kubectl exec`, or manually start a
separate `kubectl port-forward` for normal flow queries.

The local profile keeps the Relay endpoint on `localhost:4245`, while
`port-forward: true` makes the CLI create and clean up its own temporary proxy
for each command.

## Prerequisites

- `hubble`, `kubectl`, `jq`, `openssl`, and `base64` are installed locally.
- Kubernetes access permits `get` on the existing Hubble Relay TLS Secrets in
  `kube-system`.
- The target cluster has `hubble-relay` in `kube-system`.
- Treat the Relay client key as a secret. Keep it out of repositories, terminal
  output, and chat messages.

## Configure the Local Client

Run this once per cluster, replacing the context when necessary. It reads only
existing Kubernetes Secrets; it does not create or modify cluster resources.

```sh
set -e
hubble_dir="$HOME/Library/Application Support/hubble"
mkdir -p "$hubble_dir"
chmod 700 "$hubble_dir"

kubectl -n kube-system get secret hubble-relay-client-certs \
  -o jsonpath='{.data.tls\.crt}' | base64 -d > "$hubble_dir/relay-client.crt"
kubectl -n kube-system get secret hubble-relay-client-certs \
  -o jsonpath='{.data.tls\.key}' | base64 -d > "$hubble_dir/relay-client.key"
kubectl -n kube-system get secret hubble-relay-client-certs \
  -o jsonpath='{.data.ca\.crt}' | base64 -d > "$hubble_dir/relay-ca.crt"
chmod 600 "$hubble_dir/relay-client.crt" \
  "$hubble_dir/relay-client.key" "$hubble_dir/relay-ca.crt"

hubble config set port-forward true
hubble config set kube-context <cluster-context>
hubble config set kube-namespace kube-system
hubble config set tls true
hubble config set tls-ca-cert-files "$hubble_dir/relay-ca.crt"
hubble config set tls-client-cert-file "$hubble_dir/relay-client.crt"
hubble config set tls-client-key-file "$hubble_dir/relay-client.key"
hubble config set tls-server-name hubble-relay.hubble-relay.cilium.io
```

Verify the connection:

```sh
hubble config view
hubble status
```

A successful result reports `Healthcheck ... Ok`, flow-buffer capacity, and
connected/unavailable nodes. Always record unavailable nodes: Relay cannot
return their retained buffers, so an empty result is not proof that no flow was
dropped there.

### Discover the TLS Server Name

Do not set `--tls-allow-insecure`. If the expected Relay server name is not
known, read the public server certificate and use its SAN:

```sh
kubectl -n kube-system get secret hubble-relay-server-certs \
  -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | openssl x509 -noout -subject -ext subjectAltName
```

## Query Recent Drops

Hubble Relay returns a bounded, per-node retained buffer, not durable flow
history. Query promptly after reproducing the behavior. Use `--since` plus
`--all` so the result covers the requested window rather than only the default
last 20 records per node.

```sh
hubble observe \
  --since 15m \
  --all \
  --namespace <namespace> \
  --verdict DROPPED \
  --output json \
  --print-policy-names \
  > /tmp/hubble-drops.json
```

The output can include `node_status` and `lost_events` records. Exclude these
when analyzing actual flows:

```sh
jq -s '[.[] | select(.flow) | .flow]' /tmp/hubble-drops.json
```

## Aggregate Policy Denials

Group flows into policy-ready tuples before adding any rules. The following
reports source application, destination application, destination port,
direction, reason, and matched policy:

```sh
jq -r '
  select(.flow) | .flow
  | [
      (.source.namespace // "-"),
      (.source.labels // []
        | map(select(startswith("k8s:app=")) | sub("^k8s:app="; ""))
        | first // .source.pod_name // "-"),
      (.destination.namespace // "-"),
      (.destination.labels // []
        | map(select(startswith("k8s:app=")) | sub("^k8s:app="; ""))
        | first // .destination.pod_name // .destination.ip // "-"),
      (.l4.TCP.destination_port // .l4.UDP.destination_port // "-" | tostring),
      (.traffic_direction // "-"),
      (.drop_reason_desc // "-"),
      (.policy_match_name // "-")
    ] | @tsv
' /tmp/hubble-drops.json | sort | uniq -c | sort -rn
```

For every `POLICY_DENIED` tuple, inspect both sides before editing manifests:

1. Source workload egress selector and destination port.
2. Destination workload ingress selector and port.
3. Actual Pod labels, especially whether selectors need `k8s:app` rather than
   `app`.
4. Whether the generated CiliumNetworkPolicy exists in the live namespace.
5. Any Cilium transparent mTLS redirect to `15008/TCP`; allow it only when the
   associated application connection is explicitly required.

## Validate a Policy Change

1. Render the affected Jsonnet manifests locally.
2. Assert that both source egress and destination ingress include the observed
   port and matching labels.
3. Let Argo CD reconcile the manifests.
4. Restart or reproduce the affected workload flow.
5. Run the same `hubble observe` query over a fresh 10 to 15 minute window.
6. Confirm the specific `POLICY_DENIED` tuple has disappeared before widening
   any policy.

Do not add broad namespace-wide, CIDR-wide, or all-port allow rules merely to
silence Hubble. Keep each rule limited to the observed workload identity,
destination, and protocol/port.

## Common Failures

- `connection refused` to `localhost:4245`: enable `port-forward: true` and set
  the correct Kubernetes context. Do not start a persistent manual port-forward.
- `error reading server preface: EOF`: Relay requires mTLS; configure the CA,
  client certificate, client key, and TLS server name as above.
- `NODE_UNAVAILABLE`: the Relay cannot query that node's buffer; repeat after
  it reconnects or inspect the workload's node coverage.
- `lost_events`: Hubble's ring buffer overflowed; narrow the timeframe, capture
  immediately after reproduction, and treat absence of an event as inconclusive.
- Source policy appears correct but drops persist: check destination ingress
  and live rendered-policy presence. Jsonnet operator precedence can omit a
  resource branch if conditional list concatenation is not parenthesized.
