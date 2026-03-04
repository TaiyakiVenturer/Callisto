from logging import getLogger

from config import load_config
from services.memory.retrieval import RetrievalService

logger = getLogger(__name__)


class ToolCallingHandler:
    """
    LLM Tool Calling 執行路由。

    依賴注入 RetrievalService，方便測試時替換 Mock。
    """

    def __init__(self, retrieval_service: RetrievalService, default_top_k: int | None = None):
        self.retrieval = retrieval_service
        self.default_top_k = (
            default_top_k if default_top_k is not None
            else load_config()["memory"]["retrieval"]["default_top_k"]
        )

    def handle(self, tool_name: str, params: dict) -> str:
        """
        根據工具名稱執行對應邏輯，回傳供 tool role 使用的字串結果。

        Returns:
            str: 格式化後的搜尋結果，注入 LLM Context Window 用。
        """
        if tool_name == "SearchMemory":
            keyword = params.get("keyword", "")
            logger.info(f"SearchMemory called with keyword='{keyword}'")

            top_k = self.default_top_k
            results = self.retrieval.search(keyword, top_k=top_k)
            formatted = self.retrieval.format_for_injection(results)

            logger.info(
                f"SearchMemory returned {len(results)} result(s) "
                f"for keyword='{keyword}'"
            )
            return formatted

        logger.warning(f"Unknown tool name: '{tool_name}'")
        return f"Error: unknown tool '{tool_name}'"
