import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatDate, formatMoney, startOfMonth, today } from '../api/money'
import type {
  Account,
  CategoryTreeNode,
  Transaction,
  TransactionFilters,
  TransactionPage,
} from '../api/types'
import CategorySelect from '../components/CategorySelect'
import QuickAdd from '../components/QuickAdd'

const PAGE_SIZE = 50

export default function TransactionsPage() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [expenseTree, setExpenseTree] = useState<CategoryTreeNode[]>([])
  const [incomeTree, setIncomeTree] = useState<CategoryTreeNode[]>([])

  const [filters, setFilters] = useState<TransactionFilters>({
    from: startOfMonth(),
    to: today(),
    sort: 'date',
    order: 'desc',
    limit: PAGE_SIZE,
    offset: 0,
  })
  const [page, setPage] = useState<TransactionPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      api.accounts.list(),
      api.categories.tree('expense'),
      api.categories.tree('income'),
    ])
      .then(([a, e, i]) => {
        setAccounts(a)
        setExpenseTree(e)
        setIncomeTree(i)
      })
      .catch((err) => setError(err.message))
  }, [])

  const load = useCallback(() => {
    setLoading(true)
    api.transactions
      .list(filters)
      .then(setPage)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [filters])

  useEffect(load, [load])

  function patchFilters(patch: Partial<TransactionFilters>) {
    // Any filter change invalidates the current page position.
    setFilters((f) => ({ ...f, ...patch, offset: 0 }))
  }

  /**
   * Called after a transaction is saved.
   *
   * The list defaults to the current month, so a back-dated entry saves fine
   * but lands outside the visible range — which reads as "adding it didn't
   * work". Widen the range to include whatever was just added, and say so,
   * rather than leaving the user to work out why the row is missing.
   */
  function handleAdded(created: Transaction) {
    const outsideRange =
      (filters.from && created.date < filters.from) ||
      (filters.to && created.date > filters.to)

    if (outsideRange) {
      setNotice(
        `Added ${formatMoney(created.amount)} on ${formatDate(created.date)}. That date is outside the range you were viewing, so the range was widened to show it.`,
      )
      setFilters((f) => ({
        ...f,
        from: f.from && created.date < f.from ? created.date : f.from,
        to: f.to && created.date > f.to ? created.date : f.to,
        offset: 0,
      }))
      return // the filter change triggers the reload
    }

    setNotice(null)
    load()
  }

  function toggleSort(field: 'date' | 'amount' | 'description') {
    setFilters((f) => ({
      ...f,
      sort: field,
      order: f.sort === field && f.order === 'desc' ? 'asc' : 'desc',
      offset: 0,
    }))
  }

  async function remove(id: number) {
    if (!confirm('Delete this transaction?')) return
    try {
      await api.transactions.remove(id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not delete')
    }
  }

  const sortIndicator = (field: string) =>
    filters.sort === field ? (filters.order === 'desc' ? ' ↓' : ' ↑') : ''

  return (
    <div className="space-y-6">
      <QuickAdd
        accounts={accounts}
        expenseTree={expenseTree}
        incomeTree={incomeTree}
        onAdded={handleAdded}
      />

      {notice && (
        <div
          role="status"
          className="flex items-start justify-between gap-4 rounded-lg border border-line bg-surface px-4 py-3 text-sm"
        >
          <span>{notice}</span>
          <button
            onClick={() => setNotice(null)}
            aria-label="Dismiss"
            className="text-muted hover:text-ink"
          >
            ×
          </button>
        </div>
      )}

      {page && (
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Income" value={formatMoney(page.totals.income)} tone="positive" />
          <Stat label="Expenses" value={formatMoney(page.totals.expenses)} tone="negative" />
          <Stat
            label="Net"
            value={formatMoney(page.totals.net)}
            tone={Number(page.totals.net) < 0 ? 'negative' : 'positive'}
          />
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface">
        <div className="flex flex-wrap items-end gap-3 border-b border-line p-4">
          <Field label="From">
            <input
              type="date"
              value={filters.from ?? ''}
              onChange={(e) => patchFilters({ from: e.target.value || undefined })}
              className="rounded-md border border-line px-3 py-2 text-sm"
            />
          </Field>
          <Field label="To">
            <input
              type="date"
              value={filters.to ?? ''}
              onChange={(e) => patchFilters({ to: e.target.value || undefined })}
              className="rounded-md border border-line px-3 py-2 text-sm"
            />
          </Field>
          <Field label="Category">
            <CategorySelect
              tree={[...expenseTree, ...incomeTree]}
              value={filters.category_id ?? ''}
              onChange={(id) => patchFilters({ category_id: id === '' ? undefined : id })}
              includeAllOption
            />
          </Field>
          <Field label="Search">
            <input
              value={filters.q ?? ''}
              onChange={(e) => patchFilters({ q: e.target.value || undefined })}
              placeholder="Description or notes"
              className="rounded-md border border-line px-3 py-2 text-sm"
            />
          </Field>
          <button
            type="button"
            onClick={() =>
              setFilters({ sort: 'date', order: 'desc', limit: PAGE_SIZE, offset: 0 })
            }
            className="rounded-md border border-line px-3 py-2 text-sm text-muted hover:text-ink"
          >
            Clear
          </button>
        </div>

        {error && (
          <p role="alert" className="p-4 text-sm text-negative">
            {error}
          </p>
        )}

        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <Th onClick={() => toggleSort('date')}>Date{sortIndicator('date')}</Th>
              <Th onClick={() => toggleSort('description')}>
                Description{sortIndicator('description')}
              </Th>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium">Account</th>
              <Th onClick={() => toggleSort('amount')} align="right">
                Amount{sortIndicator('amount')}
              </Th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-muted">
                  Loading…
                </td>
              </tr>
            )}

            {!loading && page?.items.length === 0 && (
              <tr>
                <td colSpan={6} className="p-8 text-center text-muted">
                  No transactions in this range. Add one above.
                </td>
              </tr>
            )}

            {!loading &&
              page?.items.map((t) => {
                const negative = Number(t.amount) < 0
                return (
                  <tr key={t.id} className="border-b border-line last:border-0">
                    <td className="tnum px-4 py-2 whitespace-nowrap">
                      {formatDate(t.date)}
                    </td>
                    <td className="px-4 py-2">
                      {t.description || <span className="text-muted">—</span>}
                      {t.recurring_rule_id && (
                        <span
                          title="Generated from a recurring rule"
                          className="ml-2 rounded bg-canvas px-1.5 py-0.5 text-xs text-muted"
                        >
                          recurring
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-muted">{t.category_name}</td>
                    <td className="px-4 py-2 text-muted">{t.account_name}</td>
                    <td
                      className={`tnum px-4 py-2 text-right font-medium ${
                        negative ? 'text-negative' : 'text-positive'
                      }`}
                    >
                      {formatMoney(t.amount)}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <button
                        onClick={() => remove(t.id)}
                        className="text-xs text-muted hover:text-negative"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>

        {page && page.total > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-line p-4 text-sm">
            <span className="text-muted">
              {page.offset + 1}–{Math.min(page.offset + page.limit, page.total)} of{' '}
              {page.total}
            </span>
            <div className="flex gap-2">
              <button
                disabled={page.offset === 0}
                onClick={() =>
                  setFilters((f) => ({
                    ...f,
                    offset: Math.max(0, (f.offset ?? 0) - PAGE_SIZE),
                  }))
                }
                className="rounded-md border border-line px-3 py-1.5 disabled:opacity-40"
              >
                Previous
              </button>
              <button
                disabled={page.offset + page.limit >= page.total}
                onClick={() =>
                  setFilters((f) => ({ ...f, offset: (f.offset ?? 0) + PAGE_SIZE }))
                }
                className="rounded-md border border-line px-3 py-1.5 disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'positive' | 'negative'
}) {
  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p
        className={`tnum mt-1 text-2xl font-semibold ${
          tone === 'negative' ? 'text-negative' : 'text-positive'
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-muted">{label}</span>
      {children}
    </div>
  )
}

function Th({
  children,
  onClick,
  align = 'left',
}: {
  children: React.ReactNode
  onClick: () => void
  align?: 'left' | 'right'
}) {
  return (
    <th className={`px-4 py-2 font-medium ${align === 'right' ? 'text-right' : ''}`}>
      <button onClick={onClick} className="uppercase hover:text-ink">
        {children}
      </button>
    </th>
  )
}
