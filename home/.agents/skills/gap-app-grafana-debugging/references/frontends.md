# Frontends (Grafana Faro Web SDK)

The Grafana Faro Web SDK instruments browser-side apps and emits OTel spans for their `fetch` / `XHR` calls. In the GAP environment this means **frontends appear in `traces_service_graph_request_total` as `client`-only nodes** — they call backends but never receive inbound calls from other services. There are several dozen (claims fillout flows, `dk-webshop-*`, `service-*` portals, partner portals, etc.) and the exact set is **window-dependent** — a single peak hour enumerates fewer than a full day. Discover it, do not hardcode (Iron Rule 2).

## Enumerate the frontend set (authoritative)

Use the Faro SDK fingerprint on resource attributes:

```
mcp tempo_get-attribute-values
  name         = resource.service.name
  filter-query = { resource.telemetry.distro.name = "faro-web-sdk" }
```

This returns every Faro-instrumented `service.name` that emitted a span in the search window. `resource.telemetry.distro.name = "faro-web-sdk"` is set only by the Grafana Faro Web SDK — no false positives.

Fallback / cross-check markers (any one is browser-only):

- `resource.telemetry.sdk.language = "webjs"`
- `resource.browser.mobile` / `resource.browser.platform` / `resource.browser.language` set
- `resource.user_agent.original` set

## Topology cross-check (no Faro attribute needed)

A Faro frontend is structurally a node that is `client` but never `server` in the service graph. Independent of attributes:

```promql
# Nodes that appear as client but never as server in the search window
(
  group by (name) (label_replace(traces_service_graph_request_total,
    "name", "$1", "client", "(.+)"))
)
unless
(
  group by (name) (label_replace(traces_service_graph_request_total,
    "name", "$1", "server", "(.+)"))
)
```

**False positives** for this query: CronJobs, scheduled batch publishers, fire-and-forget producers. In practice it returns **~1200+ client-only nodes** against the several dozen actual Faro frontends, so use it as a **bootstrap/corroboration** only — never the authoritative set. Recommended workflow: pull the Faro list first (above) → filter the service-graph queries to that set. The one case for the topology query is **detection when the Faro enumeration is unavailable** (§B Step 4): the per-frontend error sweep is Prometheus-only, so it still runs against all client nodes and surfaces the impact, just unlabelled.

## Slicing by portal (which `.no` / `.dk` / `.se` host is affected)

Five Gjensidige browser hosts appear in Faro telemetry: `www.gjensidige.{no,dk,se,com}` and `www.heihuset.no` (Hei Huset sub-brand). The host lives on every Faro fetch/XHR span as `span.http.host`.

**This slicing lives in Tempo, not in PromQL service-graph metrics.** The service-graph generator builds edges by `service.name`, so portal hosts don't appear as `server` labels — `traces_service_graph_request_total{server=~"www\\.gjensidige\\..*"}` returns essentially nothing. Use TraceQL instead:

```
# Investigate failing browser traffic on a specific portal
{ resource.telemetry.distro.name = "faro-web-sdk"
  && span.http.host = "www.gjensidige.dk"
  && status = error }

# Per-portal rates via TraceQL metrics (aggregation in Tempo)
{ resource.telemetry.distro.name = "faro-web-sdk" } | rate() by (span.http.host)
{ resource.telemetry.distro.name = "faro-web-sdk"
  && status = error } | rate() by (span.http.host)
```

**Cross-portal interpretation.** Baseline each portal independently before declaring a "spike" (Iron Rule 1) — the portals run at volumes that differ by orders of magnitude (discover the current levels with a query), so raw rates are not comparable across portals. Use `quantile_over_time(...[7d:5m])` on a saved per-host series, or `compare()` / `offset 7d` against the TraceQL-metrics output. Then:

- Above-baseline on `.no` + `.dk` + `.se` simultaneously → **shared dependency** (auth, CDN, GPM/party-master, Azure region, a shared API gateway).
- Above-baseline on one host only → **portal-specific** (country-scoped backend, locale config, single-country middleware).
- `gjensidige.*` elevated but `heihuset.no` not → narrows further by sub-brand.

**Do not substitute service-name prefix for host.** The `dk-*` / `*-se` regex works cleanly for **scoped backends** (`adapter-*-se`, `dk-services-be-springboot-*`, etc.), but several Faro frontends are **shared across portals** — `report-claim`, `gje-claim-*`, `commercial-policy-overview` and others call `www.gjensidige.no` *and* `www.gjensidige.dk` depending on the user's locale. Service-name alone cannot tell you which portal the user was on; `span.http.host` can.

## What frontends mean for §B / §A / §D

- **§B Step 4 (detection — the point most often missed):** a per-frontend **error-rate** sweep is a customer-facing **detection plane**, co-equal with the WebSEAL-ext and Traefik sweeps — run it in *any* broad-mode pass, not only after a backend cause is found. It is the only signal that catches a frontend failing against a backend behind **neither** gateway, a CORS-preflight failure, or the frontend's own bad deploy. Two reachable forms: **Tempo TraceQL** — `{ faro && status=error && span.http.host=~<first-party> } | rate() by (resource.service.name)` (richest — sees CORS + non-graph hosts; the host filter is **mandatory**, see the third-party trap below) — and the **Prometheus service-graph error ratio** (always-available fallback when the Tempo proxy is down; naturally first-party). Query forms: [`query-templates.md` §C8](query-templates.md). Rank detection on **error rate**; frontend latency is a usable secondary view (a p99 from either source is robust — see below).
- **§A Step 3 (downstream edges):** if any `client` of the degraded server is in the frontend set, that backend is **directly customer-facing** — failures surface to users immediately, even if the backend itself isn't routed through Traefik.
- **§D1 (blast radius):** when listing affected clients of a degraded server `X`, label frontends explicitly. A failure that cascades into `report-claim` or `dk-webshop-house` is qualitatively different from one that cascades into an internal batch job.
- **§D3 (customer-facing exposure):** the WebSEAL external edge (which portal + junction fronts the service — `webseal_ext:requests:rate5m`, see `production-environment.md` §2) is one customer-facing signal; Faro frontend dependency is the other. They are complementary — WebSEAL sees every request that reached the internet edge (including browserless partner API traffic), Faro sees what the user's browser experienced. Run both — either signal promotes the affected service to the customer-facing list in the report.

## What the Faro signal reaches — and the host trap

Faro's **traces** are browser `fetch`/`XHR` spans (span names `GET`/`POST`/… and `HTTP GET`/… across SDK versions) plus **`CORS Preflight`** spans. That is the whole reachable surface: per-frontend API success/latency, the target `span.http.host`, and HTTP status. One trap makes a naive error sweep almost pure false positives — third-party hosts — plus a minor latency caveat:

- **Third-party host noise — filter is mandatory.** Most raw Faro error spans are fetches to ad / analytics / consent / chat domains (`doubleclick`, `googleadservices`, `usercentrics`, `hotjar`, `cjteradata`, …) failing on ad-blockers and tracking-protection — not incidents. Observed: `dk-policy-overview` 0.87 → 0.006 err/s once filtered to first-party hosts (~99% was third-party), and the naive top-3 were *all* ~99% third-party. Filter to **Gjensidige-owned registrable domains** (exact regex in [`query-templates.md` §C8](query-templates.md) — keep the one copy authoritative, it drifts per Iron Rule 2). Two subtleties the filter must honour: browsers fetch the public portal host (`www.gjensidige.*`), **never** the internal `apps-int.gjensidige.io` address (that is WebSEAL's post-edge backend, not a browser host); and a bare `gjensidige` substring is wrong — it readmits vendor hosts that carry a `gjensidige` label (`gjensidige.piwik.pro`, `gjensidige.humany.net`), so anchor on the registrable domain. The Prometheus service graph is immune (third parties aren't graph nodes), which is why it reads clean.
- **Latency is usable — but `max` / individual durations are not.** Browser spans *occasionally* carry impossible durations from clock-skew / suspended tabs (a `gje-claim-details` span at ~953 days), but these are vanishingly rare — over a full day, **~106 `duration > 1h` spans across *all* frontends** — so they corrupt a `max_over_time(duration)` or a single-trace reading, **not** a quantile. Verified at peak: `gje-claim-details` raw-span p50/p95/p99/p999 = 0.07 / 1.43 / 3.12 / 7.05 s and the Prometheus service-graph client p99 = 8.5 s — both sane single-digit seconds, consistent in shape (they differ on bucketing / window / client-side network, neither is garbage). So a frontend p99 is fine from **either** the TraceQL `quantile_over_time(duration, 0.99)` or the `traces_service_graph_request_client_seconds_bucket{client=<frontend>}` histogram — just guard `max`-style reads with `duration < 60s`. Detection still ranks on **error rate** (the cleaner customer-impact signal); latency is the secondary view for a *slowness* symptom.

What the Faro signal does **not** reach at all:

- **Browser → CDN** static-asset fetches (`cdn.gjensidige.no`) — use the CDN provider's edge metrics, invisible here.
- **Page-load timing, web-vitals, JS exceptions.** These are Faro *measurements* / *events* / *logs* (→ Loki / the Frontend Observability app), **not** OTel traces — confirmed: the only Faro span names are HTTP + CORS-preflight, no `documentLoad`/web-vital spans reach Tempo. The Prometheus `faro_receiver_*` metrics are collector-level only (labelled by Alloy pod, **no per-app dimension**), so they can't attribute to a frontend either.
- **Pre-Faro legacy bundles** that haven't adopted the SDK yet.
- Apps that emit `service.name = "not_specified"` — these collapse into a single noisy row. Chase down with the owning team if it matters for an incident.

## Edge cases when reading the enumerated list

- Some Faro `service.name`s look backend-ish (e.g. `dk-login-proxy`, `treatment-selector-admin`) — these are admin tools or BFFs running Faro on an operator UI. Sanity-check before treating them as pure end-customer apps.
- A `service.name` present in the Faro enumeration but missing from `client` in the service graph for the last hour means the bundle loaded but made no instrumented HTTP calls in that window. Still a frontend; just no service-graph activity to act on.
- Faro emits spans from the browser, so per-pod / per-namespace Kubernetes metrics do not apply — `kube_pod_*` queries on a frontend `service.name` will return empty. Frontend "health" is observed through its outbound edges (success / latency of its API calls) and through Frontend Observability events.
