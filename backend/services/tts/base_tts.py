"""
TTS Client 抽象基底類

所有 TTS service 實作必須繼承此類，並實作 get_chunk_generator() 方法。
AvatarController 只依賴此介面，不感知底層是哪個 TTS provider。
"""

from abc import ABC, abstractmethod
from typing import Generator


class BaseTTSClient(ABC):
    """TTS client 統一介面。

    Attributes:
        sample_rate: 音訊取樣率（Hz）。AvatarController 用此值開啟 pyaudio stream。
    """

    sample_rate: int

    @abstractmethod
    def get_chunk_generator(
        self,
        text: str,
        volume: float = 1.0,
    ) -> Generator[bytes, None, None]:
        """將文字合成為音訊並以 bytes generator 回傳。

        實作必須：
        - yield 16-bit PCM bytes chunks（int16, little-endian）
        - 支援 volume 參數（0.0-2.0 乘數）

        Args:
            text: 要合成的文字內容。
            volume: 音量乘數（0.0-2.0），1.0 為原始音量。

        Yields:
            bytes: PCM 音訊資料 chunk。
        """
