from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

from sqlalchemy import (
    Column, DateTime, Integer, String, Text, create_engine, event, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker

logger = getLogger(__name__)

Base = declarative_base()


class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    topic = Column(String, unique=True, nullable=False)
    summary = Column(Text, nullable=False)
    keywords = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    last_accessed = Column(DateTime, nullable=True)
    access_count = Column(Integer, default=0, nullable=False)


@event.listens_for(Memory, "after_insert")
def _sync_fts_on_insert(mapper, connection, target):
    """新記憶寫入後，同步到 FTS5 索引。"""
    connection.execute(
        text(
            "INSERT INTO memory_fts(rowid, summary, keywords)"
            " VALUES (:id, :s, :k)"
        ),
        {"id": target.id, "s": target.summary, "k": target.keywords},
    )
    logger.debug(f"Synced Memory id={target.id} to FTS index.")


@event.listens_for(Memory, "after_delete")
def _sync_fts_on_delete(mapper, connection, target):
    """記憶刪除後，同步清除 FTS5 索引。"""
    connection.execute(
        text("DELETE FROM memory_fts WHERE rowid = :id"),
        {"id": target.id},
    )
    logger.debug(f"Removed Memory id={target.id} from FTS index.")


@event.listens_for(Memory, "after_update")
def _sync_fts_on_update(mapper, connection, target):
    """記憶更新後，重新同步 FTS5 索引。

    FTS5 外部 content table 需用 'delete' 命令帶舊內容才能正確清除倒排索引。
    透過 SQLAlchemy attribute history 取得舊值。
    """
    hist_summary = inspect(target).attrs.summary.history
    hist_keywords = inspect(target).attrs.keywords.history
    old_summary = (
        hist_summary.deleted[0] if hist_summary.deleted else target.summary
    )
    old_keywords = (
        hist_keywords.deleted[0] if hist_keywords.deleted else target.keywords
    )
    connection.execute(
        text(
            "INSERT INTO memory_fts(memory_fts, rowid, summary, keywords)"
            " VALUES('delete', :id, :s, :k)"
        ),
        {"id": target.id, "s": old_summary, "k": old_keywords},
    )
    connection.execute(
        text(
            "INSERT INTO memory_fts(rowid, summary, keywords)"
            " VALUES (:id, :s, :k)"
        ),
        {"id": target.id, "s": target.summary, "k": target.keywords},
    )
    logger.debug(f"Re-synced Memory id={target.id} to FTS index after update.")


class MemoryDB:
    def __init__(self, db_url: str | None = None):
        if db_url is None:
            from config import load_config
            db_url = load_config()["memory"]["storage"]["db_url"]
        # sqlite:///path/to/file.db → 確保目錄存在（in-memory URL 不需要）
        if db_url.startswith("sqlite:///") and db_url != "sqlite:///:memory:":
            db_path = db_url[len("sqlite:///"):]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self._init_fts()
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _init_fts(self):
        """建立 FTS5 虛擬表（使用 trigram tokenizer）。

        FTS5 虛擬表在事務外補建：
        - memories table 由 SQLAlchemy 事務保護
        - FTS5 虛擬表不支援事務回滾，失敗時可用 rebuild 指令重建
        """
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(
                    summary,
                    keywords,
                    content='memories',
                    content_rowid='id',
                    tokenize='trigram'
                );
            """))
            conn.commit()
        logger.info("FTS5 virtual table ready (trigram tokenizer).")

    def rebuild_fts(self):
        """從 memories table 重建 FTS5 索引（同步修復用）。"""
        with self.engine.connect() as conn:
            conn.execute(
                text("INSERT INTO memory_fts(memory_fts) VALUES('rebuild')")
            )
            conn.commit()
        logger.info("FTS5 index rebuilt from memories table.")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_memory(
        self,
        topic: str,
        summary: str,
        keywords: str,
        content: str,
    ) -> Memory:
        """新增一筆記憶。"""
        with self.Session() as session:
            memory = Memory(
                topic=topic,
                summary=summary,
                keywords=keywords,
                content=content,
            )
            session.add(memory)
            session.commit()
            session.refresh(memory)
            logger.info(f"Added memory id={memory.id} topic={topic}")
            return memory

    def update_memory(
        self,
        topic: str,
        summary: str,
        keywords: str,
        content: str,
    ) -> Memory:
        """更新已存在的記憶；topic 不存在時建立新筆（upsert）。"""
        with self.Session() as session:
            memory = session.query(Memory).filter_by(topic=topic).first()
            if memory is not None:
                memory.summary = summary
                memory.keywords = keywords
                memory.content = content
                session.commit()
                session.refresh(memory)
                logger.info(f"Updated memory id={memory.id} topic={topic}")
                return memory
        return self.add_memory(topic, summary, keywords, content)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search_memory(self, keyword: str, top_k: int = 10) -> list[Memory]:
        """使用 FTS5 trigram 全文搜尋，回傳命中的 Memory 物件列表。

        注意：access_count / last_accessed 不在此更新，
        由 RetrievalService 在組完最終 Top-K 後呼叫 bump_access()。
        """
        if len(keyword) < 3:
            logger.warning(
                f"Keyword '{keyword}' is shorter than 3 chars; "
                "trigram FTS5 requires at least 3 characters."
            )
            return []

        with self.Session() as session:
            fts_query = text("""
                SELECT rowid FROM memory_fts
                WHERE memory_fts MATCH :k
                LIMIT :limit
            """)
            rows = session.execute(
                fts_query, {"k": keyword, "limit": top_k}
            ).fetchall()
            ids = [r[0] for r in rows]

            if not ids:
                return []

            results = (
                session.query(Memory).filter(Memory.id.in_(ids)).all()
            )

            return results

    def bump_access(self, memory_ids: list[int]) -> None:
        """更新一批記憶的 last_accessed 與 access_count。

        由 RetrievalService 在回傳最終 Top-K 後呼叫，
        確保僅對實際被使用的記憶數據正確計數（含 vector-only 命中）。
        """
        if not memory_ids:
            return
        now = datetime.now(timezone.utc)
        with self.Session() as session:
            memories = (
                session.query(Memory).filter(Memory.id.in_(memory_ids)).all()
            )
            for memory in memories:
                memory.last_accessed = now
                memory.access_count = (memory.access_count or 0) + 1
            session.commit()
            logger.debug(f"Bumped access for memory ids={memory_ids}")

    def get_by_id(self, memory_id: int) -> Memory | None:
        """依 ID 取得記憶。"""
        with self.Session() as session:
            return session.query(Memory).filter(Memory.id == memory_id).first()

    def delete_memory(self, memory_id: int) -> bool:
        """刪除單筆記憶（SQLite + FTS5 同步由 after_delete event 處理）。"""
        with self.Session() as session:
            memory = session.query(Memory).filter_by(id=memory_id).first()
            if memory is None:
                logger.warning(f"delete_memory: id={memory_id} not found.")
                return False
            session.delete(memory)
            session.commit()
            logger.info(f"Deleted memory id={memory_id}")
            return True

    def compress_memory(self, memory_id: int, new_content: str) -> Memory | None:
        """壓縮記憶 content（保留 summary/keywords 不動）。"""
        with self.Session() as session:
            memory = session.query(Memory).filter_by(id=memory_id).first()
            if memory is None:
                logger.warning(f"compress_memory: id={memory_id} not found.")
                return None
            memory.content = new_content
            session.commit()
            session.refresh(memory)
            logger.info(f"Compressed memory id={memory_id}")
            return memory

    def get_all(self) -> list[Memory]:
        """取得所有記憶（初始化 ChromaDB 用）。"""
        with self.Session() as session:
            return session.query(Memory).all()
