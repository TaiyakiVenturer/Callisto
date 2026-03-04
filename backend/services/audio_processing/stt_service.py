"""
STT (Speech-to-Text) Service
使用 faster-whisper 將語音轉換為文字
"""

from faster_whisper import WhisperModel
import logging
import os

from config import load_config

logger = logging.getLogger(__name__)


class STTService:
    """語音轉文字服務"""

    def __init__(self):
        """
        初始化 STT 服務，從 config.yaml [stt] 區塊讀取模型設定。
        """
        config = load_config()["stt"]
        self.model_size = config["model_size"]
        self.device = config["device"]
        self.compute_type = config["compute_type"]
        
        logger.info(f"載入 Whisper 模型: {self.model_size} on {self.device} ({self.compute_type})")
        
        try:
            self.model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type
            )
            logger.info("Whisper 模型載入完成")
        except Exception as e:
            logger.error(f"Whisper 模型載入失敗: {e}")
            raise
    
    def transcribe(
        self,
        audio_path: str,
        language: str = "zh",
        beam_size: int = 5,
        vad_filter: bool = False
    ) -> str:
        """
        將音訊轉換為文字
        
        Args:
            audio_path: 音訊檔案路徑
            language: 語言代碼 (zh=中文, en=英文)
            beam_size: Beam search 大小，越大越準確但越慢
            vad_filter: 是否使用內建 VAD 過濾（我們已經在外部做了）
            
        Returns:
            轉換的文字
            
        Raises:
            FileNotFoundError: 音訊檔案不存在
            Exception: 轉換失敗
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音訊檔案不存在: {audio_path}")
        
        try:
            logger.info(f"開始轉換語音: {audio_path}")
            
            # 執行轉換
            # 注意：如果當前已是 CPU 模式，不會觸發 fallback
            try:
                segments, info = self.model.transcribe(
                    audio_path,
                    language=language,
                    beam_size=beam_size,
                    temperature=0,
                    condition_on_previous_text=False,
                    vad_filter=vad_filter,
                    initial_prompt="這是一段台灣繁體中文語音對話，說話者可能語速較快"
                )
            except Exception as e:
                # Fallback 機制：僅在使用 CUDA 時才嘗試切換到 CPU
                if self.device != "cpu":
                    error_msg = str(e)
                    cuda_related_errors = ["cudnn", "cuda", "cannot load symbol", "execution_failed", "cudart"]
                    is_cuda_error = any(keyword in error_msg.lower() for keyword in cuda_related_errors)
                    
                    if is_cuda_error:
                        logger.warning(f"CUDA/cuDNN 執行錯誤，切換到 CPU: {error_msg}")
                        
                        # 重新載入 CPU 模型
                        self.device = "cpu"
                        self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
                        logger.info("已切換到 CPU 模型，重新執行轉換")
                        
                        # 重新執行 transcribe
                        segments, info = self.model.transcribe(
                            audio_path,
                            language=language,
                            beam_size=beam_size,
                            temperature=0,
                            condition_on_previous_text=False,
                            vad_filter=vad_filter,
                            initial_prompt="這是一段台灣繁體中文語音對話，說話者可能語速較快"
                        )
                    else:
                        raise
                else:
                    # 已經是 CPU 模式，直接拋出錯誤
                    raise
            
            # 組合所有 segments 的文字
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)
            
            result = "".join(text_parts).strip()
            
            logger.info(f"轉換完成: '{result}' (語言: {info.language}, 機率: {info.language_probability:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"語音轉換失敗: {e}")
            raise
    

