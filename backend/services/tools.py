from logging import getLogger

from pydantic import BaseModel, Field

logger = getLogger(__name__)


class SearchMemory(BaseModel):
    """搜尋長期記憶資料庫。符合以下任一情況時使用：
    1. 問題涉及過去的資訊、個人習慣、偏好或先前對話內容
    2. 使用者明確要求搜尋、回憶或查詢過去記憶（例如：「你還記得...嗎？」「你知道...嗎？」）
    3. 回答問題前需要確認是否有相關背景資訊
    """

    keyword: str = Field(
        description=(
            "搜尋記憶用的關鍵字，請只提供核心詞彙。"
            "例如：不要給 '請幫我搜尋 SQL 的記憶'，要給 'SQL 優化'"
        )
    )


_TOOLS: list[type[BaseModel]] = [SearchMemory]


def get_tools() -> list[dict]:
    """將 Pydantic 模型自動轉換為 Groq/OpenAI tool calling 格式。"""
    result = []
    for tool_cls in _TOOLS:
        schema = tool_cls.model_json_schema()
        description = schema.pop("description", "No description")
        result.append({
            "type": "function",
            "function": {
                "name": tool_cls.__name__,
                "description": description,
                "parameters": schema,
            },
        })
    logger.info(f"Registered {len(result)} tool(s): {[t['function']['name'] for t in result]}")
    return result
