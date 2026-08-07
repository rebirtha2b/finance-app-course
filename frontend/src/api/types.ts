// Money crosses the wire as a decimal *string* ("-42.50"), never a JSON
// number, because JSON numbers are IEEE doubles in JS and would reintroduce
// the imprecision the backend works to avoid. Keep it a string until the
// moment you format it for display; use the helpers in ./money.ts for maths.

export type CategoryKind = 'income' | 'expense'
export type AccountType = 'cash' | 'bank' | 'broker'

export interface Account {
  id: number
  name: string
  type: AccountType
  currency: string
  opening_balance: string
  archived: boolean
}

export interface Category {
  id: number
  name: string
  kind: CategoryKind
  parent_id: number | null
  icon: string | null
  color: string | null
  archived: boolean
}

export interface CategoryTreeNode extends Category {
  children: Category[]
}

export interface Transaction {
  id: number
  date: string
  amount: string
  account_id: number
  category_id: number
  description: string
  notes: string | null
  recurring_rule_id: number | null
  due_date: string | null
  category_name: string | null
  category_kind: CategoryKind | null
  account_name: string | null
}

export interface TransactionTotals {
  income: string
  expenses: string
  net: string
}

export interface TransactionPage {
  items: Transaction[]
  total: number
  limit: number
  offset: number
  totals: TransactionTotals
}

export interface TransactionFilters {
  from?: string
  to?: string
  category_id?: number
  account_id?: number
  q?: string
  sort?: 'date' | 'amount' | 'description'
  order?: 'asc' | 'desc'
  limit?: number
  offset?: number
}

export interface DataSummary {
  transactions: number
  recurring_rules: number
  budgets: number
  holdings: number
  securities: number
  price_snapshots: number
  categories: number
  accounts: number
}

export type ResetScope =
  | 'transactions'
  | 'recurring'
  | 'budgets'
  | 'portfolio'
  | 'categories'

export interface ResetResult {
  deleted: Record<string, number>
  scopes: string[]
  categories_restored: number
}

export interface CategoryComparison {
  category_id: number
  name: string
  current: string
  previous: string
  change: string
  change_percent: number | null
}

export interface YearSummary {
  year: number
  income: string
  expenses: string
  net: string
  savings_rate: number | null
  months: { month: string; income: string; expenses: string; net: string }[]
}

export interface ImportResult {
  imported: number
  skipped: number
  errors: { row: number; message: string }[]
  preview: Record<string, string>[]
  dry_run: boolean
}

export interface MonthFlow {
  month: string
  income: string
  expenses: string
  net: string
}

export interface CategorySpend {
  category_id: number
  name: string
  color: string | null
  amount: string
  percent: number
}

export interface UpcomingCharge {
  rule_id: number
  name: string
  amount: string
  due_date: string
  days_away: number
  category_name: string | null
}

export interface PortfolioCard {
  total_value: string
  day_change: string
  total_gain: string | null
  total_gain_percent: number | null
  holdings_count: number
  has_stale_prices: boolean
  prices_as_of: string | null
}

export interface Dashboard {
  base_currency: string
  today: string
  net_worth: string
  cash_total: string
  this_month: MonthFlow
  cash_flow: MonthFlow[]
  spending_by_category: CategorySpend[]
  budgets_at_risk: BudgetStatus[]
  portfolio: PortfolioCard
  upcoming: UpcomingCharge[]
}

export interface HoldingValue {
  holding_id: number
  security_id: number
  ticker: string
  name: string
  currency: string
  quantity: string
  price: string | null
  price_date: string | null
  value_native: string | null
  value_base: string | null
  day_change_base: string | null
  day_change_percent: number | null
  cost_basis_base: string | null
  gain_base: string | null
  gain_percent: number | null
  allocation_percent: number
  stale: boolean
}

export interface Portfolio {
  holdings: HoldingValue[]
  total_value_base: string
  total_cost_base: string | null
  total_gain_base: string | null
  total_gain_percent: number | null
  day_change_base: string
  base_currency: string
  prices_as_of: string | null
  has_stale_prices: boolean
  missing_prices: string[]
}

export interface SecurityLookup {
  ticker: string
  name: string
  currency: string
  exchange: string | null
  asset_type: string
}

export interface RefreshResult {
  prices_updated: number
  fx_updated: number
  failed_tickers: string[]
  failed_fx: string[]
  ok: boolean
}

export interface HoldingInput {
  ticker: string
  quantity: string
  avg_cost_price?: string | null
  account_id?: number | null
  notes?: string | null
}

export type BudgetPeriod = 'monthly' | 'yearly'

export interface Budget {
  id: number
  category_id: number
  period: BudgetPeriod
  limit: string
  start_month: string
  rollover: boolean
  active: boolean
  category_name: string | null
}

export interface BudgetStatus {
  budget_id: number
  category_id: number
  category_name: string
  period: BudgetPeriod
  limit: string
  effective_limit: string
  spent: string
  remaining: string
  rollover: string
  percent_used: number
  over_budget: boolean
  window_start: string
  window_end: string
}

export interface BudgetStatusSummary {
  month: string
  items: BudgetStatus[]
  total_limit: string
  total_spent: string
  total_remaining: string
}

export interface BudgetInput {
  category_id: number
  period?: BudgetPeriod
  limit: string
  start_month?: string
  rollover?: boolean
}

export type Frequency = 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'

export interface RecurringRule {
  id: number
  name: string
  amount: string
  category_id: number
  account_id: number
  description: string
  frequency: Frequency
  interval: number
  day_of_month: number | null
  weekday: number | null
  start_date: string
  end_date: string | null
  active: boolean
  last_generated_date: string | null
  category_name: string | null
  account_name: string | null
  monthly_equivalent: string | null
  next_due_date: string | null
}

export interface SubscriptionsSummary {
  items: RecurringRule[]
  total_monthly: string
  total_annual: string
}

export interface RecurringRuleInput {
  name: string
  amount: string
  category_id: number
  account_id: number
  description?: string
  frequency: Frequency
  interval?: number
  day_of_month?: number | null
  start_date: string
  end_date?: string | null
}

export interface TransactionInput {
  date: string
  amount: string
  account_id: number
  category_id: number
  description?: string
  notes?: string | null
}
