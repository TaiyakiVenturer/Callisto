"""
Silero VAD 服務 (ONNX Runtime 版本)
使用 ONNX Runtime 實現高效能的語音活動檢測（Voice Activity Detection）
"""

import logging
import numpy as np
import onnxruntime as ort
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class SileroVADService:
    """
    Silero VAD 語音活動檢測服務
    
    使用 ONNX Runtime 運行 Silero VAD 模型，實現實時語音檢測
    - CPU 友好，不需要 GPU
    - 低延遲（<10ms）
    - 高準確率（>90%）
    """
    
    # Silero VAD ONNX 模型下載 URL
    # 手動下載: https://huggingface.co/onnx-community/silero-vad/blob/main/onnx
    # 下載 model.onnx 並重命名為 silero_vad.onnx 放到 backend/models/ 目錄
    MODEL_URL = "https://huggingface.co/onnx-community/silero-vad/blob/main/onnx/model.onnx"
    
    def __init__(
        self,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        enable_agc: bool = False,
        target_rms_db: float = -15.0,
        limiter_threshold_db: float = -3.0,
        max_gain_db: float = 60.0,
        smoothing_factor: float = 0.1,
        noise_gate_db: float = -70.0
    ):
        """
        初始化 Silero VAD 服務
        
        Args:
            threshold: 語音檢測閾值（0.0-1.0），預設 0.5
                      - 較低值：更敏感，可能誤判噪音為語音
                      - 較高值：更保守，可能漏檢輕聲語音
            sample_rate: 音訊採樣率，預設 16000 Hz
            enable_agc: 是否啟用 AGC 自動增益控制，預設 False
            target_rms_db: AGC 目標 RMS 音量（dBFS），預設 -18.0
            limiter_threshold_db: 限幅器閾值（dBFS），預設 -3.0
            max_gain_db: 最大增益（dB），預設 20.0
            smoothing_factor: 增益平滑係數（0-1），預設 0.1
            noise_gate_db: 噪音門限（dBFS），低於此值不應用 AGC，預設 -50.0
        """
        self.threshold = threshold
        self.sample_rate = sample_rate
        
        # AGC 參數
        self.enable_agc = enable_agc
        self.target_rms_db = target_rms_db
        self.limiter_threshold_db = limiter_threshold_db
        self.max_gain_db = max_gain_db
        self.smoothing_factor = smoothing_factor
        self.noise_gate_db = noise_gate_db
        
        # AGC 狀態
        self.current_gain_db = 0.0
        
        # 下載並載入 ONNX 模型
        model_path = self._ensure_model_downloaded()
        
        # 初始化 ONNX Runtime Session（僅使用 CPU）
        logger.info("正在載入 Silero VAD ONNX 模型...")
        self.session = ort.InferenceSession(
            model_path,
            providers=['CPUExecutionProvider']
        )
        
        # 初始化模型狀態（h 和 c 是 LSTM 的隱藏狀態）
        self._reset_states()
        
        logger.info(f"✅ Silero VAD 服務已啟動（閾值: {threshold}, 採樣率: {sample_rate} Hz）")
    
    def _ensure_model_downloaded(self) -> str:
        """
        確保 ONNX 模型已下載
        
        Returns:
            模型檔案的絕對路徑
        """
        # 模型儲存在 backend/models/ 目錄
        current_dir = Path(__file__).parent
        while current_dir.name != "backend":
            current_dir = Path(current_dir).parent
        models_dir = current_dir / "models"
        models_dir.mkdir(exist_ok=True)
        
        model_path = models_dir / "silero_vad.onnx"
        
        if model_path.exists():
            logger.info(f"使用現有模型: {model_path}")
            return str(model_path)
        
        # 下載模型
        logger.info(f"正在下載 Silero VAD 模型從: {self.MODEL_URL}")
        try:
            response = requests.get(self.MODEL_URL, timeout=60)
            response.raise_for_status()
            
            model_path.write_bytes(response.content)
            logger.info(f"✅ 模型下載完成: {model_path}")
            
        except Exception as e:
            logger.error(f"❌ 模型下載失敗: {e}")
            raise RuntimeError(f"無法下載 Silero VAD 模型: {e}")
        
        return str(model_path)
    
    def _reset_states(self):
        """重置 LSTM 隱藏狀態"""
        # Silero VAD ONNX Community 模型的狀態維度：[2, 1, 128]
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        logger.debug(f"VAD 狀態已重置: shape={self.state.shape}, dtype={self.state.dtype}")
    
    def _calculate_rms_db(self, audio_float32: np.ndarray) -> float:
        """
        計算音頻的 RMS（均方根）音量，單位為 dBFS
        
        Args:
            audio_float32: 正規化的音頻數據（-1 到 1）
            
        Returns:
            RMS 音量（dBFS），範圍約 -60dB 到 0dB
        """
        # 計算 RMS
        rms = np.sqrt(np.mean(audio_float32 ** 2))
        
        # 處理靜音情況（避免 log10(0)）
        if rms < 1e-10:
            return -60.0  # 極小值，代表靜音
        
        # 轉換為 dBFS
        rms_db = 20 * np.log10(rms)
        
        return float(rms_db)
    
    def _calculate_gain_db(self, current_rms_db: float) -> float:
        """
        根據當前 RMS 計算需要的增益，並應用平滑處理
        
        Args:
            current_rms_db: 當前音頻的 RMS（dBFS）
            
        Returns:
            平滑後的增益值（dB）
        """
        # 計算目標增益
        target_gain = self.target_rms_db - current_rms_db
        
        # 限制最大增益（避免過度放大）
        target_gain = min(target_gain, self.max_gain_db)
        
        # 限制最小增益（避免過度壓縮）
        target_gain = max(target_gain, -10.0)
        
        # 平滑處理（exponential moving average）
        self.current_gain_db = (
            (1 - self.smoothing_factor) * self.current_gain_db +
            self.smoothing_factor * target_gain
        )
        
        return self.current_gain_db
    
    def _apply_limiter(self, audio_float32: np.ndarray) -> np.ndarray:
        """
        應用限幅器，防止音頻削波失真（爆音）
        
        Args:
            audio_float32: 音頻數據（-1 到 1）
            
        Returns:
            限幅後的音頻數據
        """
        # 將 dB 轉換為線性值
        threshold = 10 ** (self.limiter_threshold_db / 20)
        
        # 硬限制峰值
        limited = np.clip(audio_float32, -threshold, threshold)
        
        return limited
    
    def _apply_agc(self, audio_float32: np.ndarray) -> np.ndarray:
        """
        應用完整的 AGC 處理流程
        
        Args:
            audio_float32: 正規化的音頻數據（-1 到 1）
            
        Returns:
            AGC 處理後的音頻數據
        """
        # 1. 計算當前 RMS
        current_rms_db = self._calculate_rms_db(audio_float32)
        
        # 2. 噪音門限：極低音量不處理（避免放大純雜音）
        if current_rms_db < self.noise_gate_db:
            logger.debug(f"AGC: RMS {current_rms_db:.1f}dB 低於噪音門限 {self.noise_gate_db}dB，跳過處理")
            return audio_float32
        
        # 3. 計算需要的增益
        gain_db = self._calculate_gain_db(current_rms_db)
        
        # 4. 轉換為線性增益
        linear_gain = 10 ** (gain_db / 20)
        
        # 5. 應用增益
        amplified = audio_float32 * linear_gain
        
        # 6. 應用限幅器防止爆音
        limited = self._apply_limiter(amplified)
        
        logger.debug(
            f"AGC: RMS {current_rms_db:.1f}dB → 增益 {gain_db:.1f}dB → "
            f"目標 {self.target_rms_db:.1f}dB"
        )
        
        return limited
    
    def detect(self, audio_chunk: bytes) -> bool:
        """
        檢測音訊塊是否包含語音
        
        Args:
            audio_chunk: 音訊資料（bytes 格式）
                        - 格式：int16 PCM
                        - 聲道：單聲道
                        - 採樣率：16000 Hz
                        - 建議長度：512 或 1024 samples (32ms 或 64ms)
        
        Returns:
            True: 檢測到語音
            False: 靜音或噪音
        
        Raises:
            ValueError: 音訊格式錯誤
        """
        try:
            # 將 bytes 轉換為 numpy array (int16)
            audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
            
            # 正規化到 [-1, 1] (float32)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            
            # 應用 AGC（如果啟用）
            if self.enable_agc:
                audio_float32 = self._apply_agc(audio_float32)
            
            # 檢查音訊長度（Silero VAD 模型要求固定 512 samples）
            logger.debug(f"VAD 接收音訊塊: {len(audio_float32)} samples ({len(audio_chunk)} bytes)")
            
            if len(audio_float32) < 512:
                logger.warning(f"音訊塊過短 ({len(audio_float32)} samples)，建議至少 512 samples")
                if len(audio_float32) == 0:
                    raise ValueError("音訊塊為空")
                # 過短的音訊直接返回 False（靜音）
                return False
            
            # 準備 ONNX 輸入
            # input: [batch_size, samples] - 音訊數據
            # sr: [] (scalar) - 採樣率
            # state: [2, batch_size, 128] - LSTM 狀態
            audio_input = audio_float32.reshape(1, -1)
            logger.debug(f"VAD 輸入形狀: audio={audio_input.shape}, state={self.state.shape}, sr={self.sample_rate}")
            logger.debug(f"VAD state dtype: {self.state.dtype}, audio dtype: {audio_input.dtype}")
            
            ort_inputs = {
                'input': audio_input,
                'sr': np.array(self.sample_rate, dtype=np.int64),
                'state': self.state
            }
            
            # 執行推理
            ort_outputs = self.session.run(None, ort_inputs)
            
            # 輸出：
            # output: [batch_size, 1] - 語音概率
            # stateN: [2, batch_size, 128] - 新的 LSTM 狀態
            speech_prob = float(ort_outputs[0][0][0])
    
            # 更新狀態（保持連續性）
            # 強制確保形狀為 [2, 1, 128]
            new_state = ort_outputs[1]
            logger.debug(f"VAD state shape: input={self.state.shape}, output={new_state.shape}, output_dtype={new_state.dtype}")
            
            # 強制 reshape 為正確的形狀
            try:
                # 如果形狀已經正確，直接使用
                if new_state.shape == (2, 1, 128):
                    self.state = new_state
                else:
                    # 嘗試 reshape（期望總共 256 個元素）
                    if new_state.size == 256:
                        self.state = new_state.reshape(2, 1, 128)
                        logger.debug(f"VAD 狀態已 reshape: {new_state.shape} → {self.state.shape}")
                    else:
                        # 如果元素數量不對，重置狀態
                        logger.error(f"VAD 狀態元素數量錯誤: {new_state.size}，期望 256，重置狀態")
                        self._reset_states()
            except Exception as reshape_err:
                logger.error(f"VAD 狀態更新失敗: {reshape_err}，重置狀態")
                self._reset_states()
            
            # 根據閾值判斷
            is_speech = bool(speech_prob > self.threshold)
            
            logger.debug(f"VAD: 語音概率 = {speech_prob:.3f}, 檢測結果 = {'語音' if is_speech else '靜音'}")
            
            return is_speech
            
        except Exception as e:
            logger.error(f"VAD 檢測錯誤: {e}")
            # 發生錯誤時重置狀態，避免狀態累積
            logger.warning("VAD 檢測錯誤，重置狀態")
            self._reset_states()
            raise ValueError(f"音訊檢測失敗: {e}")
    
    def reset(self):
        """
        重置 VAD 狀態
        
        使用場景：
        - 開始新的音訊流
        - 長時間靜音後恢復檢測
        - 切換不同的音訊來源
        """
        logger.debug("重置 VAD 狀態")
        self._reset_states()
        # 重置 AGC 狀態
        if self.enable_agc:
            self.current_gain_db = 0.0
            logger.debug("AGC 狀態已重置")
    
    def set_threshold(self, threshold: float):
        """
        動態調整檢測閾值
        
        Args:
            threshold: 新的閾值（0.0-1.0）
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(f"閾值必須在 0.0 到 1.0 之間，當前值: {threshold}")
        
        logger.info(f"VAD 閾值從 {self.threshold} 調整為 {threshold}")
        self.threshold = threshold
    
    def get_stats(self) -> dict:
        """
        獲取 VAD 服務狀態資訊
        
        Returns:
            包含服務狀態的字典
        """
        stats = {
            "threshold": self.threshold,
            "sample_rate": self.sample_rate,
            "model": "Silero VAD (ONNX Runtime)",
            "providers": self.session.get_providers(),
            "status": "ready"
        }
        
        # 如果啟用 AGC，添加 AGC 資訊
        if self.enable_agc:
            stats["agc"] = {
                "enabled": True,
                "target_rms_db": self.target_rms_db,
                "limiter_threshold_db": self.limiter_threshold_db,
                "max_gain_db": self.max_gain_db,
                "current_gain_db": round(self.current_gain_db, 2),
                "noise_gate_db": self.noise_gate_db
            }
        else:
            stats["agc"] = {"enabled": False}
        
        return stats
    
    def trim_silence(
        self, 
        audio_path: str, 
        output_path: Optional[str] = None
    ) -> str:
        """
        裁剪音訊前後的靜音部分
        
        使用 Silero VAD 檢測語音活動，移除音訊開頭和結尾的靜音部分
        
        Args:
            audio_path: 輸入音訊檔案路徑 (WAV 格式)
            output_path: 輸出音訊檔案路徑，若為 None 則覆蓋原檔案
            
        Returns:
            輸出音訊檔案路徑
            
        Raises:
            ValueError: 音訊格式不符合要求
        """
        import wave
        
        if output_path is None:
            output_path = audio_path
        
        try:
            # 讀取 WAV 檔案
            with wave.open(audio_path, 'rb') as wf:
                # 驗證格式
                if wf.getnchannels() != 1:
                    raise ValueError("音訊必須是單聲道 (mono)")
                if wf.getsampwidth() != 2:
                    raise ValueError("音訊必須是 16-bit")
                
                sample_rate = wf.getframerate()
                
                # 讀取所有音訊資料
                audio_data = wf.readframes(wf.getnframes())
            
            # 重置 VAD 狀態
            self.reset()
            
            # 將音訊切分成 512 samples (32ms @ 16kHz) 的 chunks
            chunk_size = 512
            frames = []
            voiced_frames = []
            
            # 將 bytes 轉換為 int16 array
            audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
            
            # 處理每個 chunk
            for i in range(0, len(audio_int16), chunk_size):
                chunk = audio_int16[i:i + chunk_size]
                
                # 如果 chunk 不足長度，補零
                if len(chunk) < chunk_size:
                    chunk = np.pad(chunk, (0, chunk_size - len(chunk)), mode='constant')
                
                frames.append(chunk)
                
                # VAD 檢測
                try:
                    chunk_bytes = chunk.astype(np.int16).tobytes()
                    is_speech = self.detect(chunk_bytes)
                    voiced_frames.append(is_speech)
                except Exception as e:
                    logger.warning(f"VAD 檢測失敗: {e}，假設為語音")
                    voiced_frames.append(True)
            
            # 找到第一個和最後一個語音 frame
            if not any(voiced_frames):
                logger.warning("未檢測到語音活動，返回原始音訊")
                return audio_path
            
            start_idx = voiced_frames.index(True)
            end_idx = len(voiced_frames) - 1 - voiced_frames[::-1].index(True)
            
            # 保留前後各 1 個 frame 作為緩衝
            start_idx = max(0, start_idx - 1)
            end_idx = min(len(frames) - 1, end_idx + 1)
            
            # 重組音訊
            trimmed_frames = frames[start_idx:end_idx + 1]
            trimmed_audio = np.concatenate(trimmed_frames)
            
            # 如果裁剪後音訊過短，返回原始音訊
            if end_idx - start_idx + 1 < 20:
                logger.warning(f"裁剪後語音過短 ({end_idx - start_idx + 1} frames)，判定為無效，返回原始音訊")
                return audio_path

            # 寫入 WAV 檔案
            with wave.open(output_path, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(trimmed_audio.astype(np.int16).tobytes())
            
            logger.info(f"Silero VAD 裁剪完成: {len(frames)} frames -> {end_idx - start_idx + 1} frames")
            return output_path
            
        except Exception as e:
            logger.error(f"Silero VAD 裁剪失敗: {e}")
            raise
    
    def convert_to_vad_format(self, audio_path: str, output_path: str) -> str:
        """
        將音訊轉換為 VAD 支援的格式 (16kHz, mono, 16-bit)
        
        Args:
            audio_path: 輸入音訊檔案路徑
            output_path: 輸出音訊檔案路徑
            
        Returns:
            輸出音訊檔案路徑
        """
        try:
            from pydub import AudioSegment
            
            # 載入音訊
            audio = AudioSegment.from_file(audio_path)
            
            # 轉換格式
            audio = audio.set_frame_rate(self.sample_rate)  # 使用配置的採樣率
            audio = audio.set_channels(1)                    # mono
            audio = audio.set_sample_width(2)                # 16-bit
            
            # 匯出為 WAV
            audio.export(output_path, format="wav")
            
            logger.info(f"音訊格式轉換完成: {audio_path} -> {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"音訊格式轉換失敗: {e}")
            raise


