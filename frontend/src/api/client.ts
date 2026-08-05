import type {
  Account,
  Budget,
  BudgetInput,
  BudgetStatusSummary,
  Category,
  CategoryComparison,
  CategoryTreeNode,
  Dashboard,
  ImportResult,
  YearSummary,
  HoldingInput,
  HoldingValue,
  Portfolio,
  RefreshResult,
  SecurityLookup,
  RecurringRule,
  RecurringRuleInput,
  SubscriptionsSummary,
  Transaction,
  TransactionFilters,
  TransactionInput,
  TransactionPage,
} from './types'

export class ApiError extends Error {
  // Declared as a field rather than a constructor parameter property, which
  // `erasableSyntaxOnly` disallows.
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

  if (!response.ok) {
    // FastAPI puts a plain message in `detail` for HTTPException, and an array
    // of field errors there for validation failures. Surface both usefully.
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') {
        message = body.detail
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((e: { loc: string[]; msg: string }) =>
            `${e.loc.at(-1)}: ${e.msg}`,
          )
          .join(', ')
      }
    } catch {
      // Non-JSON error body; keep the generic message.
    }
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

// `object` rather than Record<string, unknown> so plain interfaces (which have
// no index signature) can be passed directly.
function query(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value))
    }
  }
  const s = search.toString()
  return s ? `?${s}` : ''
}

export const api = {
  health: () => request<{ status: string; counts: Record<string, number> }>('/api/health'),

  dashboard: () => request<Dashboard>('/api/dashboard'),

  accounts: {
    list: () => request<Account[]>('/api/accounts'),
  },

  categories: {
    list: (includeArchived = false) =>
      request<Category[]>(`/api/categories${query({ include_archived: includeArchived })}`),
    tree: (kind?: 'income' | 'expense') =>
      request<CategoryTreeNode[]>(`/api/categories/tree${query({ kind })}`),
  },

  transactions: {
    list: (filters: TransactionFilters = {}) =>
      request<TransactionPage>(`/api/transactions${query(filters)}`),
    create: (input: TransactionInput) =>
      request<Transaction>('/api/transactions', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    update: (id: number, input: Partial<TransactionInput>) =>
      request<Transaction>(`/api/transactions/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    remove: (id: number) =>
      request<void>(`/api/transactions/${id}`, { method: 'DELETE' }),
  },

  recurring: {
    list: () => request<RecurringRule[]>('/api/recurring'),
    create: (input: RecurringRuleInput) =>
      request<RecurringRule>('/api/recurring', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    update: (id: number, input: Partial<RecurringRuleInput & { active: boolean }>) =>
      request<RecurringRule>(`/api/recurring/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    remove: (id: number, deleteTransactions = false) =>
      request<void>(
        `/api/recurring/${id}${query({ delete_transactions: deleteTransactions })}`,
        { method: 'DELETE' },
      ),
    generate: () =>
      request<{ created: number; rules_processed: number }>(
        '/api/recurring/generate',
        { method: 'POST' },
      ),
  },

  subscriptions: {
    get: () => request<SubscriptionsSummary>('/api/subscriptions'),
  },

  budgets: {
    list: () => request<Budget[]>('/api/budgets'),
    status: (month?: string) =>
      request<BudgetStatusSummary>(`/api/budgets/status${query({ month })}`),
    create: (input: BudgetInput) =>
      request<Budget>('/api/budgets', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    update: (id: number, input: Partial<BudgetInput & { active: boolean }>) =>
      request<Budget>(`/api/budgets/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    remove: (id: number) => request<void>(`/api/budgets/${id}`, { method: 'DELETE' }),
  },

  portfolio: {
    get: () => request<Portfolio>('/api/portfolio'),
    refresh: () =>
      request<RefreshResult>('/api/portfolio/refresh', { method: 'POST' }),
    history: () =>
      request<{ date: string; total_value: string; total_cost: string | null }[]>(
        '/api/portfolio/history',
      ),
    lookup: (ticker: string) =>
      request<SecurityLookup>(`/api/securities/lookup${query({ ticker })}`),
    addHolding: (input: HoldingInput) =>
      request<HoldingValue>('/api/holdings', {
        method: 'POST',
        body: JSON.stringify(input),
      }),
    updateHolding: (id: number, input: Partial<HoldingInput>) =>
      request<HoldingValue>(`/api/holdings/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(input),
      }),
    removeHolding: (id: number) =>
      request<void>(`/api/holdings/${id}`, { method: 'DELETE' }),
  },

  reports: {
    exportUrl: (from?: string, to?: string) =>
      `/api/reports/export.csv${query({ from, to })}`,
    monthOverMonth: (month?: string) =>
      request<CategoryComparison[]>(
        `/api/reports/month-over-month${query({ month })}`,
      ),
    yearOverYear: (year?: number) =>
      request<CategoryComparison[]>(`/api/reports/year-over-year${query({ year })}`),
    yearly: (year?: number) =>
      request<YearSummary>(`/api/reports/yearly${query({ year })}`),

    detectColumns: async (file: File) => {
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch('/api/reports/columns', { method: 'POST', body: form })
      if (!resp.ok) throw new ApiError('Could not read the file', resp.status)
      return resp.json() as Promise<{ columns: string[]; delimiter: string }>
    },

    importCsv: async (
      file: File,
      mapping: Record<string, string>,
      defaultAccountId: number,
      defaultCategoryId: number,
      dryRun: boolean,
    ) => {
      const form = new FormData()
      form.append('file', file)
      form.append('mapping', JSON.stringify(mapping))
      form.append('default_account_id', String(defaultAccountId))
      form.append('default_category_id', String(defaultCategoryId))
      form.append('dry_run', String(dryRun))
      // No Content-Type header: the browser must set the multipart boundary.
      const resp = await fetch('/api/reports/import', { method: 'POST', body: form })
      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}))
        throw new ApiError(body.detail ?? 'Import failed', resp.status)
      }
      return resp.json() as Promise<ImportResult>
    },
  },
}
