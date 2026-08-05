import type { ThemeChoice } from '../theme'

const OPTIONS: { value: ThemeChoice; label: string; icon: string }[] = [
  { value: 'light', label: 'Light', icon: '☀' },
  { value: 'dark', label: 'Dark', icon: '☾' },
  { value: 'system', label: 'Match system', icon: '⌂' },
]

interface Props {
  choice: ThemeChoice
  onChange: (choice: ThemeChoice) => void
}

export default function ThemeToggle({ choice, onChange }: Props) {
  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="flex rounded-md border border-line p-0.5"
    >
      {OPTIONS.map((option) => (
        <button
          key={option.value}
          role="radio"
          aria-checked={choice === option.value}
          // The icon is decorative; the accessible name comes from the title
          // and aria-label, never from the glyph alone.
          title={option.label}
          aria-label={option.label}
          onClick={() => onChange(option.value)}
          className={`rounded px-2 py-1 text-xs transition-colors ${
            choice === option.value
              ? 'bg-accent text-accent-ink'
              : 'text-muted hover:text-ink'
          }`}
        >
          {option.icon}
        </button>
      ))}
    </div>
  )
}
