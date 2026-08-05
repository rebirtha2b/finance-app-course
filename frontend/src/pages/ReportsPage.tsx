import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatMoney, today } from '../api/money'
import CsvImport from '../components/CsvImport'
import type { Account, Category, CategoryComparison, YearSummary } from '../api/types'

const MONTH_NAMES = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

export default function ReportsPage() {
  const [year, setYear] = useState(new Date().getFullYear())
  const [summary, setSummary] = useState<YearSummary | null>(null)
  const [comparison, setComparison] = useState<CategoryComparison[]>([])
  const [mode, setMode] = useState<'month' | 'year'>('month')
  const [accounts, setAccounts] = useState<Account[]>([])
  const [categories, setCategories] = useState<Category[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([api.accounts.list(), api.categories.list()])
      .then(([a, c]) => {
        setAccounts(a)
        setCategories(c)
      })
      .catch((err) => setError(err.message))
  }, [])

  const load = useCallback(() => {
    const comparisonCall =
      mode === 'month'
        ? api.reports.monthOverMonth(today())
        : api.reports.yearOverYear(year)

    Promise.all([api.reports.yearly(year), comparisonCall])
      .then(([s, c]) => {
        setSummary(s)
        setComparison(c)
      })
      .catch((err) => setError(err.message))
  }, [year, mode])

  useEffect(load, [load])

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold">Reports</h1>
          <p className="mt-1 text-sm text-muted">
            Year totals, period comparisons, and getting data in and out.
          </p>
        </div>
        <div className="flex items-end gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">Year</span>
            <input
              type="number"
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="tnum w-24 rounded-md border border-line px-3 py-2 text-sm"
            />
          </label>
          <a
            href={api.reports.exportUrl()}
            download
            className="rounded-md border border-line px-4 py-2 text-sm hover:text-ink"
          >
            Export all as CSV
          </a>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-negative">
          {error}
        </p>
      )}

      {summary && (
        <div className="grid grid-cols-4 gap-4">
          <Tile label={`Income ${summary.year}`} value={formatMoney(summary.income)} />
          <Tile label="Expenses" value={formatMoney(summary.expenses)} />
          <Tile
            label="Net"
            value={formatMoney(summary.net)}
            tone={Number(summary.net) < 0 ? 'text-negative' : 'text-positive'}
          />
          <Tile
            label="Savings rate"
            value={summary.savings_rate !== null ? `${summary.savings_rate}%` : '—'}
            hint={summary.savings_rate === null ? 'No income recorded' : 'of income kept'}
          />
        </div>
      )}

      {summary && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase text-muted">
                <th className="px-4 py-2 font-medium">Month</th>
                <th className="px-4 py-2 text-right font-medium">Income</th>
                <th className="px-4 py-2 text-right font-medium">Expenses</th>
                <th className="px-4 py-2 text-right font-medium">Net</th>
              </tr>
            </thead>
            <tbody>
              {summary.months.map((m, i) => {
                const empty = m.income === '0.00' && m.expenses === '0.00'
                return (
                  <tr
                    key={m.month}
                    className={`border-b border-line last:border-0 ${empty ? 'text-muted' : ''}`}
                  >
                    <td className="px-4 py-1.5">{MONTH_NAMES[i]}</td>
                    <td className="tnum px-4 py-1.5 text-right">{formatMoney(m.income)}</td>
                    <td className="tnum px-4 py-1.5 text-right">{formatMoney(m.expenses)}</td>
                    <td
                      className={`tnum px-4 py-1.5 text-right ${
                        !empty && Number(m.net) < 0 ? 'text-negative' : ''
                      }`}
                    >
                      {formatMoney(m.net)}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface">
        <div className="flex items-center justify-between border-b border-line p-4">
          <h2 className="text-sm font-medium">
            {mode === 'month' ? 'This month vs last month' : `${year} vs ${year - 1}`}
          </h2>
          <div className="flex rounded-md border border-line p-0.5 text-sm">
            {(['month', 'year'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                aria-pressed={mode === m}
                className={`rounded px-3 py-1 ${
                  mode === m ? 'bg-accent text-accent-ink' : 'text-muted hover:text-ink'
                }`}
              >
                {m === 'month' ? 'Monthly' : 'Yearly'}
              </button>
            ))}
          </div>
        </div>

        {comparison.length === 0 ? (
          <p className="p-8 text-center text-sm text-muted">
            Nothing to compare yet — this needs spending in both periods.
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs uppercase text-muted">
                <th className="px-4 py-2 font-medium">Category</th>
                <th className="px-4 py-2 text-right font-medium">Previous</th>
                <th className="px-4 py-2 text-right font-medium">Current</th>
                <th className="px-4 py-2 text-right font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {comparison.map((c) => {
                const up = Number(c.change) > 0
                return (
                  <tr key={c.category_id} className="border-b border-line last:border-0">
                    <td className="px-4 py-2">{c.name}</td>
                    <td className="tnum px-4 py-2 text-right text-muted">
                      {formatMoney(c.previous)}
                    </td>
                    <td className="tnum px-4 py-2 text-right">{formatMoney(c.current)}</td>
                    <td
                      className={`tnum px-4 py-2 text-right ${
                        up ? 'text-negative' : 'text-positive'
                      }`}
                    >
                      {up ? '+' : ''}
                      {formatMoney(c.change)}
                      {c.change_percent !== null && (
                        <span className="ml-2 text-xs">
                          {up ? '+' : ''}
                          {c.change_percent}%
                        </span>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {accounts.length > 0 && (
        <CsvImport accounts={accounts} categories={categories} onImported={load} />
      )}
    </div>
  )
}

function Tile({
  label,
  value,
  tone = '',
  hint,
}: {
  label: string
  value: string
  tone?: string
  hint?: string
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}
