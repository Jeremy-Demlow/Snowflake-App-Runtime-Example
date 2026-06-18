# AGENTS.md

Guidance for AI agents (Cortex Code and other tools) working in this repo. Read
this first. Human docs: [README.md](README.md), [CONTRIBUTING.md](CONTRIBUTING.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## What this repo is

A **monorepo of Snowflake apps**. Each app is a folder under `apps/<name>/` with
a `snowflake.yml`. CI auto-discovers every app and deploys it — adding an app
needs no workflow edits.

- **One read-only data database**: `SKI_RESORT_DEMO`. Environments live at the
  **app layer**, not the data layer: `APPS` = production, `APPS_DEV` = dev /
  ephemeral feature-branch apps. Do **not** create a per-app database.
- Two example apps: `apps/nextjs-dashboard/` (Snowflake App Runtime / Node.js)
  and `apps/streamlit-dashboard/` (Streamlit-in-Snowflake). A third,
  `apps/ski-resort-bi/`, is a **custom-image SPCS** app (see the third lane below).

## Adding a new app — use the skills first

**Prefer the Cortex Code skills; they scaffold a complete project and wire up
local preview. Do not hand-roll an app when a skill can scaffold it.**

| Goal | Use |
|------|-----|
| Not sure which framework | **`/build-app`** — picks Streamlit vs App Runtime, then routes to the right create skill |
| Full-stack web app (custom UI, forms, workflows, Node.js) | **`/snowflake-apps`** — Snowflake App Runtime create/deploy/operate |
| Python dashboard / KPIs / analyst tool | the Streamlit-in-Snowflake skill |

Scaffold the project into a **new `apps/<your-app>/` folder** (a name that does
**not** start with `_`). Manual / offline fallback: copy
`apps/_template-streamlit/` (Python) or follow `apps/_template-nextjs/README.md`
(Node.js).

### Third lane: custom-image SPCS (advanced)

When an app needs things SiS and App Runtime can't give it — a custom Dockerfile,
system packages, or a binary like the `cortex` CLI (App Runtime is Node-only
today; SiS only adds pip packages) — build your own image and run it as a raw
SPCS service. Example: `apps/ski-resort-bi/` (Streamlit + Cortex Code Agent SDK,
Kaniko in-Snowflake build, key-pair SECRET, `CREATE SERVICE`). These apps have
**no `snowflake.yml`**, so CI auto-discovery skips them; they deploy via their
own `setup.sql`. Prefer SiS or App Runtime unless you specifically need this.

## Conventions an agent MUST follow

- App path is `apps/<name>/` with a `snowflake.yml`. Folders starting with `_`
  (e.g. `apps/_template-streamlit`, `apps/_template-nextjs`) are templates and
  are **never deployed** by CI.
- All apps read `SKI_RESORT_DEMO` (read-only). Query it; never write to it.
- `snowflake.yml` uses the `env:` `app_schema` + `app_suffix` templating so CI
  can target `APPS_DEV` (branches) and `APPS` (prod). Use `query_warehouse:
  SKI_DEMO_WH`.
- Keep deployed object names unique across apps so they don't collide in `APPS`.

## Deploy / operate

- **CI** (preferred): push a feature branch -> ephemeral deploy to `APPS_DEV`;
  merge to `main` -> deploy to `APPS` behind the `production` approval gate;
  PR close -> ephemeral apps removed. Workflows in `.github/workflows/`.
- **Manual**: `snow app deploy` (App Runtime) / `snow streamlit deploy`
  (Streamlit). Use `/opt/homebrew/bin/snow` if a broken `snow` shadows it.
- Governance (roles, schemas, grants) is DCM: `governance/` (see
  [governance/README.md](governance/README.md)) +
  `.github/workflows/dcm-deploy.yml`. CI/GitHub setup: `docs/PIPELINE_SETUP.md`.

## Ownership

`.github/CODEOWNERS`: the platform team owns `.github/**` and `governance/**`;
app teams own `apps/*`.
