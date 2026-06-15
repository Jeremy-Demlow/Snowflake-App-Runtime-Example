import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { KpiGrid } from "@/components/kpi-grid"
import { DayChart, SeasonChart, SnowChart, TrendChart } from "@/components/charts"
import {
  getDailyTrend,
  getKpis,
  getVisitsByDayOfWeek,
  getVisitsBySeason,
  getVisitsBySnowCondition,
} from "@/lib/queries"

// Required: Snowflake is not reachable during the docker build.
export const dynamic = "force-dynamic"

function ChartCard({
  title,
  description,
  children,
}: {
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base font-semibold">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

export default async function Home() {
  let kpis, bySeason, byDay, bySnow, trend
  try {
    ;[kpis, bySeason, byDay, bySnow, trend] = await Promise.all([
      getKpis(),
      getVisitsBySeason(),
      getVisitsByDayOfWeek(),
      getVisitsBySnowCondition(),
      getDailyTrend(),
    ])
  } catch (e) {
    const message = e instanceof Error ? e.message : "Unknown error"
    return (
      <main className="w-full py-12 px-4 max-w-3xl mx-auto">
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-semibold text-destructive">
              Could not load resort data
            </CardTitle>
            <CardDescription>Reading from the MARTS schema</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{message}</p>
            <p className="mt-3 text-sm text-muted-foreground">
              Check that the active role has SELECT on the MARTS schema of the
              database this app is deployed in.
            </p>
          </CardContent>
        </Card>
      </main>
    )
  }

  return (
    <main className="w-full py-10 px-4 md:px-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Daily Resort KPIs</h1>
        <p className="text-sm text-muted-foreground">
          Visitation and guest activity for season {kpis.season}
        </p>
      </div>

      <KpiGrid kpis={kpis} />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <ChartCard title="Visits by ski season" description="Total visits and unique visitors per season">
          <SeasonChart data={bySeason} />
        </ChartCard>
        <ChartCard title="Visits by day of week" description={`Within season ${kpis.season}`}>
          <DayChart data={byDay} />
        </ChartCard>
        <ChartCard title="Visits by snow condition" description="How snow quality drives turnout">
          <SnowChart data={bySnow} />
        </ChartCard>
        <ChartCard title="Daily visits trend" description={`Day-by-day for season ${kpis.season}`}>
          <TrendChart data={trend} />
        </ChartCard>
      </div>
    </main>
  )
}
