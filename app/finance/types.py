"""API 模型与应用服务共享的有限财务领域取值。"""

from enum import StrEnum


class AccountType(StrEnum):
    """支持的账户分类，持久化时使用小写值。"""

    CASH = "cash"
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"
    INVESTMENT = "investment"
    OTHER = "other"


class TransactionType(StrEnum):
    """现金流方向；存储的金额本身始终为非负数。"""

    INCOME = "income"
    EXPENSE = "expense"


class BudgetPeriod(StrEnum):
    """展示周期，与每个预算具有权威性的起止日期分离。"""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class AssetType(StrEnum):
    """持仓与市场观测共享的初始资产分类。"""

    STOCK = "stock"
    FUND = "fund"
    ETF = "etf"
    BOND = "bond"
    DEPOSIT = "deposit"
    CRYPTO = "crypto"
    OTHER = "other"


class InvestmentTransactionType(StrEnum):
    """平均成本计算支持的不可变交易方向。"""

    # 转账、拆分和分红需要后续单独定义会计规则。
    BUY = "buy"
    SELL = "sell"
