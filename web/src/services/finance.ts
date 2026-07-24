import { http } from '@/services/http'
import type {
  Account,
  AccountInput,
  AccountList,
  Budget,
  BudgetInput,
  BudgetList,
  FinanceSummary,
  Holding,
  HoldingInput,
  HoldingList,
  InvestmentTransaction,
  InvestmentTransactionInput,
  InvestmentTransactionList,
  MarketSnapshot,
  MarketSnapshotInput,
  PortfolioSummary,
  Transaction,
  TransactionImportResult,
  TransactionInput,
  TransactionList,
} from '@/types/api'

export interface PageParams {
  page?: number
  page_size?: number
}

export interface TransactionQuery extends PageParams {
  account_id?: string
  transaction_type?: 'income' | 'expense'
  category?: string
  start_date?: string
  end_date?: string
  currency?: string
  search?: string
}

export const financeApi = {
  async listAccounts(includeInactive = false): Promise<AccountList> {
    const response = await http.get<AccountList>('/finance/accounts', {
      params: { include_inactive: includeInactive, page: 1, page_size: 200 },
    })
    return response.data
  },
  async createAccount(payload: AccountInput): Promise<Account> {
    const response = await http.post<Account>('/finance/accounts', payload)
    return response.data
  },
  async updateAccount(
    id: string,
    payload: Partial<Pick<Account, 'name' | 'account_type' | 'is_active'>>,
  ): Promise<Account> {
    const response = await http.patch<Account>(`/finance/accounts/${id}`, payload)
    return response.data
  },
  async archiveAccount(id: string): Promise<void> {
    await http.delete(`/finance/accounts/${id}`)
  },

  async listTransactions(query: TransactionQuery = {}): Promise<TransactionList> {
    const response = await http.get<TransactionList>('/finance/transactions', {
      params: { page: 1, page_size: 50, ...query },
    })
    return response.data
  },
  async createTransaction(payload: TransactionInput): Promise<Transaction> {
    const response = await http.post<Transaction>('/finance/transactions', payload)
    return response.data
  },
  async updateTransaction(id: string, payload: Partial<TransactionInput>): Promise<Transaction> {
    const response = await http.patch<Transaction>(`/finance/transactions/${id}`, payload)
    return response.data
  },
  async deleteTransaction(id: string): Promise<void> {
    await http.delete(`/finance/transactions/${id}`)
  },
  async importTransactions(
    accountId: string,
    file: File,
    strict: boolean,
  ): Promise<TransactionImportResult> {
    const form = new FormData()
    form.append('file', file)
    const response = await http.post<TransactionImportResult>('/finance/transactions/import', form, {
      params: { account_id: accountId, strict },
    })
    return response.data
  },

  async listBudgets(
    query: PageParams & { start_date?: string; end_date?: string; currency?: string } = {},
  ): Promise<BudgetList> {
    const response = await http.get<BudgetList>('/finance/budgets', {
      params: { page: 1, page_size: 200, ...query },
    })
    return response.data
  },
  async createBudget(payload: BudgetInput): Promise<Budget> {
    const response = await http.post<Budget>('/finance/budgets', payload)
    return response.data
  },
  async updateBudget(id: string, payload: Partial<BudgetInput>): Promise<Budget> {
    const response = await http.patch<Budget>(`/finance/budgets/${id}`, payload)
    return response.data
  },
  async deleteBudget(id: string): Promise<void> {
    await http.delete(`/finance/budgets/${id}`)
  },
  async financeSummary(startDate: string, endDate: string, currency: string): Promise<FinanceSummary> {
    const response = await http.get<FinanceSummary>('/finance/reports/summary', {
      params: { start_date: startDate, end_date: endDate, currency },
    })
    return response.data
  },

  async listHoldings(accountId?: string): Promise<HoldingList> {
    const response = await http.get<HoldingList>('/finance/holdings', {
      params: { account_id: accountId, page: 1, page_size: 200 },
    })
    return response.data
  },
  async createHolding(payload: HoldingInput): Promise<Holding> {
    const response = await http.post<Holding>('/finance/holdings', payload)
    return response.data
  },
  async updateHolding(
    id: string,
    payload: Partial<Pick<Holding, 'asset_type' | 'quantity' | 'cost_basis'>>,
  ): Promise<Holding> {
    const response = await http.patch<Holding>(`/finance/holdings/${id}`, payload)
    return response.data
  },
  async deleteHolding(id: string): Promise<void> {
    await http.delete(`/finance/holdings/${id}`)
  },
  async listInvestmentTransactions(holdingId?: string): Promise<InvestmentTransactionList> {
    const response = await http.get<InvestmentTransactionList>(
      '/finance/investment-transactions',
      { params: { holding_id: holdingId, page: 1, page_size: 200 } },
    )
    return response.data
  },
  async createInvestmentTransaction(
    payload: InvestmentTransactionInput,
  ): Promise<InvestmentTransaction> {
    const response = await http.post<InvestmentTransaction>(
      '/finance/investment-transactions',
      payload,
    )
    return response.data
  },
  async createMarketSnapshot(payload: MarketSnapshotInput): Promise<MarketSnapshot> {
    const response = await http.post<MarketSnapshot>('/finance/market-snapshots', payload)
    return response.data
  },
  async latestMarketSnapshot(symbol: string, currency?: string): Promise<MarketSnapshot> {
    const response = await http.get<MarketSnapshot>(
      `/finance/market-snapshots/${encodeURIComponent(symbol)}/latest`,
      { params: { currency } },
    )
    return response.data
  },
  async portfolioSummary(currency: string): Promise<PortfolioSummary> {
    const response = await http.get<PortfolioSummary>('/finance/portfolio/summary', {
      params: { currency },
    })
    return response.data
  },
}
