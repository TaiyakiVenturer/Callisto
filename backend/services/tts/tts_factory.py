"""
TTS Client 工廠模組

根據 config.yaml 的 tts.provider 欄位建立對應的 BaseTTSClient 實作。
"""

import logging

from services.tts.base_tts import BaseTTSClient
from services.tts.gpt_sovits_service import GPTSoVITSV2Client
from services.tts.edge_tts_service import EdgeTTSClient

logger = logging.getLogger(__name__)

# provider 名稱 → 對應 class（value 是 class 本身，呼叫時再實例化）
_PROVIDER_MAP: dict[str, type[BaseTTSClient]] = {
    "gptsovits": GPTSoVITSV2Client,
    "edge_tts":  EdgeTTSClient,
}


def create_tts_client(config: dict) -> BaseTTSClient:
    """根據 provider 欄位建立並回傳 TTS client。

    Args:
        config: config.yaml 的 tts 區塊 dict（需包含 provider 欄位）。

    Returns:
        已初始化的 BaseTTSClient 實作。

    Raises:
        ValueError: provider 欄位缺失或不支援。
    """
    provider = config.get("provider")
    if not provider:
        raise ValueError(
            "Missing required config field: tts.provider. "
            f"Supported values: {' / '.join(_PROVIDER_MAP)}"
        )

    if provider not in _PROVIDER_MAP:
        raise ValueError(
            f"Unknown TTS provider: '{provider}'. "
            f"Supported values: {' / '.join(_PROVIDER_MAP)}"
        )

    client = _PROVIDER_MAP[provider]()
    logger.info(f"TTS client initialized (provider: {provider})")
    return client
