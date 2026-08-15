"""长期记忆聊天能力的稳定百分比分桶。"""

from __future__ import annotations

import hashlib
from uuid import UUID


def memory_rollout_enabled(
    user_id: UUID,
    *,
    feature_enabled: bool,
    percentage: int,
) -> bool:
    """按用户稳定分桶；调整百分比时只扩大或缩小同一批用户集合。"""

    if not feature_enabled or percentage <= 0:
        return False
    if percentage >= 100:
        return True
    digest = hashlib.sha256(b"aurum-memory-rollout-v1:" + user_id.bytes).digest()
    return int.from_bytes(digest[:4], "big") % 100 < percentage
