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

-- ---- App Runtime (SPCS) deployment privileges for the DEVELOPER role -------
-- Required so SKI_DEVELOPER can run `snow app deploy` without ACCOUNTADMIN.
-- (Omit if you deploy apps with an admin role instead.)
GRANT CREATE COMPUTE POOL ON ACCOUNT      TO ROLE SKI_DEVELOPER;
GRANT BIND SERVICE ENDPOINT ON ACCOUNT    TO ROLE SKI_DEVELOPER;
GRANT CREATE INTEGRATION ON ACCOUNT       TO ROLE SKI_DEVELOPER;

-- Deploy app objects into both the prod (APPS) and dev (APPS_DEV) schemas.
GRANT CREATE SERVICE          ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE IMAGE REPOSITORY ON SCHEMA <% DB %>.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE SERVICE          ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
GRANT CREATE IMAGE REPOSITORY ON SCHEMA <% DB %>.APPS_DEV TO ROLE SKI_DEVELOPER;
