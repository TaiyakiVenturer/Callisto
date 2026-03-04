from logging import getLogger

from config import load_config
from services.memory.embedding_service import EmbeddingUnavailableError
from services.memory.sql import MemoryDB
from services.memory.vector_store import VectorStore

logger = getLogger(__name__)


class RetrievalService:
    """
    混合記憶搜尋服務（FTS5 + ChromaDB Vector + RRF 排序）。

    設計原則：
    - FTS5：關鍵字精確命中（trigram tokenizer）
    - ChromaDB：語義同義詞命中（embedding cosine similarity）
    - RRF：合併兩個排名列表，不需要正規化分數

    Graceful Degradation：
    - 若 Ollama 不可用（EmbeddingUnavailableError），
      自動降級為純 FTS5 搜尋並記錄警告。
    """

    def __init__(self, db: MemoryDB, vector_store: VectorStore, rrf_k: int | None = None):
        self.db = db
        self.vector_store = vector_store
        self.rrf_k = rrf_k if rrf_k is not None else load_config()["memory"]["retrieval"]["rrf_k"]

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """
        混合搜尋，回傳 RRF 排序後的 Top-K 記憶。

        Returns:
            list of {id, topic, summary, content, rrf_score}
            依 rrf_score 降序排列，無重複 ID，長度 <= top_k。
        """
        fetch_k = top_k * 2

        # --- FTS5 搜尋 ---
        fts_results = self.db.search_memory(query, top_k=fetch_k)
        fts_ranking: dict[int, int] = {
            m.id: rank + 1 for rank, m in enumerate(fts_results)
        }

        # --- Vector 搜尋（有 Graceful Degradation）---
        vector_ranking: dict[int, int] = {}
        try:
            vector_results = self.vector_store.search(query, top_k=fetch_k)
            vector_ranking = {
                item["id"]: rank + 1
                for rank, item in enumerate(vector_results)
            }
        except EmbeddingUnavailableError as e:
            logger.warning(
                f"Ollama unavailable, falling back to FTS5-only search. "
                f"Reason: {e}"
            )

        # --- RRF 合併 ---
        all_ids = set(fts_ranking) | set(vector_ranking)
        rrf_scores: dict[int, float] = {}

        for doc_id in all_ids:
            score = 0.0
            if doc_id in fts_ranking:
                score += 1.0 / (self.rrf_k + fts_ranking[doc_id])
            if doc_id in vector_ranking:
                score += 1.0 / (self.rrf_k + vector_ranking[doc_id])
            rrf_scores[doc_id] = score

        # 降序排列，取 Top-K
        sorted_ids = sorted(rrf_scores, key=lambda x: rrf_scores[x], reverse=True)
        top_ids = sorted_ids[:top_k]

        # --- 組裝結果 ---
        results = []
        for doc_id in top_ids:
            memory = self.db.get_by_id(doc_id)
            if memory is None:
                continue
            results.append({
                "id": memory.id,
                "topic": memory.topic,
                "summary": memory.summary,
                "content": memory.content,
                "rrf_score": rrf_scores[doc_id],
            })

        # --- 更新實際回傳的 Top-K 記憶的 access 統計 ---
        if results:
            self.db.bump_access([r["id"] for r in results])

        logger.info(
            f"Retrieval query='{query}': "
            f"fts={len(fts_ranking)}, vector={len(vector_ranking)}, "
            f"rrf_top={len(results)}"
        )
        return results

    def format_for_injection(self, results: list[dict]) -> str:
        """將搜尋結果格式化為注入 Context Window 的字串。"""
        if not results:
            return "（沒有找到相關記憶）"

        parts = []
        for i, r in enumerate(results, 1):
            parts.append(
                f"[記憶 {i}] {r['topic']}\n"
                f"摘要：{r['summary']}\n"
                f"內容：{r['content']}"
            )
        return "\n\n".join(parts)
