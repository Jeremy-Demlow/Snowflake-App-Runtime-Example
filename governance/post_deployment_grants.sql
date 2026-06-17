-- ============================================================================
-- post_deployment_grants.sql — Grants DCM cannot (or should not) manage
--
-- Run MANUALLY (or via CI) as ACCOUNTADMIN AFTER `snow dcm deploy`. These are
-- separated out because:
--   * FUTURE grants and SEMANTIC VIEW grants are not part of DCM's supported
--     declarative grant set, and DCM best practice is to keep declarative
--     grants to current objects.
--   * SPCS / App Runtime deployment needs ACCOUNT-level privileges that cannot
--     be granted to a database-scoped context inside DCM.
--
-- This file is parameterized for snow CLI (<% DB %>). Example:
--   snow sql -f governance/post_deployment_grants.sql \
--     -D "DB=SKI_RESORT_DEMO" -c <connection>
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- ---- Future-proof read access (covers objects added to the data later) ----
GRANT SELECT ON FUTURE TABLES IN SCHEMA <% DB %>.MARTS   TO ROLE SKI_READONLY;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA <% DB %>.MARTS   TO ROLE SKI_READONLY;
GRANT SELECT ON FUTURE VIEWS  IN SCHEMA <% DB %>.STAGING TO ROLE SKI_READONLY;

-- ---- Cortex Analyst semantic views (read) ----------------------------------
GRANT SELECT ON ALL SEMANTIC VIEWS    IN SCHEMA <% DB %>.SEMANTIC TO ROLE SKI_READONLY;
GRANT SELECT ON FUTURE SEMANTIC VIEWS IN SCHEMA <% DB %>.SEMANTIC TO ROLE SKI_READONLY;

-- ---- Cortex Agents (read) --------------------------------------------------
-- So apps that call the agents (e.g. the ski-resort-bi explorer's Agent-aware
-- mode) can use them under SKI_READONLY.
GRANT USAGE ON SCHEMA <% DB %>.AGENTS TO ROLE SKI_READONLY;
GRANT USAGE ON AGENT <% DB %>.AGENTS.RESORT_EXECUTIVE  TO ROLE SKI_READONLY;
GRANT USAGE ON AGENT <% DB %>.AGENTS.SKI_OPS_ASSISTANT TO ROLE SKI_READONLY;

-- ---- App deployment privileges for the DEVELOPER role ----------------------
-- So SKI_DEVELOPER (the CI deploy role) can run `snow app deploy` and
-- `snow streamlit deploy` for BOTH frameworks without ACCOUNTADMIN.
-- Account-level (App Runtime build + endpoints):
GRANT CREATE COMPUTE POOL   ON ACCOUNT TO ROLE SKI_DEVELOPER;
GRANT BIND SERVICE ENDPOINT ON ACCOUNT TO ROLE SKI_DEVELOPER;
GRANT CREATE INTEGRATION    ON ACCOUNT TO ROLE SKI_DEVELOPER;

-- Shared compute pool + PyPI egress (adjust names if your account differs).
GRANT USAGE ON COMPUTE POOL SYSTEM_COMPUTE_POOL_CPU TO ROLE SKI_DEVELOPER;
GRANT USAGE ON INTEGRATION  PYPI_ACCESS_INTEGRATION  TO ROLE SKI_DEVELOPER;

-- Per-schema object creation (prod APPS + dev APPS_DEV). App Runtime uses
-- APPLICATION SERVICE + an artifact repository; Streamlit-in-Snowflake uses
-- STREAMLIT; both can also create SERVICE / IMAGE REPOSITORY objects.
GRANT CREATE STREAMLIT           ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE STREAMLIT           ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
GRANT CREATE WORKSPACE           ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE WORKSPACE           ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
GRANT CREATE APPLICATION SERVICE ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE APPLICATION SERVICE ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
GRANT CREATE ARTIFACT REPOSITORY ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE ARTIFACT REPOSITORY ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
GRANT CREATE SERVICE             ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE SERVICE             ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
GRANT CREATE IMAGE REPOSITORY    ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE IMAGE REPOSITORY    ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
