-- ============================================================================
-- warehouse.sql — Dedicated compute for the demo
--
-- A SINGLE shared warehouse for all app instances (prod + dev/branch). The
-- workload is a small read-only dashboard, so one XS warehouse is plenty.
-- Account-level object (lives outside the database), so it is safe to DEFINE
-- here even though DCM cannot define its own parent database.
-- ============================================================================

DEFINE WAREHOUSE SKI_DEMO_WH
WITH
    WAREHOUSE_SIZE = '{{ wh_size }}'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Shared compute for the ski-resort demo apps';
