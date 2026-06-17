# Ski Resort BI Explorer (custom SPCS container)

A Streamlit BI app that pairs a read-only KPI dashboard with a **governed,
free-range data explorer** powered by the Cortex Code Agent SDK, plus a deployed
Cortex Agent (`RESORT_EXECUTIVE`) consulted as a trusted baseline.

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

## Deploy (in-Snowflake, no local Docker)
1. Edit placeholders in `setup.sql` / `build_spec.yaml` / `service-spec.yaml`
   (`<YOUR_ACCOUNT>`, `<YOUR_USER>`, `<REPO_URL>`, the PEM key).
2. Run steps 1-2 of `setup.sql`, upload the build context to `BUILD_STAGE`,
   then run steps 4-8. Get the URL from `SHOW ENDPOINTS IN SERVICE ...`.

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
