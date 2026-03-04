"""Forgetting Mechanism — Phase 3

根據每筆記憶的 last_accessed 和 access_count 計算活躍度分數，
低於閾值的記憶會被壓縮或刪除。
"""
import math
from datetime import datetime
from logging import getLogger

from config import load_config
from services.memory.sql import Memory, MemoryDB
from services.memory.vector_store import VectorStore

logger = getLogger(__name__)


class ForgettingService:
    """漸進式記憶遺忘服務。"""

    def __init__(
        self,
        db: MemoryDB,
        vector_store: VectorStore,
    ) -> None:
        self.db = db
        self.vector_store = vector_store
        config = load_config()["memory"]["forgetting"]
        self.lambda_decay = config["lambda_decay"]
        self.scale = config["scale"]
        self.compress_threshold = config["compress_threshold"]
        self.delete_threshold = config["delete_threshold"]

    def score(self, memory: Memory) -> float:
        """計算單筆記憶的活躍度分數（0.0 ~ 1.0）。

        公式：time_decay * log_access_boost
        - time_decay       = exp(-lambda_decay * days_since_last_access)
        - log_access_boost = log(1 + access_count) / log(1 + scale)
        """
        if memory.last_accessed is None:
            days = 999.0
        else:
            days = (datetime.now() - memory.last_accessed).total_seconds() / 86400

        time_decay = math.exp(-self.lambda_decay * days)

        access = memory.access_count or 0
        log_boost = math.log(1 + access) / math.log(1 + self.scale)

        return min(time_decay * log_boost, 1.0)

    def run_cycle(self) -> dict:
        """掃描所有記憶，對低分記憶執行壓縮或刪除。

        Returns:
            {
                "scanned": int,
                "deleted": list[str],   # 被刪除的 memory.topic
                "compressed": list[str] # 被壓縮的 memory.topic
            }
        """
        memories = self.db.get_all()
        deleted: list[str] = []
        compressed: list[str] = []

        for memory in memories:
            s = self.score(memory)
            logger.debug(
                f"Memory id={memory.id} topic='{memory.topic}' score={s:.4f}"
            )

            if s < self.delete_threshold:
                self.db.delete_memory(memory.id)
                self.vector_store.delete_memory(memory.id)
                deleted.append(memory.topic)
                logger.info(
                    f"[DELETED] id={memory.id} topic='{memory.topic}' score={s:.4f}"
                )
            elif s < self.compress_threshold:
                new_content = f"[壓縮] {memory.summary}"
                self.db.compress_memory(memory.id, new_content)
                compressed.append(memory.topic)
                logger.info(
                    f"[COMPRESSED] id={memory.id} topic='{memory.topic}' score={s:.4f}"
                )

        result = {
            "scanned": len(memories),
            "deleted": deleted,
            "compressed": compressed,
        }
        logger.info(f"Forgetting cycle complete: {result}")
        return result
