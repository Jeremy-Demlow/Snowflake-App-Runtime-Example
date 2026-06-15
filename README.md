# Ski Resort Demo — Snowflake App Runtime Template

An **end-to-end template** for building and shipping a Snowflake app with
[Cortex Code Desktop](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code).
It is designed for people who have **never used an IDE** before — if you've used
Claude / Cowork, you can do this.

You get **one simple deploy loop** that ships **two** different apps over the
same data:

| App | Framework | What it is |
|-----|-----------|------------|
| `apps/nextjs-dashboard` | Next.js (Snowflake App Runtime) | A full web app running on Snowflake |
| `apps/streamlit-dashboard` | Streamlit in Snowflake | A Python dashboard |

Both render the **same** read-only "Daily Resort KPI" dashboard, so you can see
that the **same workflow** ships either kind of app.

## The data

The dashboards read from a ready-to-go ski-resort analytics dataset in the single
`SKI_RESORT_DEMO` database: a dimensional model (`MARTS` — daily visits, lift
scans, weather, revenue, etc.) plus Cortex Analyst semantic views (`SEMANTIC`).
**The data is already provisioned — you don't need to load or set anything up.**

There is **one** read-only data copy shared by every environment. Environments
(dev, feature branches, production) differ only by *which app object* gets
deployed and *where* — not by the data. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Build this with Cortex Code

You don't have to write any of this by hand — Cortex Code Desktop has built-in
**skills** that scaffold, deploy, and operate these apps for you. In the CoCo
chat, type:

| Skill | What it does |
|-------|--------------|
| `/build-app` | Starts a brand-new Snowflake app and helps you pick the right framework (Streamlit vs. Snowflake App Runtime). Great starting point if you're building from scratch. |
| `/snowflake-apps` | Scaffolds, runs locally, **deploys**, and troubleshoots Snowflake App Runtime (Next.js) apps — `snow app deploy`, logs, status, redeploys. |

For example, just ask: *"/snowflake-apps deploy the Next.js dashboard"* or
*"/build-app build me a KPI dashboard on the ski-resort data"*.

## What's in the box

```
.
├── docs/                  ← START HERE: ONBOARDING.md (+ ARCHITECTURE, TEARDOWN)
├── governance/            ← DCM project: roles, warehouse, grants (infra-as-code)
├── apps/                  ← the two dashboards (each has its own README)
│   ├── nextjs-dashboard/
│   └── streamlit-dashboard/
├── scripts/               ← teardown.sh
└── .github/workflows/     ← ephemeral branch apps, approval-gated PROD, PR cleanup
```

Extending the dashboards (add a chart, change a query) is documented in each
app's README: [`apps/nextjs-dashboard/README.md`](apps/nextjs-dashboard/README.md)
and [`apps/streamlit-dashboard/README.md`](apps/streamlit-dashboard/README.md).

## Quick start

New here? Open **[docs/ONBOARDING.md](docs/ONBOARDING.md)** — it walks you through
installing Cortex Code Desktop and shipping your first app.

Already set up? The whole loop is:

```bash
# 1. Create roles, warehouse, and grants (infrastructure as code, one time)
snow dcm deploy SKI_RESORT_DEMO.PUBLIC.SKI_GOVERNANCE --target MAIN

# 2. Ship the apps (defaults deploy to APPS_DEV with the _DEV suffix)
cd apps/nextjs-dashboard && snow app deploy
cd ../streamlit-dashboard && snow streamlit deploy
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the governance, apps,
and CI/CD fit together.
