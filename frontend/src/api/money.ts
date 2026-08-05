// Formatting and light arithmetic on the decimal strings the API returns.
//
// Anything that needs to be exact happens on the backend in integer cents.
// Here we only ever format for display or compare, so parsing to a number at
// the last moment is safe — but never round-trip a parsed value back to the
// API, send the user's original string.

const eur = new Intl.NumberFormat('de-DE', {
  style: 'currency',
  currency: 'EUR',
})

export function formatMoney(amount: string | number): string {
  return eur.format(typeof amount === 'string' ? Number(amount) : amount)
}

/** Absolute value, formatted — for showing expenses without the minus sign. */
export function formatAbs(amount: string): string {
  return eur.format(Math.abs(Number(amount)))
}

export function isNegative(amount: string): boolean {
  return Number(amount) < 0
}

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}

export function today(): string {
  // Local date, not UTC: `toISOString()` would roll over to tomorrow for
  // anyone east of Greenwich late in the evening.
  const now = new Date()
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

export function startOfMonth(iso = today()): string {
  return `${iso.slice(0, 7)}-01`
}

/**
 * Parse a user-typed amount into a canonical decimal string.
 * Accepts German-style "12,34" as well as "12.34", and strips spaces and
 * thousands separators. Returns null if it isn't a usable number.
 */
export function parseAmountInput(raw: string): string | null {
  const cleaned = raw.trim().replace(/\s/g, '').replace(/\./g, (match, offset, str) => {
    // A dot is a thousands separator only when a comma appears later.
    return str.includes(',', offset) ? '' : match
  })
  const normalised = cleaned.replace(',', '.')
  if (!/^-?\d*\.?\d+$/.test(normalised)) return null
  const value = Number(normalised)
  if (!Number.isFinite(value) || value === 0) return null
  return normalised
}
