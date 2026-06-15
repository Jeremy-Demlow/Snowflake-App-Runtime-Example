-- ============================================================================
-- roles.sql — Three-tier account-role hierarchy with inheritance
--
-- We use ACCOUNT roles (not database roles) for two reasons:
--   1. Every tier needs warehouse USAGE, which cannot be granted to a
--      database role (warehouses are account-level objects).
--   2. A single, readable hierarchy that a non-technical team can reason about.
--
-- ONE role set — environments are at the app layer (APPS vs APPS_DEV), not in
-- the role names. Inheritance (privileges flow UP):
--   SYSADMIN -> SKI_ADMIN -> SKI_DEVELOPER -> SKI_READONLY
-- so ADMIN automatically has everything DEVELOPER and READONLY have.
-- ============================================================================

DEFINE ROLE SKI_READONLY
    COMMENT = 'Read-only: SELECT on resort data + warehouse usage';

DEFINE ROLE SKI_DEVELOPER
    COMMENT = 'Developer: read-only + can create/deploy app objects in APPS / APPS_DEV';

DEFINE ROLE SKI_ADMIN
    COMMENT = 'Admin: full control of the demo governance objects';

-- Role hierarchy (child granted to parent)
GRANT ROLE SKI_READONLY  TO ROLE SKI_DEVELOPER;
GRANT ROLE SKI_DEVELOPER TO ROLE SKI_ADMIN;
GRANT ROLE SKI_ADMIN     TO ROLE SYSADMIN;

-- Assign the demo user a working role so onboarding "just works".
-- DEVELOPER lets them read data AND deploy the apps.
GRANT ROLE SKI_DEVELOPER TO USER {{ demo_user }};
GRANT ROLE SKI_ADMIN     TO USER {{ demo_user }};
