import { formatMoney } from '../api/money'
import type { CategorySpend } from '../api/types'
import { chartColors, useTheme } from '../theme'

// A single hue for every bar. The categories are nominal — colouring each one
// differently would burn the colour channel on information the bar length
// already carries, and past ~7 classes adjacent hues blur anyway. Ranked bars
// with direct labels beat a donut here: a donut is part-to-whole at a glance
// only, and it stops working past ~6 segments or when values are close.
export default function SpendingBreakdown({ data }: { data: CategorySpend[] }) {
  const { resolved } = useTheme()
  const bar = chartColors(resolved).series1
  const max = Math.max(...data.map((d) => Number(d.amount)), 0)

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <h2 className="text-sm font-medium">Where the money went</h2>
      <p className="text-xs text-muted">This month, by category</p>

      {data.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted">No spending this month.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {data.map((row) => (
            <li key={row.category_id}>
              <div className="flex items-baseline justify-between text-sm">
                <span>{row.name}</span>
                {/* Direct labels: the value is readable without the tooltip
                    and without relying on colour. */}
                <span className="tnum text-muted">
                  {formatMoney(row.amount)}
                  <span className="ml-2 text-xs">{row.percent}%</span>
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-canvas">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${max ? (Number(row.amount) / max) * 100 : 0}%`,
                    backgroundColor: bar,
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
