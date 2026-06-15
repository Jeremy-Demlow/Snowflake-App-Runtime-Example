# App Template — copy me

This folder is a **starting point** for a new app. The CI auto-discovery skips
any folder whose name starts with `_`, so this template is never deployed.

## Create your app

```bash
cp -r apps/_template apps/my-app
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

This template is a Streamlit app (lightest to start). To build a Next.js
(App Runtime) app instead, copy `apps/nextjs-dashboard/` and rename the object.
