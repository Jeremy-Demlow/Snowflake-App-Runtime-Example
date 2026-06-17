-- ============================================================================
-- Ski Resort BI Explorer — SPCS setup (Snowsight worksheet or snow sql)
-- ============================================================================
-- Custom-image SPCS service: bakes the Cortex Code CLI binary into the image so
-- the SDK explorer works in-Snowflake. Build is done in-Snowflake via Kaniko
-- (no local Docker). Auth is key-pair (headless) via a mounted SECRET.
--
-- Replace placeholders: <YOUR_ACCOUNT>, <YOUR_USER>, the private key PEM, and
-- <REPO_URL> (from SHOW IMAGE REPOSITORIES) inside build_spec.yaml before build.
-- ----------------------------------------------------------------------------

-- 1) Objects -----------------------------------------------------------------
CREATE DATABASE IF NOT EXISTS SKI_RESORT_BI_DB;
CREATE SCHEMA   IF NOT EXISTS SKI_RESORT_BI_DB.SPCS;
CREATE IMAGE REPOSITORY IF NOT EXISTS SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_REPO;
CREATE STAGE IF NOT EXISTS SKI_RESORT_BI_DB.SPCS.BUILD_STAGE
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE') DIRECTORY = (ENABLE = TRUE);

SHOW IMAGE REPOSITORIES IN SCHEMA SKI_RESORT_BI_DB.SPCS;  -- note repository_url

-- 2) Compute pool ------------------------------------------------------------
CREATE COMPUTE POOL IF NOT EXISTS SKI_RESORT_BI_POOL
  MIN_NODES = 1 MAX_NODES = 1
  INSTANCE_FAMILY = CPU_X64_M
  AUTO_SUSPEND_SECS = 300 AUTO_RESUME = TRUE;

-- 3) Upload build context to the stage (do in Snowsight or via PUT):
--    Dockerfile, build_spec.yaml, requirements.txt, entrypoint.sh,
--    streamlit/, cortex-code-agent/, vendor/
--    Then edit build_spec.yaml's <REPO_URL> with the repository_url from step 1.
-- LIST @SKI_RESORT_BI_DB.SPCS.BUILD_STAGE;

-- 4) Build the image in-Snowflake (Kaniko) ----------------------------------
EXECUTE JOB SERVICE
  IN COMPUTE POOL SKI_RESORT_BI_POOL
  NAME = SKI_RESORT_BI_BUILD_JOB
  FROM @SKI_RESORT_BI_DB.SPCS.BUILD_STAGE
  SPECIFICATION_FILE = 'build_spec.yaml';
-- SELECT SYSTEM$GET_SERVICE_STATUS('SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_BUILD_JOB');
-- SELECT SYSTEM$GET_SERVICE_LOGS('SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_BUILD_JOB', 0, 'kaniko-builder', 500);
-- SHOW IMAGES IN IMAGE REPOSITORY SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_REPO;

-- 5) Runtime egress (EAI) ----------------------------------------------------
-- Hosts the CLI + agent calls reach at runtime (from the proven SPCS-CLI guide).
CREATE OR REPLACE NETWORK RULE SKI_RESORT_BI_DB.SPCS.EGRESS_RULE
  TYPE = 'HOST_PORT' MODE = 'EGRESS'
  VALUE_LIST = (
    'ai.snowflake.com',
    'snowflakecomputing.com',
    'snowflakecomputing.app',
    'snowflake.com',
    '<YOUR_ACCOUNT>.snowflakecomputing.com',
    'pypi.org', 'files.pythonhosted.org', 'github.com', 'raw.githubusercontent.com'
  );
CREATE OR REPLACE EXTERNAL ACCESS INTEGRATION SKI_RESORT_BI_EAI
  ALLOWED_NETWORK_RULES = (SKI_RESORT_BI_DB.SPCS.EGRESS_RULE)
  ENABLED = TRUE;

-- 6) Key-pair SECRET for headless auth --------------------------------------
-- Paste the PEM private key (registered for <YOUR_USER>, with USAGE on
-- SKI_READONLY). Keep this out of git.
CREATE OR REPLACE SECRET SKI_RESORT_BI_DB.SPCS.SKI_BI_PRIVATE_KEY
  TYPE = GENERIC_STRING
  SECRET_STRING = '-----BEGIN PRIVATE KEY-----
<PASTE_PEM_LINES>
-----END PRIVATE KEY-----';

-- 7) Create the service ------------------------------------------------------
-- The spec lives in service-spec.yaml (source of truth). Inline here for one-shot
-- setup; keep them in sync. Fill <YOUR_ACCOUNT>/<YOUR_USER> + image FQN.
CREATE SERVICE SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_SERVICE
  IN COMPUTE POOL SKI_RESORT_BI_POOL
  FROM SPECIFICATION $$
spec:
  containers:
    - name: ski-resort-bi
      image: /ski_resort_bi_db/spcs/ski_resort_bi_repo/ski-resort-bi:latest
      env:
        SNOWFLAKE_ACCOUNT: "<YOUR_ACCOUNT>"
        SNOWFLAKE_USER: "<YOUR_USER>"
        SNOWFLAKE_CONNECTION_NAME: "myconnection"
      secrets:
        - snowflakeSecret: SKI_RESORT_BI_DB.SPCS.SKI_BI_PRIVATE_KEY
          secretKeyRef: secret_string
          envVarName: SNOWFLAKE_PRIVATE_KEY
      resources:
        requests: {memory: 2Gi, cpu: 1000m}
        limits:   {memory: 4Gi, cpu: 2000m}
      readinessProbe: {port: 8080, path: /}
  endpoints:
    - name: app
      port: 8080
      public: true
$$
  EXTERNAL_ACCESS_INTEGRATIONS = (SKI_RESORT_BI_EAI)
  MIN_INSTANCES = 1 MAX_INSTANCES = 1;

-- 8) Endpoint + logs ---------------------------------------------------------
-- SELECT SYSTEM$GET_SERVICE_STATUS('SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_SERVICE');
-- SHOW ENDPOINTS IN SERVICE SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_SERVICE;  -- ingress_url
-- SELECT SYSTEM$GET_SERVICE_LOGS('SKI_RESORT_BI_DB.SPCS.SKI_RESORT_BI_SERVICE', 0, 'ski-resort-bi', 200);

-- Network policy gotcha: if the account has a network policy, allow SPCS ingress
-- IPs BEFORE creating the service:
--   CREATE OR REPLACE NETWORK RULE SKI_RESORT_BI_DB.SPCS.SPCS_INGRESS
--     TYPE='IPV4' MODE='INGRESS' VALUE_LIST=('153.45.0.0/16');
--   ALTER NETWORK POLICY <POLICY> ADD ALLOWED_NETWORK_RULE_LIST=(SKI_RESORT_BI_DB.SPCS.SPCS_INGRESS);
