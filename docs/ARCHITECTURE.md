# Architecture

This template is deliberately small but shows a complete, production-shaped
workflow. The key idea: the data is **one read-only copy**, so environments
live at the **app layer**, not the data layer.

```mermaid
flowchart TD
  demo[(SKI_RESORT_DEMO)] --> dcm["DCM governance: roles + warehouse + APPS/APPS_DEV schemas + grants"]
  dcm --> ro["SKI_READONLY can SELECT MARTS + SEMANTIC"]
  ro --> nextjs["Next.js dashboard (App Runtime / SPCS)"]
  ro --> streamlit["Streamlit dashboard"]
  ci["GitHub Actions"] -.->|"feature branch -> APPS_DEV (ephemeral)"| nextjs
  ci -.->|"main + approval -> APPS (prod)"| streamlit
```

## 1. Data

The dashboards read from a ready-to-go ski-resort analytics dataset in the
single `SKI_RESORT_DEMO` database (a dimensional model in `MARTS` plus Cortex
Analyst semantic views in `SEMANTIC`). The data is already provisioned; the
apps simply read from it.

There is **one** data copy shared by every environment. Because the data is
read-only and identical everywhere, there is no per-environment data database —
this is what lets environments collapse onto the app layer.

## 2. Governance: DCM (infrastructure as code)

The [`governance/`](../governance) directory is a single DCM project. It
**declaratively manages** everything *around* the data — it does not redefine
the data tables or semantic views. For a full explainer of DCM and the role it
plays, see [`governance/README.md`](../governance/README.md). It defines:

- **Warehouse** `SKI_DEMO_WH` — one shared XS warehouse for all app instances.
- **Three account roles** with inheritance (no environment suffix):

  ```mermaid
  graph TD
    SYSADMIN[SYSADMIN] --> ADMIN["SKI_ADMIN"]
    ADMIN --> DEVELOPER["SKI_DEVELOPER"]
    DEVELOPER --> READONLY["SKI_READONLY"]
  ```

- **Two app schemas** in the database:
  - `APPS` — production app objects (consumers use these).
  - `APPS_DEV` — dev + ephemeral feature-branch app objects.
- **Grants**: read-only `SELECT` + `USAGE` on `MARTS` and `SEMANTIC` (current and
  **future** objects), warehouse `USAGE`, developer `CREATE` on both app schemas,
  and the role-to-user assignment that makes onboarding "just work".

Roles are **account-level** (not database roles) because warehouse `USAGE` cannot
be granted to a database role.

### Environments

There is **one** database and **one** governance project (target `MAIN` in
[`governance/manifest.yml`](../governance/manifest.yml)). Environments differ
only by *where an app object is deployed*:

| Environment        | Schema     | App name suffix      |
| ------------------ | ---------- | -------------------- |
| local / default    | `APPS_DEV` | `_DEV`               |
| ephemeral branch   | `APPS_DEV` | `_<BRANCH>` (CI)     |
| production         | `APPS`     | _(none)_ (CI)        |

The app `snowflake.yml` exposes `app_schema` and `app_suffix` as templating
variables; CI overrides them with `--env` (no file edits / no `sed`).

## 3. Apps: a registry of many apps

The `apps/` folder is a **registry**. Each subfolder is one app with its own
`snowflake.yml`; CI discovers them all. Adding `apps/<your-app>/` ships a new app
with no pipeline changes (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

```mermaid
flowchart LR
  subgraph registry [apps/ = registry]
    a1["nextjs-dashboard (snowflake-app)"]
    a2["streamlit-dashboard (streamlit)"]
    a3["_template-streamlit / _template-nextjs (skipped: start with _)"]
    a4["your-new-app"]
  end
  registry --> scan["prepare job: glob apps/*/snowflake.yml, skip _*, read type"]
  scan --> matrix["matrix [{name,dir,type}]"]
  matrix --> r1["snowflake-app -> snow app deploy -x"]
  matrix --> r2["streamlit -> snow streamlit deploy -x"]
```

The two example apps query the data read-only and render the same Daily Resort
KPIs (visits, unique visitors, visits/guest, pass-holder %, weekend share, snow
conditions) from `SEM_DAILY_SUMMARY` and `FACT_PASS_USAGE` + `DIM_DATE`. Both
hardcode the single data database `SKI_RESORT_DEMO`.

- [`apps/nextjs-dashboard`](../apps/nextjs-dashboard) — Snowflake App Runtime
  (Next.js), `snow app deploy` to SPCS.
- [`apps/streamlit-dashboard`](../apps/streamlit-dashboard) — Streamlit in
  Snowflake, `snow streamlit deploy`.
- [`apps/_template-streamlit`](../apps/_template-streamlit) + [`apps/_template-nextjs`](../apps/_template-nextjs)
  — copy-me starters; the `_` prefix keeps them out of CI.

The point is the **shared deploy loop**: one matrix ships every app, either framework.

### The third lane: a custom SPCS app outside the registry

[`apps/ski-resort-bi`](../apps/ski-resort-bi) is a more advanced example: a
Streamlit BI dashboard **plus an AI chat panel** that answers questions about the
data with text, tables, and charts (two modes — a governed read-only explorer,
and an "Agent-aware" mode that consults the deployed Cortex Agents). It bundles
the `cortex` CLI **binary**, which neither Streamlit-in-Snowflake nor App Runtime
can host, so it runs as a **raw SPCS custom container** (its own `Dockerfile` +
`CREATE SERVICE`).

Because it isn't a standard `snow app` / `snow streamlit` project, it has **no
`snowflake.yml`** and is intentionally **excluded from the CI auto-discovery
registry** (the `prepare` job skips it; path filters exclude `apps/ski-resort-bi/**`).
It's deployed via its own [`setup.sql`](../apps/ski-resort-bi/setup.sql) and
documented in its [README](../apps/ski-resort-bi/README.md). It still relies on
the same governance layer — it queries the data as `SKI_READONLY` and uses the
Cortex Agents + semantic views that `post_deployment_grants.sql` grants.

## 4. CI/CD: GitHub Actions

Four workflows, all using the official
[`snowflakedb/snowflake-cli-action`](https://github.com/snowflakedb/snowflake-cli-action)
to install the CLI, followed by a `snow connection test -x` sanity check.
Credentials use the **secrets vs variables** split (sensitive values masked,
role/db/warehouse as readable variables) — see
[PIPELINE_SETUP.md](PIPELINE_SETUP.md).

```mermaid
flowchart TD
  feat["push feature branch / PR"] --> devwf["deploy-dev.yml (matrix over apps/*)"]
  devwf --> appsdev["each app -> APPS_DEV, suffix _BRANCH"]
  pr["PR to main"] --> dcmp["dcm-deploy.yml: PLAN on governance/** change"]
  close["PR closed"] --> cleanwf["cleanup-branch.yml: drop each app's branch copy"]
  main["merge to main"] --> prodwf["deploy-prod.yml (matrix)"]
  main --> dcmd["dcm-deploy.yml: DEPLOY governance MAIN"]
  prodwf --> gate{"production approval"}
  gate -->|approved| appsprod["each app -> APPS (prod)"]
```

- **Feature branches / PRs**: `deploy-dev.yml` discovers every app and deploys
  each to `APPS_DEV` with a sanitized branch suffix — isolated services + URLs.
- **PR close**: `cleanup-branch.yml` removes that branch's apps.
- **PROD**: `deploy-prod.yml` deploys from `main` only, behind the `production`
  GitHub Environment approval gate.
- **Governance**: `dcm-deploy.yml` plans on PRs touching `governance/**` and
  deploys target `MAIN` on merge (it connects as `ACCOUNTADMIN`).
- Auth: key-pair via a temporary connection (`-x`) for apps; the nested
  `SNOWFLAKE_CONNECTIONS_DEFAULT_*` shape for `snow dcm`.

> Endpoint URLs are assigned by Snowflake (`<hash>-<org>-<account>.snowflakecomputing.app`)
> and are not customizable; a vanity domain requires PrivateLink + your own DNS.

## 5. Maintenance model

Who owns what, and what each change triggers:

| Concern | Lives in | Trigger | Owner |
| --- | --- | --- | --- |
| An app's code/config | `apps/<name>/` | branch -> `APPS_DEV`; merge -> `APPS` (gated) | app team |
| Adding an app | `/build-app` or copy `apps/_template-*` | same, no CI edit | app team |
| Removing an app | delete folder | stops deploys; prod object dropped **manually** | app team |
| Governance | `governance/**` | PR plan -> merge deploys `MAIN` | platform/admin |
| Pipeline itself | `.github/**` | PR review (CODEOWNERS) | platform team |
| Credentials / env wiring | GitHub Settings | one-time + on rotation | admin |

[`.github/CODEOWNERS`](../.github/CODEOWNERS) enforces the split: platform owns
`.github/**` and `governance/**`; app teams self-serve `apps/*`. CI never deletes
prod objects automatically — removing an app is a deliberate manual step.

## Teardown

To remove what this template created (the ephemeral branch apps, the production
apps, or the full governance), see [TEARDOWN.md](TEARDOWN.md).
