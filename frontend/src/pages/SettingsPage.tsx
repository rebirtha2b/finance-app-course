import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import type { DataSummary, ResetScope } from '../api/types'

const PHRASE = 'DELETE MY DATA'

const SCOPES: {
  key: ResetScope
  label: string
  describe: (s: DataSummary) => string
  note?: string
}[] = [
  {
    key: 'transactions',
    label: 'Income & expenses',
    describe: (s) => `${s.transactions} transaction${s.transactions === 1 ? '' : 's'}`,
  },
  {
    key: 'recurring',
    label: 'Recurring rules',
    describe: (s) => `${s.recurring_rules} rule${s.recurring_rules === 1 ? '' : 's'}`,
    note: 'Charges they already created are kept — that money really moved.',
  },
  {
    key: 'budgets',
    label: 'Budgets',
    describe: (s) => `${s.budgets} budget${s.budgets === 1 ? '' : 's'}`,
  },
  {
    key: 'portfolio',
    label: 'Portfolio',
    describe: (s) => `${s.holdings} holding${s.holdings === 1 ? '' : 's'}, ${s.price_snapshots} stored price${s.price_snapshots === 1 ? '' : 's'}`,
  },
  {
    key: 'categories',
    label: 'Categories & accounts',
    describe: (s) => `${s.categories} categories, ${s.accounts} account${s.accounts === 1 ? '' : 's'}`,
    note: 'Also clears transactions, rules and budgets, since they all point at a category. The defaults are recreated afterwards.',
  },
]

export default function SettingsPage() {
  const [summary, setSummary] = useState<DataSummary | null>(null)
  const [selected, setSelected] = useState<Set<ResetScope>>(new Set())
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const load = useCallback(() => {
    api.settings
      .dataSummary()
      .then(setSummary)
      .catch((err) => setError(err.message))
  }, [])

  useEffect(load, [load])

  function toggle(scope: ResetScope) {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(scope)) next.delete(scope)
      else next.add(scope)
      return next
    })
    setDone(null)
  }

  // Both gates must be satisfied, and they are independent on purpose: ticking
  // boxes alone cannot delete anything, and typing the phrase alone cannot either.
  const phraseMatches = confirm === PHRASE
  const canReset = selected.size > 0 && phraseMatches && !busy

  async function runReset() {
    if (!canReset) return
    setBusy(true)
    setError(null)
    try {
      const result = await api.settings.reset([...selected], confirm)
      const parts = Object.entries(result.deleted).map(
        ([what, count]) => `${count} ${what.replace(/_/g, ' ')}`,
      )
      setDone(parts.length ? `Deleted ${parts.join(', ')}.` : 'There was nothing to delete.')
      setSelected(new Set())
      setConfirm('')
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Settings</h1>
        <p className="mt-1 text-sm text-muted">
          What is stored, and how to clear it.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-negative">
          {error}
        </p>
      )}

      {summary && (
        <div className="rounded-lg border border-line bg-surface p-4">
          <h2 className="text-sm font-medium">Stored data</h2>
          <dl className="mt-3 grid grid-cols-4 gap-4 text-sm">
            {[
              ['Transactions', summary.transactions],
              ['Recurring rules', summary.recurring_rules],
              ['Budgets', summary.budgets],
              ['Holdings', summary.holdings],
              ['Categories', summary.categories],
              ['Accounts', summary.accounts],
              ['Stored prices', summary.price_snapshots],
              ['Securities', summary.securities],
            ].map(([label, value]) => (
              <div key={label as string}>
                <dt className="text-xs uppercase tracking-wide text-muted">{label}</dt>
                <dd className="tnum mt-0.5 text-lg font-medium">{value}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface p-4">
        <h2 className="text-sm font-medium">Back up first</h2>
        <p className="mt-1 text-sm text-muted">
          Export your transactions before deleting anything — a reset cannot be
          undone. Your holdings and budgets are not included in the export, so
          note those separately if you want them back.
        </p>
        <a
          href={api.reports.exportUrl()}
          download
          className="mt-3 inline-block rounded-md border border-line px-4 py-2 text-sm"
        >
          Export all transactions as CSV
        </a>
      </div>

      <div className="rounded-lg border border-negative/40 bg-surface p-4">
        <h2 className="text-sm font-medium text-negative">Reset data</h2>
        <p className="mt-1 text-sm text-muted">
          Permanently deletes what you select. There is no undo, and no
          confirmation dialog after this — the two steps below are the
          confirmation.
        </p>

        <ul className="mt-4 space-y-3">
          {SCOPES.map((scope) => (
            <li key={scope.key}>
              <label className="flex cursor-pointer items-start gap-3">
                <input
                  type="checkbox"
                  checked={selected.has(scope.key)}
                  onChange={() => toggle(scope.key)}
                  className="mt-1"
                />
                <span className="text-sm">
                  <span className="font-medium">{scope.label}</span>
                  {summary && (
                    <span className="text-muted"> — {scope.describe(summary)}</span>
                  )}
                  {scope.note && (
                    <span className="mt-0.5 block text-xs text-muted">{scope.note}</span>
                  )}
                </span>
              </label>
            </li>
          ))}
        </ul>

        <div className="mt-5 border-t border-line pt-4">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-muted">
              Type <span className="font-mono font-medium text-ink">{PHRASE}</span> to
              enable the button
            </span>
            <input
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder={PHRASE}
              aria-label={`Type ${PHRASE} to confirm`}
              className="w-64 rounded-md border border-line px-3 py-2 font-mono text-sm"
            />
          </label>

          <button
            onClick={runReset}
            disabled={!canReset}
            className="mt-3 rounded-md bg-negative px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? 'Deleting…' : `Delete selected data${selected.size ? ` (${selected.size})` : ''}`}
          </button>

          {selected.size === 0 && phraseMatches && (
            <p className="mt-2 text-xs text-muted">Select at least one item above.</p>
          )}

          {done && (
            <p role="status" className="mt-3 text-sm text-positive">
              {done}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
