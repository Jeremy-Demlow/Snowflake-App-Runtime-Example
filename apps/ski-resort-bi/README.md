# Ski Resort BI Explorer (custom SPCS container)

A Streamlit BI app that pairs a read-only KPI dashboard with a **governed,
free-range data explorer** powered by the Cortex Code Agent SDK, plus a deployed
Cortex Agent (`RESORT_EXECUTIVE`) consulted as a trusted baseline.

This is the repo's **"third lane"** example — see the
[root README](../../README.md) and [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)
for how the three deployment lanes (SiS / App Runtime / raw SPCS) compare.

## Why this is a custom-image SPCS app (not `type: streamlit`)

The explorer's engine (`cocosdkagent` → `cortex_code_agent_sdk`) shells out to
the **`cortex` CLI binary**, which is curl-installed, not pip-installable. The
managed Streamlit-in-Snowflake runtime can only add pip packages, so it cannot
host the binary. This app therefore ships as its **own container image** (the
`cortex` CLI baked in) deployed to **Snowpark Container Services**.

> Note for this repo: the auto-discovery CI deploys `type: streamlit` (SiS) and
> `type: snowflake-app` (App Runtime). This app is a **raw-SPCS custom image**,
> which those two paths don't cover (App Runtime exposes only a build-time EAI
> and no secret mount; this app needs a **runtime** EAI + a key-pair secret).
> It has no `snowflake.yml`, so the CI auto-discovery skips it; deploy it with
> `setup.sql` (Kaniko build + `CREATE SERVICE`).
>
> **Roadmap:** Snowflake App Runtime is **Node.js-only** today (Python is on the
> roadmap). Once App Runtime supports Python, a Streamlit container like this can
> migrate to the simpler `type: snowflake-app` lane and drop the hand-rolled
> Dockerfile/service spec. Until then, raw SPCS is the way to run a containerized
> Streamlit you fully control.

## Auth note

The container authenticates headless via a **key-pair private key mounted as a
Snowflake SECRET** (the entrypoint writes `connections.toml`). This is the
lowest-friction path for the bundled `cortex` CLI, which expects a
`connections.toml`. Two things to know:

- The idiomatic SPCS pattern is the auto-rotating **OAuth token** at
  `/snowflake/session/token` (no secret to manage). Prefer it if/when the CLI
  supports that flow.
- Use a **dedicated low-privilege service user** granted only `SKI_READONLY`
  for the mounted key — not a personal user's key.

## Two explorer modes (A/B, toggle in Settings)
- **Explore-only** — answers purely from the marts via the SDK's `sql_execute`.
- **Agent-aware** — pre-fetches the `RESORT_EXECUTIVE` agent's answer (REST,
  with multi-turn history), then the explorer enhances it with deeper SQL.

### Rich answers: tables + charts
Both modes render more than prose — the chat surfaces **result tables** and
**charts** in-line:
- **Agent-aware** renders the Cortex Agent's own Vega-Lite chart specs + tables.
- **Explore-only** parses each `sql_execute` result into a table and adds a
  conservative **auto-chart** (a datetime column → line; a single category →
  bar; otherwise table only).
- A **"Show charts"** toggle in Settings turns charts off (tables always show).

The dashboard and chat are isolated `st.fragment`s, so interacting with a chart
doesn't reset the conversation and a chat turn doesn't reload the dashboard.

## Layout
```
streamlit/            Streamlit UI (app.py entry) + bridge to the SDK
cortex-code-agent/    policy, guardrails, agent REST client, prompts
vendor/               vendored cocosdkagent wheel (see VENDORED.md)
Dockerfile            installs the cortex CLI + deps + app
entrypoint.sh         writes connections.toml from the mounted key-pair secret
build_spec.yaml       Kaniko in-Snowflake build
service-spec.yaml     SPCS service (secret mount + :8080 endpoint)
setup.sql             end-to-end: repo, stage, build, EAI, secret, service
```

## What it creates (in Snowflake)
`setup.sql` stands up a self-contained SPCS deployment (separate from the data):
- `SKI_RESORT_BI_DB.SPCS` — infra DB/schema for the service.
- **Image repository** + **build stage** (Kaniko in-Snowflake build).
- **Compute pool** for the service.
- **External Access Integration** for runtime egress (Snowflake hosts, PyPI, GitHub).
- **Key-pair SECRET** holding the service user's private key (mounted into the container).
- **Service** `SKI_RESORT_BI_SERVICE` with a public `:8080` endpoint.
- A dedicated **service user** (e.g. `SKI_BI_SVC`, role `SKI_READONLY`) for headless auth.
- A **user-scoped network policy** allowing the SPCS egress IP range — required
  if your account has a restrictive (e.g. VPN) network policy, since the
  container's outbound IPs would otherwise be blocked (`setup.sql` step 9).

## Deploy (in-Snowflake, no local Docker)
1. Edit placeholders in `setup.sql` / `build_spec.yaml` / `service-spec.yaml`
   (`<YOUR_ACCOUNT>`, `<YOUR_USER>`, `<REPO_URL>`, the PEM key).
2. Run steps 1-2 of `setup.sql`, upload the build context to `BUILD_STAGE`,
   then run steps 4-8. Get the URL from `SHOW ENDPOINTS IN SERVICE ...`.
3. **Data layer (one-time):** ensure the Cortex Agents + semantic views point at
   `SKI_RESORT_DEMO` — `setup.sql` step 10 repoints the 11 `SEM_*` views to
   `SKI_RESORT_DEMO.MARTS` and re-grants `SKI_READONLY`. Without this the
   Agent-aware mode fails ("database doesn't exist or not authorized").

## Local development
Use a gitignored `.localdev/connections.toml` (copy `.localdev/connections.toml.example`)
with an **absolute** key path, then:
```bash
SNOWFLAKE_CONNECTION_NAME=myconnection streamlit run streamlit/app.py
```
Requires the `cortex` CLI on PATH locally for the explorer.

## Data + agent dependency
Runtime-only (no code coupling): reads the read-only `SKI_RESORT_DEMO` marts
(under role `SKI_READONLY`, warehouse `SKI_DEMO_WH`) and calls the Cortex Agents
`SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE` / `SKI_OPS_ASSISTANT`. These agents and
the 11 `SKI_RESORT_DEMO.SEMANTIC` views they use already exist in this repo's
demo database. To target a different database, change `SKI_RESORT_DATABASE` /
the agent FQNs in `cortex-code-agent/policy.py` and the connection blocks in
`entrypoint.sh`.
