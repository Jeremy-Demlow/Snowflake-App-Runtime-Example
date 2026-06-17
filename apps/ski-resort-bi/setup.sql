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

-- ============================================================================
-- 9) NETWORK POLICY GOTCHA (REQUIRED if the account has a network policy)
-- ----------------------------------------------------------------------------
-- The container connects OUT to Snowflake (<YOUR_ACCOUNT>.snowflakecomputing.com:443)
-- using the key-pair in connections.toml. Its source IPs are the SPCS service
-- egress IPs (153.45.0.0/16). If the account has a restrictive network policy
-- (e.g. a VPN allowlist), those egress IPs are blocked and every query fails:
--   250001 (08001): ... Incoming request with IP/Token 153.45.x.x is not allowed
--
-- Fix WITHOUT touching the (shared) account policy: give the SERVICE USER its
-- own network policy that allows the SPCS egress range. A user-level policy
-- overrides the account policy for that user only, so the strict account policy
-- still applies to everyone else, and the explorer stays pinned to SKI_READONLY.
--   (We keep key-pair auth on purpose: it pins the explorer to a read-only role.
--    The SPCS OAuth token would run as the service owner, removing that guardrail.)
CREATE OR REPLACE NETWORK POLICY SKI_BI_SVC_NP
  ALLOWED_IP_LIST = ('153.45.0.0/16')
  COMMENT = 'Allow SPCS service egress IPs for the SKI_BI_SVC service user only.';
ALTER USER SKI_BI_SVC SET NETWORK_POLICY = SKI_BI_SVC_NP;
-- New connections pick this up immediately; no service restart needed.
--
-- (Separately, if a network policy also blocks INGRESS to the public endpoint,
-- add the SPCS ingress range to the account policy via an INGRESS network rule.)

-- ============================================================================
-- 10) DATA LAYER: semantic views + agents must point at SKI_RESORT_DEMO
-- ----------------------------------------------------------------------------
-- The Agent-aware chat lane calls the deployed Cortex Agents
-- (SKI_RESORT_DEMO.AGENTS.RESORT_EXECUTIVE / SKI_OPS_ASSISTANT), whose
-- cortex_analyst_text_to_sql tools query the semantic views in
-- SKI_RESORT_DEMO.SEMANTIC.SEM_*. Those views + agents were cloned from the
-- AM_SKI_RESORT sample. GOTCHA: a clone copies the semantic views with their
-- base `tables(...)` still pointing at AM_SKI_RESORT.MARTS.*, which the
-- read-only role (SKI_READONLY) cannot access -> the agent answers
-- "database doesn't exist or not authorized". Re-point every SEM_* view's base
-- tables to SKI_RESORT_DEMO.MARTS.* (all required base tables already live
-- there). Run as a role that can CREATE in the SEMANTIC schema (e.g. ACCOUNTADMIN).
USE SCHEMA SKI_RESORT_DEMO.SEMANTIC;
DECLARE
  c CURSOR FOR SELECT column1 AS vn FROM VALUES
    ('SEM_CUSTOMER_BEHAVIOR'),('SEM_CUSTOMER_SATISFACTION'),('SEM_DAILY_SUMMARY'),
    ('SEM_LESSONS_ANALYTICS'),('SEM_MARKETING_ANALYTICS'),('SEM_OPERATIONS'),
    ('SEM_PASSHOLDER_ANALYTICS'),('SEM_REVENUE'),('SEM_SAFETY_INCIDENTS'),
    ('SEM_STAFFING_ANALYTICS'),('SEM_WEATHER_ANALYTICS');
  ddl STRING;
  n INT DEFAULT 0;
BEGIN
  FOR rec IN c DO
    -- GET_DDL needs a constant, so build the FQN string inline per-iteration.
    ddl := GET_DDL('SEMANTIC_VIEW', 'SKI_RESORT_DEMO.SEMANTIC.' || rec.vn);
    ddl := REPLACE(ddl, 'AM_SKI_RESORT.', 'SKI_RESORT_DEMO.');
    EXECUTE IMMEDIATE :ddl;   -- recreated in the current (SEMANTIC) schema
    n := n + 1;
  END FOR;
  RETURN 'repointed ' || n || ' semantic views to SKI_RESORT_DEMO.MARTS';
END;

-- CREATE OR REPLACE drops grants, so re-grant read access to the explorer role:
GRANT USAGE ON SCHEMA SKI_RESORT_DEMO.SEMANTIC TO ROLE SKI_READONLY;
GRANT SELECT ON ALL SEMANTIC VIEWS IN SCHEMA SKI_RESORT_DEMO.SEMANTIC TO ROLE SKI_READONLY;
GRANT SELECT ON FUTURE SEMANTIC VIEWS IN SCHEMA SKI_RESORT_DEMO.SEMANTIC TO ROLE SKI_READONLY;

-- Verify (as SKI_READONLY) that a view resolves + returns data:
--   USE ROLE SKI_READONLY; USE WAREHOUSE SKI_DEMO_WH;
--   SELECT * FROM SEMANTIC_VIEW(
--     SKI_RESORT_DEMO.SEMANTIC.SEM_REVENUE
--     METRICS FACT_TICKET_SALES.TICKET_REVENUE
--     DIMENSIONS DIM_LOCATION.LOCATION_NAME);
-- The agent specs themselves reference the views by FQN (SKI_RESORT_DEMO.SEMANTIC.*)
-- and do NOT need editing once the views are repointed.

