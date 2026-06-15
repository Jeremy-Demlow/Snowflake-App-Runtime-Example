# Streamlit Dashboard (Streamlit in Snowflake)

The same Daily Resort KPI dashboard as a Streamlit app. It reads from the single
fixed data database `SKI_RESORT_DEMO` (one read-only copy shared by every
environment) — no per-environment config.

## Run locally

1. Copy the example connection and fill it in (use an **absolute** key path):
   ```bash
   cp .localdev/connections.toml.example .localdev/connections.toml
   # edit .localdev/connections.toml
   ```
2. Run it (no install needed — `uv` fetches deps on the fly; pin Python 3.12):
   ```bash
   SNOWFLAKE_HOME="$PWD/.localdev" SNOWFLAKE_DEFAULT_CONNECTION_NAME=localdev \
     uv run --python 3.12 --with streamlit --with "snowflake-connector-python[pandas]" \
     --with altair streamlit run streamlit_app.py
   ```
3. Open http://localhost:8501.

> Pin `--python 3.12`: on 3.13 `uv` builds `cryptography` from source (very slow).

## Deploy

```bash
snow streamlit deploy --replace --prune    # -> APPS_DEV, suffix _DEV
```
CI deploys ephemeral per-branch apps to `APPS_DEV` and, on `main`, the prod app
to `APPS` — all via `--env app_schema`/`app_suffix` overrides. See
`.github/workflows/`.

The SiS **container runtime** requires `pyproject.toml` + the
`PYPI_ACCESS_INTEGRATION` external access integration (both declared in
`snowflake.yml`) — do not remove them.

## Add a chart

Add a `load_*()` query function (qualified with the `FACT`/`DIM_*` names) and an
`st.altair_chart(...)` block in `streamlit_app.py`. Mirror the Next.js app so the
two stay in sync.
