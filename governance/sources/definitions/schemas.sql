-- ============================================================================
-- schemas.sql — App schemas for deployed app objects
--
-- Environments live at the APP layer, separated by schema:
--   APPS      -> production app objects (consumers use these)
--   APPS_DEV  -> dev + ephemeral feature-branch app objects
--
-- These are SIBLING schemas inside the existing demo database. DCM cannot
-- define the parent database or the parent schema (PUBLIC), but defining new
-- schemas inside the existing database is supported.
--
-- Both the Next.js (App Runtime) and Streamlit apps create their objects here.
-- ============================================================================

DEFINE SCHEMA {{ db }}.APPS
    COMMENT = 'Production app objects (Next.js + Streamlit dashboards)';

DEFINE SCHEMA {{ db }}.APPS_DEV
    COMMENT = 'Dev + ephemeral feature-branch app objects';
