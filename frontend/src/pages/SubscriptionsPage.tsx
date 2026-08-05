import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatDate, formatMoney } from '../api/money'
import type { Account, CategoryTreeNode, RecurringRule, SubscriptionsSummary } from '../api/types'
import RecurringForm from '../components/RecurringForm'

const FREQUENCY_LABEL: Record<string, string> = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  quarterly: 'Quarterly',
  yearly: 'Yearly',
}

function describe(rule: RecurringRule): string {
  const base = FREQUENCY_LABEL[rule.frequency] ?? rule.frequency
  return rule.interval > 1 ? `${base} × every ${rule.interval}` : base
}

export default function SubscriptionsPage() {
  const [summary, setSummary] = useState<SubscriptionsSummary | null>(null)
  const [paused, setPaused] = useState<RecurringRule[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [expenseTree, setExpenseTree] = useState<CategoryTreeNode[]>([])
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([api.accounts.list(), api.categories.tree('expense')])
      .then(([a, t]) => {
        setAccounts(a)
        setExpenseTree(t)
      })
      .catch((err) => setError(err.message))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([api.subscriptions.get(), api.recurring.list()])
      .then(([s, all]) => {
        setSummary(s)
        setPaused(all.filter((r) => !r.active))
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  async function setActive(rule: RecurringRule, active: boolean) {
    try {
      await api.recurring.update(rule.id, { active })
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not update')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">Subscriptions & recurring costs</h1>
          <p className="mt-1 text-sm text-muted">
            Every committed outgoing, normalised to a monthly figure so they can be
            compared and added up.
          </p>
        </div>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink"
          >
            Add recurring cost
          </button>
        )}
      </div>

      {showForm && (
        <RecurringForm
          accounts={accounts}
          expenseTree={expenseTree}
          onCreated={() => {
            setShowForm(false)
            load()
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      {error && (
        <p role="alert" className="text-sm text-negative">
          {error}
        </p>
      )}

      {summary && (
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-lg border border-line bg-surface p-4">
            <p className="text-xs uppercase tracking-wide text-muted">Per month</p>
            <p className="tnum mt-1 text-2xl font-semibold">
              {formatMoney(summary.total_monthly)}
            </p>
          </div>
          <div className="rounded-lg border border-line bg-surface p-4">
            <p className="text-xs uppercase tracking-wide text-muted">Per year</p>
            <p className="tnum mt-1 text-2xl font-semibold">
              {formatMoney(summary.total_annual)}
            </p>
          </div>
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium">Frequency</th>
              <th className="px-4 py-2 text-right font-medium">Charge</th>
              <th className="px-4 py-2 text-right font-medium">Per month</th>
              <th className="px-4 py-2 font-medium">Next charge</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="p-8 text-center text-muted">
                  Loading…
                </td>
              </tr>
            )}

            {!loading && summary?.items.length === 0 && (
              <tr>
                <td colSpan={7} className="p-8 text-center text-muted">
                  No recurring costs yet. Add rent, streaming, insurance — anything
                  that charges you on a schedule.
                </td>
              </tr>
            )}

            {!loading &&
              summary?.items.map((rule) => (
                <tr key={rule.id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2 font-medium">{rule.name}</td>
                  <td className="px-4 py-2 text-muted">{rule.category_name}</td>
                  <td className="px-4 py-2 text-muted">{describe(rule)}</td>
                  <td className="tnum px-4 py-2 text-right text-negative">
                    {formatMoney(rule.amount)}
                  </td>
                  <td className="tnum px-4 py-2 text-right font-medium">
                    {rule.monthly_equivalent && formatMoney(rule.monthly_equivalent)}
                  </td>
                  <td className="tnum px-4 py-2 text-muted">
                    {rule.next_due_date ? formatDate(rule.next_due_date) : '—'}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => setActive(rule, false)}
                      className="text-xs text-muted hover:text-ink"
                    >
                      Pause
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {paused.length > 0 && (
        <div className="rounded-lg border border-line bg-surface p-4">
          <h2 className="text-sm font-medium text-muted">Paused</h2>
          <ul className="mt-2 space-y-1">
            {paused.map((rule) => (
              <li key={rule.id} className="flex items-center justify-between text-sm">
                <span className="text-muted">
                  {rule.name} · {formatMoney(rule.amount)} · {describe(rule)}
                </span>
                <button
                  onClick={() => setActive(rule, true)}
                  className="text-xs text-accent hover:underline"
                >
                  Resume
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
