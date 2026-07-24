export type MoneyValue = string | number

export type AccountType =
  | 'cash'
  | 'checking'
  | 'savings'
  | 'credit'
  | 'investment'
  | 'other'

export type TransactionType = 'income' | 'expense'
export type BudgetPeriod = 'monthly' | 'quarterly' | 'yearly' | 'custom'
export type AssetType = 'stock' | 'fund' | 'etf' | 'bond' | 'deposit' | 'crypto' | 'other'
export type InvestmentTransactionType = 'buy' | 'sell'
export type UserRole = 'admin' | 'user'
export type UserStatus = 'active' | 'disabled'

export interface PageResponse {
  page: number
  page_size: number
  total: number
}

export interface User {
  id: string
  username: string
  email: string
  role: UserRole
  status: UserStatus
  must_change_password: boolean
  password_changed_at: string | null
  created_at: string
  updated_at: string
}

export interface AuthTokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  refresh_expires_in: number
  must_change_password: boolean
}

export interface Account {
  id: string
  name: string
  account_type: AccountType
  currency: string
  balance: MoneyValue
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface AccountList extends PageResponse {
  items: Account[]
}

export interface AccountInput {
  name: string
  account_type: AccountType
  currency: string
  opening_balance: number
}

export interface Transaction {
  id: string
  account_id: string
  transaction_type: TransactionType
  amount: MoneyValue
  currency: string
  category: string
  description: string | null
  transaction_date: string
  source: string
  created_at: string
  updated_at: string
}

export interface TransactionList extends PageResponse {
  items: Transaction[]
}

export interface TransactionInput {
  account_id: string
  transaction_type: TransactionType
  amount: number
  currency: string
  category: string
  description?: string | null
  transaction_date: string
  source?: string
}

export interface ImportErrorItem {
  row: number
  field: string | null
  message: string
}

export interface TransactionImportResult {
  total_rows: number
  imported_rows: number
  skipped_rows: number
  errors: ImportErrorItem[]
  committed: boolean
}

export interface Budget {
  id: string
  category: string
  period: BudgetPeriod
  amount: MoneyValue
  currency: string
  start_date: string
  end_date: string
  created_at: string
  updated_at: string
}

export interface BudgetList extends PageResponse {
  items: Budget[]
}

export interface BudgetInput {
  category: string
  period: BudgetPeriod
  amount: number
  currency: string
  start_date: string
  end_date: string
}

export interface BudgetExecution {
  budget_id: string
  category: string
  budget_amount: MoneyValue
  spent_amount: MoneyValue
  remaining_amount: MoneyValue
  utilization_percent: MoneyValue
}

export interface FinanceSummary {
  start_date: string
  end_date: string
  currency: string
  income: MoneyValue
  expense: MoneyValue
  net_cash_flow: MoneyValue
  account_balance: MoneyValue
  budget_amount: MoneyValue
  budget_spent: MoneyValue
  budget_remaining: MoneyValue
  budgets: BudgetExecution[]
  data_as_of: string
}

export interface Holding {
  id: string
  account_id: string
  symbol: string
  asset_type: AssetType
  quantity: MoneyValue
  cost_basis: MoneyValue
  currency: string
  created_at: string
  updated_at: string
}

export interface HoldingList extends PageResponse {
  items: Holding[]
}

export interface HoldingInput {
  account_id: string
  symbol: string
  asset_type: AssetType
  quantity: number
  cost_basis: number
  currency: string
}

export interface InvestmentTransaction {
  id: string
  holding_id: string
  transaction_type: InvestmentTransactionType
  quantity: MoneyValue
  price: MoneyValue
  fee: MoneyValue
  realized_gain: MoneyValue
  currency: string
  transaction_at: string
}

export interface InvestmentTransactionList extends PageResponse {
  items: InvestmentTransaction[]
}

export interface InvestmentTransactionInput {
  holding_id: string
  transaction_type: InvestmentTransactionType
  quantity: number
  price: number
  fee: number
  currency: string
  transaction_at: string
}

export interface MarketSnapshot {
  id: string
  symbol: string
  asset_type: AssetType
  price: MoneyValue
  currency: string
  recorded_at: string
  data_source: string
}

export interface MarketSnapshotInput {
  symbol: string
  asset_type: AssetType
  price: number
  currency: string
  recorded_at: string
  data_source: string
}

export interface HoldingPerformance {
  holding_id: string
  symbol: string
  quantity: MoneyValue
  cost_basis: MoneyValue
  cost_value: MoneyValue
  current_price: MoneyValue | null
  market_value: MoneyValue | null
  unrealized_gain: MoneyValue | null
  price_recorded_at: string | null
}

export interface PortfolioSummary {
  currency: string
  total_cost_value: MoneyValue
  total_market_value: MoneyValue | null
  total_unrealized_gain: MoneyValue | null
  holdings: HoldingPerformance[]
  data_as_of: string
}

export interface ApiErrorPayload {
  error?: {
    code?: string
    message?: string
    request_id?: string | null
  }
  detail?: string
  details?: unknown[]
}
