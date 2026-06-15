-- ============================================================================
-- grants.sql — Privileges (imperative GRANTs, applied declaratively by DCM)
--
-- Scope: read-only access to the resort data + developer access to the app
-- schemas (APPS / APPS_DEV). Uses only DCM-supported grant patterns
-- (USAGE / SELECT ON ALL / CREATE). Future grants and semantic-view grants
-- live in ../../post_deployment_grants.sql (see that file for why).
--
-- Privileges are granted to the LOWEST role that needs them; higher roles
-- inherit automatically via the hierarchy in roles.sql.
-- ============================================================================

-- ---- Warehouse (account role only) ----------------------------------------
GRANT USAGE   ON WAREHOUSE SKI_DEMO_WH TO ROLE SKI_READONLY;
GRANT OPERATE ON WAREHOUSE SKI_DEMO_WH TO ROLE SKI_DEVELOPER;

-- ---- Database + read schemas (READONLY) -----------------------------------
GRANT USAGE ON DATABASE {{ db }}        TO ROLE SKI_READONLY;
GRANT USAGE ON SCHEMA {{ db }}.MARTS    TO ROLE SKI_READONLY;
GRANT USAGE ON SCHEMA {{ db }}.SEMANTIC TO ROLE SKI_READONLY;
GRANT USAGE ON SCHEMA {{ db }}.STAGING  TO ROLE SKI_READONLY;

-- ---- Read-only object grants on existing data objects -------------------
GRANT SELECT ON ALL TABLES IN SCHEMA {{ db }}.MARTS   TO ROLE SKI_READONLY;
GRANT SELECT ON ALL VIEWS  IN SCHEMA {{ db }}.MARTS   TO ROLE SKI_READONLY;
GRANT SELECT ON ALL VIEWS  IN SCHEMA {{ db }}.STAGING TO ROLE SKI_READONLY;

-- ---- App schemas ----------------------------------------------------------
-- READONLY needs USAGE on APPS to reach the PRODUCTION apps consumers use.
GRANT USAGE ON SCHEMA {{ db }}.APPS TO ROLE SKI_READONLY;

-- DEVELOPER can build/deploy app objects in both prod (APPS) and dev (APPS_DEV).
GRANT USAGE ON SCHEMA {{ db }}.APPS_DEV TO ROLE SKI_READONLY;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE
    ON SCHEMA {{ db }}.APPS     TO ROLE SKI_DEVELOPER;
GRANT CREATE TABLE, CREATE VIEW, CREATE STAGE
    ON SCHEMA {{ db }}.APPS_DEV TO ROLE SKI_DEVELOPER;
