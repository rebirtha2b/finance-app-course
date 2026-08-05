import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { parseAmountInput, today } from '../api/money'
import type { Account, CategoryTreeNode, Frequency } from '../api/types'
import CategorySelect from './CategorySelect'

interface Props {
  accounts: Account[]
  expenseTree: CategoryTreeNode[]
  onCreated: () => void
  onCancel: () => void
}

const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'daily', label: 'Daily' },
]

export default function RecurringForm({
  accounts,
  expenseTree,
  onCreated,
  onCancel,
}: Props) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [frequency, setFrequency] = useState<Frequency>('monthly')
  const [dayOfMonth, setDayOfMonth] = useState('1')
  const [startDate, setStartDate] = useState(today())
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [accountId, setAccountId] = useState<number | ''>('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (accountId === '' && accounts.length > 0) setAccountId(accounts[0].id)
  }, [accounts, accountId])

  const usesDayOfMonth = ['monthly', 'quarterly', 'yearly'].includes(frequency)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    const parsed = parseAmountInput(amount)
    if (parsed === null) return setError('Enter an amount, e.g. 12,99')
    if (!name.trim()) return setError('Give it a name')
    if (categoryId === '') return setError('Pick a category')
    if (accountId === '') return setError('Pick an account')

    setSaving(true)
    try {
      await api.recurring.create({
        name: name.trim(),
        // Recurring costs are always entered as a magnitude and stored as an
        // expense; this form only creates outgoings.
        amount: `-${parsed.replace('-', '')}`,
        category_id: categoryId,
        account_id: accountId,
        frequency,
        start_date: startDate,
        day_of_month: usesDayOfMonth ? Number(dayOfMonth) : null,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="rounded-lg border border-line bg-surface p-4">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Name">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Netflix"
            autoFocus
            className="w-40 rounded-md border border-line px-3 py-2 text-sm"
          />
        </Field>

        <Field label="Amount">
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            inputMode="decimal"
            placeholder="12,99"
            className="tnum w-28 rounded-md border border-line px-3 py-2 text-right text-sm"
          />
        </Field>

        <Field label="Frequency">
          <select
            value={frequency}
            onChange={(e) => setFrequency(e.target.value as Frequency)}
            className="rounded-md border border-line bg-surface px-3 py-2 text-sm"
          >
            {FREQUENCIES.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
        </Field>

        {usesDayOfMonth && (
          <Field label="Day">
            <input
              type="number"
              min={1}
              max={31}
              value={dayOfMonth}
              onChange={(e) => setDayOfMonth(e.target.value)}
              className="tnum w-20 rounded-md border border-line px-3 py-2 text-sm"
            />
          </Field>
        )}

        <Field label="Starts">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="rounded-md border border-line px-3 py-2 text-sm"
          />
        </Field>

        <Field label="Category">
          <CategorySelect
            tree={expenseTree}
            value={categoryId}
            onChange={setCategoryId}
          />
        </Field>

        <Field label="Account">
          <select
            value={accountId}
            onChange={(e) => setAccountId(Number(e.target.value))}
            className="rounded-md border border-line bg-surface px-3 py-2 text-sm"
          >
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </Field>

        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Create'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md border border-line px-4 py-2 text-sm text-muted"
        >
          Cancel
        </button>
      </div>

      {usesDayOfMonth && Number(dayOfMonth) > 28 && (
        <p className="mt-3 text-xs text-muted">
          Day {dayOfMonth} falls back to the last day in shorter months, then returns
          to the {dayOfMonth}
          {'th'} — it never drifts.
        </p>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      )}
    </form>
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
