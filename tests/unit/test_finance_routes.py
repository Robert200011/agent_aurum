"""完整阶段二 HTTP 接口面的 OpenAPI 注册检查。"""

from __future__ import annotations

from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def test_phase_two_finance_routes_are_registered() -> None:
    app = create_app(
        Settings(
            environment="test",
            bootstrap_admin=False,
            jwt_secret_key=SecretStr("test-signing-key-with-more-than-32-characters"),
        )
    )
    paths = set(app.openapi()["paths"])

    assert "/api/v1/finance/accounts" in paths
    assert "/api/v1/finance/transactions" in paths
    assert "/api/v1/finance/transactions/import" in paths
    assert "/api/v1/finance/budgets" in paths
    assert "/api/v1/finance/holdings" in paths
    assert "/api/v1/finance/investment-transactions" in paths
    assert "/api/v1/finance/market-snapshots/{symbol}/latest" in paths
    assert "/api/v1/finance/portfolio/summary" in paths
    assert "/api/v1/finance/reports/summary" in paths
