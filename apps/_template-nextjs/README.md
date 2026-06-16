# Node.js App Template (Snowflake App Runtime)

The **Node.js / Snowflake App Runtime** starter (full-stack web apps: custom UI,
forms, multi-step workflows). CI auto-discovery skips any folder whose name
starts with `_`, so this folder is never deployed.

> This is intentionally **not** a runnable app. Snowflake App Runtime projects
> are scaffolded by the Cortex Code skill, which generates the full Next.js
> project (package.json, app/, app.yml, tests, local preview). Hand-maintaining
> a parallel skeleton here would drift — so we point you at the scaffolder.

## Create your app (recommended)

In the Cortex Code chat, run one of:

- **`/build-app`** — describe what you want; it picks the framework and, for a
  full-stack app, routes to `/snowflake-apps` to scaffold it.
- **`/snowflake-apps`** — go straight to the App Runtime create flow.

Scaffold the project into a **new `apps/<your-app>/` folder** (a non-`_` name),
then commit + push a branch — CI discovers and deploys it like any other app.

For a complete working example, see [`apps/nextjs-dashboard/`](../nextjs-dashboard/).

## Repo conventions your scaffolded app must adopt

After scaffolding, align the generated `snowflake.yml` with this repo so CI can
deploy it to both `APPS_DEV` (branches) and `APPS` (prod). See
[`snowflake.yml`](snowflake.yml) in this folder for the exact shape:

- `database: SKI_RESORT_DEMO` (one shared, read-only data DB — no per-app DB).
- `env:` block with `app_schema` + `app_suffix`, referenced by the entity
  `schema` and `name` (CI sets these per environment).
- `query_warehouse: SKI_DEMO_WH`.
- The data DB is read-only; query it, don't write to it.

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the full add-an-app flow.
