"""API 第一版的组合根。"""

from fastapi import APIRouter

from app.api import accounts, auth, budgets, holdings, reports, system, transactions, users

router = APIRouter()
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(accounts.router)
router.include_router(transactions.router)
router.include_router(budgets.router)
router.include_router(holdings.router)
router.include_router(holdings.investment_router)
router.include_router(holdings.market_router)
router.include_router(holdings.portfolio_router)
router.include_router(reports.router)
