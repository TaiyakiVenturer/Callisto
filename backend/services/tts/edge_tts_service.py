"""
Edge-TTS Client Module

輕量雲端 TTS 服務，使用 Microsoft Edge TTS（edge-tts）。
在沒有本地 GPT-SoVITS server 的環境下可作為替代方案。

edge-tts 的底層是 async generator，本模組透過
asyncio.new_event_loop() 橋接為同步 Generator[bytes]，
避免與 FastAPI/uvicorn 的 event loop 衝突。
"""

import asyncio
import logging
from typing import Generator

import edge_tts
import numpy as np

from config import load_config
from services.tts.base_tts import BaseTTSClient

logger = logging.getLogger(__name__)


class EdgeTTSClient(BaseTTSClient):
    """Microsoft Edge TTS client，實作 BaseTTSClient 介面。

    edge-tts 輸出固定 24kHz 16-bit mono PCM。
    音量控制邏輯與 GPTSoVITSV2Client 一致（numpy int16 clip）。
    """

    sample_rate: int = 24000

    def __init__(self):
        cfg = load_config()["tts"]["edge_tts"]
        self.voice: str = cfg["voice"]
        self.rate: str = cfg.get("rate", "+0%")
        self.edge_volume: str = cfg.get("volume", "+0%")

    def get_chunk_generator(self, text: str, volume: float = 1.0) -> Generator[bytes, None, None]:
        """生成 TTS 音訊並以 generator 形式逐 chunk yield PCM bytes。

        使用獨立的 asyncio event loop 收集全部音訊後再 yield，
        不影響 FastAPI 的 event loop。

        Args:
            text: 要轉換為語音的文字。
            volume: 音量乘數（0.0-2.0，default: 1.0）。

        Yields:
            bytes: 16-bit PCM 音訊 chunks。

        Raises:
            ValueError: volume 超出有效範圍。
        """
        if not (0.0 <= volume <= 2.0):
            raise ValueError(f"Volume must be between 0.0 and 2.0, got {volume}")

        async def _collect_audio() -> list[bytes]:
            chunks: list[bytes] = []
            comm = edge_tts.Communicate(
                text,
                voice=self.voice,
                rate=self.rate,
                volume=self.edge_volume,
            )
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    chunks.append(chunk["data"])
            return chunks

        loop = asyncio.new_event_loop()
        try:
            audio_chunks = loop.run_until_complete(_collect_audio())
        except Exception as e:
            logger.error(f"EdgeTTSClient: 音訊生成失敗: {e}")
            return
        finally:
            loop.close()

        for data in audio_chunks:
            if not data:
                continue

            if volume != 1.0:
                audio_data = np.frombuffer(data, dtype=np.int16)
                audio_data = np.clip(
                    (audio_data * volume).astype(np.int16), -32768, 32767
                )
                data = audio_data.tobytes()

            yield data
