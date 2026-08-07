import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { parseAmountInput, today } from '../api/money'
import type { Account, CategoryTreeNode, Transaction } from '../api/types'
import CategorySelect from './CategorySelect'

interface Props {
  accounts: Account[]
  expenseTree: CategoryTreeNode[]
  incomeTree: CategoryTreeNode[]
  // Receives the saved transaction so the page can react to its date — a
  // back-dated entry may fall outside the list's current filter.
  onAdded: (created: Transaction) => void
}

type Direction = 'expense' | 'income'

export default function QuickAdd({ accounts, expenseTree, incomeTree, onAdded }: Props) {
  const [direction, setDirection] = useState<Direction>('expense')
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(today())
  const [categoryId, setCategoryId] = useState<number | ''>('')
  const [accountId, setAccountId] = useState<number | ''>('')
  const [description, setDescription] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const amountRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    amountRef.current?.focus()
  }, [])

  useEffect(() => {
    if (accountId === '' && accounts.length > 0) setAccountId(accounts[0].id)
  }, [accounts, accountId])

  // The category list depends on the direction, so a stale selection from the
  // other list must not survive the toggle.
  useEffect(() => {
    setCategoryId('')
  }, [direction])

  const tree = direction === 'expense' ? expenseTree : incomeTree

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    const parsed = parseAmountInput(amount)
    if (parsed === null) {
      setError('Enter an amount, e.g. 12,34')
      amountRef.current?.focus()
      return
    }
    if (categoryId === '') {
      setError('Pick a category')
      return
    }
    if (accountId === '') {
      setError('Pick an account')
      return
    }

    // The user types a magnitude; the toggle decides the sign. Typing an
    // explicit minus for a refund on an expense category still works.
    const magnitude = parsed.replace('-', '')
    const signed =
      direction === 'expense'
        ? parsed.startsWith('-')
          ? magnitude // "-" on an expense means a refund: keep it positive
          : `-${magnitude}`
        : parsed

    setSaving(true)
    try {
      const created = await api.transactions.create({
        date,
        amount: signed,
        account_id: accountId,
        category_id: categoryId,
        description,
      })
      setAmount('')
      setDescription('')
      amountRef.current?.focus()
      onAdded(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="rounded-lg border border-line bg-surface p-4"
      aria-label="Quick add transaction"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex rounded-md border border-line p-0.5">
          {(['expense', 'income'] as Direction[]).map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDirection(d)}
              aria-pressed={direction === d}
              className={`rounded px-3 py-1.5 text-sm capitalize transition-colors ${
                direction === d
                  ? 'bg-accent text-accent-ink'
                  : 'text-muted hover:text-ink'
              }`}
            >
              {d}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="qa-amount" className="text-xs text-muted">
            Amount
          </label>
          <input
            id="qa-amount"
            ref={amountRef}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            inputMode="decimal"
            placeholder="0,00"
            className="tnum w-32 rounded-md border border-line px-3 py-2 text-right text-sm"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="qa-date" className="text-xs text-muted">
            Date
          </label>
          <input
            id="qa-date"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-md border border-line px-3 py-2 text-sm"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="qa-category" className="text-xs text-muted">
            Category
          </label>
          <CategorySelect
            id="qa-category"
            tree={tree}
            value={categoryId}
            onChange={setCategoryId}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="qa-account" className="text-xs text-muted">
            Account
          </label>
          <select
            id="qa-account"
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
        </div>

        <div className="flex min-w-40 flex-1 flex-col gap-1">
          <label htmlFor="qa-desc" className="text-xs text-muted">
            Description
          </label>
          <input
            id="qa-desc"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Optional"
            className="rounded-md border border-line px-3 py-2 text-sm"
          />
        </div>

        <button
          type="submit"
          disabled={saving}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          {saving ? 'Saving…' : 'Add'}
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      )}
    </form>
  )
}
