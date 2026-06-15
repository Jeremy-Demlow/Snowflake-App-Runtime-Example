"use client"

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import type { DayRow, SeasonRow, SnowRow, TrendRow } from "@/lib/queries"

const BRAND = "#29b5e8"
const BRAND_DARK = "#0a2f5a"

const axisProps = {
  stroke: "var(--muted-foreground)",
  fontSize: 12,
  tickLine: false,
  axisLine: false,
}

function tooltipStyle() {
  return {
    contentStyle: {
      background: "var(--card)",
      border: "1px solid var(--border)",
      borderRadius: "0.5rem",
      color: "var(--card-foreground)",
      fontSize: 12,
    },
  }
}

export function SeasonChart({ data }: { data: SeasonRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="season" {...axisProps} />
        <YAxis {...axisProps} />
        <Tooltip {...tooltipStyle()} />
        <Bar dataKey="visits" name="Total visits" fill={BRAND} radius={[4, 4, 0, 0]} />
        <Bar dataKey="uniqueVisitors" name="Unique visitors" fill={BRAND_DARK} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function DayChart({ data }: { data: DayRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="day" {...axisProps} />
        <YAxis {...axisProps} />
        <Tooltip {...tooltipStyle()} />
        <Bar dataKey="visits" name="Visits" fill={BRAND} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function SnowChart({ data }: { data: SnowRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 8, left: 16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
        <XAxis type="number" {...axisProps} />
        <YAxis type="category" dataKey="condition" width={80} {...axisProps} />
        <Tooltip {...tooltipStyle()} />
        <Bar dataKey="visits" name="Visits" fill={BRAND} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function TrendChart({ data }: { data: TrendRow[] }) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
        <XAxis dataKey="day" {...axisProps} minTickGap={40} />
        <YAxis {...axisProps} />
        <Tooltip {...tooltipStyle()} />
        <Line type="monotone" dataKey="visits" name="Daily visits" stroke={BRAND} strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
