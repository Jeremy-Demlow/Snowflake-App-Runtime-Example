#!/usr/bin/env bash
# Container entrypoint: materialize a key-pair connections.toml from the mounted
# Snowflake SECRET, then launch Streamlit. The CLI explorer, the agent REST
# client (_jwt_auth.py), and the dashboard connector all read this file.
#
# Auth note: the SPCS-CLI guide uses authenticator=externalbrowser, which needs
# a human. This app is headless, so we use SNOWFLAKE_JWT (key-pair) instead --
# the same way we run the CLI headless locally.
set -euo pipefail

KEY_DIR="${HOME}/.snowflake/keys"
KEY_FILE="${KEY_DIR}/rsa_key.p8"
mkdir -p "${KEY_DIR}"

# Private key is delivered as a mounted SECRET (PEM contents in this env var).
if [ -n "${SNOWFLAKE_PRIVATE_KEY:-}" ]; then
  printf '%s\n' "${SNOWFLAKE_PRIVATE_KEY}" > "${KEY_FILE}"
  chmod 600 "${KEY_FILE}"
fi

ACCOUNT="${SNOWFLAKE_ACCOUNT:?set SNOWFLAKE_ACCOUNT}"
USER_NAME="${SNOWFLAKE_USER:?set SNOWFLAKE_USER}"

cat > "${HOME}/.snowflake/connections.toml" <<EOF
# Dashboard connection (KPIs)
[myconnection]
account = "${ACCOUNT}"
user = "${USER_NAME}"
authenticator = "SNOWFLAKE_JWT"
private_key_file = "${KEY_FILE}"
role = "${DASHBOARD_ROLE:-SKI_READONLY}"
warehouse = "${DASHBOARD_WAREHOUSE:-SKI_DEMO_WH}"
database = "${DASHBOARD_DATABASE:-SKI_RESORT_DEMO}"
schema = "${DASHBOARD_SCHEMA:-MARTS}"

# Read-only explorer connection (governs the SDK's sql_execute)
[ski_readonly]
account = "${ACCOUNT}"
user = "${USER_NAME}"
authenticator = "SNOWFLAKE_JWT"
private_key_file = "${KEY_FILE}"
role = "SKI_READONLY"
warehouse = "SKI_DEMO_WH"
database = "SKI_RESORT_DEMO"
schema = "MARTS"
EOF
chmod 600 "${HOME}/.snowflake/connections.toml"

export SNOWFLAKE_CONNECTION_NAME="${SNOWFLAKE_CONNECTION_NAME:-myconnection}"

exec streamlit run streamlit/app.py \
  --server.port 8080 \
  --server.address 0.0.0.0 \
  --server.headless true
