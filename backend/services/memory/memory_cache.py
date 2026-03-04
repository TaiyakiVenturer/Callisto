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
        config = load_config()["llm"]
        self._system_prompt: str = config["system_prompt"]
        self.max_turns: int = config["max_cache_length"]  # 真實對話輪數上限（tool calling 中繼訊息不計）
        self.chat_history: list[dict] = [
            {"role": "system", "content": self._system_prompt}
        ]

    def reset_history(self) -> None:
        """重置對話歷史（保留 system prompt，使用 __init__ 已讀取的設定）。"""
        self.chat_history = [
            {"role": "system", "content": self._system_prompt}
        ]

    def _user_turn_count(self) -> int:
        """計算目前歷史中的真實對話輪數（以 user 訊息數量為準）。"""
        return sum(1 for msg in self.chat_history if msg.get("role") == "user")

    def _drop_oldest_turn(self) -> None:
        """移除最舊的完整對話輪次。

        從第一則 user 訊息開始，刪除直到下一則 user 訊息（不含）為止，
        一次清除整個 turn cluster（user + tool_calls + tool 結果 + 最終 assistant 回覆），
        避免殘留孤立的 tool 訊息導致 API 錯誤。
        """
        # 找第一則 user 訊息（跳過 index 0 的 system）
        start = 1
        while start < len(self.chat_history) and self.chat_history[start].get("role") != "user":
            start += 1

        if start >= len(self.chat_history):
            return

        # 找下一則 user 訊息的位置（= 這個 cluster 的結束邊界）
        end = start + 1
        while end < len(self.chat_history) and self.chat_history[end].get("role") != "user":
            end += 1

        del self.chat_history[start:end]
        logger.warning(
            f"add_history: 對話輪數超過上限，移除最舊對話輪次（{end - start} 條訊息）。"
        )

    def add_history(self, message: dict) -> None:
        """
        新增一則訊息到對話歷史。

        支援 role: system / user / assistant / tool。
        - assistant 訊息允許 content=None（純 tool_calls 回應）。
        - tool 訊息必須包含 content 和 tool_call_id。
        - 超過 max_turns 時，移除最舊的完整對話輪次（含 tool calling 中繼訊息）。
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

        while self._user_turn_count() > self.max_turns:
            self._drop_oldest_turn()

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

    def get_recent_turns(self, n: int) -> list[tuple[str, str]]:
        """從對話歷史中提取最近 n 輪的 (user_msg, assistant_msg) 對。

        跳過 content=None 的 assistant 訊息（純 tool_calls 中繼步驟）
        和 role=tool 的工具回傳訊息，只配對有實際文字內容的 user/assistant 對。

        Returns:
            按時間順序排列的對話對列表，最多 n 筆。
        """
        pairs: list[tuple[str, str]] = []
        i = len(self.chat_history) - 1
        while i > 0 and len(pairs) < n:
            msg = self.chat_history[i]
            if msg.get("role") == "assistant" and msg.get("content"):
                # 往前找最近一則 user 訊息
                j = i - 1
                while j > 0 and self.chat_history[j].get("role") != "user":
                    j -= 1
                if self.chat_history[j].get("role") == "user":
                    pairs.append((self.chat_history[j]["content"], msg["content"]))
                    i = j - 1
                    continue
            i -= 1
        pairs.reverse()
        return pairs

    def show_history(self) -> Generator:
        """逐行 yield 對話歷史（除錯用）。"""
        def generator():
            for msg in self.chat_history:
                yield f"{msg.get('role')}: {msg.get('content')}"
        return generator()
