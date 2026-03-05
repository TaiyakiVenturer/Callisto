"""
LLM Client 工廠模組

根據 config.yaml 的 llm.provider 欄位建立對應的 OpenAI-compatible client。
所有支援的 provider 都實作 OpenAI REST API 規格，因此回傳統一的 openai.OpenAI 型別。
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "ollama": ("http://localhost:11434/v1", "ollama"),
    "groq":   ("https://api.groq.com/openai/v1", os.getenv("GROQ_API_KEY") or ""),
}


def create_llm_client(config: dict) -> OpenAI:
    """根據 provider 欄位建立並回傳 OpenAI-compatible LLM client。

    啟動時會呼叫 models.list() 驗證連線與 API key，
    失敗時立即拋出 RuntimeError，避免對話時才發現 LLM 不通。

    Args:
        config: config.yaml 的 llm 區塊 dict（需包含 provider 欄位）。

    Returns:
        已驗證可連線的 openai.OpenAI client。

    Raises:
        ValueError: 不支援的 provider 值。
        RuntimeError: 連線失敗或 API key 無效。
    """
    provider = config.get("provider")
    if not provider:
        raise ValueError(
            "Missing required config field: llm.provider. "
            f"Supported values: {' / '.join(_PROVIDER_MAP)}"
        )

    if provider not in _PROVIDER_MAP:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported values: {' / '.join(_PROVIDER_MAP)}"
        )

    base_url, api_key = _PROVIDER_MAP[provider]
    client = OpenAI(base_url=base_url, api_key=api_key)
    _health_check(client, provider, base_url)
    return client


def _health_check(client: OpenAI, provider: str, base_url: str) -> None:
    """呼叫 models.list() 驗證連線與 API key。

    Args:
        client: 已初始化的 OpenAI client。
        provider: provider 名稱，用於錯誤訊息。
        base_url: 該 provider 的 base URL，用於錯誤訊息。

    Raises:
        RuntimeError: 連線失敗或認證錯誤。
    """
    try:
        client.models.list()
        logger.info(f"LLM health check passed (provider: {provider})")
    except Exception as e:
        raise RuntimeError(
            f"LLM provider '{provider}' is unreachable or API key is invalid: {e}\n"
            f"  → Verify the provider is accessible at {base_url}"
        ) from e
