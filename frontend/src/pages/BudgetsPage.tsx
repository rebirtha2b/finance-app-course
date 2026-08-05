import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatMoney, today } from '../api/money'
import type { BudgetStatusSummary, CategoryTreeNode } from '../api/types'
import CategorySelect from '../components/CategorySelect'

/** Colour by how close to the limit you are — green until it matters. */
function toneFor(percent: number, over: boolean): string {
  if (over) return 'bg-negative'
  if (percent >= 85) return 'bg-warn-mark'
  return 'bg-positive'
}

export default function BudgetsPage() {
  const [month, setMonth] = useState(today().slice(0, 7))
  const [summary, setSummary] = useState<BudgetStatusSummary | null>(null)
  const [expenseTree, setExpenseTree] = useState<CategoryTreeNode[]>([])
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [limit, setLimit] = useState('')
  const [rollover, setRollover] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.categories
      .tree('expense')
      .then(setExpenseTree)
      .catch((err) => setError(err.message))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    api.budgets
      .status(`${month}-01`)
      .then(setSummary)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [month])

  useEffect(load, [load])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const cleaned = limit.trim().replace(',', '.')
    if (!/^\d*\.?\d+$/.test(cleaned) || Number(cleaned) <= 0) {
      return setError('Enter a limit greater than zero')
    }
    if (categoryId === '') return setError('Pick a category')

    try {
      await api.budgets.create({
        category_id: categoryId,
        limit: cleaned,
        start_month: `${month}-01`,
        rollover,
      })
      setLimit('')
      setCategoryId('')
      setRollover(false)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    }
  }

  async function remove(id: number) {
    try {
      await api.budgets.remove(id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">Budgets</h1>
          <p className="mt-1 text-sm text-muted">
            Monthly limits per category. A budget on a parent category covers its
            sub-categories.
          </p>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Month</span>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="rounded-md border border-line px-3 py-2 text-sm"
          />
        </label>
      </div>

      <form
        onSubmit={create}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4"
      >
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted">Category</span>
          <CategorySelect tree={expenseTree} value={categoryId} onChange={setCategoryId} />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted">Monthly limit</span>
          <input
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            inputMode="decimal"
            placeholder="400,00"
            className="tnum w-32 rounded-md border border-line px-3 py-2 text-right text-sm"
          />
        </div>
        <label className="flex items-center gap-2 py-2 text-sm text-muted">
          <input
            type="checkbox"
            checked={rollover}
            onChange={(e) => setRollover(e.target.checked)}
          />
          Roll over unspent
        </label>
        <button
          type="submit"
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
        >
          Set budget
        </button>
      </form>

      {error && (
        <p role="alert" className="text-sm text-negative">
          {error}
        </p>
      )}

      {summary && summary.items.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Budgeted" value={formatMoney(summary.total_limit)} />
          <Stat label="Spent" value={formatMoney(summary.total_spent)} />
          <Stat
            label="Remaining"
            value={formatMoney(summary.total_remaining)}
            negative={Number(summary.total_remaining) < 0}
          />
        </div>
      )}

      <div className="space-y-3">
        {loading && <p className="text-sm text-muted">Loading…</p>}

        {!loading && summary?.items.length === 0 && (
          <div className="rounded-lg border border-line bg-surface p-8 text-center text-muted">
            No budgets for this month yet. Set one above.
          </div>
        )}

        {!loading &&
          summary?.items.map((item) => {
            const pct = Math.min(item.percent_used, 100)
            return (
              <div
                key={item.budget_id}
                className="rounded-lg border border-line bg-surface p-4"
              >
                <div className="flex items-baseline justify-between">
                  <div className="flex items-baseline gap-2">
                    <span className="font-medium">{item.category_name}</span>
                    {item.period === 'yearly' && (
                      <span className="rounded bg-canvas px-1.5 py-0.5 text-xs text-muted">
                        yearly
                      </span>
                    )}
                    {Number(item.rollover) > 0 && (
                      <span className="rounded bg-canvas px-1.5 py-0.5 text-xs text-muted">
                        +{formatMoney(item.rollover)} rolled over
                      </span>
                    )}
                  </div>
                  <div className="tnum text-sm">
                    <span className={item.over_budget ? 'text-negative' : ''}>
                      {formatMoney(item.spent)}
                    </span>
                    <span className="text-muted"> / {formatMoney(item.effective_limit)}</span>
                  </div>
                </div>

                <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-canvas">
                  <div
                    className={`h-full rounded-full ${toneFor(item.percent_used, item.over_budget)}`}
                    style={{ width: `${Math.max(pct, 0)}%` }}
                  />
                </div>

                <div className="mt-2 flex items-center justify-between text-xs">
                  <span className={item.over_budget ? 'text-negative' : 'text-muted'}>
                    {item.over_budget
                      ? `${formatMoney(String(-Number(item.remaining)))} over budget`
                      : `${formatMoney(item.remaining)} left · ${item.percent_used}% used`}
                  </span>
                  <button
                    onClick={() => remove(item.budget_id)}
                    className="text-muted hover:text-negative"
                  >
                    Remove
                  </button>
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  negative,
}: {
  label: string
  value: string
  negative?: boolean
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`tnum mt-1 text-2xl font-semibold ${negative ? 'text-negative' : ''}`}>
        {value}
      </p>
    </div>
  )
}
