import logging
from typing import Generator

from config import load_config

logger = logging.getLogger(__name__)

# Groq API 所有合法 role
_VALID_ROLES = {"system", "user", "assistant", "tool"}

# 傳給 API 時需要 passthrough 的欄位（timestamp 等內部欄位不傳）
_API_KEYS = {"role", "content", "tool_calls", "tool_call_id", "name"}


class MemoryCache:
    """Context Window 管理，維護對話歷史並支援 Tool Calling 訊息格式。"""

    def __init__(self):
        config = load_config()
        self._system_prompt: str = config["llm"]["system_prompt"]
        self.max_len: int = 1 + config["llm"]["max_cache_length"] * 2  # 1 (system) + N * (user + assistant)
        self.chat_history: list[dict] = [
            {"role": "system", "content": self._system_prompt}
        ]

    def reset_history(self) -> None:
        """重置對話歷史（保留 system prompt，使用 __init__ 已讀取的設定）。"""
        self.chat_history = [
            {"role": "system", "content": self._system_prompt}
        ]

    def add_history(self, message: dict) -> None:
        """
        新增一則訊息到對話歷史。

        支援 role: system / user / assistant / tool。
        - assistant 訊息允許 content=None（純 tool_calls 回應）。
        - tool 訊息必須包含 content 和 tool_call_id。
        - 超過 max_len 時移除最舊的非 system 訊息（index 1）。
        """
        role = message.get("role")

        if role not in _VALID_ROLES:
            logger.warning(f"add_history: 拒絕非法 role='{role}'，訊息未加入。")
            return

        # assistant 可以 content=None（只有 tool_calls），其他 role 必須有 content
        if role != "assistant" and not message.get("content"):
            logger.warning(f"add_history: role='{role}' 缺少 content，訊息未加入。")
            return

        if role == "tool" and not message.get("tool_call_id"):
            logger.warning("add_history: tool 訊息缺少 tool_call_id，訊息未加入。")
            return

        self.chat_history.append(message)

        while len(self.chat_history) > self.max_len:
            self.chat_history.pop(1)
            logger.warning("add_history: 對話歷史超過上限，移除最舊訊息。")

    def get_api_history(self) -> list[dict]:
        """
        回傳可直接傳給 Groq API 的訊息列表。

        只保留 API 所需欄位（role, content, tool_calls, tool_call_id, name），
        過濾掉 None 值及內部欄位。
        """
        return [
            {k: v for k, v in msg.items() if k in _API_KEYS and v is not None}
            for msg in self.chat_history
        ]

    def show_history(self) -> Generator:
        """逐行 yield 對話歷史（除錯用）。"""
        def generator():
            for msg in self.chat_history:
                yield f"{msg.get('role')}: {msg.get('content')}"
        return generator()
