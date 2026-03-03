"""
openWakeWord 關鍵字喚醒服務 (Keyword Spotting Service)
使用 openWakeWord 實現喚醒詞「嘿 Callisto」的檢測
"""

import logging
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from collections import deque

logger = logging.getLogger(__name__)

# 嘗試導入 openwakeword
try:
    from openwakeword.model import Model as OpenWakeWordModel
    OPENWAKEWORD_AVAILABLE = True
except ImportError:
    logger.warning("openwakeword 未安裝，KWS 服務將無法使用")
    OPENWAKEWORD_AVAILABLE = False


class KeywordSpottingService:
    """
    關鍵字喚醒檢測服務
    
    使用 openWakeWord 檢測喚醒詞「嘿 Callisto」
    - 支援多種預訓練模型
    - 需要 1-2 秒音訊累積以提高準確率
    - CPU 友好，低延遲
    """
    
    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        chunk_size: int = 1280  # 80ms @ 16kHz
    ):
        """
        初始化 KWS 服務（簡化版：移除內部 buffer）
        
        Args:
            wake_words: 喚醒詞列表，預設使用 ["hey_jarvis"]
                       可用的預訓練模型：
                       - "hey_jarvis"
                       - "alexa"  
                       - "hey_mycroft"
                       - "hey_rhasspy"
            threshold: 檢測閾值（0.0-1.0），預設 0.5
                      - 較低值：更敏感，可能誤觸發
                      - 較高值：更保守，可能漏檢
            sample_rate: 音訊採樣率，必須是 16000 Hz
            chunk_size: 每次處理的音訊塊大小（samples）
        
        Raises:
            RuntimeError: openwakeword 未安裝或模型載入失敗
        """
        if not OPENWAKEWORD_AVAILABLE:
            raise RuntimeError("openwakeword 未安裝，請執行: uv add openwakeword")
        
        if sample_rate != 16000:
            raise ValueError(f"KWS 僅支援 16kHz 採樣率，當前: {sample_rate} Hz")
        
        self.wake_words = wake_words or ["hey_jarvis"]  # 使用預訓練模型
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        
        # 只載入 wake_words 中有對應 .onnx 檔案的模型
        # 若找不到檔案則視為預訓練模型名稱（由 openwakeword 內建載入）
        _model_dir = Path("./models")
        self.wake_word_paths = [
            str((_model_dir / f"{w}.onnx").resolve())
            for w in self.wake_words
            if (_model_dir / f"{w}.onnx").exists()
        ] or None

        # 初始化 openWakeWord 模型
        try:
            logger.info(f"正在載入 openWakeWord 模型，喚醒詞: {self.wake_words}")

            self.model = OpenWakeWordModel(
                wakeword_model_paths=self.wake_word_paths
            )
            
            # 確認請求的喚醒詞是否可用
            available_models = list(self.model.models.keys())
            logger.info(f"✅ 可用的喚醒詞模型: {available_models}")
            
            # 驗證請求的喚醒詞是否存在
            for wake_word in self.wake_words:
                if wake_word not in available_models:
                    logger.warning(
                        f"⚠️ 喚醒詞 '{wake_word}' 不在可用模型列表中，"
                        f"可用: {available_models}"
                    )
            
            logger.info(f"✅ openWakeWord 服務已啟動")
            logger.info(f"   監聽喚醒詞: {self.wake_words}")
            logger.info(f"   檢測閾值: {threshold}")
            logger.info(f"   採樣率: {sample_rate} Hz")
            
        except Exception as e:
            logger.error(f"❌ openWakeWord 模型載入失敗: {e}")
            raise RuntimeError(f"無法載入 KWS 模型: {e}")
    
    def detect(self, audio_chunk: bytes) -> Optional[Tuple[str, float]]:
        """
        檢測喚醒詞（簡化版：直接接收完整 1.5 秒音訊）
        
        Args:
            audio_chunk: 完整的 1.5 秒音訊資料（bytes 格式，int16 PCM）
                        由 AudioMonitorService 的環形 buffer 提供
                        要求：
                        - 格式：int16 PCM
                        - 長度：24000 samples (1.5s @ 16kHz)
                        - 聲道：單聲道
                        - 採樣率：16000 Hz
        
        Returns:
            (關鍵詞, 信心度) 元組，如果沒有檢測到則返回 None
            例如: ("hey_jarvis", 0.95) 或 None
        
        Raises:
            ValueError: 音訊格式錯誤
        """
        try:
            # 將 bytes 轉換為 numpy array (int16)
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            
            if len(audio_int16) == 0:
                raise ValueError("音訊塊為空")
            
            # 執行檢測
            # predict() 返回字典: {wake_word: score}
            prediction = self.model.predict(audio_int16)
            
            # 只檢查我們指定的喚醒詞
            detected_keyword = None
            max_score = 0.0
            
            for wake_word in self.wake_words:
                # 只檢查指定的喚醒詞
                if wake_word in prediction:
                    score = prediction[wake_word]
                    logger.debug(f"KWS: {wake_word} = {score:.3f}")
                    
                    if score > self.threshold and score > max_score:
                        detected_keyword = wake_word
                        max_score = score
            
            if detected_keyword:
                logger.info(f"🎯 檢測到喚醒詞: {detected_keyword} (信心度: {max_score:.3f})")
                return (detected_keyword, max_score)
            
            return None
            
        except Exception as e:
            logger.error(f"KWS 檢測錯誤: {e}")
            raise ValueError(f"喚醒詞檢測失敗: {e}")
    
    def reset(self):
        """
        重置 KWS 服務狀態（簡化版：不再需要清空 buffer）
        
        用於新的音訊流開始時
        """
        # 不再需要：self.audio_buffer.clear()
        # 重置模型狀態（如果模型有狀態）
        if hasattr(self.model, 'reset'):
            self.model.reset()
        logger.info("KWS 服務狀態已重置")
    
    def set_threshold(self, threshold: float):
        """
        動態調整檢測閾值
        
        Args:
            threshold: 新的閾值（0.0-1.0）
        
        Raises:
            ValueError: 閾值超出有效範圍
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"閾值必須在 0.0 到 1.0 之間，當前值: {threshold}")
        
        logger.info(f"KWS 閾值從 {self.threshold} 調整為 {threshold}")
        self.threshold = threshold
    
    def get_supported_keywords(self) -> List[str]:
        """
        獲取當前監聽的喚醒詞列表
        
        Returns:
            當前監聽的喚醒詞名稱列表
        """
        return self.wake_words.copy()
    
    def get_available_models(self) -> List[str]:
        """
        獲取所有可用的喚醒詞模型列表
        
        Returns:
            所有已載入的喚醒詞模型名稱列表
        """
        return list(self.model.models.keys())
    
    def get_stats(self) -> Dict:
        """
        獲取 KWS 服務狀態資訊
        
        Returns:
            包含服務狀態的字典
        """
        return {
            "wake_words": self.wake_words,
            "threshold": self.threshold,
            "sample_rate": self.sample_rate,
            "chunk_size": self.chunk_size,
            "available_models": list(self.model.models.keys()),
            "status": "ready"
        }
