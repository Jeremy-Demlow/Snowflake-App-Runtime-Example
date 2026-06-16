# Contributing

This repo is a **monorepo of Snowflake apps**. Each app lives under `apps/<name>/`
and is deployed automatically by CI. You add apps; you do not edit the pipeline.

## Add a new app

### Recommended: use the Cortex Code skills

The skills scaffold a complete project (and wire up local preview) — don't
hand-roll an app when a skill can build it:

- **`/build-app`** — describe what you want; it picks the framework and routes
  to the right create skill.
- **`/snowflake-apps`** — go straight to a Node.js / Snowflake App Runtime app.
- the **Streamlit-in-Snowflake** skill — for a Python dashboard.

Scaffold into a new `apps/<name>/` folder (a name not starting with `_`), then
branch/commit/push (step 4 below). AI-agent guidance lives in
[AGENTS.md](AGENTS.md).

### Manual / offline alternative

1. **Copy a starter:**
   ```bash
   cp -r apps/_template-streamlit apps/my-app    # Python (Streamlit)
   # for Node.js (App Runtime), see apps/_template-nextjs/README.md
   ```
2. **Edit `apps/my-app/snowflake.yml`** — replace `MY_APP` with a unique object
   name. Keep `database: SKI_RESORT_DEMO`, the `app_schema`/`app_suffix` env
   block, and `query_warehouse: SKI_DEMO_WH` as-is.
3. **Build your app** (`streamlit_app.py`, or the scaffolded Next.js project).
4. **Branch, commit, push:**
   ```bash
   git checkout -b my-app
   git add apps/my-app
   git commit -m "add my-app"
   git push -u origin my-app
   ```

CI (`deploy-dev.yml`) discovers `apps/my-app/` automatically and deploys it to
`SKI_RESORT_DEMO.APPS_DEV` as `<OBJECT>_<BRANCH>`. No workflow edits required.

## The lifecycle

| Step | What happens | Where it lands |
|------|--------------|----------------|
| push a feature branch | `deploy-dev.yml` deploys every app | `APPS_DEV`, `<APP>_<BRANCH>` |
| open a PR | review on the ephemeral URLs; governance changes get a DCM plan | — |
| merge to `main` | `deploy-prod.yml` deploys (after approval) | `APPS`, `<APP>` |
| close the PR | `cleanup-branch.yml` removes your branch's dev apps | — |

## Conventions

- **Discovery:** CI deploys every `apps/*/snowflake.yml`. Folders whose name
  starts with `_` (like `apps/_template-streamlit`) are **skipped** — use that
  prefix for scaffolding or work-in-progress you don't want deployed.
- **App type:** read from the `snowflake.yml` entity `type:` —
  `snowflake-app` (App Runtime) or `streamlit` (Streamlit in Snowflake).
- **One data DB:** all apps read `SKI_RESORT_DEMO` (read-only). Don't add a
  per-app database.
- **Naming:** the deployed object is `<name-in-snowflake.yml><suffix>`. Keep
  names unique across apps so they don't collide in `APPS`.

## Remove an app

CI only deploys what exists, so deleting the folder stops future deploys — but
it does **not** drop the already-deployed production object (CI never deletes
prod objects automatically). Remove it explicitly:

```bash
# delete the app from the prod APPS schema (and dev, if present)
./scripts/teardown.sh all          # prod apps + governance, OR drop one object:
snow sql -q "DROP STREAMLIT IF EXISTS SKI_RESORT_DEMO.APPS.MY_APP"
git rm -r apps/my-app && git commit -m "remove my-app"
```

## Local development

Each example app's README has copy-paste local-run steps
([nextjs](apps/nextjs-dashboard/README.md),
[streamlit](apps/streamlit-dashboard/README.md)). Use a gitignored
`.localdev/connections.toml` with an **absolute** key path.

## Ownership

`.github/CODEOWNERS` assigns `.github/**` and `governance/**` to the platform
team (they require review). `apps/*` is owned by the contributing team — you can
iterate without a platform bottleneck. See the maintenance model in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
