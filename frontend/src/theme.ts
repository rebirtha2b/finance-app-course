import { useEffect, useState } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'finance-theme'

function systemTheme(): ResolvedTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function storedChoice(): ThemeChoice {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw === 'light' || raw === 'dark' ? raw : 'system'
}

/**
 * Stamp the choice onto <html> so the CSS can react.
 *
 * "system" removes the attribute entirely rather than writing the resolved
 * value, so the `prefers-color-scheme` block stays in charge — that way the
 * app follows the OS if the user changes it later in the session.
 */
export function applyTheme(choice: ThemeChoice): void {
  const root = document.documentElement
  if (choice === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', choice)
}

export function useTheme() {
  const [choice, setChoice] = useState<ThemeChoice>(() => storedChoice())
  const [resolved, setResolved] = useState<ResolvedTheme>(() =>
    storedChoice() === 'system' ? systemTheme() : (storedChoice() as ResolvedTheme),
  )

  useEffect(() => {
    applyTheme(choice)
    localStorage.setItem(STORAGE_KEY, choice)
    setResolved(choice === 'system' ? systemTheme() : choice)
  }, [choice])

  // Follow the OS while the choice is "system", even if it changes mid-session.
  useEffect(() => {
    if (choice !== 'system') return
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setResolved(systemTheme())
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [choice])

  return { choice, setChoice, resolved }
}

/**
 * Chart colours, resolved for the active theme.
 *
 * Charts are drawn by a library into inline SVG attributes, so they cannot
 * inherit CSS custom properties the way the rest of the UI does — the values
 * have to be read in JS. These are the same hexes as the CSS tokens.
 */
export function chartColors(theme: ResolvedTheme) {
  return theme === 'dark'
    ? {
        series1: '#3987e5',
        series2: '#d95926',
        grid: '#2c2c2a',
        axis: '#898781',
        surface: '#1a1a19',
        tooltipText: '#ffffff',
        cursor: 'rgba(255,255,255,0.06)',
      }
    : {
        series1: '#2a78d6',
        series2: '#eb6834',
        grid: '#e1e0d9',
        axis: '#898781',
        surface: '#ffffff',
        tooltipText: '#0b0b0b',
        cursor: 'rgba(11,11,11,0.04)',
      }
}
