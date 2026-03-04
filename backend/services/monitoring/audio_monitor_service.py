"""
音訊監聽協調服務 (Audio Monitor Service)
整合 VAD + KWS + 音訊緩衝區，實現完整的語音監聽流程
"""

import logging
import numpy as np
import time
from typing import Optional, Dict, List
from collections import deque
from enum import Enum

from services.audio_processing.silero_vad_service import SileroVADService
from services.audio_processing.kws_service import KeywordSpottingService

logger = logging.getLogger(__name__)


class MonitorState(Enum):
    """監聽狀態"""
    IDLE = "idle"                      # 空閒（靜音）
    SPEECH_DETECTED = "speech"         # 檢測到語音
    KEYWORD_DETECTED = "keyword"       # 檢測到喚醒詞


class AudioMonitorService:
    """
    音訊監聽協調服務
    
    並行運行 VAD 和 KWS：
    - VAD: 作為「驗證器」，確認是否為真實語音
    - KWS: 持續運行，檢測喚醒詞（避免漏掉開頭音節）
    
    使用環形緩衝區保留最近 N 秒音訊，用於後續處理
    """
    
    def __init__(
        self,
        wake_words: Optional[List[str]] = None,
        vad_threshold: float = 0.5,
        kws_threshold: float = 0.5,
        buffer_duration: float = 1.5,
        keyword_cooldown: float = 1.0,
        sample_rate: int = 16000
    ):
        """
        初始化音訊監聽服務
        
        Args:
            wake_words: 喚醒詞列表，預設 ["hey_jarvis"]
            vad_threshold: VAD 檢測閾值（0.0-1.0）
            kws_threshold: KWS 檢測閾值（0.0-1.0）
            buffer_duration: 環形 buffer 時長（秒），預設 1.5
            keyword_cooldown: KWS Cooldown（秒），預設 1.0
            sample_rate: 音訊採樣率（Hz），必須是 16000
        """
        if sample_rate != 16000:
            raise ValueError(f"音訊採樣率必須是 16000 Hz，當前: {sample_rate} Hz")
        
        self.sample_rate = sample_rate
        self.buffer_duration = buffer_duration
        self.wake_words = wake_words or ["hey_jarvis"]
        self.keyword_cooldown = keyword_cooldown
        
        # 初始化 VAD 和 KWS 服務
        logger.info("正在初始化 AudioMonitorService...")
        self.vad_service = SileroVADService()
        
        # 直接創建 KWS 實例
        self.kws_service = KeywordSpottingService(
            wake_words=self.wake_words,
            threshold=kws_threshold
        )
        
        # 環形 buffer（供 KWS 使用：儲存最近 1.5 秒音訊）
        self.buffer_size = int(sample_rate * buffer_duration)
        self.audio_buffer = deque(maxlen=self.buffer_size)
        
        # VAD Debounce
        self.vad_debounce_threshold = 3  # 連續 3 個 chunk 才確認
        self.speech_chunk_counter = 0
        
        # KWS Cooldown
        self.last_keyword_time: Optional[float] = None
        
        # 統計資訊
        self.stats = {
            "total_chunks": 0,
            "speech_chunks": 0,
            "silence_chunks": 0,
            "keywords_detected": 0,  # 成功檢測到的喚醒詞次數
            "cooldown_ignored": 0
        }
        
        logger.info("✅ AudioMonitorService 已啟動")
        logger.info(f"   VAD 閾值: {vad_threshold}")
        logger.info(f"   VAD Debounce: {self.vad_debounce_threshold} chunks")
        logger.info(f"   KWS 閾值: {kws_threshold}")
        logger.info(f"   KWS Cooldown: {keyword_cooldown} 秒")
        logger.info(f"   監聽喚醒詞: {self.wake_words}")
        logger.info(f"   Buffer 時長: {buffer_duration} 秒")
    
    def process_audio_chunk(self, audio_chunk: bytes) -> Dict:
        """
        處理音訊塊（VAD Debounce + 串聯 KWS）
        
        流程：
        1. VAD 檢測單一 chunk
        2. VAD Debounce（連續 3 個 chunk 才確認）
        3. VAD 通過後觸發 KWS（使用環形 buffer 1.5 秒音訊）
        
        Args:
            audio_chunk: 音訊資料（bytes 格式，int16 PCM，512 samples = 32ms）
        
        Returns:
            事件字典：
            - {"event": "silence"}
            - {"event": "speech", "duration": float}
            - {"event": "keyword_detected", "keyword": str, "timestamp": float}
        """
        try:
            # 轉換為 numpy array
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # 加入環形 buffer
            self.audio_buffer.extend(audio_int16)
            
            # 更新統計
            self.stats["total_chunks"] += 1
            
            # Step 1: VAD 檢測單一 chunk
            is_speech = self.vad_service.detect(audio_chunk)
            
            # Step 2: VAD Debounce
            if is_speech:
                self.speech_chunk_counter += 1
                logger.debug(f"VAD: 語音 chunk={self.speech_chunk_counter}")
                
                # 連續 3 個 chunk 才確認是語音
                if self.speech_chunk_counter >= self.vad_debounce_threshold:
                    self.stats["speech_chunks"] += 1
                    
                    # Step 3: 觸發 KWS 檢測（用環形 buffer 1.5 秒音訊）
                    keyword_event = self._check_keyword()
                    
                    if keyword_event:
                        # 檢測到關鍵詞
                        return keyword_event
                    else:
                        # 沒有關鍵詞，返回 speech 事件
                        duration = self.speech_chunk_counter * 0.032  # 每個 chunk 32ms
                        return {
                            "event": "speech",
                            "duration": duration
                        }
                else:
                    # 還不到 3 個 chunk，暫時返回 silence（等待累積）
                    return {"event": "silence"}
            else:
                # 靜音，重置計數器
                if self.speech_chunk_counter > 0:
                    logger.debug(f"VAD: 語音結束（持續 {self.speech_chunk_counter} chunks）")
                self.speech_chunk_counter = 0
                self.stats["silence_chunks"] += 1
                
                return {"event": "silence"}
            
        except Exception as e:
            logger.error(f"❌ 處理音訊塊時發生錯誤: {e}")
            return {"event": "error", "message": str(e)}
    
    def _check_keyword(self) -> Optional[Dict]:
        """
        使用環形 buffer 1.5 秒音訊進行 KWS 檢測（帶 cooldown）
        
        Returns:
            - 檢測到關鍵詞：{"event": "keyword_detected", "keyword": str, "timestamp": float}
            - 未檢測到或冷卻期內：None
        """
        current_time = time.time()
        
        # 檢查 cooldown（避免重複觸發）
        if self.last_keyword_time and (current_time - self.last_keyword_time) < self.keyword_cooldown:
            time_since_last = current_time - self.last_keyword_time
            self.stats["cooldown_ignored"] += 1
            logger.debug(f"🕐 KWS 在冷卻期內（距上次 {time_since_last:.2f}s）")
            return None
        
        # 確認環形 buffer 有足夠數據（1.5 秒 = 24000 samples）
        if len(self.audio_buffer) < self.buffer_size:
            logger.debug(f"⚠️ Buffer 不足（{len(self.audio_buffer)}/{self.buffer_size}）")
            return None
        
        # 使用環形 buffer 進行 KWS 檢測
        audio_array = np.array(self.audio_buffer, dtype=np.int16)
        result = self.kws_service.detect(audio_array.tobytes())
        
        if result:
            # 檢測到關鍵詞
            detected_keyword, confidence = result
            self.last_keyword_time = current_time
            self.stats["keywords_detected"] += 1
            
            # 清空環形 buffer（避免重複觸發）
            self.audio_buffer.clear()
            logger.info(f"🎤 檢測到關鍵詞: {detected_keyword} (信心度: {confidence:.3f})")
            
            return {
                "event": "keyword_detected",
                "keyword": detected_keyword,
                "timestamp": current_time,
                "confidence": float(confidence)  # 轉換為 Python float（JSON 可序列化）
            }
        
        return None
    
    def get_buffer_audio(self, duration: Optional[float] = None) -> bytes:
        """
        獲取緩衝區中的音訊
        
        Args:
            duration: 要獲取的時長（秒），None 表示獲取全部
        
        Returns:
            音訊資料（bytes 格式，int16 PCM）
        """
        if duration is None:
            # 返回全部緩衝區
            audio_array = np.array(self.audio_buffer, dtype=np.int16)
        else:
            # 返回最近 N 秒
            samples = int(self.sample_rate * duration)
            samples = min(samples, len(self.audio_buffer))
            
            # 從緩衝區末尾取出指定長度
            audio_array = np.array(
                list(self.audio_buffer)[-samples:],
                dtype=np.int16
            )
        
        return audio_array.tobytes()
    
    def _get_vad_probability(self, audio_chunk: bytes) -> float:
        """
        獲取 VAD 原始概率（用於調試和微調）
        
        Args:
            audio_chunk: 音訊資料
            
        Returns:
            語音概率（0.0-1.0）
        """
        try:
            # 呼叫 VAD 服務的內部方法獲取概率
            # 注意：這需要修改 VAD 服務以暴露概率
            # 暫時使用簡單方法：重新檢測
            import numpy as np
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            audio_input = audio_float32.reshape(1, -1)
            
            ort_inputs = {
                'input': audio_input,
                'sr': np.array(self.vad_service.sample_rate, dtype=np.int64),
                'state': self.vad_service.state
            }
            
            ort_outputs = self.vad_service.session.run(None, ort_inputs)
            return float(ort_outputs[0][0][0])
        except Exception as e:
            logger.debug(f"無法獲取 VAD 概率: {e}")
            return 0.0
    
    def reset(self):
        """重置所有狀態"""
        logger.info("重置 AudioMonitorService 狀態")
        
        # 清空緩衝區
        self.audio_buffer.clear()
        
        # 重置 VAD Debounce 計數器
        self.speech_chunk_counter = 0
        
        # 重置服務狀態
        self.vad_service.reset()
        self.kws_service.reset()
        
        # 重置狀態追蹤
        self.current_state = MonitorState.IDLE
        self.speech_start_time = None
        self.last_event_time = time.time()
        self.last_keyword_time = None  # 重置冷卻期
    
    def get_stats(self) -> Dict:
        """
        獲取服務統計資訊
        
        Returns:
            包含統計資料的字典
        """
        total = self.stats["total_chunks"]
        
        return {
            "current_state": self.current_state.value,
            "buffer_size": len(self.audio_buffer),
            "buffer_capacity": self.buffer_size,
            "buffer_duration": len(self.audio_buffer) / self.sample_rate,
            "total_chunks": total,
            "speech_chunks": self.stats["speech_chunks"],
            "silence_chunks": self.stats["silence_chunks"],
            "keyword_detections": self.stats["keyword_detections"],
            "false_alarms": self.stats["false_alarms"],
            "speech_ratio": (
                self.stats["speech_chunks"] / total * 100 if total > 0 else 0
            ),
            "false_alarm_rate": (
                self.stats["false_alarms"] / 
                max(self.stats["keyword_detections"] + self.stats["false_alarms"], 1) * 100
            )
        }
    
    def set_vad_threshold(self, threshold: float):
        """動態調整 VAD 閾值"""
        self.vad_service.set_threshold(threshold)
        logger.info(f"VAD 閾值已調整為: {threshold}")
    
    def set_kws_threshold(self, threshold: float):
        """動態調整 KWS 閾值"""
        self.kws_service.set_threshold(threshold)
        logger.info(f"KWS 閾值已調整為: {threshold}")
