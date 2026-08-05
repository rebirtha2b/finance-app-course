import { useEffect } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import BudgetsPage from './pages/BudgetsPage'
import DashboardPage from './pages/DashboardPage'
import PortfolioPage from './pages/PortfolioPage'
import ReportsPage from './pages/ReportsPage'
import ThemeToggle from './components/ThemeToggle'
import { useTheme } from './theme'
import SubscriptionsPage from './pages/SubscriptionsPage'
import TransactionsPage from './pages/TransactionsPage'

const NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/subscriptions', label: 'Subscriptions' },
  { to: '/budgets', label: 'Budgets' },
  { to: '/portfolio', label: 'Portfolio' },
  { to: '/reports', label: 'Reports' },
]

/** Single-key navigation, in the spirit of a keyboard-first tool. */
const SHORTCUTS: Record<string, string> = {
  d: '/dashboard',
  t: '/transactions',
  s: '/subscriptions',
  b: '/budgets',
  p: '/portfolio',
  r: '/reports',
}

export default function App() {
  const navigate = useNavigate()
  const { choice, setChoice } = useTheme()

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Never hijack a key the user is typing into a field, or a browser
      // shortcut like Ctrl+R.
      const target = e.target as HTMLElement | null
      if (
        e.ctrlKey ||
        e.metaKey ||
        e.altKey ||
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.tagName === 'SELECT' ||
        target?.isContentEditable
      ) {
        return
      }
      const destination = SHORTCUTS[e.key.toLowerCase()]
      if (destination) navigate(destination)
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  return (
    <div className="min-h-full">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl items-center gap-8 px-6 py-4">
          <span className="text-base font-semibold tracking-tight">Finance</span>
          <nav className="flex gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm transition-colors ${
                    isActive
                      ? 'bg-accent/10 font-medium text-accent'
                      : 'text-muted hover:bg-canvas hover:text-ink'
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <ThemeToggle choice={choice} onChange={setChoice} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/transactions" element={<TransactionsPage />} />
          <Route path="/subscriptions" element={<SubscriptionsPage />} />
          <Route path="/budgets" element={<BudgetsPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/reports" element={<ReportsPage />} />
        </Routes>
      </main>
    </div>
  )
}
