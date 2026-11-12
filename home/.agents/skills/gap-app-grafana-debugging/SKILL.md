---
name: gap-app-grafana-debugging
description: >
  Debug the Gjensidige Application Platform (GAP) production runtime via the
  Grafana MCP (Prometheus, Tempo, Hubble/Cilium). Use when a GAP-hosted service
  is slow, failing, returning 5xx, spiking in latency, or "acting weird"; when
  an incident's starting service or domain is unclear; for broad health checks
  ("anything wrong right now?"); for tracing flows end to end (WebSEAL edge →
  Traefik → domain → core); for attributing latency or errors to a core system
  (DB2/S2000 SP failures, SQLCODE errors, bare-IP backends), the Azure data
  plane, Kafka/Confluent, or a public-site CMS tenant; for portal
  login/authentication failures (the per-market EAI plane — BankID / OIDC
  brokers); or pinpointing which customer/partner portal is affected via the
  IBM WebSEAL edge (webseal_ext/webseal_int). Covers targeted ("debug this
  service") and broad ("something is wrong, where do I start?") workflows, with
  baseline comparison so chronically noisy services aren't mistaken for active
  incidents.
---

# Debugging GAP via Grafana

Systematic, evidence-driven workflow for debugging the Gjensidige Application Platform (GAP) production runtime using the Grafana MCP — Prometheus (metrics), Tempo (traces), and Hubble/Cilium for L3/L4. Logs (Loki) are not exposed through the MCP; if logs are needed, switch to the Grafana UI for that step.

## Iron Rule 1: Compare to baseline before reporting an issue

Many production services run with a **non-trivial steady-state error rate, latency tail, or restart frequency**. Reporting "service X has 1% errors" without checking whether 1% is its normal level is a false positive.

> Every quantitative finding ("error rate is N%", "latency is Ns", "M req/s") MUST be confirmed against a historical baseline (typically last 7 days) **before** being stated as an issue.

If the current value is within 1–2σ of the 7-day distribution, it is the **normal situation** — note it as context, do not call it the cause.

**No exceptions:**
- Not for "obvious" spikes
- Not because the service name sounds important
- Not because a customer complained (their complaint may be downstream)

### Baseline patterns: which to use when

Three shapes appear in this skill and they are not interchangeable:

- **`quantile_over_time(<expr>[7d:5m])`** — the *distribution* of 5-minute values across the last 7 days. **Use this when asking "is the current 5-minute value anomalous?"** The 5-minute resolution preserves diurnal and weekly patterns, so a quiet-at-night service does not always look "below baseline" during business hours. This is the canonical anomaly-check pattern.
- **`<expr> offset 7d`** — the same metric exactly one week ago. Use for **same-time-of-week** comparison, especially traffic-volume questions where weekly seasonality dominates (Monday morning vs. Saturday night).
- **`rate(<metric>[7d])`** — the *average* rate over the whole 7-day window. **Do not use this as a magnitude anomaly baseline** — it smooths over nightly dips and makes daytime traffic always look elevated. Two legitimate uses only: a rough "how big is this normally" sanity check, and **set-membership** comparison (which backends/labels appear at all over 7d vs. now — e.g. the §B Step 2 "new hotspot" check). For *"is this 5-minute value anomalous?"*, always use `quantile_over_time(...[7d:5m])` instead.

When in doubt: use `quantile_over_time(...[7d:5m])`.

**Historical incidents:** when investigating a past window, evaluate baseline subqueries **at a timestamp inside the window** (instant query with the evaluation time set to e.g. mid-window), so the 7-day lookback ends at the incident. Evaluated at *now*, the baseline window absorbs the incident itself and its aftermath, and the comparison silently degrades.

## Iron Rule 2: Trust the query, not the memo

The environment changes faster than this skill can be updated. Service names move between namespaces, stored procedures get added or retired, Azure instances get re-numbered, ownership shifts during reorgs. If a live query result contradicts something stated in this skill or its references, **trust the query**. Note the discrepancy in the final report so the skill can be updated.

This applies especially to: specific service names, specific stored-procedure names, Azure resource instance suffixes, namespace ownership, and migration state. The **patterns** are stable (DB names, host suffixes, naming conventions, integration shapes); the **instances** are not. When a task needs an instance, discover it with a query — do not read it from a table here.

## Iron Rule 3: Time strings default to Europe/Oslo

The operators using this skill work in Norwegian local time. A silent UTC interpretation shifts every incident timestamp by 1 or 2 hours, which is the kind of mistake that desyncs an investigation from the people running it.

> Any time string the user gives **or** that you produce in a report is **Europe/Oslo** by default, unless the string carries an explicit offset (e.g. `14:00 UTC`, `13:00+00:00`). If it has an offset, respect it.

**Parsing user input.** "Yesterday at 14:00", "this Monday", "between 09:00 and 11:00", "the incident started at 09:14" → all Europe/Oslo. When converting to RFC3339 for an MCP call (`startRfc3339`, `endRfc3339`, etc.), attach the Oslo offset: `+02:00` during CEST (last Sunday of March → last Sunday of October), `+01:00` during CET. The MCP needs the offset; the operator does not.

**Presenting output.** Show timestamps as plain local times — `2026-05-27 09:14` or `09:14–09:42` — without an offset suffix. Oslo is implicit. The conversion still has to happen: if the MCP returns a UTC or Unix-epoch value, **convert it to Oslo** before showing it. Never present a raw UTC timestamp as if it were local.

**Pure-relative expressions are exempt.** `now-1h`, `[5m]`, `[7d]`, `offset 7d`, and any Prometheus range vector are timezone-independent — pass them through as-is. The rule applies only to absolute timestamps.

Two MCP-mechanics traps follow from this rule and are easy to get subtly wrong — instant queries **always** require `startTime`, and epoch-second range samples must be anchored, not hand-converted (±1 h drift otherwise). Both are documented with the query templates: [`query-templates.md` § MCP query mechanics](references/query-templates.md).

## Iron Rule 4: Weight findings by absolute impact during low-traffic hours

Norwegian operating hours mean traffic falls off sharply between roughly **00:00 and 05:00**. During those hours a handful of failed requests becomes a dramatic-looking percentage, even though the customer-impact footprint is tiny.

> If the incident window falls inside 00:00–05:00, always report the **absolute** affected-request count alongside the relative rate, and weight severity by the absolute number.

The `quantile_over_time(...[7d:5m])` baseline correctly flags a night-time spike as anomalous (it preserves diurnal patterns by comparing 02:00 to past 02:00s), so this is **not** an excuse to suppress the finding — only to right-size its urgency. A 10× error-rate spike at 02:30 representing 8 errors is real, but it is not the same severity as a 10× spike at 14:30 representing 8000 errors.

```promql
# Absolute affected requests over the incident window (errors per second × seconds)
sum(rate(traces_service_graph_request_failed_total{server="<X>"}[5m])) * 300

# Or just the running counter delta over the window
increase(traces_service_graph_request_failed_total{server="<X>"}[<window>])
```

Report both numbers (rate and absolute count) and let the reader judge. Inside §D4, prefix night-hour findings with a `(low-traffic window)` note so the incident owner sees the context without having to re-derive it.

## Iron Rule 5: Customer impact is established at the WebSEAL edge

Each gateway has a precise role. **IBM WebSEAL external** (`webseal_ext:requests:rate5m`) receives all internet traffic — customers on the web portals and partners on the API portals — and names the affected portal (`service_name`), route (`junction`), backend (`junctioned_server`), and outcome (`response_code`). **IBM WebSEAL internal** (`webseal_int:requests:rate5m`) receives part of the internal traffic: the SOA-layer front door (`prodsoa-*`) and intranet portals. **Traefik** is — without exception — the internal gateway for the cluster: every in-cluster request passes through it, which makes it the most sensitive *detector* of issues (§B Step 2).

> Claim customer or partner impact from (a) the **WebSEAL external edge** — which portal, which junction — or (b) a **Faro frontend** (detected in broad mode at §B Step 4; enumerated and attributed at §D0/§D3). These two are complementary: WebSEAL ext sees every request that reached the edge (including browserless partner API traffic); Faro sees what the user's browser experienced. Traefik evidence places the issue *in the cluster*; the WebSEAL/Faro pair places it *with an audience*.

The loudest customer-impact signal of all is portal traffic **collapsing** at the external edge (DNS, WebSEAL itself, network path) — a signal that exists only there, so a broad health check starts at `webseal_ext` (§B Step 1). One acknowledged gap: browser → `cdn.gjensidige.no` asset fetches reach neither WebSEAL nor Faro traces — for CDN incidents the provider's edge metrics are the impact source (production-environment.md §8). See `references/production-environment.md` §2 (Edge gateways) for the portal classification and label semantics.

## When to Use

- A service is reported slow, failing, throwing 5xx, or "acting weird"
- An incident has been declared and the starting service / domain is unclear
- Pinpointing which customer or partner portal an issue reaches (WebSEAL edge → junction → backend)
- Broad health check: "is anything wrong right now?"
- A browser app / page is broken or slow for users — a Faro-instrumented frontend (detected in broad mode at §B Step 4)
- Tracing a flow north-south (WebSEAL → Traefik → domain → core) or east-west (pod ↔ pod)
- Attributing latency or errors to a specific core system or Azure backend
- Portal login/authentication failures (the per-market EAI plane — BankID / OIDC brokers)
- Investigating a public-site CMS tenant issue

## Required Background

The environment has a fixed shape — read it once and keep it in mind. See [`references/production-environment.md`](references/production-environment.md) for:

- The two AKS clusters and observability datasources
- The edge gateways — IBM WebSEAL external (the true customer/partner edge) and internal (SOA front door + part of the intranet traffic), with metrics `webseal_ext:requests:rate5m` / `webseal_int:requests:rate5m`
- North-south (Traefik — internal-only, per Iron Rule 5) and east-west (Cilium/Hubble + Tempo) traffic planes
- The **login plane** — per-market EAI instances (`itsec-eai-gf{no,dk,se}`) behind each portal's `/eai` junction: ID-provider login, WebSEAL login/error pages (`TAM_OP` / `ERROR_CODE`), post-login enrichment, shared login-state Redis (§11)
- The **core systems**: S2000, GK + GPM (party master, legacy + new in parallel migration), IDIT, F2100, Dynamics 365, Archive/E-Archive/OnDemand
- Azure data plane (per-domain PostgreSQL / Redis / Blob / Service Bus / Key Vault)
- Confluent Kafka topic naming convention
- Public-site CMS layout (`gjensidige-{no,dk,se,com,builders}` running Enonic XP)
- The `cdn.gjensidige.no` shared static-asset dependency

The **frontend layer** (browser apps instrumented with the Grafana Faro Web SDK) appears in the service graph as `client`-only nodes — they call backends but are never servers. Treat them as a first-class **detection plane** (broad mode, §B Step 4) — not only as blast-radius/customer-exposure participants (§D). See [`references/frontends.md`](references/frontends.md) for the enumeration query, the two false-positive traps (third-party-host noise, garbage span durations), and what the Faro signal does and does not reach.

For ready-to-paste query templates see [`references/query-templates.md`](references/query-templates.md).

## Two Modes

```
                  ┌─────────────────────────────────┐
                  │  Do you know which service or   │
                  │  domain is involved?            │
                  └────────────┬────────────────────┘
                               │
                    ┌──────────┴──────────┐
                    │                     │
                   yes                    no
                    │                     │
                    ▼                     ▼
              TARGETED MODE         BROAD MODE
                  §A                    §B
                                         │
                                         │  finds a candidate
                                         ▼
                                       §A
```

Broad mode is **not** an alternative to targeted mode — it's a way to find a starting service when the symptom is vague. Once §B has surfaced a candidate (a failing WebSEAL portal/junction, a hot Traefik backend, a degraded core, a noisy namespace), switch to §A on that service and continue from there.

## §A. Targeted Mode — Specific Service or Domain

Use when the user names a service, namespace, route, endpoint, or business domain.

### Step 1. Confirm the service exists and is alive

```promql
# Is the deployment running?
kube_deployment_status_replicas_ready{deployment="<name>"}
  / kube_deployment_status_replicas{deployment="<name>"}

# Recent restarts (last hour vs 7-day baseline)
sum by (pod) (rate(kube_pod_container_status_restarts_total{
  namespace="<ns>", pod=~"<name>.*"}[1h]))
sum by (pod) (rate(kube_pod_container_status_restarts_total{
  namespace="<ns>", pod=~"<name>.*"}[7d]))
```

If replicas-ready < replicas-desired, that is the first finding — investigate why before continuing (OOMKilled, ImagePullBackOff, readiness probes).

### Step 2. Compare current SLI to 7-day baseline

For any quantitative claim, run **both** queries and compare:

```promql
# Inbound RPS now vs 7-day median
sum (rate(traces_service_graph_request_total{server="<name>"}[5m]))
quantile_over_time(0.5,
  sum (rate(traces_service_graph_request_total{server="<name>"}[5m]))[7d:5m])

# Inbound error rate now vs 7-day median
sum (rate(traces_service_graph_request_failed_total{server="<name>"}[5m]))
  / sum (rate(traces_service_graph_request_total{server="<name>"}[5m]))
quantile_over_time(0.5,
  (sum (rate(traces_service_graph_request_failed_total{server="<name>"}[5m]))
   / sum (rate(traces_service_graph_request_total{server="<name>"}[5m])))[7d:5m])

# p99 latency now vs 7-day p95 of p99
histogram_quantile(0.99, sum by (le) (
  rate(traces_service_graph_request_server_seconds_bucket{server="<name>"}[5m])))
quantile_over_time(0.95,
  histogram_quantile(0.99, sum by (le) (
    rate(traces_service_graph_request_server_seconds_bucket{server="<name>"}[5m])))[7d:5m])
```

**Decision:** if current is inside the baseline distribution → the symptom is chronic, not new. Tell the user. If outside → continue.

> **Absence of telemetry is not health.** These SLIs are built from traces — a service whose pods are down (or unreachable) produces *no* spans, so its service-graph error rate reads as quiet rather than 100%. If Step 1 showed a replica gap, or the queries above return empty/collapsing volume, quantify the failure at the gateways instead: the service's WebSEAL junction response codes (`query-templates.md` §A0.5/§A0.7) and Traefik `code=~"5.."` for `exported_service=~".*-<svc>-.*"` — the edge counts every request that never reached a pod (`502`/`503`/`504`).

### Step 3. Identify which dependency degraded

Most service-level problems are caused by a downstream:

```promql
# What does this service call, and how is each leg behaving?
topk(20, sum by (server) (rate(traces_service_graph_request_total{
  client="<name>"}[5m])))

histogram_quantile(0.99, sum by (le, server) (
  rate(traces_service_graph_request_client_seconds_bucket{client="<name>"}[5m])))

sum by (server) (rate(traces_service_graph_request_failed_total{client="<name>"}[5m]))
  / sum by (server) (rate(traces_service_graph_request_total{client="<name>"}[5m]))
```

Run the same three queries with `offset 7d` to baseline each edge. **The degraded edge is the candidate cause.**

If the degraded server is one of the **core systems** or an external endpoint, jump to §C — and resolve it to the failing **endpoint(s)** (method + path), not just the host.

### Step 4. Pull traces for the live error pattern

```traceql
# Slow inbound on this service in last 15 min
{ resource.service.name = "<name>" && kind = server && duration > <p99-baseline> }

# Failed inbound on this service
{ resource.service.name = "<name>" && status = error }

# What does a typical slow trace touch downstream?
# (load one trace, follow the span tree to the slowest child)
```

### Step 5. Run §D follow-up actions, then confirm and report

Once you have a candidate cause, **always** run §D before writing the report. The cause alone is not enough — the report needs blast radius, cascade status, and customer exposure.

State: (a) the symptom, (b) the baseline showing it's anomalous, (c) the dependency edge or root cause, (d) one or two example traces, (e) the §D follow-up findings. Do not report a "fix"; report the **cause + scope + suggested next actions**.

## §B. Broad Mode — "Something is Wrong, Where Do I Start?"

Use when the symptom is vague: customer complaints, partner reports, a dashboard looks off, or no service is named.

> **Start here.** Lead with the two 5xx sweeps — **WebSEAL-ext** per junction (Step 1) and **Traefik** per backend (Step 2), the cluster's most sensitive detectors (Iron Rule 5) — each against its 7-day baseline (Iron Rule 1). The **third customer-facing detector is the Faro frontend plane (Step 4)** — the only one that sees browser-observed failures against backends behind neither gateway; include it in any customer-impact sweep, do not leave it to §D. Then fork on the goal: **chasing one vague symptom to its cause** → work the detection sweeps (Steps 1–4) and take the largest-deviation winner (Step 5); **enumerating every active incident** (a periodic or on-demand sweep) → *Exhaustive sweep mode* below, absolute-ranked, each candidate its own §A lead. The **Azure data plane** and **network plane (Cilium/Hubble)** are deliberately **not** in the initial sweep — they are rarely the prime suspect, and their failures already surface as degraded edges on victim services in Steps 1–4. Reach for them as **Confirmation probes** (below) once a candidate points at a data backend or a network/DNS cause.

### Step 1. Snapshot the customer edge (WebSEAL external)

Start where the customers are. `webseal_ext:requests:rate5m` is the internet-facing IBM WebSEAL gateway — `service_name` = the portal the request arrived on, `junction` = the route, `junctioned_server` = the backend it forwarded to, `response_code` = what the caller got. See `references/production-environment.md` §2 for the portal classification (customer vs partner vs internal) and label semantics.

```promql
# Per-portal traffic now vs baseline — a collapsing portal RPS is the loudest
# customer signal there is, and it exists only at this edge
sum by (service_name) (webseal_ext:requests:rate5m)
quantile_over_time(0.5, sum by (service_name) (webseal_ext:requests:rate5m)[7d:5m])

# Per-portal 5xx ratio, now vs baseline — several portals run a chronic 5xx
# floor (observed medians span well over an order of magnitude across portals),
# so judge the delta from each portal's own baseline, not the level (Iron Rule 1)
sum by (service_name) (webseal_ext:requests:rate5m{response_code=~"5.."})
  / sum by (service_name) (webseal_ext:requests:rate5m)
quantile_over_time(0.5,
  (sum by (service_name) (webseal_ext:requests:rate5m{response_code=~"5.."})
   / sum by (service_name) (webseal_ext:requests:rate5m))[7d:5m])

# Drill an affected portal down to the failing route + backend, now vs baseline
# (several junctions error chronically — same Iron Rule 1 logic per junction)
topk(15, sum by (junction, junctioned_server, response_code) (
  webseal_ext:requests:rate5m{service_name="<portal>", response_code=~"5.."}))
topk(15, quantile_over_time(0.5, sum by (junction, junctioned_server, response_code) (
  webseal_ext:requests:rate5m{service_name="<portal>", response_code=~"5.."})[7d:5m]))
```

If the failing `junctioned_server` matches `<svc>.apps-int.gjensidige.io`, the backend is a GAP service: follow the handoff chain — WebSEAL junction → Traefik `exported_service=~".*-<svc>-.*"` → service graph `server="<svc>"` → pods (templates in `query-templates.md` §A0) — and switch to §A on `<svc>`. A `junctioned_server` outside `apps-int` (`*.mistral.mistralnett.com` hostnames, bare IPs) does **not** reveal where the workload runs — `mistralnett.com` is a legacy naming zone whose hostnames front both on-prem hosts and GAP-hosted containers. Discover the runtime with a query (service-graph `server`, `kube_pod_info`, or a trace — the in-cluster service name can differ from the hostname prefix); when nothing in-cluster matches, WebSEAL response codes are the covering metric. `junctioned_server="-"` means WebSEAL answered the request itself — the login/session plane (auth redirects `302`, `401`s, cached `200`/`304`): IAM territory. Sparse 5xx series churn out of the 5-minute window — over an incident window, query a **range**, not an instant (see Common Mistakes).

> **Scope of this step:** WebSEAL measures volume and response codes, so Step 1 detects **errors and traffic collapse**. A latency-only symptom ("the site is slow") shows a clean edge here — slowness is measured at Traefik p99 (Step 2) and on the Faro frontends' outbound edges (Step 4 / §D0). A clean Step 1 narrows the symptom; it does not clear customer impact.

### Step 2. Snapshot the internal gateways (Traefik + WebSEAL internal)

Traefik is internal-only (Iron Rule 5), but everything in-cluster passes through it — which makes it the most sensitive *detector*:

```promql
# Traefik 5xx rate by backend, now vs 7-day baseline
topk(20, sum by (exported_service) (
  rate(traefik_service_requests_total{code=~"5..",
  cluster="aks-apps-int-prod-013"}[5m])))

# Same expression, 7-day window
topk(20, sum by (exported_service) (
  rate(traefik_service_requests_total{code=~"5..",
  cluster="aks-apps-int-prod-013"}[7d])))

# p99 latency per backend, 5m vs 7d-average — many backends sit chronically
# above 1s, so a hotspot is a backend far above ITS OWN 7d level (Iron Rule 1)
histogram_quantile(0.99, sum by (le, exported_service) (
  rate(traefik_router_request_duration_seconds_bucket[5m]))) > 1
histogram_quantile(0.99, sum by (le, exported_service) (
  rate(traefik_router_request_duration_seconds_bucket[7d])))

# Confirm a single latency candidate against its 7-day distribution
quantile_over_time(0.95, histogram_quantile(0.99, sum by (le) (
  rate(traefik_router_request_duration_seconds_bucket{
    exported_service=~".*-<svc>-.*"}[5m])))[7d:5m])
```

For the 5xx pair: anything appearing in the 5-minute list but **not** in the 7-day list is a *new* hotspot. For the latency pair: a hotspot is a backend whose current p99 sits far above its own 7-day level (appearing in both lists is normal). Either way, that is the target — classify its exposure via Step 1 / §D3.

> **Label trap:** the two Traefik metrics name backends differently — `traefik_service_requests_total` carries `exported_service="<ns>-<svc>-<port>@kubernetesgateway"`, while `traefik_router_request_duration_seconds_*` carries router-derived names (`httproute-<ns>-<svc>-gw-…-wrr@kubernetesgateway`). An exact-value join across them silently returns empty. Filter each with the substring regex `.*-<svc>-.*` — it matches both schemes.

`webseal_int:requests:rate5m` is the **internal** WebSEAL gateway: the front door for the SOA layer (`service_name=~"prodsoa-.*"` — the `-ext`/`-int` suffix is SOA zoning; both live on this internal gateway, see §C) and part — not all — of the intranet/tooling traffic (`intra.mistral.mistralnett.com`):

```promql
# Internal-gateway 5xx by portal, route and backend, now vs baseline
# (keep the topk wrapper on the baseline — unwrapped it exceeds MCP response limits)
topk(15, sum by (service_name, junction, junctioned_server) (
  webseal_int:requests:rate5m{response_code=~"5.."}))
topk(15, quantile_over_time(0.5, sum by (service_name, junction, junctioned_server) (
  webseal_int:requests:rate5m{response_code=~"5.."})[7d:5m]))
```

### Step 3. Snapshot the core systems

The core systems are the most likely root causes of cross-cutting incidents. Sweep them all in one regex:

```promql
# Volume per core (current)
sum by (server) (rate(traces_service_graph_request_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m]))

# p99 client-side latency per core (current)
histogram_quantile(0.99, sum by (le, server) (
  rate(traces_service_graph_request_client_seconds_bucket{
    server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m])))

# Error rate per core (current)
sum by (server) (rate(traces_service_graph_request_failed_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m]))
/ sum by (server) (rate(traces_service_graph_request_total{
  server=~".*(mistralnett|sapiensmgs|fdc\\.dk|dynamics\\.com|evry\\.com).*"}[5m]))
```

> **This sweep matches hostname-based cores only.** Backends reached by IP — notably S2000's DB2 mainframe (JDBC; a bare IP with no `db.name` label in the service graph) — do not appear here, so a clean result can still hide a failing core. Resolve any degraded bare-IP `server` separately (see "Resolving a bare-IP server", below). The `mistralnett` match is primarily the SOA bus, but `*.mistralnett.com` is a shared legacy domain hosting other systems too (DataPower, app hosts, DB2 hosts) — confirm the specific hostname before attributing (production-environment.md §4).

Pair each with `quantile_over_time(...[7d:5m])` for the baseline. A core system error rate that doubles vs baseline is almost certainly the proximate cause of any cross-domain symptom. This sweep names the failing *host*; for an HTTP core, resolve it to the failing **endpoints** (method + path) in §C ("Drilling into an external HTTP edge failure") before reporting.

### Step 4. Snapshot the frontend plane (Faro)

The Faro browser apps (§D0, `frontends.md`) are a **customer-facing detector the gateway sweeps miss** — the single most common reason frontend impact goes unreported. A frontend can fail against a backend behind **neither** WebSEAL nor Traefik, hit a CORS-preflight failure, or break on its own deploy — none of which lights up Steps 1–2. Sweep per-frontend **error rate**:

```traceql
# Primary (Tempo): absolute first-party API-error rate per frontend. The host
# filter is MANDATORY (raw spans are ~99% third-party ad/analytics noise —
# doubleclick, usercentrics, hotjar). Anchor on Gjensidige-owned registrable
# domains; a bare "gjensidige" substring readmits vendors (gjensidige.piwik.pro).
{ resource.telemetry.distro.name = "faro-web-sdk" && status = error
  && span.http.host =~ ".*(gjensidige\\.(no|dk|se|com|io)|heihuset\\.no|mistralnett\\.com)$" }
  | rate() by (resource.service.name)
```

```promql
# Fallback (Prometheus, when the Tempo proxy is down): per-frontend error ratio,
# vs its own 7-day quantile_over_time(...[7d:5m]) baseline (full form: §C8).
# Naturally first-party — only backends are graph servers.
sum by (client) (rate(traces_service_graph_request_failed_total{client=~"<FRONTENDS>"}[5m]))
  / sum by (client) (rate(traces_service_graph_request_total{client=~"<FRONTENDS>"}[5m]))
```

Rank by **absolute** first-party errors (Iron Rule 4 — frontends are low-volume; a 90% ratio can be a handful of requests) and baseline each against its own history (Iron Rule 1). A frontend above baseline is a customer-facing candidate: switch to §A on it and drill its error traces to the failing backend (observed: `gje-claim-details` → `api-claim-private-dk` → IDIT adapters, failing spans pinned at a ~65s timeout). Full queries + both false-positive traps: [`query-templates.md` §C8](references/query-templates.md) and [`frontends.md`](references/frontends.md).

### Step 5. Triangulate

You should now have one or more candidates: a failing WebSEAL portal/junction, a hot backend in Traefik, a degraded core, or **a frontend with an anomalous first-party error rate (Step 4)**. **Pick the candidate with the largest deviation from baseline**, switch to Targeted Mode (§A) on that service, and proceed. A WebSEAL-edge **or Faro-frontend** candidate outranks an equally-deviant internal one — it is already customer-attributed.

If the winner's degraded downstream edge lands on an Azure backend, or its symptom is timeouts / connection-refused / DNS faults with no application-level error, run the matching **Confirmation probe** (below) to name the data-plane or network root cause — before, or alongside, the §A drill.

### Confirmation probes — data plane & network plane

These two planes are **not** prime suspects, so they are not part of the initial sweep. They rarely originate an incident alone, and when they do their effect **does not hide** — an Azure backend outage or a network/DNS fault surfaces first as **degraded edges on its victim services**, which the gateway, core, and frontend sweeps (Steps 1–4) already catch. Use them to **name a root cause**, not to detect one:

- **Azure data plane** (PostgreSQL, Azure SQL, Redis, Blob, Key Vault, Service Bus) — run when a degraded service's downstream edge (§A Step 3 / §B Step 3) lands on an Azure backend, or when a cluster of otherwise-unrelated services degrades together (a shared data backend is a classic common cause). Per-service error-rate sweep + the per-domain hostname convention: [`query-templates.md` §C9](references/query-templates.md), [`production-environment.md` §5](references/production-environment.md).
- **Network plane (Cilium/Hubble)** — run when the symptom is timeouts, connection-refused, or intermittent failures with no application-level error (the fingerprint of dropped flows or DNS faults; the "lots of timeouts" triage row). Dropped-flow, drop-reason, DNS and TCP-flag queries: [`query-templates.md` §B](references/query-templates.md).

### Exhaustive sweep mode — enumerate every incident

Step 5 collapses the sweep to a single winner — right for one reported symptom, lossy for a periodic or on-demand sweep that must surface **all** active incidents. The high-cardinality `topk(N)`-by-rate sweeps make it worse: one incident is rarely one series, so a single large incident fills the list and **evicts an independent smaller one entirely**. A signal missed at the sweep is unrecoverable, while a noise candidate is cheaply dismissed downstream — so for enumeration, bias the **sweep** toward recall and let **§A** reject the noise.

Apply this to the four high-cardinality sweeps — Traefik 5xx-by-backend and the `webseal_int` 5xx sweep (§B Step 2), the `webseal_ext` portal→junction drill (§B Step 1, per affected portal), and the per-frontend first-party error sweep (§B Step 4); the per-portal edge and core sweeps are bounded and stay as they are. (The Azure data plane and network plane are not swept even in enumeration mode — a data-plane or network fault surfaces through its victim services in the sweeps above and is then named via the Confirmation probes, so dropping them from the sweep costs no recall.) On each, **rank by absolute affected requests** (Iron Rule 4) under a generous cap that is a response-size guard rather than a selector — being absolute-ranked, what it drops is always the lowest-impact tail — and walk the list as individual §A leads until the absolute count is negligible. Two cautions carry the precision: rank by absolute impact, **not** a current/baseline ratio (a near-zero baseline turns one stray 5xx into a top "anomaly" and floods the list); and confirm against the **window**, not the sweep instant — a sweep runs after the window closes, so an already-subsided incident still shows in the window-total rank yet reads quiet at any instant, so confirm on the window's **peak** against a *pre-window* baseline (Iron Rule 1, *Historical incidents*). Query forms per metric (counter vs recording-rule) and the absolute-count math: [`query-templates.md` §A3-sweep](references/query-templates.md). Keep Step 5's single-winner funnel for interactive use, where the one largest-deviation cause is exactly what you want.

### Resolving a bare-IP server

`traces_service_graph_*` shows some backends as a **bare IP** (e.g. `139.113.31.225`) rather than a hostname, because the metric carries no `db.name` / `server.address` label — only the address the client connected to. You **cannot** identify a bare-IP server from metrics alone, and the §B Step 3 core sweep will not match it.

When a degraded `server` (in broad mode, §A Step 3, or §D blast radius) is a bare IP, resolve its true identity by pulling **one** trace to it and reading the span attributes:

```traceql
{ span.server.address = "<ip>" }
```

- **Database engine** → `span.db.system` + `span.db.name` + `span.db.connection_string` identify the system. DB2 is a fleet of databases on several addresses (some bare IPs, some hostnames — e.g. GPF's `gps_esop`/`gpfp01` live on a different IP), so key on `db.name`, not the address: `db.name=zaz23400` = **S2000 (or GK)** — go to §C and drill into the failing stored procedure.
- **HTTP** → `span.server.address` (the real hostname) + `span.peer.service` identify the target — route to the matching core.

Known fingerprint (verify — instances drift, per Iron Rule 2): `db.system=db2` + `db.name=zaz23400` at `db2://139.113.31.225:2504` → the S2000 DB2 mainframe. `db.user` varies by caller — don't rely on it.

## §C. When the Suspect is a Core System

If the degraded edge points at a core system, drill in by identifying the *family* (stable for years) and then discovering the *live entry points and hot procedures/endpoints* with a query. See [`references/production-environment.md`](references/production-environment.md) for the integration shape of each core.

> **Note on `traces_spanmetrics_calls_total`** — the spanmetrics generator emits a narrow label set: `service`, `span_name`, `span_kind`, `status_code`, `k8s_namespace_name`. The full `db.*` and `server.*` attributes are **not** preserved as Prometheus labels (they are still in Tempo, so TraceQL queries see them). When filtering DB traffic in PromQL, match on `span_name=~"CALL PROD\\.<family>.*"` (DB2 stored procs) or use `traces_service_graph_*` with the `server` label (Postgres hosts, HTTP endpoints). Reaching for `db_name="zaz23400"` here will silently return empty.

| Core | Identifying pattern | Discover live entry points & hot calls |
|---|---|---|
| **S2000** (NO non-life, DB2 mainframe) | `span.db.system="db2"` + `span.db.name="zaz23400"` + statement family `PROD.E*SP`, reached by direct JDBC (surfaces as a **bare IP** in the service graph — see "Resolving a bare-IP server" in §B). | Find which procedure is failing and why — see "Drilling into a DB2 stored-procedure failure" below. The `E*SP` family includes `ESK*`, `EPS*`, `EPO*`, `ERI*`, `EAG*`, `EAF*`, `EDE*`, `EGFE*`, `EPD*`, `EPR*` — but **always discover the live set**, do not assume from this list. |
| **GK** (legacy party master, same DB2) | `span.db.system="db2"` + `span.db.name="zaz23400"` + statement matches `PROD\.GK[GH]?.*P`. | Find the live bridge service: `topk(5, sum by (service) (rate(traces_spanmetrics_calls_total{span_name=~"CALL PROD\\.GK.*"}[1h])))`. Group the same query by `span_name` to find the hot procedure. |
| **GPM** (new party master, Azure PG) | `span.db.system="postgresql"` + `span.db.name="gpmdb"`. PG host matches `.*\.postgres\.database\.azure\.com`. | Find the live caller of the GPM PG instance: `topk(5, sum by (client) (rate(traces_service_graph_request_total{server=~"gpm-cpo-party-[a-z]+-prod-psql-.*\\.postgres\\.database\\.azure\\.com"}[1h])))` (the region token varies — keep it a wildcard). |
| **IDIT** (Sapiens MGS SaaS, DK insurance) | `span.server.address =~ ".*sapiensmgs\\.com.*"`. Adapter-ring pattern — never called directly, always via per-entity adapters. | Find the live adapters: `topk(20, sum by (client) (rate(traces_service_graph_request_total{server=~".*sapiensmgs.*"}[5m])))`. |
| **F2100** (FDC, DK industry / pension) | `span.server.address =~ ".*\\.fdc\\.dk.*"`. Proxy-service pattern, country-suffixed. | Find the live proxies: `topk(10, sum by (client) (rate(traces_service_graph_request_total{server=~".*fdc\\.dk.*"}[5m])))`. The country is encoded in the client-service suffix. |
| **Dynamics 365** (CRM) | `span.server.address =~ ".*\\.dynamics\\.com"`. Also check the async path via `*.servicebus.windows.net`. | Find the live bridge services: `topk(10, sum by (client) (rate(traces_service_graph_request_total{server=~".*dynamics\\.com"}[5m])))`. |
| **Archive / E-Archive / OnDemand** (Tietoevry) | `span.server.address =~ "(earkiv\|wsedok\\.ec)\\.evry\\.com"`. E-Archive = long-term store, OnDemand = dynamic doc generation. | Find the live facade APIs: `topk(10, sum by (client) (rate(traces_service_graph_request_total{server=~".*evry\\.com"}[5m])))`. |

When a core system is impacted, the blast radius is wide — list the affected client services (D1) so the incident owner sees the full impact.

> **The host is not the reportable granularity — the endpoint is.** This holds for **any external HTTP `server` edge**, not only the cores in the table above: the per-core queries (and §A Step 3 / §B Step 3) name the failing *host* and its *callers*, but "`sapiensmgs.com` is failing" is not an actionable finding — "`GET /idit-web/api/v2/loss-event/{id}` is returning `422`" is. (DB and messaging edges — Postgres, Redis, Service Bus — drill via `db.*` / `messaging.*` instead; this drill is for HTTP.)

### Drilling into an external HTTP edge failure

Applies to any external HTTP server: the cores above (IDIT, F2100, Dynamics, Archive) **and** the non-core HTTP egress edges in [`production-environment.md` §10](references/production-environment.md) — public-sector APIs, identity providers (BankID, Signicat), Microsoft Graph, partner APIs. `traces_service_graph_*` carries only the `server` (host) label, and spanmetrics `span_name` for an outbound call is the **bare method** (`GET`, `POST`, … — verified live, no path). Neither metric names *which endpoint* is failing; method + path live only on the spans. Resolve it exactly as a DB2 failure is resolved to procedure + SQLCODE — pull the failing spans and read the endpoint off them.

1. **WHICH endpoints** — the HTTP attribute scheme varies by caller (newer services emit `http.request.method` + `url.full`; older ones `http.method` + `http.target`/`http.url`), and `url.path` is frequently empty even when `url.full` is set — so select **both** schemes and use whichever is populated:

   ```traceql
   { span.server.address =~ ".*sapiensmgs\\.com.*" && status = error }
     | select(span.http.request.method, span.http.method, span.url.full, span.url.path, span.http.target, span.http.response.status_code, span.http.status_code)
   ```

   `status = error` only catches spans the *caller* flagged failed. An external core often returns a 4xx the caller tolerates (verified: IDIT answers `422` on a not-found lookup, never marked `status=error`), so also filter on the status code directly to catch those: `{ span.server.address =~ ".*sapiensmgs\\.com.*" && span.http.response.status_code >= 400 }`.

2. **Normalise + report** — `url.full` embeds IDs and query strings (`…/api/policy/PD1000004051976/00?…`), so collapse the volatile segments before grouping or reporting (`/idit-web/api/policy/{id}`), or every request reads as its own endpoint. Report each failing endpoint as `<METHOD> <normalised-path> → <status>` — e.g. `GET /idit-web/api/v2/loss-event/{id} → 422`. **Never report an external HTTP edge as the cause without naming the failing endpoint(s)** — the endpoint is to an HTTP core what the SQLCODE is to DB2.

### Drilling into a DB2 stored-procedure failure (S2000 / GK)

S2000 and the SOA bus are **cross-domain infrastructure** — used by every domain, not any one of them. A DB2 failure therefore shows up as a multi-domain symptom; do not anchor the investigation to whichever domain reported it first.

Two layers fail independently — establish which one:

- **The SOA layer** — a `prodsoa-ext/int.mistral.mistralnett.com` hostname edge is degraded. But `prodsoa-*` is a **front door for the whole SOA layer**, not one service — a high edge rate is an aggregate, and the layer rarely fails uniformly (e.g. an S2000 slowdown hits only the DB2-backed backends). Never report `prodsoa-*` itself as the cause. The front door is the **internal WebSEAL gateway**, so decompose it by junction first (HTTP-layer problem):

  ```promql
  # Failing SOA route + the concrete backend it forwards to
  topk(10, sum by (service_name, junction, junctioned_server) (
    webseal_int:requests:rate5m{service_name=~"prodsoa-.*", response_code=~"5.."}))
  ```

  `junction` names the SOA operation route (`/gf/risiko`, `/gf/part`, …) and `junctioned_server` the backend — mostly `<svc>.apps-int.gjensidige.io` GAP services (continue in-cluster on `server="<svc>"`), plus some legacy hosts and bare IPs. The SOA layer runs inside the GAP cluster, so in-cluster callers **hairpin**: GAP pod → `webseal_int` → `apps-int` → Traefik → SOA pod — one logical call is measurable at the caller's client edge, the junction, and Traefik (legs agree in shape, not 1:1 in magnitude — see production-environment.md §4). For operation-level detail (`url.full`, payload, SQLCODE) confirm with a **trace** — the server span after the `server.address=prodsoa-*` client hop. Identify the backends from the junction metric or the trace (they neither all share a `soa` name nor sit in one namespace).
- **S2000 / DB2** — `CALL PROD.*` spans error, or the bare-IP JDBC edge is degraded. (Mainframe-layer problem.)

A DB2 **slowdown** (not a crash) shows up as **latency, not errors** — `CALL PROD.*` `STATUS_CODE_ERROR` counts can stay near zero while the bare-IP edge p99 explodes (observed 0.2s → 40s). Check edge latency first:

```promql
# Bare-IP S2000 DB2 edge p99 (resolve the IP per §B; e.g. 139.113.31.225 = zaz23400)
histogram_quantile(0.99, sum by (le) (rate(traces_service_graph_request_client_seconds_bucket{server="139.113.31.225"}[5m])))
```

> **Dilution caveat:** the bare-IP edge p99 aggregates **every procedure** on that DB2 host. A single slow procedure can be fully diluted by healthy traffic and leave the edge flat (observed: edge p99 ~0.3s while one SP family ran to its 30s ceiling). If the edge reads normal but a caller is timing out, drill to the **calling SOA service's server-side p99** and to per-procedure durations in TraceQL — failing-call durations pinned at a round ceiling (10s/30s/…) are timeouts:
>
> ```traceql
> { span.db.name = "zaz23400" && name = "CALL PROD.<proc>" && duration > 10s }
> ```

Then drill the failing/slow calls in two steps:

1. **WHICH procedure** — find the failing procs (spanmetrics carries `status_code`):

   ```promql
   sum by (service, span_name) (rate(traces_spanmetrics_calls_total{
     span_name=~"CALL PROD\\..*", status_code="STATUS_CODE_ERROR"}[5m]))
   ```

2. **WHY** — pull the DB2 `SQLCODE` from the failing span's `exception` event:

   ```traceql
   { span.db.name = "zaz23400" && status = error }
   ```

   Read `exception.message` (`SQLCODE` / `SQLSTATE` / `SQLERRMC`) and interpret it with the SQLCODE table in [`references/production-environment.md`](references/production-environment.md) §3. **Never report a DB2 *failure* without its SQLCODE** — the code *is* the cause. A whole proc family failing with the same SQLCODE, starting and recovering together, is a single mainframe deploy/bind event. The exception: a pure latency/timeout **slowdown** (callers aborting, spans pinned at a round time ceiling, no exception event) produces **no SQLCODE** — report the timeout/latency evidence instead and state explicitly that no SQLCODE exists.

## §D. After Identifying the Cause — Blast Radius

The cause alone is **not** a complete answer. Once §A, §B, or §C has produced a candidate cause (a degraded server `X`), run every check below before writing the final report. **When the candidate is a Faro frontend (§B Step 4), `X` is the failing backend edge you drilled it to** — the frontend is client-only (no fan-in), so it appears as the customer-facing surface in the §D4 Faro line, not in the §D1/§D2 caller lists. The report describes *what is happening* and *who is affected* — what to do about it is the reader's call.

### D0. Enumerate the Faro frontend set (prerequisite)

If you have not already done this in the conversation, run it now — the result feeds §D1 (caller labeling), §D3 (customer-facing signal), and §D4 (report):

```
mcp tempo_get-attribute-values
  name         = resource.service.name
  filter-query = { resource.telemetry.distro.name = "faro-web-sdk" }
```

Hold the returned list as `FRONTENDS = {…}`. See [`references/frontends.md`](references/frontends.md) for why this set matters and how to slice it by portal.

### D1. Blast radius — every dependent caller

```promql
topk(150, sum by (client) (rate(traces_service_graph_request_total{server="<X>"}[<window>])))
```

Evaluate over the **incident window**, not a `[5m]` snapshot, and keep the cap a completeness guard rather than a selector: a wide cross-domain core (S2000, the SOA bus) has far more dependent callers than a top-30 list holds, and a caller that hit `<X>` earlier but is now blocked or backing off reads quiet in a 5-minute slice. List them all here — §D2 sorts cascaded from contained.

For each client found:

1. Record its namespace (resolve with `kube_pod_info{pod=~"<client>.*"}` if not obvious from the name). Group clients by namespace so the report shows which teams are affected.
2. **Label each caller as `FRONTEND` if it is in the `FRONTENDS` set from §D0, otherwise `BACKEND`.** Every `FRONTEND` caller is, by definition, a direct customer-facing surface and must appear in the §D4 `Customer-facing affected (Faro frontends)` line of the report — regardless of Traefik exposure.

### D2. Cascade check — are dependent callers themselves now degraded?

For each client from D1, compare its error rate / p99 over the incident window to its 7-day baseline:

```promql
# Per-client error rate over the window
sum by (server) (rate(traces_service_graph_request_failed_total{
  server=~"<client1>|<client2>|..."}[<window>]))
/ sum by (server) (rate(traces_service_graph_request_total{
  server=~"<client1>|<client2>|..."}[<window>]))

# Per-client error rate baseline
quantile_over_time(0.5, (
  sum by (server) (rate(traces_service_graph_request_failed_total{
    server=~"<client1>|<client2>|..."}[5m]))
  / sum by (server) (rate(traces_service_graph_request_total{
    server=~"<client1>|<client2>|..."}[5m]))
)[7d:5m])
```

Mark each affected client as **CASCADED** (error rate up) or **CONTAINED** (still healthy despite calling the broken thing — usually means good fallbacks or low call volume).

> **Frontend callers are client-only.** A Faro `FRONTEND` caller (from §D0) never appears as a `server` in the service graph, so the query above returns *empty* for it — which reads as "CONTAINED" when you actually have no signal. To judge whether a frontend cascaded, look at **its own outbound edge to `<X>`** (`client="<frontend>", server="<X>"` failure rate / p99) and its other downstream edges, not at it as a server. Do not silently mark a frontend CONTAINED on missing server-side data.

### D3. Customer-facing exposure — which affected clients are user-visible?

Two independent, complementary customer-facing signals — **WebSEAL external edge** (server side: every request that arrived at the internet edge, including browserless partner API traffic) and **Faro frontends** (browser side: what the user's own session experienced). Run **both** — either one promotes the affected service to the customer/partner-facing list, and each covers paths only it sees (Iron Rule 5).

```promql
# Signal 1: the service is fronted by the external WebSEAL edge — returns the
# portal(s) and route(s) that depend on it. 24h window, because low-traffic
# portals (e.g. partner.gjensidige.no) drop out of instant results.
sum by (service_name, junction) (max_over_time(webseal_ext:requests:rate5m{
  junctioned_server=~"(<client1>|<client2>|...)\\.apps-int\\.gjensidige\\.io"}[24h])) > 0

# Signal 2: affected service called directly by a Faro frontend (FRONTENDS from §D0).
# Use the incident <window> (or 24h), NOT [5m] — like Signal 1, a frontend that called
# the service earlier in the window but has since errored out / backed off drops from a
# 5-minute snapshot and silently vanishes from the customer-facing list.
sum by (server) (rate(traces_service_graph_request_total{
  server=~"<client1>|<client2>|...",
  client=~"<FRONTENDS regex>"}[<window>])) > 0
```

Signal 1 also answers **who**: classify each returned `service_name` against the portal table (`references/production-environment.md` §2) — *customer portal* (`www.gjensidige.{no,se,dk,com}`, `www.gouda.{no,fi,dk}`, `www.gouda-rf.se`) or *partner API portal* (`connect-mtls.gjensidige.com`, `connect.gjensidige.com`, `partner.gjensidige.no`, `services.gjensidige.no`). Run the same `junctioned_server` check against `webseal_int:requests:rate5m` for **internal-user exposure** (intranet, customer handlers, SOA junctions) — not customer impact, but it scopes which internal flows feel it.

Anything that appears in either signal is a **customer-visible surface** — call it out at the top of the report. A failure in a chatty internal service is not the same as a failure in something that fronts www.gjensidige.no or sits behind a Faro app like `report-claim` / `dk-webshop-*`.

### D4. Report template

Use this structure for the final write-up:

```
SYMPTOM
  <one-line description of the customer-visible or operator-visible symptom>

ANOMALY CONFIRMED
  <metric> = <current> vs <baseline>=<value> (period: <last X min>)
  Absolute impact: <N errors/sec or N affected requests over the window>
  Started ~<YYYY-MM-DD HH:MM>  # Europe/Oslo, per Iron Rule 3
  <(low-traffic window) — only include if start is in 00:00–05:00, per Iron Rule 4>

ROOT CAUSE
  <named system / edge / procedure / endpoint>
  Evidence:
    - <degraded edge query result>
    - <failing endpoint(s) — METHOD + normalised path + status — if the cause is an external HTTP edge (§C); SQLCODE if DB2>
    - <example trace ID(s)>

BLAST RADIUS
  Customer-facing affected (WebSEAL ext — customer portals):   <portal → junction list, or "none">
  Partner-facing affected (WebSEAL ext — partner API portals): <portal → junction list, or "none">
  Customer-facing affected (Faro frontends):                   <list of FRONTEND callers from §D1, or "none">
  Internal-user exposure (WebSEAL int — intranet / SOA):       <list, or "none">
  Internal affected (CASCADED):              <list with namespaces>
  Internal affected (CONTAINED, no error spike yet): <list with namespaces>
```

**The customer-facing and partner-facing lines are required.** Writing "none" is acceptable when the §D1/§D3 checks returned empty; *omitting* a line is not. If you find yourself writing the report without having run §D0 and the §D3 WebSEAL exposure check, stop and run them. Exposure classes come from the WebSEAL portal table and the Faro set (Iron Rule 5).

## Triage Table

| Symptom | First check | Then | Read next |
|---|---|---|---|
| Single service slow / failing | Replica health → 5xx and p99 vs 7-day baseline | Identify degraded downstream edge | §A |
| Multiple services failing in same domain (e.g. all claims APIs) | Edge from those services into S2000 / IDIT / Archive | Confirm the core is the common factor | §A → §C |
| "Whole site is broken" / public-web outage | `webseal_ext` per-portal RPS + 5xx vs baseline (which portal? traffic collapsed or erroring?), then drill the affected portal to junction + `junctioned_server` | `gjensidige-{no,dk,se,com}/builders-exp-*` health, `views-api-*`, `builders-cache-*`; check `cdn.gjensidige.no` backend path and the CDN edge externally | §B → §A |
| Partner reports API failures | `webseal_ext` partner portals (`connect-mtls.gjensidige.com`, `connect.gjensidige.com`, `partner.gjensidige.no`, `services.gjensidige.no`): junction + `junctioned_server` + `response_code` | Follow the failing `junctioned_server` into the cluster (§A on the GAP service) — partner API traffic has no Faro signal, WebSEAL ext is the only edge view | §B → §A |
| Customer login broken (NO / DK / SE) | The portal's `/eai` junction codes vs baseline on `webseal_ext` (`junctioned_server="-"` = WebSEAL's own session plane), then §A on the market's EAI instance `itsec-eai-gf{no,dk,se}` (`team-it-security`) | One failing `/eai/bankid` (NO) / `/eai/nid` (DK/SE) trace names the leg: the market's IdP (`auth.bankid.no`, `sid.gjensidige.{dk,se}`), the shared `gpm-itsec` Redis state store (one instance serves all three markets), the enrichment fan-out into SOA / party / F2100 / IDIT (§C), or the landing apps (`application-portal*`) | §A, [prod-env §11](references/production-environment.md) |
| Claims domain misbehaving | S2000 stored-procedure error rate + Archive (`kda-archive-earchive-a2a`) + `claims-soa-*` p99 | Check both DataPower and SOA bus paths | §A → §C |
| DB2 / stored-proc errors (`CALL PROD.*` failing, any domain) | Failing procs via spanmetrics `status_code`, then the SQLCODE from the `exception` event | Distinguish the SOA-bus edge (decompose `prodsoa-*` by `webseal_int` junction → `junctioned_server`) from S2000/DB2 (bare-IP / `CALL PROD.*`); read the SQLCODE | §C |
| Customer / party data issues (lookups failing, consent broken, customer details missing) | Both party masters in parallel: GK procedure error rate (`PROD.GK*P`) via `party-party-cs-service` + GPM health via `party-gpm-service` → `gpmdb` on Azure PG (`gpm-cpo-party-*-prod-psql-*.postgres.database.azure.com` — region token varies) | Determine which path the affected caller uses (legacy GK or new GPM) — they can fail independently during migration | §A → §C |
| Pension (GPF) errors | F2100 (`*.fdc.dk` + `omni-fdc.dk`) volume + DB2 (`gpfp01` / `gps_esop`) + `gpf-amelding` workload | Don't forget public-sector APIs (Skatt, NAV, NorskPensjon) | §A → §C |
| DK / SE business broken | IDIT (`*.sapiensmgs.com`) for DK, F2100 (`*.fdc.dk`) for both, plus the per-country adapter rings | Check `gapi-adapter-*-idit` (DK) and `*-fdcproxy-gf{dk,se}` first | §A → §C |
| Kafka-driven flow stalled | `confluent_kafka_server_consumer_lag_offsets` per topic + topic naming (`o.gfno.s2000.*`, `o.gfdk.policy.*`) | Trace the consumer service and check its pod health | §A |
| "Lots of timeouts" pattern | `hubble_dns_responses_total{rcode!="No Error"}`, `cilium_drop_count_total`, then per-edge p99 | DNS or NetworkPolicy issue is the leading hypothesis | §B |
| Site slow but **not** erroring (pages load, slowly; WebSEAL edge clean) | Traefik p99 per backend, 5m vs 7d (§B Step 2 — WebSEAL measures volume + codes, so slowness shows there as *clean*) | Faro frontends' outbound client-edge p99 toward their backends (§D0 set, `client=<frontend>`), then §A Step 3 on the slowest edge | §B → §A |
| Customers report errors but no page or service is named | The three customer-facing detectors vs baseline: `webseal_ext` 5xx (Step 1), Traefik 5xx (Step 2), and the **Faro frontend** first-party error sweep (Step 4) | Take the largest-deviation candidate into §A; for a Faro candidate, apply the mandatory first-party host filter (§C8) | §B → §A |
| "This specific page / app is broken for users" | Confirm the page is a Faro frontend by looking up its `service.name` in the Faro enumeration (`resource.telemetry.distro.name = "faro-web-sdk"`), then treat that frontend as the starting service and check its downstream edges | The frontend's `server` set in `traces_service_graph_*` is the list of backends it depends on — apply §A Step 3 to each | §A, [`references/frontends.md`](references/frontends.md) |
| Cannot reproduce / nothing obvious | Run §B end-to-end | Often the symptom is chronic — confirm with 30-day baseline | §B |

## Common Mistakes

These are the non-obvious, **mechanical** traps — the ones that are not already an Iron Rule or a Red Flag. For the principle-level mistakes — reporting without a baseline, a DB2 failure without its SQLCODE, a bare IP or a Traefik edge as customer impact, an external host without its endpoint — see the Iron Rules and the Red Flags checklist; they are the canonical statement and are not repeated here.

| Mistake | Reality |
|---|---|
| Stopping at the first error in a trace, or blaming the service that called the broken thing | The first error you find is often cascading, and the *calling* service is usually the **victim**, not the cause. Walk to the **root span** of the failure tree and name the dependency where the failure actually lives — a core (S2000, IDIT, F2100, Dynamics, Archive) or a data/network backend — not the service that called it. |
| "The WebSEAL 5xx instant query returned empty → no errors" | 5xx series churn in and out of the 5-minute window; sparse errors vanish from instant results (observed: an empty instant during a window containing hundreds of errors). Query the incident window as a range, or `60 * sum_over_time(...[<window>])` for the absolute count (not `avg_over_time × window` — it overcounts sparse series by ~1/presence-fraction; see query-templates.md §A0.4). |
| Wrapping `webseal_*:requests:rate5m` in `rate()` / `increase()` | They are recording rules that are **already** per-second 5m rates. Sum them directly for RPS; use `60 * sum_over_time(...[<window>])` for absolute counts (60 = the rules' eval interval — `avg_over_time × window` overcounts sparse 5xx series; see query-templates.md §A0.4). No raw counter is exposed, and there is no WebSEAL latency metric — latency comes from Traefik / the service graph after the handoff. |
| Reading `prodsoa-ext` as "external/internet-facing" | The `-ext`/`-int` suffix is SOA zoning. Both `prodsoa-*` front doors live on the **internal** WebSEAL gateway (`webseal_int`). Internet traffic enters via `webseal_ext` portals only. |
| Joining the two Traefik metrics by exact `exported_service` value | They use different naming schemes — `traefik_service_requests_total` has `<ns>-<svc>-<port>@kubernetesgateway`, the duration metric has router-derived `httproute-…-wrr@kubernetesgateway` names. The exact-value join silently returns empty; filter each with `.*-<svc>-.*`. |
| Ranking frontends by raw Faro error spans | Most raw `{faro && status=error}` spans are ad/analytics/consent fetches failing on ad-blockers (`doubleclick`, `usercentrics`, `hotjar`) — pure noise that buries real incidents (observed ~99% third-party). Filter `span.http.host` to first-party Gjensidige registrable domains (or use the Prometheus service-graph ratio, which is immune). |
| Reading a `client=<frontend> → server=itsec-eai-*` service-graph edge as a dependency | It is a **login-wall bounce**: the caller's portal request lacked a valid session and WebSEAL redirected it into the login plane. `url.query` on the EAI span (`TAM_OP=login&URL=…`) names the bounced request. A rising frontend → EAI edge means sessions are being sent to login (session loss / auth outage), not EAI load. See [`references/production-environment.md` §11](references/production-environment.md). |
| Mistaking `views-api-*` for the CMS | Enonic XP is `builders-exp-{tenant}`. `views-api-*` is the per-tenant BFF Enonic calls for dynamic data. |
| Forgetting Linkerd is being phased out | Do not query Linkerd metrics (`response_total{direction=...}`). Use Hubble (`hubble_flows_processed_total`), Tempo, OTel service-graph, and Spring Boot HTTP metrics instead. |

## Red Flags — Stop and Re-check

- You are about to report an error rate without a 7-day comparison
- You are about to name a "root cause" without showing the degraded edge
- You are about to attribute a degraded **bare-IP** server without a trace-confirmed identity (resolve it — see "Resolving a bare-IP server" in §B)
- You are about to report a DB2 / stored-procedure failure without its `SQLCODE` / `SQLSTATE` (unless it is a latency/timeout slowdown with no exception event — then say so explicitly, per §C)
- You are about to name an external HTTP edge (a core, or any HTTP server — BankID, Signicat, a partner API, …) as the cause without its failing **endpoint(s)** (method + path) — the host is not the granularity; pull them off the spans (`url.full`), see §C "Drilling into an external HTTP edge failure"
- You are reasoning from a service name rather than from a metric
- You ran a broad health check (§B) and never swept the frontend plane (§B Step 4) — frontend-first incidents are invisible to the gateway and core sweeps (Steps 1–3)
- You are about to write the §D4 BLAST RADIUS without having run §D0 (Faro frontend enumeration)
- You are about to claim — or rule out — customer impact without the WebSEAL external-edge check (§D3 Signal 1) *and* the Faro check (§D3 Signal 2)
- You are about to cite Traefik as evidence of customer exposure (Iron Rule 5)
- You are reading a single trace and generalising
- The incident window is inside 00:00–05:00 and you are quoting a relative rate without the absolute count (Iron Rule 4)

Each of these means: pull the baseline and the metric, then continue.

## Worked Example

For a full §A → §C → §D walkthrough that ends in a populated §D4 report — pattern to copy when you write yours — see [`references/worked-example.md`](references/worked-example.md).

## What the Skill Does Not Do

- It does not implement fixes or recommend escalation paths. It identifies the cause and the affected scope; the reader decides what to do with that.
- It does not use alerts, either as detection signals or as evidence. Detection and attribution are metric- and trace-driven only.
- It does not query logs. Loki is not exposed through the Grafana MCP. If logs are required to confirm a hypothesis after metrics + traces have narrowed the window, the responder must switch to the Grafana UI for that step.
- It does not run against test/non-prod environments without explicit instruction.
