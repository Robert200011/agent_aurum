"""为测试收集阶段提供隔离且不可用于真实环境的配置。"""

from __future__ import annotations

import os

# app.main 在模块加载时创建 ASGI 应用，因此测试配置必须先于测试模块导入。
os.environ.setdefault(
    "AURUM_DATABASE_URL",
    "postgresql+asyncpg://test:test@localhost:5432/aurum_test",
)
os.environ.setdefault(
    "AURUM_MIGRATION_DATABASE_URL",
    "postgresql+asyncpg://test_owner:test@localhost:5432/aurum_test",
)
os.environ.setdefault(
    "AURUM_JWT_SECRET_KEY",
    "test-only-signing-key-with-more-than-32-characters",
)
os.environ.setdefault("AURUM_BOOTSTRAP_ADMIN", "false")
