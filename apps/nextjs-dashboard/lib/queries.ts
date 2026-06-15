/**
 * queries.ts — All Snowflake reads for the Daily Resort KPI dashboard.
 *
 * Every query is READ-ONLY and fully qualified with DEMO_DB.MARTS, so it runs
 * under the SKI_READONLY role. DEMO_DB is the single fixed data database
 * (SKI_RESORT_DEMO) — one read-only copy shared by every environment.
 *
 * Data model (AM_SKI_RESORT analytics dataset):
 *   FACT_PASS_USAGE — one row per guest per ski day
 *   DIM_DATE        — ski_season, is_weekend, snow_condition, day_name
 *   DIM_CUSTOMER    — is_pass_holder, customer_segment
 */
import { querySnowflake } from "@/lib/snowflake"
import { DEMO_DB } from "@/lib/constants"

const FACT = `${DEMO_DB}.MARTS.FACT_PASS_USAGE`
const DIM_DATE = `${DEMO_DB}.MARTS.DIM_DATE`
const DIM_CUSTOMER = `${DEMO_DB}.MARTS.DIM_CUSTOMER`

/** The most recent ski season that actually has visit data. */
const LATEST_SEASON = `(
  SELECT MAX(d.ski_season)
  FROM ${FACT} pu
  JOIN ${DIM_DATE} d ON pu.date_key = d.date_key
)`

export interface Kpis {
  season: string
  totalVisits: number
  uniqueVisitors: number
  avgHoursPerVisit: number
  passHolderPct: number
  weekendSharePct: number
}

export async function getKpis(): Promise<Kpis> {
  const rows = await querySnowflake(`
    SELECT
      ${LATEST_SEASON} AS ski_season,
      COUNT(*) AS total_visits,
      COUNT(DISTINCT pu.customer_key) AS unique_visitors,
      ROUND(AVG(pu.hours_on_mountain), 2) AS avg_hours_per_visit,
      ROUND(100 * COUNT_IF(c.is_pass_holder) / NULLIF(COUNT(*), 0), 1) AS pass_holder_pct,
      ROUND(100 * COUNT_IF(d.is_weekend) / NULLIF(COUNT(*), 0), 1) AS weekend_share_pct
    FROM ${FACT} pu
    JOIN ${DIM_DATE} d ON pu.date_key = d.date_key
    JOIN ${DIM_CUSTOMER} c ON pu.customer_key = c.customer_key
    WHERE d.ski_season = ${LATEST_SEASON}
  `)
  const r = rows[0] ?? {}
  return {
    season: r.SKI_SEASON ?? "—",
    totalVisits: Number(r.TOTAL_VISITS ?? 0),
    uniqueVisitors: Number(r.UNIQUE_VISITORS ?? 0),
    avgHoursPerVisit: Number(r.AVG_HOURS_PER_VISIT ?? 0),
    passHolderPct: Number(r.PASS_HOLDER_PCT ?? 0),
    weekendSharePct: Number(r.WEEKEND_SHARE_PCT ?? 0),
  }
}

export interface SeasonRow { season: string; visits: number; uniqueVisitors: number }

export async function getVisitsBySeason(): Promise<SeasonRow[]> {
  const rows = await querySnowflake(`
    SELECT d.ski_season AS season,
           COUNT(*) AS visits,
           COUNT(DISTINCT pu.customer_key) AS unique_visitors
    FROM ${FACT} pu
    JOIN ${DIM_DATE} d ON pu.date_key = d.date_key
    GROUP BY d.ski_season
    ORDER BY d.ski_season
  `)
  return rows.map((r) => ({
    season: r.SEASON,
    visits: Number(r.VISITS),
    uniqueVisitors: Number(r.UNIQUE_VISITORS),
  }))
}

export interface DayRow { day: string; visits: number }

export async function getVisitsByDayOfWeek(): Promise<DayRow[]> {
  const rows = await querySnowflake(`
    SELECT d.day_name AS day,
           COUNT(*) AS visits
    FROM ${FACT} pu
    JOIN ${DIM_DATE} d ON pu.date_key = d.date_key
    WHERE d.ski_season = ${LATEST_SEASON}
    GROUP BY d.day_name
    ORDER BY MIN(DAYOFWEEKISO(d.full_date))
  `)
  return rows.map((r) => ({ day: r.DAY, visits: Number(r.VISITS) }))
}

export interface SnowRow { condition: string; visits: number; avgHours: number }

export async function getVisitsBySnowCondition(): Promise<SnowRow[]> {
  const rows = await querySnowflake(`
    SELECT d.snow_condition AS condition,
           COUNT(*) AS visits,
           ROUND(AVG(pu.hours_on_mountain), 2) AS avg_hours
    FROM ${FACT} pu
    JOIN ${DIM_DATE} d ON pu.date_key = d.date_key
    WHERE d.ski_season = ${LATEST_SEASON}
    GROUP BY d.snow_condition
    ORDER BY visits DESC
  `)
  return rows.map((r) => ({
    condition: r.CONDITION,
    visits: Number(r.VISITS),
    avgHours: Number(r.AVG_HOURS),
  }))
}

export interface TrendRow { day: string; visits: number }

export async function getDailyTrend(): Promise<TrendRow[]> {
  const rows = await querySnowflake(`
    SELECT TO_VARCHAR(d.full_date, 'YYYY-MM-DD') AS day,
           COUNT(*) AS visits
    FROM ${FACT} pu
    JOIN ${DIM_DATE} d ON pu.date_key = d.date_key
    WHERE d.ski_season = ${LATEST_SEASON}
    GROUP BY d.full_date
    ORDER BY d.full_date
  `)
  return rows.map((r) => ({ day: r.DAY, visits: Number(r.VISITS) }))
}

