# Query Templates

> The query *shapes* are stable; specific identifiers inside templates (service names, hostnames, procedure names) drift. Per Iron Rule 2 in SKILL.md, **trust the result of a live query over the placeholders here**.

Ready-to-paste PromQL and TraceQL templates for the Grafana MCP. Every quantitative template comes in **two forms**: current value and 7-day baseline, so you can compare before reporting an anomaly. Prefer `quantile_over_time(...[7d:5m])` as the baseline shape — see "Baseline patterns" in SKILL.md for when each shape applies.

Datasource UIDs: Prometheus `prometheus`, Tempo `tempo`. (Loki is not available via the Grafana MCP — use the Grafana UI for log queries.)

## MCP query mechanics (timestamps)

Two `query_prometheus` mechanics that follow from Iron Rule 3 (Oslo-time handling) and are easy to get subtly wrong:

- **Instant queries still require `startTime`.** The MCP tool marks `startTime` as required on *every* call — for an instant query (`queryType="instant"`, which ignores `endTime`/`stepSeconds`) it is the single evaluation timestamp. Always set it: a **live** sweep ("what is broken right now?", §B) evaluates at `startTime="now"`; a **historical** instant query — a mid-window baseline (Iron Rule 1) or a re-run boundary — evaluates at the RFC3339 timestamp inside the window. Sending it empty makes the MCP reject the call, costing a retry on every batch.
- **Converting epoch samples.** Range-query results carry epoch-second timestamps; hand arithmetic on them is where investigations silently drift by ±1 h (observed in testing: a report with every timestamp 40–60 min off). Anchor every conversion: the first sample of a range query equals the query's RFC3339 start time, so derive sample times as `start + N × step` from that anchor — or re-run the boundary of interest as an instant query at an RFC3339 timestamp instead of converting by hand.

---

## A0. Customer edge — IBM WebSEAL

`webseal_ext:requests:rate5m` (internet: customer portals + partner APIs) and `webseal_int:requests:rate5m` (SOA front door + intranet) are **recording rules that are already per-second 5m rates** — sum them directly; for absolute counts use `60 * sum_over_time(...[<window>])` (60 = the rules' eval interval — see §A0.4 for why this, not `avg_over_time × window`). Labels: `service_name` (portal), `junction` (route), `junctioned_server` (backend), `response_code`. Portal classification and label semantics: [`production-environment.md` §2](production-environment.md).

### A0.1. Per-portal RPS (current vs baseline) — detects both error spikes and traffic collapse
```promql
sum by (service_name) (webseal_ext:requests:rate5m)
quantile_over_time(0.5, sum by (service_name) (webseal_ext:requests:rate5m)[7d:5m])
```

### A0.2. Per-portal 5xx ratio (current vs baseline)
```promql
sum by (service_name) (webseal_ext:requests:rate5m{response_code=~"5.."})
  / sum by (service_name) (webseal_ext:requests:rate5m)
# baseline — several portals run a chronic 5xx floor; judge the delta (Iron Rule 1)
quantile_over_time(0.5,
  (sum by (service_name) (webseal_ext:requests:rate5m{response_code=~"5.."})
   / sum by (service_name) (webseal_ext:requests:rate5m))[7d:5m])
```

### A0.3. Drill an affected portal to route + backend (current vs baseline)
```promql
topk(15, sum by (junction, junctioned_server, response_code) (
  webseal_ext:requests:rate5m{service_name="<portal>", response_code=~"5.."}))
# baseline — several junctions error chronically
topk(15, quantile_over_time(0.5, sum by (junction, junctioned_server, response_code) (
  webseal_ext:requests:rate5m{service_name="<portal>", response_code=~"5.."})[7d:5m]))
```
Sparse 5xx series churn in and out of the 5m window — an empty instant result over an incident window calls for a **range query** over that window instead.

### A0.4. Absolute error count over a window (Iron Rule 4)
These rules are a LogQL `rate()` over the WebSEAL log stream (one request = one log line), emitted **one sample per 60 s**, and a `(portal, junction, server, code)` series exists *only* while that combination saw traffic in the trailing 5 m. So the absolute count is `60 * sum_over_time(...)` — **not** `avg_over_time × <window-seconds>`. `avg_over_time` divides by the count of *present* samples, so for a sparse 5xx series (present for a tiny fraction of the window) it overcounts by `1 / (fraction of the window the series existed)` — verified ~110× on a real sparse junction (24 036 vs ~217 true). The two agree only for a dense, always-present series.
```promql
60 * sum by (service_name, junction, junctioned_server, response_code) (
  sum_over_time(webseal_ext:requests:rate5m{
    service_name="<portal>", response_code=~"5.."}[<window>]))
```
`60` is the Loki ruler eval interval (verify per Iron Rule 2: a dense series gives `count_over_time(...[1h]) = 60`); it does **not** scale with `<window>`. For an exact count, run `count_over_time({…} | json | response_code=~"5.." [<window>])` on the Loki log stream in the Grafana UI — the rate rule can only approximate.

### A0.5. GAP handoff chain — WebSEAL junction → Traefik → service graph
For `junctioned_server="<svc>.apps-int.gjensidige.io"` the hostname prefix `<svc>` is the k8s Service name (Traefik `exported_service` shape: `<namespace>-<svc>-<port>@kubernetesgateway`):
```promql
# Leg 2: Traefik
sum by (exported_service, code) (rate(traefik_service_requests_total{
  exported_service=~".*-<svc>-.*", cluster="aks-apps-int-prod-013"}[5m]))
# Leg 3: service graph (then pods via kube_pod_info{pod=~"<svc>.*"})
sum by (client) (rate(traces_service_graph_request_total{server="<svc>"}[5m]))
```
Legs agree in shape (spike timing, code mix); magnitudes differ per leg ([`production-environment.md` §4](production-environment.md)).

### A0.6. SOA front-door decomposition (internal gateway, current vs baseline)
```promql
topk(10, sum by (service_name, junction, junctioned_server) (
  webseal_int:requests:rate5m{service_name=~"prodsoa-.*", response_code=~"5.."}))
# baseline — keep the topk wrapper: unwrapped, the 7d subquery exceeds MCP response limits
topk(10, quantile_over_time(0.5, sum by (service_name, junction, junctioned_server) (
  webseal_int:requests:rate5m{service_name=~"prodsoa-.*", response_code=~"5.."})[7d:5m]))
```

### A0.7. Customer/partner exposure of a set of services (§D3 Signal 1)
```promql
# 24h max_over_time keeps low-traffic portals (e.g. partner.gjensidige.no) in the result
sum by (service_name, junction) (max_over_time(webseal_ext:requests:rate5m{
  junctioned_server=~"(<svc1>|<svc2>)\\.apps-int\\.gjensidige\\.io"}[24h])) > 0
```

---

## A. North-South — Traefik ingress (internal gateway)

Traefik carries all in-cluster ingress — the most sensitive issue *detector*; exposure classification happens at the WebSEAL edge (§A0, SKILL.md Iron Rule 5).

### A1. Per-backend RPS (current)
```promql
topk(20, sum by (exported_service) (
  rate(traefik_service_requests_total{cluster="aks-apps-int-prod-013"}[5m])))
```

### A2. Per-backend RPS (7-day baseline)
```promql
topk(20, sum by (exported_service) (
  rate(traefik_service_requests_total{cluster="aks-apps-int-prod-013"}[7d])))
```

### A3. Per-backend 5xx rate (current vs baseline)
```promql
# current
sum by (exported_service) (rate(traefik_service_requests_total{code=~"5..",
  cluster="aks-apps-int-prod-013"}[5m])) > 0
# baseline (median over 7d)
quantile_over_time(0.5,
  sum by (exported_service) (rate(traefik_service_requests_total{code=~"5..",
    cluster="aks-apps-int-prod-013"}[5m]))[7d:5m])
```

### A3-sweep. Recall-first selection for exhaustive sweep mode
Queries for SKILL.md §B *Exhaustive sweep mode* — rank by **absolute affected requests** under a generous `topk(150)` cap (a response-size guard, not a selector), then hand each candidate to §A top-down.

Traefik 5xx-by-backend — a counter, so absolute count is `increase`:
```promql
topk(150, sum by (exported_service) (increase(traefik_service_requests_total{
  code=~"5..", cluster="aks-apps-int-prod-013"}[<window>])))
```
WebSEAL `webseal_int` sweep and `webseal_ext` portal→junction drill — recording-rule rates, so absolute count is `60 * sum_over_time(...)` (never `rate()`/`increase()` on these, and never `avg_over_time × window` — it overcounts sparse 5xx series; see §A0.4):
```promql
# webseal_int sweep as written; webseal_ext drill: swap the metric, add service_name="<portal>"
topk(150, 60 * sum by (service_name, junction, junctioned_server) (
  sum_over_time(webseal_int:requests:rate5m{response_code=~"5.."}[<window>])))
```
The `60` cancels in the ranking (order is just `sum_over_time`) — it only sets the reported magnitude; using `avg_over_time` here would distort the ranking itself, inflating sparse-but-bursty series above steady higher-volume ones. Why absolute and not a `peak/baseline` ratio, and how to confirm window-aware: SKILL.md §B *Exhaustive sweep mode*.

### A4. p99 latency per backend (current vs baseline)
```promql
histogram_quantile(0.99, sum by (le, exported_service) (
  rate(traefik_router_request_duration_seconds_bucket{
    cluster="aks-apps-int-prod-013"}[5m]))) > 1
# 7d-average p99 per backend — many sit chronically above 1s; a hotspot is a
# backend far above ITS OWN 7d level, not merely above 1s
histogram_quantile(0.99, sum by (le, exported_service) (
  rate(traefik_router_request_duration_seconds_bucket{
    cluster="aks-apps-int-prod-013"}[7d])))
# confirm a single candidate against its 7-day distribution
quantile_over_time(0.95, histogram_quantile(0.99, sum by (le) (
  rate(traefik_router_request_duration_seconds_bucket{
    exported_service=~".*-<svc>-.*"}[5m])))[7d:5m])
```
**Label trap:** `exported_service` on the duration metric carries router-derived names (`httproute-<ns>-<svc>-gw-…-wrr@kubernetesgateway`), on `traefik_service_requests_total` it carries `<ns>-<svc>-<port>@kubernetesgateway`. Exact-value joins across the two silently return empty — filter each with `.*-<svc>-.*`.

### A5. TLS expiry (days)
```promql
(traefik_tls_certs_not_after - time()) / 86400
```

---

## B. East-West (Cilium / Hubble) — L3/L4

### B1. Top namespaces sending flows
```promql
topk(10, sum by (namespace) (
  label_replace(sum by (source) (
    rate(hubble_flows_processed_total{cluster="aks-apps-int-prod-013"}[5m])),
    "namespace","$1","source","([-a-z0-9]+)/.+")))
```

### B2. Top namespaces with DROPPED inbound flows (NetworkPolicy denials etc.)
```promql
topk(10, sum by (namespace) (
  label_replace(sum by (destination) (
    rate(hubble_flows_processed_total{verdict="DROPPED"}[5m])),
    "namespace","$1","destination","([-a-z0-9]+)/.+")))
```

### B3. Cilium drop reasons
```promql
sum by (reason) (rate(cilium_drop_count_total[5m]))
```

### B4. DNS error rate
```promql
# rcode is a string label ("No Error", "Non-Existent Domain", "Server Failure", …),
# not numeric — `rcode!="0"` would include normal responses.
sum by (rcode) (rate(hubble_dns_responses_total{rcode!="No Error"}[5m]))
```

### B5. TCP flag distribution (RST/SYN — connection health)
```promql
sum by (flag) (rate(hubble_tcp_flags_total[5m]))
```

---

## C. East-West / Egress — OTel service-graph

The **single richest** source: `traces_service_graph_*` captures every cross-process call (internal *and* outbound to external systems).

### C1. Service-to-service call graph (current)
```promql
topk(30, sum by (client, server) (rate(traces_service_graph_request_total[5m])))
```

### C2. Per-edge p99 server-side latency
```promql
histogram_quantile(0.99, sum by (le, client, server) (
  rate(traces_service_graph_request_server_seconds_bucket[5m])))
```

### C3. Per-edge p99 client-side latency (includes network)
```promql
histogram_quantile(0.99, sum by (le, client, server) (
  rate(traces_service_graph_request_client_seconds_bucket[5m])))
```

### C4. Per-edge failure rate
```promql
sum by (client, server) (rate(traces_service_graph_request_failed_total[5m]))
  / sum by (client, server) (rate(traces_service_graph_request_total[5m]))
```

### C5. Single-service outbound footprint
```promql
topk(20, sum by (server) (rate(traces_service_graph_request_total{
  client="<service>"}[5m])))
```

### C6. Single-service inbound footprint
```promql
topk(20, sum by (client) (rate(traces_service_graph_request_total{
  server="<service>"}[5m])))
```

### C7. 7-day baseline of any C-series query
Replace `[5m]` with `[7d]` for total volume, or wrap with:
```promql
quantile_over_time(0.5, <expression>[7d:5m])
```

### C8. Frontend plane sweep (Faro frontends) — SKILL.md §B Step 4

Browser-observed API **failure** per frontend. Two reachable signals — both first-party-only (never rank raw Faro errors; see the trap). Rank by absolute first-party error rate (Iron Rule 4 — frontends are low-volume, so a high ratio can be a handful of requests).

**Signal A — Tempo TraceQL (primary; sees CORS preflights + fetches to non-graph hosts).** Auto-scoped to the Faro set by the fingerprint; the `span.http.host` first-party filter is mandatory:
```traceql
{ resource.telemetry.distro.name = "faro-web-sdk" && status = error
  && span.http.host =~ ".*(gjensidige\\.(no|dk|se|com|io)|heihuset\\.no|mistralnett\\.com)$" }
  | rate() by (resource.service.name)
```
The filter anchors on **Gjensidige-owned registrable domains** — browsers fetch the public portal host (`www.gjensidige.*`, intranet `mistral.mistralnett.com`), never the internal `apps-int.gjensidige.io` address. A bare `gjensidige` substring is wrong: it readmits vendor hosts carrying a `gjensidige` label (`gjensidige.piwik.pro`, `gjensidige.humany.net`). Confirm/extend the host set with `tempo_get-attribute-values name=span.http.host filter={ … faro-web-sdk }` (Iron Rule 2 — vendors drift). Baseline by re-running over a window shifted back 7d (same weekday/time) and comparing, or `| compare()`.

**Signal B — Prometheus service-graph error ratio (always-available fallback; works when the Tempo proxy is down).** Naturally first-party — only backend nodes are graph servers — and gives a clean ratio for the anomaly check:
```promql
sum by (client) (rate(traces_service_graph_request_failed_total{client=~"<FRONTENDS>"}[5m]))
  / sum by (client) (rate(traces_service_graph_request_total{client=~"<FRONTENDS>"}[5m]))
quantile_over_time(0.5, (
  sum by (client) (rate(traces_service_graph_request_failed_total{client=~"<FRONTENDS>"}[5m]))
  / sum by (client) (rate(traces_service_graph_request_total{client=~"<FRONTENDS>"}[5m])))[7d:5m])
```

**Signal A vs B answer different questions** (verified — the rankings differ): A ranks by *how many* requests fail (absolute rate, Iron Rule 4 volume); B by *what fraction* fail vs baseline (is it broken). Use both — `gje-claim-details` was mid-pack on absolute rate but top on ratio (22.4% now vs 6.8% 7-day baseline → ~3.3× anomalous).

**Traps** (full detail in `frontends.md`):
- **Third-party host noise** (the real false-positive source) — most raw Faro errors are ad/analytics/consent fetches (`doubleclick`, `usercentrics`, `hotjar`, …) failing on ad-blockers. Observed: `dk-policy-overview` 0.87 → 0.006 err/s after the host filter (~99% third-party). Signal A needs the filter; Signal B is immune.
- **`max`/individual span durations** — rare clock-skew/suspended-tab spans (~106/day across all frontends, up to ~953 days) corrupt `max`, **not** quantiles: frontend p99 is robust from either source (raw-span ≈ 3.1 s, histogram ≈ 8.5 s for `gje-claim-details`). Guard only `max`-style reads with `duration < 60s`.

**Drill:** switch to §A on the worst frontend and pull its error traces → the failing backend edge — e.g. `gje-claim-details` → `api-claim-private-dk` → `gapi-adapter-*-idit`, failing spans pinned at a ~65s timeout ceiling.

### C9. Azure data-plane probe (per-service error rate) — SKILL.md §B Confirmation probes

A **confirmation/attribution** probe, not a detector — run it once a candidate's degraded downstream edge (§A Step 3 / §B Step 3) lands on an Azure backend, or when a cluster of unrelated services degrades together (shared data backend = classic common cause). Many domain services depend on per-domain Azure backends that never appear in the on-prem/SaaS cores sweep. Baseline any spike with `quantile_over_time(...[7d:5m])` (Iron Rule 1) before calling it the cause; resolve the per-domain instance from the hostname (`gpm-{domain}-*` / `gpm-cpo-{domain}-*` — [`production-environment.md` §5](production-environment.md)).
```promql
# Per-Azure-service error rate (current) — PostgreSQL / Azure SQL / Redis / Blob / Key Vault / Service Bus
sum by (server) (rate(traces_service_graph_request_failed_total{
  server=~".*\\.(postgres\\.database|servicebus|redis\\.cache|blob\\.core|vault)\\.(azure|windows)\\.(com|net)"}[5m]))
/ sum by (server) (rate(traces_service_graph_request_total{
  server=~".*\\.(postgres\\.database|servicebus|redis\\.cache|blob\\.core|vault)\\.(azure|windows)\\.(com|net)"}[5m]))
```

---

## D. Per-core diagnostics

### D1. Volume + error rate to each core (current vs baseline)
```promql
# current volume per core
sum by (server) (rate(traces_service_graph_request_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m]))

# 7-day baseline
sum by (server) (rate(traces_service_graph_request_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[7d]))

# per-core error rate
sum by (server) (rate(traces_service_graph_request_failed_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m]))
  / sum by (server) (rate(traces_service_graph_request_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m]))
```

### D2. S2000 — direct DB2 traffic
```promql
# spanmetrics has no db.name/db.statement labels — the procedure name is in span_name
# (format: "CALL PROD.<family>"). Filter on the S2000 procedure family.
sum by (service, span_name) (rate(traces_spanmetrics_calls_total{
  span_name=~"CALL PROD\\.E.*SP"}[5m]))

# WHICH stored procedures are failing (S2000 E*SP + GK GK*P in one sweep).
# status_code IS a spanmetrics label — this is how you find the failing procs.
sum by (service, span_name) (rate(traces_spanmetrics_calls_total{
  span_name=~"CALL PROD\\..*", status_code="STATUS_CODE_ERROR"}[5m]))
```

### D2b. Party master — GK (legacy, DB2) and GPM (new, Azure PG)
```promql
# GK volume — callers using legacy stored procedures (span_name carries the procedure)
sum by (service, span_name) (rate(traces_spanmetrics_calls_total{
  span_name=~"CALL PROD\\.GK.*"}[5m]))

# GK bridge service health
sum (rate(traces_service_graph_request_total{server="party-party-cs-service"}[5m]))
histogram_quantile(0.99, sum by (le) (
  rate(traces_service_graph_request_server_seconds_bucket{
    server="party-party-cs-service"}[5m])))

# GPM volume — modern path via Azure PostgreSQL
# (server matches the pattern; the live instance suffix changes with failovers)
sum (rate(traces_service_graph_request_total{
  client="party-gpm-service",
  server=~"gpm-cpo-party-[a-z]+-prod-psql-.*\\.postgres\\.database\\.azure\\.com"}[5m]))

# GPM service health
sum (rate(traces_service_graph_request_total{server="party-gpm-service"}[5m]))
histogram_quantile(0.99, sum by (le) (
  rate(traces_service_graph_request_server_seconds_bucket{
    server="party-gpm-service"}[5m])))

# Side-by-side error rate — both party masters
sum (rate(traces_service_graph_request_failed_total{server="party-party-cs-service"}[5m]))
  / sum (rate(traces_service_graph_request_total{server="party-party-cs-service"}[5m]))
sum (rate(traces_service_graph_request_failed_total{server="party-gpm-service"}[5m]))
  / sum (rate(traces_service_graph_request_total{server="party-gpm-service"}[5m]))
```

### D3. F2100 — by gateway path
```promql
sum by (server) (rate(traces_service_graph_request_total{
  server=~".*\\.fdc\\.dk.*"}[5m]))
```

### D4. Archive — both planes split
```promql
# E-Archive (long-term storage)
sum (rate(traces_service_graph_request_total{server="earkiv.evry.com"}[5m]))
# OnDemand / eDok (dynamic doc generation)
sum (rate(traces_service_graph_request_total{server="wsedok.ec.evry.com"}[5m]))
```

### D5. External HTTP edge — WHICH endpoints are failing (method + path)
Service graph + spanmetrics name the failing **host**, never the endpoint (spanmetrics `span_name` is the bare method — `GET`/`POST`/…), so this is a **trace** query — for any external HTTP `server` (the cores **and** the §10 edges: BankID, Signicat, partner APIs, …). Scheme varies by caller, so select both; `url.path` is often empty while `url.full` is set. Rationale + reporting rule: SKILL.md §C.
```traceql
# Failing endpoints on an external HTTP edge (swap the host regex per edge — see G5)
{ span.server.address =~ ".*sapiensmgs\\.com.*" && status = error }
  | select(span.http.request.method, span.http.method, span.url.full, span.url.path, span.http.target, span.http.response.status_code, span.http.status_code)

# Also catch 4xx the caller TOLERATED (won't be status=error — e.g. IDIT 422 on a not-found lookup)
{ span.server.address =~ ".*sapiensmgs\\.com.*" && span.http.response.status_code >= 400 }
  | select(span.http.request.method, span.url.full, span.http.response.status_code)
```
Normalise the volatile path segments (`/idit-web/api/policy/{id}`, not the raw URL with its IDs + query string), then report each as `<METHOD> <normalised-path> → <status>`.

Companion metric — WHICH **method** is failing on the degraded caller (no path here — that's why the drill above is a trace query); set the selector to the calling service:
```promql
sum by (service, span_name, status_code) (rate(traces_spanmetrics_calls_total{
  service="<calling-service>", span_kind="SPAN_KIND_CLIENT"}[5m]))
```

---

## E. Async — Kafka (Confluent)

### E1. Topic throughput
```promql
sum by (topic) (rate(confluent_kafka_server_received_records[5m]))
sum by (topic) (rate(confluent_kafka_server_sent_records[5m]))
```

### E2. Consumer lag (the canonical Kafka-stall signal)
```promql
# Label is consumer_group_id (Confluent Cloud naming), not consumer_group —
# the wrong name still parses but collapses all groups together.
max by (topic, consumer_group_id) (confluent_kafka_server_consumer_lag_offsets)
```

### E3. S2000 outbox volume by topic
```promql
sum by (topic) (rate(confluent_kafka_server_received_records{
  topic=~"o\\.gfno\\.s2000\\..*"}[5m]))
```

---

## F. Pod / deployment health

### F1. Replica gap (unhealthy deployments)
```promql
kube_deployment_status_replicas_ready / kube_deployment_status_replicas < 1
```

### F2. Restart rate (current vs baseline)
```promql
# current
sum by (namespace, pod) (rate(kube_pod_container_status_restarts_total[1h])) > 0
# baseline
quantile_over_time(0.95,
  sum by (namespace, pod) (rate(kube_pod_container_status_restarts_total[1h]))[7d:1h])
```

### F3. OOMKilled in the last hour
`kube_pod_container_status_last_terminated_reason` is a **gauge** holding `1` for as long as OOMKilled is the container's *last* termination reason — it stays `1` long after the kill. `increase()`/`rate()` on it is wrong (functions doc: never on a gauge): a flat `1` series has increase `0`, so the kill is silently dropped (verified: 17 containers in OOMKilled state, `increase(...[1h]) > 0` returned empty). Detect a *fresh* OOM by using the reason gauge as a filter and taking the increase of the restart **counter**:
```promql
kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1
  and on (namespace, pod, container)
increase(kube_pod_container_status_restarts_total[1h]) > 0
```
For "which containers are *currently* in an OOMKilled state" (includes stale kills from before the window), read the gauge directly — `max_over_time` guards against scrape gaps:
```promql
max_over_time(kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}[1h]) > 0
```

### F4. Per-pod working-set memory (GB)
```promql
sum by (namespace, pod) (container_memory_working_set_bytes{
  container!="", container!="POD"}) / 1024 / 1024 / 1024
```

---

## G. TraceQL — drill into Tempo

### G1. Slow inbound on a service
```traceql
{ resource.service.name = "<name>" && kind = server && duration > 2s }
```

### G2. Errors anywhere
```traceql
{ status = error }
```

### G3. Slow stored procedure on S2000
```traceql
{ span.db.system = "db2" && span.db.name = "zaz23400" && duration > 500ms }
```

### G3b. WHY a stored procedure is failing — read the DB2 SQLCODE
```traceql
# All failing DB2 calls on the mainframe (the exception event carries the SQLCODE)
{ span.db.name = "zaz23400" && status = error }

# Surface the SQLCODE for a specific failing proc set (proc names illustrative — discover the live failing set with the D2 status_code query first)
{ name =~ "CALL PROD\\.(EGFE28SP|EDE012SP)" && event.exception.message =~ ".*SQLCODE=.*" }

# Confirm ONE SQLCODE explains every error in a proc family (expect zero results if it does)
{ name =~ "CALL PROD\\..*SP" && status = error
  && event.exception.message !~ ".*SQLCODE=-440.*" }
```

`traceql-search` returns only the matched span's attributes — to read the full message, filter on `event.exception.message` (as above) or `tempo_get-trace` one trace. The `exception` event holds `exception.type` + `SQLCODE` / `SQLSTATE` / `SQLERRMC`. Interpret the code with the SQLCODE table in [`production-environment.md`](production-environment.md) §3.

### G4. Calls to a specific S2000 stored procedure
```traceql
{ span.db.statement =~ ".*PROD\\.ESK62NSP.*" }
```

### G4b. GK (legacy party master) stored-procedure calls
```traceql
# All GK procedures (both GKG* and GKH* families)
{ span.db.system = "db2" && span.db.name = "zaz23400"
  && span.db.statement =~ ".*PROD\\.GK[GH]?.*P.*" }

# Slow GK calls
{ span.db.system = "db2" && span.db.name = "zaz23400"
  && span.db.statement =~ ".*PROD\\.GK.*" && duration > 500ms }

# A specific GK procedure (e.g. customer-lookup GKG414P)
{ span.db.statement =~ ".*PROD\\.GKG414P.*" }
```

### G4c. GPM (new party master) Azure PG traffic
```traceql
{ span.db.system = "postgresql" && span.db.name = "gpmdb" }
{ resource.service.name = "party-gpm-service" && kind = client }
```

### G5. All traffic to a specific core
```traceql
{ span.server.address =~ ".*\\.fdc\\.dk.*" }            # F2100
{ span.server.address =~ ".*sapiensmgs\\.com.*" }       # IDIT
{ span.server.address =~ ".*\\.dynamics\\.com" }        # Dynamics
{ span.server.address =~ "(earkiv|wsedok\\.ec)\\.evry\\.com" }  # Archive
{ span.server.address =~ ".*\\.mistralnett\\.com.*" }   # mistralnett.com — SOA bus, DataPower, app hosts (many systems)
```
To surface the **endpoint** (method + path) rather than just the host, append the `select` from §D5 (and see §D5 for the 4xx-tolerated variant and the reporting format).

### G6. Cross-system flows (traces that touched both X and Y)
```traceql
# IDIT call + Postgres call in same trace
{ span.server.address =~ ".*sapiensmgs.*" } && { span.db.system = "postgresql" }

# S2000 stored proc + Dynamics CRM
{ span.db.name = "zaz23400" } && { span.server.address =~ ".*dynamics\\.com" }
```

### G7. Slow database queries (any engine)
```traceql
{ span.db.system != nil && duration > 500ms }
```

### G8. Kafka publish errors
```traceql
{ span.messaging.system = "kafka" && status = error }
```

### G9. Inbound scanned mail via Kofax
```traceql
{ resource.service.name = "kda-archive-kofax-a2a" }
```

### G10. Login plane (EAI) — see [`production-environment.md` §11](production-environment.md)
```traceql
# Failing logins, any market — the trace names the broken leg (IdP, Redis state store, enrichment)
{ resource.service.name =~ "itsec-eai-gf(no|dk|se)" && kind = server && status = error }

# Who is bounced to the login page, and from which URL (WebSEAL local-response params)
{ resource.service.name =~ "itsec-eai-gf(no|dk|se)" && name = "GET /eai/op" } | select(span.url.query)

# WebSEAL error-page bounces with the failure code + failing URL. These answer
# HTTP 200 (the error page rendered), so status=error / error-rate SLIs miss them
{ resource.service.name =~ "itsec-eai-gf(no|dk|se)" && span.url.query =~ ".*TAM_OP=error.*" } | select(span.url.query, span.http.response.status_code)

# Failed login flow — both BankID and the authentication chain
{ span.server.address =~ ".*bankid\\.no" } && { status = error }
```

---

## H. Quick recipes

### H1. "Is service X anomalous right now?"
```promql
# Run current + 7d baseline for: RPS, p99, error_rate.
# Use quantile_over_time(...[7d:5m]) for the baseline, NOT rate(...[7d]) — the
# latter smooths over nightly dips and inflates daytime traffic (see Iron Rule 1).
sum (rate(traces_service_graph_request_total{server="X"}[5m]))
quantile_over_time(0.5,
  sum (rate(traces_service_graph_request_total{server="X"}[5m]))[7d:5m])
histogram_quantile(0.99, sum by (le) (
  rate(traces_service_graph_request_server_seconds_bucket{server="X"}[5m])))
quantile_over_time(0.95, histogram_quantile(0.99, sum by (le) (
  rate(traces_service_graph_request_server_seconds_bucket{server="X"}[5m])))[7d:5m])
sum (rate(traces_service_graph_request_failed_total{server="X"}[5m]))
  / sum (rate(traces_service_graph_request_total{server="X"}[5m]))
```

### H2. "Why is service X slow?" — find degraded downstream
```promql
# 1. Outbound footprint
topk(10, sum by (server) (rate(traces_service_graph_request_total{client="X"}[5m])))
# 2. Per-edge p99
histogram_quantile(0.99, sum by (le, server) (
  rate(traces_service_graph_request_client_seconds_bucket{client="X"}[5m])))
# 3. Pick the edge with highest p99 → repeat H1 against that server
```

### H3. "Are we dropping inbound traffic somewhere?"
```promql
topk(10, sum by (namespace) (
  label_replace(sum by (destination) (
    rate(hubble_flows_processed_total{verdict="DROPPED"}[5m])),
    "namespace","$1","destination","([-a-z0-9]+)/.+")))
# rcode is a string label — see B4 for the gotcha
sum by (rcode) (rate(hubble_dns_responses_total{rcode!="No Error"}[5m]))
sum by (reason) (rate(cilium_drop_count_total[5m]))
```

### H4. "Which clients depend on this server X?"
```promql
topk(150, sum by (client) (rate(traces_service_graph_request_total{server="X"}[<window>])))
```
Blast radius — over the incident window, completeness-guard cap (a wide cross-domain server fans in past a top-30 list; see §D1). Sort by impact; §D2 separates cascaded from contained.

### H5. Full §D blast-radius sweep (run after every root cause)

Given a confirmed-broken server `X`:

```promql
# D1 — all dependent callers over the incident window (completeness-guard cap, see §D1)
topk(150, sum by (client) (rate(traces_service_graph_request_total{server="X"}[<window>])))

# D2 — error rate of each caller over the window vs 7-day baseline (replace <clients> with the regex)
sum by (server) (rate(traces_service_graph_request_failed_total{server=~"<clients>"}[<window>]))
  / sum by (server) (rate(traces_service_graph_request_total{server=~"<clients>"}[<window>]))
quantile_over_time(0.5, (
  sum by (server) (rate(traces_service_graph_request_failed_total{server=~"<clients>"}[5m]))
  / sum by (server) (rate(traces_service_graph_request_total{server=~"<clients>"}[5m]))
)[7d:5m])

# D3 — customer/partner exposure of any cascaded client (WebSEAL ext, see A0.7)
sum by (service_name, junction) (max_over_time(webseal_ext:requests:rate5m{
  junctioned_server=~"(<clients>)\\.apps-int\\.gjensidige\\.io"}[24h])) > 0
# …and the Faro-frontend signal (§D3 Signal 2 in SKILL.md). Over the <window>, NOT [5m]
# — a frontend that called the service earlier but has since backed off drops from a snapshot.
sum by (server) (rate(traces_service_graph_request_total{
  server=~"<clients>", client=~"<FRONTENDS regex>"}[<window>])) > 0
```

