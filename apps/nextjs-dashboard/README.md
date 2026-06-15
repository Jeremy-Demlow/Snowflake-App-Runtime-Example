# Next.js Dashboard (Snowflake App Runtime)

The Daily Resort KPI dashboard as a Next.js app that runs on Snowflake (SPCS).
It reads from the single fixed data database `SKI_RESORT_DEMO` (one read-only
copy shared by every environment) — see `lib/constants.ts`.

## Run locally

1. Copy the example connection and fill it in (use an **absolute** key path):
   ```bash
   cp .localdev/connections.toml.example .localdev/connections.toml
   # edit .localdev/connections.toml
   ```
2. Install deps and start the dev server, pointing at that connection:
   ```bash
   npm install
   SNOWFLAKE_HOME="$PWD/.localdev" SNOWFLAKE_DEFAULT_CONNECTION_NAME=localdev npm run dev
   ```
3. Open http://localhost:3000.

> The `SNOWFLAKE_HOME` trick is only needed because the Snowflake SDK doesn't
> expand `~` in `private_key_file`. If your `~/.snowflake/connections.toml`
> already uses an absolute key path, just set `SNOWFLAKE_DEFAULT_CONNECTION_NAME`.

## Deploy

```bash
snow app deploy            # -> APPS_DEV, suffix _DEV (snowflake.yml defaults)
```
CI deploys ephemeral per-branch apps to `APPS_DEV` and, on `main`, the prod app
to `APPS` — all via `--env app_schema`/`app_suffix` overrides (no file edits).
See `.github/workflows/`.

## Key files

| File | Purpose |
|------|---------|
| `app/page.tsx` | The dashboard page (server component, fetches all data) |
| `lib/queries.ts` | All read-only SQL; reads the fixed `SKI_RESORT_DEMO` data DB |
| `components/charts.tsx` | Recharts client components (season/day/snow/trend) |
| `components/kpi-grid.tsx` | The KPI metric cards |
| `lib/snowflake.ts` | Connection helper (SPCS token / local TOML) — don't edit |
| `snowflake.yml` | Deploy target: schema + name suffix (templated via `env:` + `--env`) |

## Add a chart

1. Add a query function in `lib/queries.ts` (copy an existing one; keep it fully
   qualified via the `tables()` helper).
2. Add a client chart component in `components/charts.tsx`.
3. Fetch it in `app/page.tsx` (add to the `Promise.all`) and drop a `<ChartCard>`
   into the grid.
