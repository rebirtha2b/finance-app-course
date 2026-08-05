import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { formatDate, formatMoney } from '../api/money'
import CashFlowChart from '../components/CashFlowChart'
import SpendingBreakdown from '../components/SpendingBreakdown'
import type { Dashboard } from '../api/types'

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-muted">Loading…</p>
  if (error)
    return (
      <p role="alert" className="text-sm text-negative">
        {error}
      </p>
    )
  if (!data) return null

  const netNegative = Number(data.this_month.net) < 0

  return (
    <div className="space-y-6">
      {/* Hero figures. Proportional (not tabular) digits: equal-width figures
          make large standalone numbers look loose. */}
      <div className="grid grid-cols-4 gap-4">
        <Tile label="Net worth" value={formatMoney(data.net_worth)} big />
        <Tile label="Income this month" value={formatMoney(data.this_month.income)} />
        <Tile label="Spent this month" value={formatMoney(data.this_month.expenses)} />
        <Tile
          label="Net this month"
          value={formatMoney(data.this_month.net)}
          tone={netNegative ? 'text-negative' : 'text-positive'}
        />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <CashFlowChart data={data.cash_flow} />
        </div>
        <SpendingBreakdown data={data.spending_by_category} />
      </div>

      <div className="grid grid-cols-3 gap-4">
        <Card title="Portfolio" href="/portfolio">
          {data.portfolio.holdings_count === 0 ? (
            <Empty>
              No holdings yet.{' '}
              <Link to="/portfolio" className="text-accent hover:underline">
                Add one
              </Link>
              .
            </Empty>
          ) : (
            <div className="space-y-2">
              <p className="text-2xl font-semibold">
                {formatMoney(data.portfolio.total_value)}
              </p>
              <p className="text-sm">
                <span className="text-muted">Day </span>
                <span
                  className={
                    Number(data.portfolio.day_change) < 0
                      ? 'text-negative'
                      : 'text-positive'
                  }
                >
                  {formatMoney(data.portfolio.day_change)}
                </span>
              </p>
              {data.portfolio.total_gain !== null && (
                <p className="text-sm">
                  <span className="text-muted">Total gain </span>
                  <span
                    className={
                      Number(data.portfolio.total_gain) < 0
                        ? 'text-negative'
                        : 'text-positive'
                    }
                  >
                    {formatMoney(data.portfolio.total_gain)}
                    {data.portfolio.total_gain_percent !== null &&
                      ` (${data.portfolio.total_gain_percent.toFixed(1)}%)`}
                  </span>
                </p>
              )}
              <p className="text-xs text-muted">
                {data.portfolio.holdings_count} holding
                {data.portfolio.holdings_count === 1 ? '' : 's'}
                {data.portfolio.has_stale_prices && ' · some prices are not current'}
              </p>
            </div>
          )}
        </Card>

        <Card title="Budgets needing attention" href="/budgets">
          {data.budgets_at_risk.length === 0 ? (
            <Empty>Nothing close to its limit.</Empty>
          ) : (
            <ul className="space-y-2">
              {data.budgets_at_risk.map((b) => (
                <li key={b.budget_id} className="text-sm">
                  <div className="flex justify-between">
                    <span>{b.category_name}</span>
                    <span className={`tnum ${b.over_budget ? 'text-negative' : ''}`}>
                      {formatMoney(b.spent)} / {formatMoney(b.effective_limit)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full rounded-full bg-canvas">
                    <div
                      className={`h-full rounded-full ${
                        b.over_budget ? 'bg-negative' : 'bg-warn-mark'
                      }`}
                      style={{ width: `${Math.min(b.percent_used, 100)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Due in the next 14 days" href="/subscriptions">
          {data.upcoming.length === 0 ? (
            <Empty>Nothing scheduled.</Empty>
          ) : (
            <ul className="space-y-1.5">
              {data.upcoming.map((u) => (
                <li key={u.rule_id} className="flex justify-between text-sm">
                  <span>
                    {u.name}
                    <span className="ml-2 text-xs text-muted">
                      {u.days_away === 0
                        ? 'today'
                        : u.days_away === 1
                          ? 'tomorrow'
                          : formatDate(u.due_date)}
                    </span>
                  </span>
                  <span className="tnum text-negative">{formatMoney(u.amount)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}

function Tile({
  label,
  value,
  tone = '',
  big,
}: {
  label: string
  value: string
  tone?: string
  big?: boolean
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 font-semibold ${big ? 'text-3xl' : 'text-2xl'} ${tone}`}>
        {value}
      </p>
    </div>
  )
}

function Card({
  title,
  href,
  children,
}: {
  title: string
  href: string
  children: React.ReactNode
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-medium">{title}</h2>
        <Link to={href} className="text-xs text-muted hover:text-ink">
          View
        </Link>
      </div>
      {children}
    </div>
  )
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>
}
