import { useState } from 'react'
import { api } from '../api/client'
import type { Account, Category, ImportResult } from '../api/types'

interface Props {
  accounts: Account[]
  categories: Category[]
  onImported: () => void
}

const FIELDS: { key: string; label: string; required?: boolean }[] = [
  { key: 'date', label: 'Date', required: true },
  { key: 'amount', label: 'Amount', required: true },
  { key: 'description', label: 'Description' },
  { key: 'category', label: 'Category' },
  { key: 'account', label: 'Account' },
  { key: 'notes', label: 'Notes' },
]

/** Guess a mapping from common header names so the usual case needs no work. */
function guessMapping(columns: string[]): Record<string, string> {
  const guesses: Record<string, string[]> = {
    date: ['date', 'datum', 'buchungstag', 'valuta', 'transaction date'],
    amount: ['amount', 'betrag', 'value', 'sum', 'umsatz'],
    description: ['description', 'verwendungszweck', 'text', 'payee', 'memo', 'name'],
    category: ['category', 'kategorie'],
    account: ['account', 'konto'],
    notes: ['notes', 'notiz', 'comment'],
  }
  const mapping: Record<string, string> = {}
  for (const [field, candidates] of Object.entries(guesses)) {
    const hit = columns.find((c) => candidates.includes(c.trim().toLowerCase()))
    if (hit) mapping[field] = hit
  }
  return mapping
}

export default function CsvImport({ accounts, categories, onImported }: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [columns, setColumns] = useState<string[]>([])
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [accountId, setAccountId] = useState<number>(accounts[0]?.id ?? 0)
  const [categoryId, setCategoryId] = useState<number>(0)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const expenseCategories = categories.filter((c) => c.kind === 'expense')

  async function pickFile(picked: File | null) {
    setFile(picked)
    setResult(null)
    setError(null)
    if (!picked) return
    try {
      const { columns } = await api.reports.detectColumns(picked)
      setColumns(columns)
      setMapping(guessMapping(columns))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read the file')
    }
  }

  async function run(dryRun: boolean) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      setResult(
        await api.reports.importCsv(
          file,
          mapping,
          accountId,
          categoryId || expenseCategories[0]?.id,
          dryRun,
        ),
      )
      if (!dryRun) onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-lg border border-line bg-surface p-4">
      <h2 className="text-sm font-medium">Import from CSV</h2>
      <p className="mt-1 text-xs text-muted">
        Works with bank exports. Amounts may use either "1.234,56" or "1,234.56";
        dates may be ISO or day-first. Nothing is written until you confirm.
      </p>

      <input
        type="file"
        accept=".csv,text/csv"
        onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
        className="mt-3 block text-sm"
      />

      {columns.length > 0 && (
        <>
          <div className="mt-4 grid grid-cols-3 gap-3">
            {FIELDS.map((f) => (
              <label key={f.key} className="flex flex-col gap-1">
                <span className="text-xs text-muted">
                  {f.label}
                  {f.required && <span className="text-negative"> *</span>}
                </span>
                <select
                  value={mapping[f.key] ?? ''}
                  onChange={(e) =>
                    setMapping((m) => {
                      const next = { ...m }
                      if (e.target.value) next[f.key] = e.target.value
                      else delete next[f.key]
                      return next
                    })
                  }
                  className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
                >
                  <option value="">— not in file —</option>
                  {columns.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>

          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Account for unmatched rows</span>
              <select
                value={accountId}
                onChange={(e) => setAccountId(Number(e.target.value))}
                className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                {accounts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-muted">Category for unmatched rows</span>
              <select
                value={categoryId}
                onChange={(e) => setCategoryId(Number(e.target.value))}
                className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm"
              >
                <option value={0}>Other expenses</option>
                {expenseCategories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>

            <button
              onClick={() => run(true)}
              disabled={busy || !mapping.date || !mapping.amount}
              className="rounded-md border border-line px-4 py-2 text-sm disabled:opacity-50"
            >
              Preview
            </button>
            <button
              onClick={() => run(false)}
              disabled={busy || !result || result.imported === 0}
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
            >
              Import {result?.dry_run ? `${result.imported} rows` : ''}
            </button>
          </div>
        </>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-negative">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 space-y-3 text-sm">
          <p className={result.dry_run ? 'text-muted' : 'text-positive'}>
            {result.dry_run
              ? `${result.imported} row(s) ready to import`
              : `Imported ${result.imported} transaction(s)`}
            {result.errors.length > 0 && ` · ${result.errors.length} row(s) with problems`}
          </p>

          {result.errors.length > 0 && (
            <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md bg-canvas p-3 text-xs">
              {result.errors.map((e, i) => (
                <li key={i} className="text-negative">
                  Row {e.row}: {e.message}
                </li>
              ))}
            </ul>
          )}

          {result.dry_run && result.preview.length > 0 && (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line text-left uppercase text-muted">
                  <th className="py-1 font-medium">Date</th>
                  <th className="py-1 text-right font-medium">Amount</th>
                  <th className="py-1 font-medium">Description</th>
                  <th className="py-1 font-medium">Category</th>
                </tr>
              </thead>
              <tbody>
                {result.preview.map((p, i) => (
                  <tr key={i} className="border-b border-line last:border-0">
                    <td className="tnum py-1">{p.date}</td>
                    <td className="tnum py-1 text-right">{p.amount}</td>
                    <td className="py-1">{p.description}</td>
                    <td className="py-1 text-muted">{p.category}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
