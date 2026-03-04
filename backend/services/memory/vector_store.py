from logging import getLogger

import chromadb
from chromadb.config import Settings

from services.memory.embedding_service import EmbeddingService

logger = getLogger(__name__)

_COLLECTION_NAME = "callisto_memories"


class VectorStore:
    """
    ChromaDB 向量儲存封裝。

    提供記憶的向量 CRUD 和語義搜尋介面，
    讓上層的 RetrievalService 不直接操作 ChromaDB API。
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        persist_dir: str | None = None,
        collection_name: str = _COLLECTION_NAME,
    ):
        self.embedding_service = embedding_service
        self.collection_name = collection_name

        if persist_dir is None:
            from config import load_config
            persist_dir = load_config()["memory"]["storage"]["chroma_persist_dir"]

        if persist_dir:
            self.client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            # 記憶體模式（測試使用）
            self.client = chromadb.EphemeralClient(
                settings=Settings(anonymized_telemetry=False)
            )
            logger.warning(
                "Initialized VectorStore in in-memory mode. "
                "Data will not persist across runs."
            )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(
            f"VectorStore ready: collection='{collection_name}', "
            f"persist='{persist_dir or 'in-memory'}'"
        )

    def add_memory(
        self,
        memory_id: int,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        """
        向量化文字並存入 ChromaDB。

        Raises:
            EmbeddingUnavailableError: Ollama 不可用時向上傳遞。
        """
        embedding = self.embedding_service.embed(text)
        self.collection.upsert(
            ids=[str(memory_id)],
            embeddings=[embedding],
            documents=[text],
            metadatas=[metadata if metadata else None],
        )
        logger.debug(f"Upserted vector for memory id={memory_id}")

    def search(
        self, query_text: str, top_k: int = 5
    ) -> list[dict]:
        """
        語義搜尋，回傳最相近的 top_k 筆記憶。

        Returns:
            list of {id: int, text: str, metadata: dict, distance: float}
            distance 為 cosine distance（越小越近）。

        Raises:
            EmbeddingUnavailableError: Ollama 不可用時向上傳遞。
        """
        embedding = self.embedding_service.embed(query_text)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=min(top_k, self.collection.count() or 1),
            include=["documents", "metadatas", "distances"],
        )

        items = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for i, doc_id in enumerate(ids):
            items.append({
                "id": int(doc_id),
                "text": documents[i],
                "metadata": metadatas[i],
                "distance": distances[i],
            })

        return items

    def delete_memory(self, memory_id: int) -> None:
        """從 ChromaDB 刪除向量。"""
        self.collection.delete(ids=[str(memory_id)])
        logger.debug(f"Deleted vector for memory id={memory_id}")

    def count(self) -> int:
        """回傳 Collection 中的向量數量。"""
        return self.collection.count()
