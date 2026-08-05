import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/client'
import { formatDate, formatMoney } from '../api/money'
import type { Portfolio, SecurityLookup } from '../api/types'

function formatQuantity(q: string): string {
  // Trim trailing zeros so whole-share holdings don't read "10.00000000".
  const n = Number(q)
  return Number.isInteger(n) ? String(n) : q.replace(/0+$/, '').replace(/\.$/, '')
}

function signedClass(value: string | number | null): string {
  if (value === null) return ''
  return Number(value) < 0 ? 'text-negative' : 'text-positive'
}

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)

  const [ticker, setTicker] = useState('')
  const [quantity, setQuantity] = useState('')
  const [avgCost, setAvgCost] = useState('')
  const [lookup, setLookup] = useState<SecurityLookup | null>(null)
  const [lookupError, setLookupError] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    api.portfolio
      .get()
      .then(setPortfolio)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(load, [load])

  async function checkTicker() {
    setLookup(null)
    setLookupError(null)
    if (!ticker.trim()) return
    try {
      setLookup(await api.portfolio.lookup(ticker.trim()))
    } catch (err) {
      setLookupError(err instanceof Error ? err.message : 'Lookup failed')
    }
  }

  async function addHolding(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const qty = quantity.trim().replace(',', '.')
    if (!/^\d*\.?\d+$/.test(qty) || Number(qty) <= 0) {
      return setError('Enter a number of shares greater than zero')
    }

    setAdding(true)
    try {
      await api.portfolio.addHolding({
        ticker: ticker.trim(),
        quantity: qty,
        avg_cost_price: avgCost.trim() ? avgCost.trim().replace(',', '.') : null,
      })
      setTicker('')
      setQuantity('')
      setAvgCost('')
      setLookup(null)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add holding')
    } finally {
      setAdding(false)
    }
  }

  async function refresh() {
    setRefreshing(true)
    setNotice(null)
    setError(null)
    try {
      const result = await api.portfolio.refresh()
      if (result.ok) {
        setNotice(`Updated ${result.prices_updated} price(s).`)
      } else {
        // A partial failure is worth saying out loud, but it is not an error
        // state — the last known prices are still on screen.
        setNotice(
          `Updated ${result.prices_updated} price(s). No fresh data for ${result.failed_tickers.join(', ')} — showing the last known price.`,
        )
      }
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Refresh failed')
    } finally {
      setRefreshing(false)
    }
  }

  async function remove(id: number) {
    try {
      await api.portfolio.removeHolding(id)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not remove')
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold">Portfolio</h1>
          <p className="mt-1 text-sm text-muted">
            Enter the number of shares you own; prices update automatically to the
            latest daily close.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={refreshing}
          className="rounded-md border border-line px-4 py-2 text-sm disabled:opacity-50"
        >
          {refreshing ? 'Refreshing…' : 'Refresh prices'}
        </button>
      </div>

      {portfolio && portfolio.has_stale_prices && (
        <div className="rounded-lg border border-warn-line bg-warn-surface px-4 py-3 text-sm text-warn-ink">
          {portfolio.missing_prices.length > 0 ? (
            <>
              No price data yet for{' '}
              <strong>{portfolio.missing_prices.join(', ')}</strong>. Values exclude
              these holdings.
            </>
          ) : (
            <>
              Some prices are older than others. Showing the most recent close
              available for each holding
              {portfolio.prices_as_of && <> — oldest is {formatDate(portfolio.prices_as_of)}</>}
              .
            </>
          )}
        </div>
      )}

      {notice && (
        <div className="rounded-lg border border-line bg-surface px-4 py-3 text-sm text-muted">
          {notice}
        </div>
      )}
      {error && (
        <p role="alert" className="text-sm text-negative">
          {error}
        </p>
      )}

      {portfolio && (
        <div className="grid grid-cols-3 gap-4">
          <Stat label="Total value" value={formatMoney(portfolio.total_value_base)} />
          <Stat
            label="Day change"
            value={formatMoney(portfolio.day_change_base)}
            tone={signedClass(portfolio.day_change_base)}
          />
          <Stat
            label="Total gain"
            value={
              portfolio.total_gain_base !== null
                ? `${formatMoney(portfolio.total_gain_base)}${
                    portfolio.total_gain_percent !== null
                      ? ` (${portfolio.total_gain_percent.toFixed(1)}%)`
                      : ''
                  }`
                : '—'
            }
            tone={signedClass(portfolio.total_gain_base)}
            hint={portfolio.total_gain_base === null ? 'Add an average cost to track gains' : undefined}
          />
        </div>
      )}

      <form
        onSubmit={addHolding}
        className="flex flex-wrap items-end gap-3 rounded-lg border border-line bg-surface p-4"
      >
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted">Ticker</span>
          <input
            value={ticker}
            onChange={(e) => {
              setTicker(e.target.value.toUpperCase())
              setLookup(null)
              setLookupError(null)
            }}
            onBlur={checkTicker}
            placeholder="AAPL or SAP.DE"
            className="w-36 rounded-md border border-line px-3 py-2 text-sm uppercase"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted">Shares</span>
          <input
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            inputMode="decimal"
            placeholder="10"
            className="tnum w-24 rounded-md border border-line px-3 py-2 text-right text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted">
            Avg cost per share{lookup ? ` in ${lookup.currency}` : ''} (optional)
          </span>
          <input
            value={avgCost}
            onChange={(e) => setAvgCost(e.target.value)}
            inputMode="decimal"
            placeholder="—"
            className="tnum w-28 rounded-md border border-line px-3 py-2 text-right text-sm"
          />
        </div>
        <button
          type="submit"
          disabled={adding}
          className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-accent-ink disabled:opacity-50"
        >
          {adding ? 'Adding…' : 'Add holding'}
        </button>

        {lookup && (
          <p className="w-full text-xs text-positive">
            ✓ {lookup.name} · {lookup.currency}
            {lookup.exchange && ` · ${lookup.exchange}`}
          </p>
        )}
        {lookupError && <p className="w-full text-xs text-negative">{lookupError}</p>}
      </form>

      <div className="overflow-x-auto rounded-lg border border-line bg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <th className="px-4 py-2 font-medium">Ticker</th>
              <th className="px-4 py-2 text-right font-medium">Shares</th>
              <th className="px-4 py-2 text-right font-medium">Last close</th>
              <th className="px-4 py-2 text-right font-medium">Value</th>
              <th className="px-4 py-2 text-right font-medium">Day</th>
              <th className="px-4 py-2 text-right font-medium">Gain / loss</th>
              <th className="px-4 py-2 text-right font-medium">Weight</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={8} className="p-8 text-center text-muted">
                  Loading…
                </td>
              </tr>
            )}

            {!loading && portfolio?.holdings.length === 0 && (
              <tr>
                <td colSpan={8} className="p-8 text-center text-muted">
                  No holdings yet. Add a ticker and the number of shares you own.
                </td>
              </tr>
            )}

            {!loading &&
              portfolio?.holdings.map((h) => (
                <tr key={h.holding_id} className="border-b border-line last:border-0">
                  <td className="px-4 py-2">
                    <div className="font-medium">{h.ticker}</div>
                    <div className="text-xs text-muted">{h.name}</div>
                  </td>
                  <td className="tnum px-4 py-2 text-right">
                    {formatQuantity(h.quantity)}
                  </td>
                  <td className="tnum px-4 py-2 text-right">
                    {h.price ? (
                      <>
                        <div>
                          {h.price} {h.currency}
                        </div>
                        {h.price_date && (
                          <div
                            className={`text-xs ${h.stale ? 'text-warn-mark' : 'text-muted'}`}
                          >
                            {formatDate(h.price_date)}
                          </div>
                        )}
                      </>
                    ) : (
                      <span className="text-muted">no price</span>
                    )}
                  </td>
                  <td className="tnum px-4 py-2 text-right font-medium">
                    {h.value_base ? formatMoney(h.value_base) : '—'}
                  </td>
                  <td className={`tnum px-4 py-2 text-right ${signedClass(h.day_change_base)}`}>
                    {h.day_change_base ? formatMoney(h.day_change_base) : '—'}
                  </td>
                  <td className={`tnum px-4 py-2 text-right ${signedClass(h.gain_base)}`}>
                    {h.gain_base !== null ? (
                      <>
                        <div>{formatMoney(h.gain_base)}</div>
                        {h.gain_percent !== null && (
                          <div className="text-xs">{h.gain_percent.toFixed(1)}%</div>
                        )}
                      </>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="tnum px-4 py-2 text-right text-muted">
                    {h.allocation_percent.toFixed(1)}%
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => remove(h.holding_id)}
                      className="text-xs text-muted hover:text-negative"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Stat({
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
      <p className={`tnum mt-1 text-2xl font-semibold ${tone}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  )
}
