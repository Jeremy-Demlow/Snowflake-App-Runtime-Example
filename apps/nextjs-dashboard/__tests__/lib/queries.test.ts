import { describe, it, expect, vi, beforeEach } from "vitest"

// DEMO_DB is a fixed constant (SKI_RESORT_DEMO) in constants.ts — one read-only
// data copy shared by every environment. Queries must fully qualify with it.
const DB = "SKI_RESORT_DEMO"

// Capture the SQL the query layer sends.
const calls: string[] = []
vi.mock("@/lib/snowflake", () => ({
  querySnowflake: vi.fn(async (sql: string) => {
    calls.push(sql)
    return []
  }),
}))

const { getKpis, getVisitsBySeason } = await import("@/lib/queries")

describe("KPI query builder", () => {
  beforeEach(() => {
    calls.length = 0
  })

  it("qualifies tables with the configured database and joins fact to date dim", async () => {
    await getVisitsBySeason()
    const sql = calls.find((s) => s.includes("FACT_PASS_USAGE"))
    expect(sql).toBeTruthy()
    expect(sql).toContain(`${DB}.MARTS.FACT_PASS_USAGE`)
    expect(sql).toContain(`${DB}.MARTS.DIM_DATE`)
    expect(sql).toMatch(/JOIN\s+SKI_RESORT_DEMO\.MARTS\.DIM_DATE\s+d\s+ON\s+pu\.date_key\s*=\s*d\.date_key/)
  })

  it("kpis query also joins the customer dimension", async () => {
    await getKpis()
    const sql = calls.find((s) => s.includes("pass_holder_pct"))
    expect(sql).toContain(`${DB}.MARTS.DIM_CUSTOMER`)
  })
})
