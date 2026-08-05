import type { CategoryTreeNode } from '../api/types'

interface Props {
  tree: CategoryTreeNode[]
  value: number | ''
  onChange: (id: number | '') => void
  includeAllOption?: boolean
  id?: string
  className?: string
}

/**
 * Grouped category picker. Parents that have children appear as the optgroup
 * label *and* as a selectable option, because "Food" with no sub-category is a
 * legitimate choice — grouping alone would make the parent unselectable.
 */
export default function CategorySelect({
  tree,
  value,
  onChange,
  includeAllOption,
  id,
  className = '',
}: Props) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
      className={`rounded-md border border-line bg-surface px-3 py-2 text-sm ${className}`}
    >
      {includeAllOption && <option value="">All categories</option>}
      {!includeAllOption && <option value="">Select category…</option>}
      {tree.map((parent) =>
        parent.children.length > 0 ? (
          <optgroup key={parent.id} label={parent.name}>
            <option value={parent.id}>{parent.name} (general)</option>
            {parent.children.map((child) => (
              <option key={child.id} value={child.id}>
                {child.name}
              </option>
            ))}
          </optgroup>
        ) : (
          <option key={parent.id} value={parent.id}>
            {parent.name}
          </option>
        ),
      )}
    </select>
  )
}
