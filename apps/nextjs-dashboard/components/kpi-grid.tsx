import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { Kpis } from "@/lib/queries"

function formatNumber(n: number): string {
  return new Intl.NumberFormat("en-US").format(n)
}

interface Metric {
  label: string
  value: string
  hint?: string
}

export function KpiGrid({ kpis }: { kpis: Kpis }) {
  const metrics: Metric[] = [
    { label: "Total visits", value: formatNumber(kpis.totalVisits), hint: `Season ${kpis.season}` },
    { label: "Unique visitors", value: formatNumber(kpis.uniqueVisitors) },
    { label: "Avg hours / visit", value: `${kpis.avgHoursPerVisit.toFixed(1)} h` },
    { label: "Pass-holder share", value: `${kpis.passHolderPct.toFixed(1)}%` },
    { label: "Weekend share", value: `${kpis.weekendSharePct.toFixed(1)}%` },
  ]

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
      {metrics.map((m) => (
        <Card key={m.label}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {m.label}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-semibold tracking-tight">{m.value}</div>
            {m.hint && <div className="mt-1 text-xs text-muted-foreground">{m.hint}</div>}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
