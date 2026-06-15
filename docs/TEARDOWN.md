# Teardown — Remove What the Template Created

Environments live at the **app layer** over one shared, read-only data database,
so there are two distinct things you might remove. In every case the ski-resort
**data is left untouched** — it is pre-existing and not managed by this project.

| You want to remove…                                   | Command                              |
| ----------------------------------------------------- | ------------------------------------ |
| One ephemeral feature-branch app pair (in `APPS_DEV`) | `./scripts/teardown.sh branch <name>`|
| The production apps **and** all governance            | `./scripts/teardown.sh all`          |

> Order matters for the full teardown: remove the app objects first, then the
> governance objects. The script does this for you.

In normal operation you rarely run these by hand — CI removes each branch's
ephemeral apps automatically when its PR closes (`.github/workflows/cleanup-branch.yml`).

## Remove one ephemeral branch's apps

```bash
./scripts/teardown.sh branch my-feature
```

Equivalent manual steps (suffix is the uppercased, sanitized branch name):

```bash
cd apps/nextjs-dashboard && \
  snow app teardown --force --env app_schema=APPS_DEV --env app_suffix=_MY_FEATURE
snow sql -q "DROP STREAMLIT IF EXISTS SKI_RESORT_DEMO.APPS_DEV.SKI_RESORT_STREAMLIT_MY_FEATURE"
```

## Remove the production apps + all governance

```bash
./scripts/teardown.sh all
```

Equivalent manual steps:

```bash
# 1. Production app objects (in APPS)
cd apps/nextjs-dashboard && \
  snow app teardown --force --env app_schema=APPS --env app_suffix=
snow sql -q "DROP STREAMLIT IF EXISTS SKI_RESORT_DEMO.APPS.SKI_RESORT_STREAMLIT"

# 2. Purge the DCM governance objects — drops the warehouse, the three roles,
#    the APPS / APPS_DEV schemas, and their grants. (Requires Snowflake CLI 3.17+.)
snow dcm purge SKI_RESORT_DEMO.PUBLIC.SKI_GOVERNANCE --target MAIN --force
snow dcm drop  SKI_RESORT_DEMO.PUBLIC.SKI_GOVERNANCE --if-exists
```

## Verify the governance objects are gone

```bash
snow sql -q "SHOW ROLES LIKE 'SKI_%'"
snow sql -q "SHOW WAREHOUSES LIKE 'SKI_DEMO_WH'"
```

Both should return no rows. The `SKI_RESORT_DEMO` data database remains in place.
