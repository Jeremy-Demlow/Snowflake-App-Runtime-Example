# Streamlit App Template — copy me

The **Streamlit-in-Snowflake** starter for a new app. CI auto-discovery skips
any folder whose name starts with `_`, so this template is never deployed.

> **Building a brand-new app? Prefer the Cortex Code skills.** Run `/build-app`
> (it picks the framework) or the Streamlit skill directly — they scaffold a
> richer app and wire up local preview. This folder is the manual / offline
> path, and a minimal reference for the repo conventions. For a Node.js
> (Snowflake App Runtime) app, see [`apps/_template-nextjs/`](../_template-nextjs/README.md).

## Create your app (manual path)

```bash
cp -r apps/_template-streamlit apps/my-app
# edit apps/my-app/snowflake.yml: set a unique object name (replace MY_APP)
# edit apps/my-app/streamlit_app.py: build your dashboard
git checkout -b my-app
git add apps/my-app && git commit -m "add my-app" && git push -u origin my-app
```

Pushing the branch triggers `deploy-dev.yml`, which discovers `apps/my-app/`
and deploys it to `SKI_RESORT_DEMO.APPS_DEV` as `MY_APP_<BRANCH>`. Open a PR,
get it reviewed, merge to `main`, and (after approval) it ships to
`SKI_RESORT_DEMO.APPS` as `MY_APP`.

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for the full flow.

## What stays the same across all apps

- Reads the single shared data DB `SKI_RESORT_DEMO` (read-only).
- Deploys via `app_schema` + `app_suffix` env templating (CI sets these).
- Uses the shared warehouse `SKI_DEMO_WH`.

For a full Streamlit example, see [`apps/streamlit-dashboard/`](../streamlit-dashboard/).
