# Worked Example — "claims is failing this morning"

A full §A → §C → §D walkthrough showing how the workflow turns into a report. The specific service names, IPs, and procedure names below are illustrative; in a real invocation, discover them via Iron Rule 2 — query the live environment, do not assume the names from this page.

**Symptom:** "claims is failing this morning."

1. **Confirm (§A Step 2):** inbound error rate for `claims-soa-skadesak` — current vs `quantile_over_time(...[7d:5m])`. Suppose it is 38% now vs ~0.3% baseline. *Anomaly confirmed.*

2. **Locate the degraded edge (§A Step 3):** per-edge failure rate out of `claims-soa-skadesak`:
   ```promql
   sum by (server) (rate(traces_service_graph_request_failed_total{
     client="claims-soa-skadesak"}[5m]))
     / sum by (server) (rate(traces_service_graph_request_total{
     client="claims-soa-skadesak"}[5m]))
   ```
   Suppose the degraded `server` is a **bare IP** (e.g. `139.113.31.225`) at 100% failure — not a hostname. *It cannot be identified from metrics alone.*

3. **Resolve the bare IP (§B "Resolving a bare-IP server"):** pull one trace to it:
   ```traceql
   { span.server.address = "139.113.31.225" && status = error }
   ```
   The span carries `db.system=db2`, `db.name=zaz23400`, `db.connection_string=db2://139.113.31.225:2504`. *The bare IP is the S2000 DB2 mainframe.*

4. **Drill into the core (§C "Drilling into a DB2 stored-procedure failure"):**
   - **WHICH** — failing procedures via spanmetrics `status_code`:
     ```promql
     sum by (service, span_name) (rate(traces_spanmetrics_calls_total{
       span_name=~"CALL PROD\\..*", status_code="STATUS_CODE_ERROR"}[5m]))
     ```
     Suppose `CALL PROD.ESK62NSP` dominates.
   - **WHY** — read the SQLCODE from the failing span's `exception` event:
     ```traceql
     { name = "CALL PROD.ESK62NSP" && status = error }
     ```
     Suppose `exception.message` = `DB2 SQL Error: SQLCODE=-440, SQLSTATE=42884, SQLERRMC=PROCEDURE;PROD.ESK62NSP`. Per the SQLCODE table (`production-environment.md` §3), `-440` = routine not found → a mainframe DDL/deploy or missing bind. A whole proc family failing with the same code, starting and recovering together, confirms a single deploy/bind event — not an app-side fault.

5. **Run §D follow-up:**
   - **D1** — clients of the mainframe running that procedure: `claims-soa-skadesak`, `claims-soa-skadeoversikta2a`, `claims-soa-skade`, `claims-soa-skadesaka2a` (namespace `team-claims`). S2000 is cross-domain — callers from other domains may appear too.
   - **D2** — cascade check: `claims-soa-skadesak` error rate up from 0.3% → 38% (CASCADED). Others still within baseline (CONTAINED).
   - **D3** — customer exposure via WebSEAL ext + Faro (both signals): the `webseal_ext` 24h junction check on `(claims-soa-.*)\.apps-int\.gjensidige\.io` returns no customer/partner portal junctions; the Faro check shows frontend `report-claim` calling `claims-soa-skadesak` directly. **User-visible via the claims frontend.** The same check on `webseal_int` returns the `/gf/skadeoversikt` SOA junction → internal customer handlers are also exposed.

6. **Report (using §D4 template):**
   ```
   SYMPTOM
     Claims domain APIs returning 5xx since ~09:14.

   ANOMALY CONFIRMED
     claims-soa-skadesak inbound error rate = 38% vs 0.3% 7-day baseline
     Started ~2026-06-03 09:14

   ROOT CAUSE
     S2000 DB2 stored procedure PROD.ESK62NSP (db.name=zaz23400,
     db2://139.113.31.225:2504) returning SQLCODE=-440 / SQLSTATE=42884
     (routine not found → mainframe DDL/deploy or missing bind)
     - Example trace IDs: <ids>

   BLAST RADIUS
     Customer-facing affected (WebSEAL ext — customer portals):   none
     Partner-facing affected (WebSEAL ext — partner API portals): none
     Customer-facing affected (Faro frontends):                   report-claim → claims-soa-skadesak
     Internal-user exposure (WebSEAL int — intranet / SOA):       /gf/skadeoversikt junction
     Internal affected (CASCADED): claims-soa-skadesak (error rate 0.3% → 38%)
     Internal affected (CONTAINED): claims-soa-skadeoversikta2a, claims-soa-skade, claims-soa-skadesaka2a
   ```

## What the report does and does not do

- ✅ States baseline alongside every quantitative claim
- ✅ Resolves the bare-IP backend to a named system (S2000) before attributing blame
- ✅ Names the actual root cause down to the procedure AND its SQLCODE
- ✅ Distinguishes CASCADED from CONTAINED victims (not all callers are equally hurt)
- ✅ Flags customer-visible exposure explicitly, with the audience (Faro frontend users + internal handlers via the SOA junction; portals clean)
- ❌ Does not blame `claims-soa-skadesak` (it's a symptom, not the cause)
- ❌ Does not report the bare IP as the cause, nor the DB2 failure without its SQLCODE
- ❌ Does not propose fixes or escalation paths — the reader infers those from BLAST RADIUS and ROOT CAUSE

## Variant — when the cause is an external HTTP edge (not DB2)

A DB2 failure resolves to **procedure + SQLCODE**; an external HTTP edge resolves the same way to **endpoint + status** — the host alone is never the answer. Suppose §A/§B point at `server="gjensidige-idit.sapiensmgs.com"` erroring. Stopping at "IDIT is failing" is the mistake (the service graph only knows the host); drill to the endpoints (§C / templates §D5), normalise the IDs out, and the ROOT CAUSE names the endpoint:

```
ROOT CAUSE
  IDIT (Sapiens MGS SaaS, gjensidige-idit.sapiensmgs.com) — failing endpoint:
    GET /idit-web/api/v2/loss-event/{id} → 422   (POST /idit-web/api/search/ unaffected)
  Evidence:
    - traces_service_graph error rate to sapiensmgs.com up vs 7-day baseline (host-level)
    - failing endpoint GET /idit-web/api/v2/loss-event/{id} = 422, via gapi-adapter-claim-idit
    - Example trace IDs: <ids>
```

The same shape applies to any external HTTP edge — the other cores (`*.fdc.dk`, `*.dynamics.com`, `*.evry.com`) and non-core edges (BankID, Signicat, partner APIs) alike.
