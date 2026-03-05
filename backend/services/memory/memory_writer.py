import json
import logging

from openai import OpenAI

from config import load_config
from services.memory.sql import MemoryDB
from services.memory.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MemoryWriter:
    """對話記憶寫入服務。

    在對話輪次結束後判斷是否值得保存，若是則寫入 SQLite 和 ChromaDB。
    """

    def __init__(
        self,
        db: MemoryDB,
        vector_store: VectorStore,
        llm_client: OpenAI,
    ):
        self.db = db
        self.vector_store = vector_store
        self.llm_client = llm_client
        config = load_config()["memory"]["llm"]
        self.writer_model = config["writer_model"]
        self.writer_temperature = config["writer_temperature"]
        self.writer_system_prompt = config["writer_system_prompt"]

    def analyze(self, turns: list[tuple[str, str]]) -> dict | None:
        """LLM 呼叫，判斷多輪對話批次是否值得保存並提取記憶欄位。

        Args:
            turns: 按時間順序排列的 (user_msg, assistant_msg) 對列表。

        Returns:
            dict with keys (topic, summary, keywords, content) if worth saving,
            None if not worth saving or on error.
        """
        parts = [
            f"[Turn {i + 1}]\nUser: {u}\nAssistant: {a}"
            for i, (u, a) in enumerate(turns)
        ]
        user_content = "\n\n".join(parts)
        try:
            response = self.llm_client.chat.completions.create(
                model=self.writer_model,
                messages=[
                    {"role": "system", "content": self.writer_system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=self.writer_temperature,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
        except Exception as e:
            logger.warning(f"analyze: LLM API error or JSON parse failed: {e}")
            return None

        if not data.get("save"):
            return None

        for field in ("topic", "summary", "keywords", "content"):
            if not data.get(field):
                logger.warning(f"analyze: missing required field '{field}'")
                return None

        return data

    def write(self, turns: list[tuple[str, str]]) -> bool:
        """分析多輪對話批次並寫入記憶。SQLite 寫入成功即視為成功（SQLite-first）。

        Args:
            turns: 按時間順序排列的 (user_msg, assistant_msg) 對列表。

        Returns:
            True if memory was written, False if skipped or SQLite failed.
        """
        if not turns:
            return False
        result = self.analyze(turns)
        if result is None:
            logging.info("write: analyze() returned None, skipping memory write.")
            return False

        try:
            memory = self.db.update_memory(
                topic=result["topic"],
                summary=result["summary"],
                keywords=result["keywords"],
                content=result["content"],
            )
        except Exception as e:
            logger.error(f"write: SQLite write failed for topic={result['topic']}: {e}")
            return False

        try:
            self.vector_store.add_memory(
                memory.id,
                memory.content,
                {"topic": memory.topic},
            )
        except Exception as e:
            logger.warning(
                f"write: ChromaDB write failed for topic={memory.topic} "
                f"(SQLite OK, search falls back to FTS5): {e}"
            )

        logger.info(f"write: memory saved topic={memory.topic} id={memory.id}")
        return True
