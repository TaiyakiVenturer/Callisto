"""
GPT-SoVITS V2 TTS Streaming Integration Module

This module provides a client for the GPT-SoVITS V2 TTS streaming API,
supporting streaming audio generation with reference voice cloning.

Features:
- Stream TTS audio generation with reference voice cloning
- Support for multiple languages with reference audio prompts
- Optimized for GPU memory constraints (GTX 1060 6GB compatible)
"""

import logging
from typing import Generator

import numpy as np
import requests

from config import load_config
from services.tts.base_tts import BaseTTSClient

logger = logging.getLogger(__name__)

class GPTSoVITSV2Client(BaseTTSClient):
    """
    Client for GPT-SoVITS V2 TTS Streaming API.
    
    This client handles communication with the GPT-SoVITS V2 TTS server,
    providing methods for streaming audio generation with voice cloning,
    playback, and saving.
    
    Args:
        base_url: Base URL of the GPT-SoVITS server (default: http://127.0.0.1:9880)
        sample_rate: Audio sample rate in Hz (default: 32000 for V2)
    
    Attributes:
        base_url: The base URL of the TTS server
        tts_endpoint: The API endpoint for TTS generation
        sample_rate: Audio sampling rate
    """
    
    def __init__(self):
        """
        Initialize the GPT-SoVITS V2 TTS client.
        Reads base_url, sample_rate and all TTS params from config.yaml [tts] block.
        """
        self.config = load_config()["tts"]["gptsovits"]
        self.base_url = f"http://{self.config['host']}:{self.config['port']}"
        self.tts_endpoint = "/tts"
        self.sample_rate = self.config["sample_rate"]
        self.language = self.config["language"]

        # Startup connectivity check — warning only, TTS failure is non-fatal
        try:
            requests.get(self.base_url, timeout=2)
        except Exception:
            logger.warning(
                f"GPT-SoVITS server at {self.base_url} is unreachable. "
                "TTS will fail at runtime. "
                "Start the server, or set `tts.provider: edge_tts` in config.yaml"
            )
    
    def _generate_stream(
        self,
        text: str,
        language: str = "zh",
    ) -> requests.Response:
        """
        Generate TTS audio stream from text with reference voice.
        
        This method sends a request to the GPT-SoVITS V2 API and returns a
        streaming response object with PCM audio data. The response can be 
        used for playback or saving to a file.
        
        Args:
            text: Text to convert to speech
            voice: Path to reference audio file for voice cloning
            prompt_text: Text content of the reference audio
            language: Target language code (e.g., "zh", "en", "ja")
            prompt_lang: Language of the prompt text (default: "zh")
            streaming_mode: Streaming quality mode (0=low, 1=medium, 2=high, default: 2)
            batch_size: Batch size for inference (default: 1 for memory efficiency)
        
        Returns:
            requests.Response object with streaming PCM audio data
        
        Raises:
            ValueError: If text or required parameters are empty
            requests.exceptions.RequestException: If network error occurs
            requests.exceptions.HTTPError: If API returns error status
        
        Example:
            >>> client = GPTSoVITSV2Client()
            >>> response = client.generate_stream(
            ...     text="Hello World",
            ...     voice="voices/ref.wav",
            ...     prompt_text="Reference text here"
            ... )
            >>> client.play_stream(response)
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        
        if not self.config["voice"]:
            raise ValueError("Voice (reference audio path) cannot be empty")
        
        if not self.config["prompt_text"] or not self.config["prompt_text"].strip():
            raise ValueError("Prompt text cannot be empty")
        
        # Build the request payload for V2 API
        payload = {
            "text": text,
            "text_lang": language,
            "ref_audio_path": self.config["voice"],
            "prompt_text": self.config["prompt_text"],
            "prompt_lang": self.config["prompt_lang"],
            "media_type": "raw",  # PCM format for streaming
            "streaming_mode": self.config["streaming_mode"],
            "batch_size": self.config["batch_size"],
            "parallel_infer": True
        }
        
        url = f"{self.base_url}{self.tts_endpoint}"
        
        try:
            # Send POST request with streaming enabled
            response = requests.post(url, json=payload, stream=True, timeout=60)
            response.raise_for_status()
            return response
        
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException(
                "Request timed out. Please check if the GPT-SoVITS server is running."
            )
        except requests.exceptions.ConnectionError:
            raise requests.exceptions.RequestException(
                f"Failed to connect to GPT-SoVITS server at {self.base_url}. "
                "Please ensure the server is running."
            )
        except requests.exceptions.HTTPError as e:
            error_msg = f"GPT-SoVITS API returned error: {e.response.status_code}"
            try:
                error_detail = e.response.json()
                error_msg += f" - {error_detail}"
            except Exception:
                error_msg += f" - {e.response.text}"
            raise requests.exceptions.HTTPError(error_msg)

    def get_chunk_generator(self, text: str, volume: float = 1.0) -> Generator[bytes, None, None]:
        """生成 TTS 音訊並以 generator 形式逐 chunk yield PCM bytes。

        符合 BaseTTSClient 介面，呼叫端不需要感知底層 HTTP response 細節。

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

        response = self._generate_stream(text, language=self.language)

        for chunk in response.iter_content(chunk_size=1024):
            if not chunk:
                continue

            if volume != 1.0:
                audio_data = np.frombuffer(chunk, dtype=np.int16)
                audio_data = np.clip(
                    (audio_data * volume).astype(np.int16), -32768, 32767
                )
                chunk = audio_data.tobytes()

            yield chunk
