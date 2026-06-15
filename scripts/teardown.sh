#!/usr/bin/env bash
#
# teardown.sh — Remove app objects this template created.
#
# Environments are at the APP layer (one shared data database), so there are
# two things you might tear down:
#
#   branch <name>   Remove ONE ephemeral feature-branch app pair from APPS_DEV
#                   (Next.js + Streamlit), e.g. the apps CI created for a PR.
#   all             Remove the PRODUCTION apps from APPS *and* purge the DCM
#                   governance objects (roles, warehouse, APPS / APPS_DEV
#                   schemas, grants).
#
# Never touches the ski-resort DATA — that database is pre-existing.
#
# Usage:
#   ./scripts/teardown.sh branch my-feature   [connection]
#   ./scripts/teardown.sh all                 [connection]
#
# Requires Snowflake CLI 3.17+ (for `snow dcm purge`).
set -euo pipefail

MODE="${1:-}"
DB="SKI_RESORT_DEMO"
PROJECT="${DB}.PUBLIC.SKI_GOVERNANCE"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Same slug rule as .github/workflows/deploy-dev.yml.
slugify() {
  echo "$1" | tr '[:lower:]' '[:upper:]' | tr -c 'A-Z0-9' '_' \
    | sed 's/_\+/_/g; s/^_//; s/_$//' | cut -c1-24
}

case "$MODE" in
  branch)
    BRANCH="${2:-}"
    CONN="${3:-}"
    [[ -n "$BRANCH" ]] || { echo "Usage: $0 branch <name> [connection]" >&2; exit 1; }
    CONN_ARG=(); [[ -n "$CONN" ]] && CONN_ARG=(-c "$CONN")
    SUFFIX="_$(slugify "$BRANCH")"

    echo "==> Removing ephemeral branch apps in ${DB}.APPS_DEV (suffix ${SUFFIX})"
    ( cd "${ROOT}/apps/nextjs-dashboard" && \
      snow app teardown --force --env app_schema=APPS_DEV --env "app_suffix=${SUFFIX}" "${CONN_ARG[@]}" ) || \
      echo "   (no Next.js app to remove, or already gone)"
    snow sql -q "DROP STREAMLIT IF EXISTS ${DB}.APPS_DEV.SKI_RESORT_STREAMLIT${SUFFIX}" "${CONN_ARG[@]}" || \
      echo "   (no Streamlit app to remove, or already gone)"
    echo "==> Done."
    ;;

  all)
    CONN="${2:-}"
    CONN_ARG=(); [[ -n "$CONN" ]] && CONN_ARG=(-c "$CONN")

    echo "==> This removes the PRODUCTION apps AND all governance (roles, warehouse,"
    echo "    APPS / APPS_DEV schemas, grants). The ${DB} data is left untouched."
    read -r -p "Continue? (yes/no) " ans
    [[ "$ans" == "yes" ]] || { echo "Aborted."; exit 0; }

    echo "==> 1/3 Removing production Next.js app"
    ( cd "${ROOT}/apps/nextjs-dashboard" && \
      snow app teardown --force --env app_schema=APPS --env app_suffix= "${CONN_ARG[@]}" ) || \
      echo "   (no Next.js app to remove, or already gone)"

    echo "==> 2/3 Removing production Streamlit app"
    snow sql -q "DROP STREAMLIT IF EXISTS ${DB}.APPS.SKI_RESORT_STREAMLIT" "${CONN_ARG[@]}" || \
      echo "   (no Streamlit app to remove, or already gone)"

    echo "==> 3/3 Purging DCM governance objects"
    snow dcm purge "$PROJECT" --target MAIN --force "${CONN_ARG[@]}"
    snow dcm drop "$PROJECT" --if-exists "${CONN_ARG[@]}" || true
    echo "==> Done. The ${DB} data database was left untouched."
    ;;

  *)
    echo "Usage:" >&2
    echo "  $0 branch <name> [connection]   # remove one ephemeral feature-branch app pair" >&2
    echo "  $0 all           [connection]   # remove prod apps + purge governance" >&2
    exit 1
    ;;
esac
