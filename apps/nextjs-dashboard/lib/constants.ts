/** App title — displayed in the nav header and browser tab */
export const APP_TITLE = "Ski Resort — Daily KPIs"

/** Path to the logo in /public (used in the header and as favicon) */
export const LOGO_SRC = "/icon.svg"

/**
 * The database the dashboard reads from. There is ONE read-only data copy
 * shared by every environment, so this is a single fixed value — dev and prod
 * app instances point at the same data and differ only by which app object /
 * schema (APPS vs APPS_DEV) they deploy into.
 */
export const DEMO_DB = "SKI_RESORT_DEMO"
