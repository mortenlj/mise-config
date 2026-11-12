# Production Environment Map

> Names, hostnames, and migration states drift fast. Per Iron Rule 2 in the parent SKILL.md, **if a live query contradicts this file, trust the query** and note the discrepancy in your final report so this file can be updated.

This file describes the **stable shape** of the runtime environment — patterns, conventions, integration shapes. Volatile instance-level facts (specific service names beyond a few structurally fixed ones, specific procedure names, specific Azure resource suffixes, exact pod counts) are deliberately omitted; discover them with a query.

## 1. Clusters and observability

| Item | Value |
|---|---|
| Workloads cluster | `aks-apps-int-prod-013` |
| Platform/tooling cluster | `aks-tools-mgt-prod-003` |
| CNI | **Cilium** + **Hubble** (L3/L4 network observability) |
| Service mesh | Linkerd is being phased out (as of last-verified date above) — **do not query Linkerd metrics**. Use Hubble + Tempo + OTel service-graph instead. |
| Ingress | **Traefik** (`system-traefik` namespace) |
| Telemetry pipeline | **OpenTelemetry Collector** → Tempo + Prometheus(Mimir) (Loki exists in the platform but is not exposed via the Grafana MCP — use the Grafana UI for log queries) |
| GitOps & policy | ArgoCD, Gatekeeper, Falco, Trivy |

### Grafana MCP datasources (UIDs)

| UID | Type | Purpose |
|---|---|---|
| `prometheus` | Prometheus | All metrics (default datasource) |
| `tempo` | Tempo | Distributed traces, TraceQL |
| `azure-monitor-gjensidige` | Azure Monitor | Azure-native metrics for platform services |

## 2. Traffic Planes

```
   NORTH — Internet (customers, partners)        Intranet (employees, tooling, SOA)
                  │                                          │
                  ▼                                          ▼
        ┌───────────────────┐                     ┌───────────────────┐
        │ WebSEAL external  │                     │ WebSEAL internal  │  ← the TRUE edges
        │ webseal_ext:…     │                     │ webseal_int:…     │    (portal, junction,
        └─────────┬─────────┘                     └─────────┬─────────┘     backend, code)
                  │ junctioned_server                       │ SOA front door (prodsoa-*),
                  │                                         │ intranet — some, NOT all,
        ┌─────────┴──────────────┬──────────────────────────┘ internal traffic
        ▼                        ▼
  <svc>.apps-int          legacy-NAMED backends (*.mistralnett.com, bare IPs
  .gjensidige.io          — hosting varies: on-prem hosts OR GAP containers)
        │
        ▼
  ┌──────────────┐    egress to downstream systems
  │   Traefik    │ ─────────────────────────────────► SOUTH (core systems, DBs, SaaS)
  │   ingress    │   INTERNAL gateway,
  └──────┬───────┘   without exception (Iron Rule 5)
 ════════ ▼ ═════════════════════════════════════
 ║              EAST ↔ WEST                     ║
 ║  pod↔pod via Cilium/Hubble + traces + OTel   ║
 ║  Confluent Kafka — async backbone            ║
 ════════════════════════════════════════════════
```

| Plane | Primary source | Secondary source |
|---|---|---|
| Customer / partner edge (internet) | `webseal_ext:requests:rate5m` | Faro frontend spans (browser side — see `frontends.md`) |
| Internal-user / SOA edge | `webseal_int:requests:rate5m` | — |
| North-South ingress (in-cluster) | `traefik_*` metrics | Tempo `kind=server` root spans |
| North-South egress | `traces_service_graph_*` (client → external server) | Tempo `span.server.address`, `span.peer.service` |
| East-West L3/L4 | **Cilium / Hubble** (`hubble_flows_processed_total`, `cilium_*`) | — |
| East-West L7 / application | Tempo TraceQL + OTel `traces_service_graph_*` | Spring Boot `http_server_requests_*` / `http_client_request_*` |
| Async east-west | `confluent_kafka_*` + Tempo `span.messaging.*` | — |

### Edge gateways — IBM WebSEAL

Two WebSEAL reverse-proxy fleets are the true edges; Traefik is — without exception — the internal gateway for the cluster. Customer and partner impact is established here (SKILL.md Iron Rule 5). Two metrics, both **recording rules that are already per-second 5m rates** — sum directly for RPS, `60 * sum_over_time(...[<window>])` for absolute counts (60 = the rules' eval interval; `avg_over_time × window` overcounts sparse 5xx — see query-templates.md §A0.4):

- `webseal_ext:requests:rate5m` — the **external** gateway: all internet traffic (customer web portals + partner API portals)
- `webseal_int:requests:rate5m` — the **internal** gateway: *some, not all* internal traffic — the SOA-layer front door (`prodsoa-*`) and intranet portals used by internal tooling and customer handlers. The SOA layer is deployed inside the GAP cluster, so in-cluster callers routinely **hairpin** through this gateway: GAP pod → `webseal_int` → `<svc>.apps-int.gjensidige.io` → Traefik → SOA pod in the same cluster (see §4)

| Label | Meaning | Examples |
|---|---|---|
| `service_name` | the host / web portal the gateway instance received the request on | `www.gjensidige.no`, `connect.gjensidige.com`, `prodsoa-ext.mistral.mistralnett.com` |
| `junction` | the route the traffic was matched to | `/api-kunde`, `/eai`, `/gf/risiko` |
| `junctioned_server` | the backend that junction forwards to | `api-kunde.apps-int.gjensidige.io`, `P-114-270-210.mistral.mistralnett.com`, `139.105.73.148`, `-` |
| `response_code` | HTTP status returned to the caller | `200`, `302`, `401`, `500`, `502` |

**Portal classification — the "who" of customer impact** (discover the live set with label-values per Iron Rule 2; low-traffic portals drop out of instant results — use a 24h `max_over_time` window):

| Class | `service_name` (on `webseal_ext`) | Affected population |
|---|---|---|
| Customer portals | `www.gjensidige.{no,se,dk,com}`, `www.gouda.{no,fi,dk}`, `www.gouda-rf.se` | End customers on the public websites |
| Partner API portals | `connect-mtls.gjensidige.com`, `connect.gjensidige.com`, `partner.gjensidige.no`, `services.gjensidige.no` | Partners consuming our APIs — machine-to-machine traffic, so WebSEAL ext is the edge view for these |
| Internal portals (on `webseal_int`) | `intra.mistral.mistralnett.com`, `prodsoa-ext.mistral.mistralnett.com`, `prodsoa-int.mistral.mistralnett.com` | Employees, customer handlers, internal tooling, the SOA layer |

> **Naming trap:** `prodsoa-ext` is on the **internal** gateway — the `-ext`/`-int` suffix is SOA zoning, not internet exposure.

**`junctioned_server` families — where to take the investigation next:**

| Pattern | Meaning | Next hop |
|---|---|---|
| `<svc>.apps-int.gjensidige.io` | a GAP k8s service | Match into the cluster for the end-to-end view: Traefik `exported_service=~".*-<svc>-.*"` (shape `<namespace>-<svc>-<port>@kubernetesgateway`) → service graph `server="<svc>"` → Service and Pod. Templates in `query-templates.md` §A0. Known exception: the `gf{no,dk,se}-eai` login-plane backends, where the hostname prefix is not the service name — see §11. |
| `*.mistral.mistralnett.com` (incl. `P-114-*` machine names) | legacy-**named** backend — the domain is a naming/network zone, not a hosting statement: many services behind these hostnames run as containers in the GAP cluster, others on on-prem hosts | Discover the runtime per Iron Rule 2: look for an in-cluster match — service-graph `server`, `kube_pod_info`, or a trace (the k8s service name can differ from the hostname prefix). If nothing in-cluster matches, WebSEAL response codes are the covering metric. |
| bare IP | unnamed legacy backend | Identify out-of-band; WebSEAL response codes are the available signal. |
| `-` / `localhost` | WebSEAL answered the request itself | The login/session plane (auth redirects `302`, `401`s, cached `200`/`304`) — IAM territory. |

**Gotchas:**

- **WebSEAL measures volume + response codes.** Latency lives in Traefik / the service graph after the `apps-int` handoff.
- **Sparse-series churn.** A (portal, junction, server, code) series exists only while that combination saw traffic in the 5-minute window. An empty instant result ≠ zero errors over the incident window — query a range, or `60 * sum_over_time(...[<window>])` for absolute counts (not `avg_over_time × window` — it overcounts sparse series; see query-templates.md §A0.4).
- The metrics aggregate the whole gateway fleet; the four labels above are the complete label set.

## 3. The Core Systems

Most cross-cutting production incidents trace back to one of these. They are systems of record — services in the cluster are facades or callers, the truth lives outside the cluster.

For each core, the **identifying pattern** is the stable, multi-year fact. Specific service names, procedure names, and adapter rings churn — discover them with the queries in SKILL.md §C.

| Core | What it owns | Identifying pattern | Integration shape |
|---|---|---|---|
| **S2000** | NO non-life insurance (policy, claim, party, agreement) | `span.db.system="db2"` + `span.db.name="zaz23400"` + statement family `PROD.E*SP`, reached by **direct JDBC**. In `traces_service_graph_*` this surfaces as a **bare IP** (`139.113.31.225:2504` — verify, the IP may drift) because the service-graph metrics carry no `db.name`. | Stored-procedure RPC on the DB2 mainframe. Called **directly over JDBC** by many cluster services across domains (claims, sales, service, party/GK, …). Also fronted by IBM MQ + Kafka outbox (`o.gfno.s2000.*`) + adapter ring |
| **GK** (legacy party master) | NO customer / party master (legacy, migrating away) | Same DB2 mainframe as S2000 but a **separate procedure family**: `span.db.statement =~ "PROD\.GK[GH]?.*P"`. Observed procedure prefixes are `GKG*` and `GKH*` — discover the live set with the query in SKILL.md §C. | Stored-procedure RPC on the same DB2 mainframe as S2000; cluster-internal bridge service in `team-party` |
| **GPM** (new party master) | NO + DK customer / party master (modern, active migration target) | `span.db.system="postgresql"` + `span.db.name="gpmdb"`. PG host matches `gpm-cpo-party-{region}-prod-psql-*.postgres.database.azure.com` (region token varies — see §5). | Direct PG over Azure; bridge and consent services in `team-party` |
| **IDIT** (Sapiens MGS SaaS) | DK insurance core (policy, claim, party, proposal, contact, dictionary) | `span.server.address =~ ".*sapiensmgs\\.com.*"`. **Never called directly** — always via a per-entity adapter ring with service-name shape `gapi-adapter-{entity}-idit`. | Per-entity adapter ring fronting SaaS HTTPS |
| **F2100** (FDC, DK industry platform) | Cross-country pension + insurance | `span.server.address =~ ".*\\.fdc\\.dk.*"`. Reached via country-suffixed proxy services (`*-fdcproxy-gfdk`, `*-fdcproxy-gfse`) + DataPower `DP-GPF.svc.omni-fdc.dk`. | Proxy services + DataPower + pension-domain direct |
| **Dynamics 365** (CRM) | Customer interaction events, NO + DK tenants | `span.server.address =~ ".*\\.dynamics\\.com"`. Async path goes via Service Bus (`*.servicebus.windows.net`). | Direct HTTPS + Service Bus events + S2000↔Dynamics bridge service |
| **Archive / E-Archive / OnDemand** (Tietoevry) | Document system of record (long-term store + on-demand generation) | `span.server.address =~ "(earkiv\|wsedok\\.ec)\\.evry\\.com"`. Backbone services live in namespace `team-kda-archive`. | Multi-layer facade with external storage; inbound scans via Kofax service |

> **Party-master migration:** Party master is in **parallel migration**. GK (legacy on DB2) and GPM (new on Azure PG) both run in production today. Different callers route through different masters, so a "customer data" incident must be checked on **both** paths before assigning blame. If a query later shows traffic on only one path, the migration may have completed — trust the query.

### Integration patterns to internalise

| Pattern | Where it applies | How to recognise |
|---|---|---|
| Stored-procedure RPC on the mainframe | S2000 (`PROD.E*SP` family) **and** GK (`PROD.GK*P` family) — both on the same `ZAZ23400` DB2, distinguishable only by the procedure-name prefix | `span.db.operation="CALL"` + `span.db.name="zaz23400"` + statement prefix |
| Per-entity adapter ring | IDIT | Service names matching `gapi-adapter-*-idit` |
| Proxy services | F2100 | Service names `*-fdcproxy-gf{se,dk}` |
| Async bridges over Service Bus + Kafka | Dynamics | `dynamics-*` namespace + Service Bus host |
| Multi-layer facade with external storage | Archive | `team-kda-archive` services + `*.evry.com` targets |

### DB2 databases (`db.name`)

The on-prem DB2 fleet hosts several databases, reachable by bare IP or `*.mistral.mistralnett.com` hostname — key on `db.name`, not the address:

| `db.name` | System |
|---|---|
| `zaz23400` | S2000 + GK (shared mainframe) |
| `gpfp01`, `gps_esop` | GPF (pension) |
| `ivhp01`, `ivhp02` | IVH (InformasjonsVareHus — enterprise data warehouse) |

### Reading a DB2 stored-procedure failure (SQLCODE)

When an S2000 (or GK) stored-procedure span has `status=error`, the *why* lives in the span's `exception` event — `exception.message` carries `SQLCODE`, `SQLSTATE`, and `SQLERRMC`. The table maps the most diagnostic DB2 codes to a **starting hypothesis** — per Iron Rule 2, confirm it against the live signal; do not report it as fact.

| SQLCODE / SQLSTATE | Likely meaning | Where to point |
|---|---|---|
| **-440** / 42884 | Routine not found / no matching signature | SP dropped, recreated with a new signature, or `EXECUTE` not granted → **mainframe DDL / deploy** |
| **-805** / 51002 | Package not found in collection | **Bind missing** after a deploy |
| **-204** / 42704 | Object / procedure undefined | Object missing on the mainframe |
| **-471** / 55023 | SP body failed | Logic / data error **inside** the SP — read `SQLERRMC` for the failing module |
| **-803** / 23505 | Duplicate key / unique-constraint violation | Data conflict in the statement (can be **benign by design** — e.g. `ShedLock` scheduler-lock rows) |
| **-905** / 57014 | Resource limit exceeded (RLF / ASUTIME) — SP **killed** | SP ran past its CPU/time limit (runaway or expensive query, or a tightened limit); `SQLERRMC` names the proc + limit |
| **-952** / 57014 | Query interrupted / cancelled | Long-running query cancelled — usually the caller timed out and cancelled, or an operator interrupt |
| **-911 / -913** / 40001, 57033 | Deadlock / lock timeout | Contention on the mainframe |
| **-30081 / -4499 / -4470** | Connection / communication failure | Network or DB2 listener down — **connectivity, not logic** (but `-4499/08001` "Read timed out" *with* a high bare-IP edge p99 = mainframe **saturated/slow**, not down) |

`SQLERRMC` names the offending object / module (for `-905`, the procedure and the limit it blew) — always quote it. A whole *family* of procedures failing with the **same** SQLCODE that starts and recovers together is the signature of a single mainframe deploy / bind event, not an app-side fault. The table is not exhaustive — read any other negative SQLCODE the same way (e.g. `-104`/42601 SQL syntax or `-804`/07002 bad input parameters point to an **application bug**, not the mainframe); look up unfamiliar codes.

## 4. The integration tier (SOA bus)

`prodsoa-ext.mistral.mistralnett.com` (external-facing) and `prodsoa-int.mistral.mistralnett.com` (internal) are the **SOA bus** — a legacy ESB that brokers HTTP integration calls. A routing layer, not a system of record — it owns no data.

> **`prodsoa-*` is a front door for the whole SOA layer, not one service.** It routes to many distinct backends — in-cluster GAP services and external systems alike. A high error/latency rate on the `prodsoa-*` hostname edge is therefore an **aggregate**, and the layer rarely fails uniformly. Never attribute it to the bus itself — decompose it. The front door lives on the **internal WebSEAL gateway** (`-ext`/`-int` is SOA zoning; both hostnames are `service_name`s on `webseal_int`), so `webseal_int:requests:rate5m{service_name=~"prodsoa-.*"}` breaks the layer down by `junction` (the SOA operation route) and `junctioned_server` (the concrete backend — mostly `<svc>.apps-int.gjensidige.io` GAP services, plus legacy hosts and bare IPs). For operation-level detail, read a trace: the server span after the `server.address=prodsoa-*` client hop, whose `url.full` names the operation. Identify the backend set from the junction metric or from traces — they neither all share a `soa` name nor sit in one namespace. See §C "Drilling into a DB2 stored-procedure failure" and SKILL.md §B Step 2.

**The SOA layer is deployed in the same cluster as every other GAP service.** A typical SOA call from inside the cluster therefore **hairpins**: GAP pod → WebSEAL internal (`prodsoa-*` junction) → back into the same cluster (`<svc>.apps-int.gjensidige.io`, through Traefik) → SOA pod. One logical call thus shows up at three measurement points — the caller's client edge in the service graph, the `webseal_int` junction, and Traefik — before reaching the SOA service's own server-side telemetry. (Verified in traces: e.g. root `api-forsikringer` → client span `server.address=prodsoa-ext.mistral.mistralnett.com` → server spans at `salg-soa-risiko`, all in one trace.)

Trace context propagates through the hairpin, so the service graph links the caller **directly** to the SOA service (`client="api-forsikringer", server="salg-soa-risiko"`); the `prodsoa-*` hostname additionally appears as a server-only **virtual node** from the callers' client spans. The measurement points agree in *shape* (spike timing, response-code mix), not in magnitude — each leg counts at a different point (gateway-answered responses count on the junction; in-cluster callers add to Traefik), so per-leg volumes differ structurally and drift over time. Match flows by **identity** (`junction` → `junctioned_server` → `exported_service` → `server`) and compare shapes across legs; treat absolute counts as per-leg facts, never reconcile them 1:1.

> `*.mistralnett.com` is a **shared legacy domain** spanning many distinct systems — the SOA bus (`prodsoa-*`), CRM (`crmapps`), the intranet (`intra`), and several DB2 / database hosts (`db2prod`, `gnfdbag-p*`, …). Match the specific hostname for the system you mean — and remember the domain says nothing about hosting: many services behind `mistralnett` names run as containers in the GAP cluster, others on legacy machines.

## 5. Azure data plane (per-domain)

Per-domain instance with a stable name shape. Discover the actual hostname currently in use with a `topk by (server)` against `traces_service_graph_request_total` — the **instance suffix** (`-001`, `-002`, `-004`, …) changes with failovers.

| Service | Hostname shape |
|---|---|
| PostgreSQL Flexible Server | `gpm-cpo-{domain}-{region}-prod-psql-*.postgres.database.azure.com` (one or more per business domain) |
| Azure SQL | `gpm-cpo-{domain}-{region}-prod-sql-*.database.windows.net` |
| Redis Cache | `gpm-{domain}-redis-{region}-prod-redis.redis.cache.windows.net` |
| Blob Storage | `gpm{…}prodsa.blob.core.windows.net` |
| Key Vault | `gpm-{domain}-shr-{region}-prod-kv.vault.azure.net` |
| Service Bus | `gpm-{domain}-{region}-prod-sbus.servicebus.windows.net` |

`{region}` is a short region token (`en` and `we` both observed live). It varies per resource: keep it a wildcard (`[a-z]+`) in regexes, never an anchor.

`{domain}` is one of the business-domain slugs (e.g. `party`, `gpf`, `kda`, `salg`, `swe`, …). The slug set drifts as domains split or merge — discover the current set with `topk(30, count by (server) ({server=~"gpm-.*\\.(postgres\\.database|servicebus|redis|vault)\\.(azure|windows)\\.(com|net)"}))` rather than reading it from a list.

## 6. Confluent Kafka

Central event backbone. Topic naming convention reveals layout:

```
{p|o|s}.{gfno|gfdk}.{domain}.{type}.{detail}.r.{n}
```

| Segment | Meaning |
|---|---|
| `p` | produced (input) |
| `o` | outbox |
| `s` | stream |
| `gfno`, `gfdk` | Gjensidige Forsikring Norge / Danmark |
| `domain` | `s2000`, `policy`, `claim`, `party`, `crm`, `iam`, `partners`, `communication`, `task`, etc. |
| `type` | `fct` (fact), `notf` (notification), `sys` (system event), `que` (queue), `delta` |
| `r.n` | revision number |

S2000 outbox: `o.gfno.s2000.fct.outbox-stka{001\|050\|101}-{stream}.r.0`

Confluent metrics: `confluent_kafka_server_*` (received_records, sent_records, consumer_lag_offsets).

## 7. Public-Site CMS (Enonic XP, multi-tenant)

Five namespaces, identical template, one tenant per market:

| Namespace | Tenant |
|---|---|
| `gjensidige-no` | www.gjensidige.no |
| `gjensidige-dk` | www.gjensidige.dk |
| `gjensidige-se` | www.gjensidige.se |
| `gjensidige-com` | www.gjensidige.com (corporate / IR) |
| `gjensidige-builders` | shared SDK + asset origin + intranet |

Per namespace:

| Deployment | Role |
|---|---|
| `builders-exp-{tenant}` | **Enonic XP** — the CMS itself. Java + embedded Elasticsearch. |
| `views-api-{tenant}` | Lightweight per-tenant BFF that Enonic calls for dynamic data |
| `builders-cache-{tenant}` | HTTP edge cache fronting Enonic |
| `builders-image-optimizer-{tenant}` | On-the-fly image transforms |
| `builders-globals-core-navigation-{tenant}` | Shared header widget |
| `builders-globals-footer-{tenant}` | Shared footer widget |
| `application-portal-deployment` (DK, SE only) | Customer authenticated landing |

The `gjensidige-builders` namespace additionally hosts the asset-server variants and is the most-called node in the CMS estate.

## 8. `cdn.gjensidige.no`

Shared static-content CDN used by **both** browsers (north-south, dominant load, **invisible to traces**) and several backend services (Enonic XP, application portals, communication services, document/output servers).

- True load lives at the CDN edge — use the CDN provider's dashboard for actual customer-visible health. Service-graph metrics only show the small backend-originated tail.
- Discover the current backend callers with `topk(20, sum by (client) (rate(traces_service_graph_request_total{server="cdn.gjensidige.no"}[5m])))`.

A CDN outage degrades the public site, customer-portal landing pages, outgoing emails, generated letters, and product disclosures simultaneously — wide blast radius.

## 9. Namespace Conventions

> **Do not memorise downstream-dependency mappings from a table.** Domain-to-core mappings change as services are added, migrated, or split. Always discover the actual downstream dependencies of a service with a live `traces_service_graph_*` query (see [`query-templates.md` §C5 / §H2 / §H4`](query-templates.md)). What follows is **only** namespace/naming conventions — useful for locating a service, not for guessing what it depends on.

### Naming pattern

Workload namespaces follow one of three patterns:

| Pattern | Examples | Notes |
|---|---|---|
| `team-<name>` (most common) | `team-claims`, `team-gpf`, `team-party`, `team-service`, `team-salg`, `team-sweden`, `team-dynamics`, `team-it-security`, `team-kda-archive`, `team-kda-communication`, `team-services-denmark`, `team-bi-data-science`, `team-enabling-ai`, `team-mobile-app`, `team-utbytte`, `team-fraud`, `team-map`, `team-sands`, `team-boligsalg`, `team-builders`, … (discover the live set with `kube_namespace_labels` rather than relying on this list) | The default. The ns name encodes team ownership directly. |
| `integration-<area>` (no `team-` prefix) | `integration-soa`, `integration-api`, `integration-eip`, `integration-adapter`, `integration-kafka`, `integration-denmark`, `integration-ai` | Integration teams pre-date the `team-` convention. |
| `gjensidige-<tenant>` | `gjensidige-no`, `gjensidige-dk`, `gjensidige-se`, `gjensidige-com`, `gjensidige-builders` | Public-site CMS tenants only. |
| Misc / non-team | `commercial-uw`, `default`, `gatekeeper-system`, `kube-system`, `system-*` | Platform / infra. |

### Locating a service when only the name is known

A service named e.g. `claims-soa-skadesak` can live in `team-claims` or in `integration-soa` depending on ownership. To find the actual namespace, query:

```promql
kube_pod_info{pod=~"<service-name>.*"}
```

or look at `resource.k8s.namespace.name` in any of its spans.

### Country conventions in service names (not in namespace names)

- `*-se` suffix → Sweden flow (lives mostly in `team-sweden`, but not exclusively)
- `dk-*` prefix → Denmark flow (lives mostly in `team-services-denmark`, but country-spread)
- No suffix usually means Norway (the default), though there are exceptions

### What lives where — only the things that are structurally stable

| Stable fact | Where |
|---|---|
| Enonic XP CMS tenants | `gjensidige-{no,dk,se,com,builders}` (one tenant per ns) |
| KDA archive backbone | `team-kda-archive` |
| KDA communication services | `team-kda-communication` |
| Pension (GPF) | `team-gpf` |
| Party master (both GK bridge `party-party-cs-service` and new `party-gpm-service`) | `team-party` |
| IDIT adapter ring (`gapi-adapter-*-idit`) | `team-services-denmark` |
| FDC/F2100 proxies (`integration-soa-fdcproxy-*`) | `integration-soa` |
| S2000 ↔ Dynamics bridge (`dynamics-crm-services-s2000todyn`) | `team-dynamics` |
| Traefik | `system-traefik` |

Everything else: **discover with a query**, do not assume.

## 10. External downstream — quick reference

| Category | Examples (regex match in `span.server.address`) |
|---|---|
| `mistralnett.com` — shared domain spanning many different systems (SOA bus, DataPower, app hosts, …), mixed hosting | `.*\\.mistralnett\\.com.*` |
| Azure PostgreSQL | `.*\\.postgres\\.database\\.azure\\.com` |
| Azure Redis | `.*\\.redis\\.cache\\.windows\\.net` |
| Azure Blob | `.*\\.blob\\.core\\.windows\\.net` |
| Azure Service Bus | `.*\\.servicebus\\.windows\\.net` |
| Azure Key Vault | `.*\\.vault\\.azure\\.net` |
| Tietoevry archive | `(earkiv\|wsedok\\.ec)\\.evry\\.com` |
| Dynamics 365 | `.*\\.dynamics\\.com` |
| IDIT | `.*sapiensmgs\\.com.*` |
| F2100 (FDC) | `.*\\.fdc\\.dk.*` |
| NO public sector | `.*\\.(bankid\|altinn\|skatteetaten\|nav\|brreg)\\.no` |
| Identity / signing | `id\\.signicat\\.com`, `api\\.signicat\\.com`, `auth\\.tsp\\.buypass\\.no` |
| Finans Norge | `.*\\.finansnorge\\.no` |
| Microsoft identity | `login\\.microsoftonline\\.com`, `graph\\.microsoft\\.com` |
| Confluent Cloud | `.*\\.confluent\\.cloud` |

## 11. The login plane (EAI)

`itsec-eai` is the WebSEAL login engine ("External Authentication Interface"): it authenticates portal users against external ID providers, renders WebSEAL's login/error pages, and enriches fresh sessions with customer data. One instance per market in `team-it-security` (plus `-beta` shadows), each behind the `/eai` junction of its portal — on **`webseal_ext` only**, with part of the junction traffic answered by the gateway itself (`junctioned_server="-"`):

| Portal (`service_name`) | `/eai` backend (`junctioned_server`) | k8s service / service-graph `server` |
|---|---|---|
| `www.gjensidige.no` | `gfno-eai.apps-int.gjensidige.io` | `itsec-eai-gfno` |
| `www.gjensidige.dk` | `gfdk-eai.apps-int.gjensidige.io` | `itsec-eai-gfdk` |
| `www.gjensidige.se` | `gfse-eai.apps-int.gjensidige.io` | `itsec-eai-gfse` |

The apps-int hostname prefix differs from the k8s service name here (`gfno-eai` vs `itsec-eai-gfno`), so the §2 prefix-to-service handoff recipe does not apply — use this table (Traefik backends match `exported_service=~".*-itsec-eai-.*"`). The same trap hits the §D3 / H5 customer-exposure check: built from the service names (`itsec-eai-gfno.apps-int…`) the `junctioned_server` regex matches nothing and EAI reads as not customer-facing — use the `gf{no,dk,se}-eai` hostnames from this table instead.

Fully OTel-traced with route-level span names (`GET /eai/op`, `/eai/bankid`, `/eai/nid`, …). It exposes no Micrometer/JVM metrics — SLIs come from the service graph, spanmetrics, Traefik, and WebSEAL.

| Role | Where it shows in telemetry |
|---|---|
| ID-provider login | NO: `/eai/bankid` calls `auth.bankid.no` + `userinfo.bankid.no` directly (smaller flows: Buypass, Handelsbanken). DK / SE: `/eai/nid` calls the market's OIDC broker `sid.gjensidige.dk` / `sid.gjensidige.se`. Client spans carry the IdP `url.full`. On success EAI answers WebSEAL with `am-eai-*` session headers + `302` — the headers are invisible in telemetry; an invalid handshake bounces the user to `/eai/op?TAM_OP=eai_auth_error`. |
| WebSEAL local-response pages | `/eai/op` renders the login/error page. WebSEAL passes `TAM_OP=<operation>` (`login`, `error`, `stepup`, `acct_locked`, `too_many_sessions`, `eai_auth_error`, …), `ERROR_CODE=<hex>`, and `URL=<the protected URL that triggered it>` — all readable on the span's `url.query`. `ERROR_CODE=0x00000000` = plain login; anything else is a failure code — ISAM/WebSEAL hex (e.g. `0x132120c8` invalid credentials, `0x38cf04d7` junction backend not responding), `BID-*` (BankID) or `EAI-*` (EAI-internal) — lookup table: `doc/ERROR_CODE.txt` in the `gjensidige/itsec-eai` repo for the legacy + WebSEAL hex codes; the OIDC-era codes (`BID-E0`–`E5`, `EAI-7`–`11`, `EAI-9001`) are defined in the servlet source. Triage-critical pair: `EAI-9001` = user cancelled at the IdP (benign, common), `EAI-08` = post-login enrichment lookup failed (a backend fault). Error-page bounces typically answer HTTP `200` (the page rendered fine), so they never appear in error-rate SLIs or `status = error` searches — find them by query-string match (`query-templates.md` G10). |
| Post-login customer enrichment | Parallel fan-out per market, hairpinned via `prodsoa-ext` (§4): NO → `integration-soa-parta2a` + `integration-soa-legitimering` (→ party master); DK → FdcProxy customer (F2100) + IDIT contacts + useradmin; SE → `integration-soa-fdcproxy-gfse` + customer adapter. A login failure is therefore often a **core failure** (§3) — one failing login trace names the leg. |

Every market's login flow stores and validates its OIDC `state` in the **same shared Azure Redis** (`gpm-itsec-redis-*`) — observed as `SETEX`/`GET`/`DEL <state>` spans inside `/eai/bankid` and `/eai/nid` traces in all three markets. When login degrades in more than one market at once, check this shared dependency first: the Redis client edge (`client=~"itsec-eai.*", server=~"gpm-itsec-redis.*"`) from each instance. (The Redis client code swallows connection failures rather than crashing, so the symptom is degraded logins, not EAI 5xx — verify at the edge, per Iron Rule 2.) One trace blind spot: EAI queries the ISAM **LDAP** registry over JNDI, which emits no span — an LDAP problem shows as slow/erroring EAI server spans with no failing child.

**Bounce edges:** service-graph edges `client=<app> → server=itsec-eai-*` (Faro frontends and backend callers alike) are **login-wall bounces**, not dependencies: the caller's portal request lacked a valid session and WebSEAL redirected it into the login plane (same-origin redirect, so trace context survives). `url.query` on the EAI span — `TAM_OP=login&URL=…` — names the original bounced request. A rising frontend → EAI edge measures sessions being sent to login, not EAI load.
