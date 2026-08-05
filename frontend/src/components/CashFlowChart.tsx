import { useState } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatMoney } from '../api/money'
import type { MonthFlow } from '../api/types'
import { chartColors, useTheme } from '../theme'

// Categorical slots 1 and 2. Income and expenses are two *identities*, not a
// good/bad judgement, so these are categorical hues rather than status colors
// (status red/green is reserved for things that actually mean good or bad).
//
// The dark steps are selected for the dark surface rather than flipped from
// the light ones, and each pair was run through the palette validator against
// its own surface: light CVD ΔE 24.7, dark 26.8 — both clear of the ≥8 floor.
// See chartColors() in ../theme.

function monthLabel(iso: string): string {
  const [y, m] = iso.split('-')
  return `${['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][Number(m) - 1]} ${y.slice(2)}`
}

function compact(value: number): string {
  // One decimal, not whole thousands: Recharts picks ticks like 1600/2400,
  // and rounding those to "2k" and "2k" puts duplicate labels on the axis.
  if (Math.abs(value) >= 1000) {
    const k = value / 1000
    return `${Number.isInteger(k) ? k : k.toFixed(1)}k`
  }
  return String(Math.round(value))
}

export default function CashFlowChart({ data }: { data: MonthFlow[] }) {
  const [showTable, setShowTable] = useState(false)
  // Recharts writes colours into SVG attributes, so they cannot inherit the
  // CSS custom properties the rest of the UI uses — they must be resolved here.
  const { resolved } = useTheme()
  const c = chartColors(resolved)

  const rows = data.map((m) => ({
    month: monthLabel(m.month),
    Income: Number(m.income),
    Expenses: Number(m.expenses),
    net: m.net,
  }))

  const hasData = rows.some((r) => r.Income > 0 || r.Expenses > 0)

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-4 flex items-baseline justify-between">
        <div>
          <h2 className="text-sm font-medium">Income vs expenses</h2>
          <p className="text-xs text-muted">Last 12 months</p>
        </div>
        <button
          onClick={() => setShowTable((s) => !s)}
          className="text-xs text-muted hover:text-ink"
        >
          {showTable ? 'Show chart' : 'Show as table'}
        </button>
      </div>

      {!hasData ? (
        <p className="py-12 text-center text-sm text-muted">
          No transactions yet — this fills in as you add income and expenses.
        </p>
      ) : showTable ? (
        // The table view is the accessible twin: every value the chart encodes
        // is readable here without relying on colour.
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface">
              <tr className="border-b border-line text-left text-xs uppercase text-muted">
                <th className="py-2 font-medium">Month</th>
                <th className="py-2 text-right font-medium">Income</th>
                <th className="py-2 text-right font-medium">Expenses</th>
                <th className="py-2 text-right font-medium">Net</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.month} className="border-b border-line last:border-0">
                  <td className="py-1.5">{r.month}</td>
                  <td className="tnum py-1.5 text-right">{formatMoney(r.Income)}</td>
                  <td className="tnum py-1.5 text-right">{formatMoney(r.Expenses)}</td>
                  <td
                    className={`tnum py-1.5 text-right ${Number(r.net) < 0 ? 'text-negative' : ''}`}
                  >
                    {formatMoney(r.net)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 4 }}>
            {/* Horizontal hairlines only — solid, one shade off the surface. */}
            <CartesianGrid stroke={c.grid} vertical={false} />
            <XAxis
              dataKey="month"
              tick={{ fill: c.axis, fontSize: 11 }}
              tickLine={false}
              axisLine={{ stroke: c.grid }}
            />
            <YAxis
              tick={{ fill: c.axis, fontSize: 11 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={compact}
              width={44}
            />
            <Tooltip
              cursor={{ fill: c.cursor }}
              formatter={(value) => formatMoney(Number(value ?? 0))}
              contentStyle={{
                borderRadius: 8,
                border: `1px solid ${c.grid}`,
                backgroundColor: c.surface,
                color: c.tooltipText,
                fontSize: 12,
              }}
              labelStyle={{ color: c.tooltipText }}
            />
            <Legend
              iconType="circle"
              iconSize={8}
              wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
            />
            {/* 2px surface gap between adjacent bars; rounded data-ends. */}
            <Bar dataKey="Income" fill={c.series1} radius={[4, 4, 0, 0]} barSize={10} />
            <Bar
              dataKey="Expenses"
              fill={c.series2}
              radius={[4, 4, 0, 0]}
              barSize={10}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
