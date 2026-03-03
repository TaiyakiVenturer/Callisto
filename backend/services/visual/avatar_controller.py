import requests
import time
import numpy as np
import pyaudio
from typing import Literal
import logging
import re

from services.audio_processing.gpt_sovits_service import GPTSoVITSV2Client
from .vmm_service import VMMController

# 設定日誌
logger = logging.getLogger(__name__)

class AvatarController:
    """負責控制 TTS 與 VMM 虛擬形象動作控制器類別"""
    def __init__(self, tts_client: GPTSoVITSV2Client, vmm_service: VMMController):
        self.tts_client = tts_client
        self.vmm_service = vmm_service

        self.p = pyaudio.PyAudio()
        self.current_mouth_open = 0
        self.smooth_factor = 0.5

    def __del__(self):
        if hasattr(self, 'p') and self.p is not None:
            self.p.terminate()

    def perform(self, 
            response: requests.Request, 
            volume: float = 1.0, 
            emote: Literal["Neutral", "Joy", "Angry", "Sorrow", "Fun", "Surprised", "Blink"] = "Neutral",
            level: float = 1.0
        ):
        """依照收到音訊, 播放 TTS 及控制 VMM 虛擬角色開口及表情"""
        cable_index = self.vmm_service.find_cable_index()
        generator = self.tts_client.get_stream_generator(response, volume)

        stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=32000,
            output=True,
            output_device_index=cable_index
        )

        try:
            # 重置VMM表情
            self.vmm_service.send_expression("Neutral", 1.0)
            self.vmm_service.send_lip_sync(0.0)

            last_expression_time = 0
            self.current_mouth_open = 0
            for chunk in generator:
                # 播放音訊
                stream.write(chunk)

                mouth_open = self._cal_mouth_open(chunk, volume)
                # 有表情時嘴巴開合程度削弱
                mouth_open = mouth_open if emote == "Neutral" else mouth_open * 0.7
                self.vmm_service.send_lip_sync(mouth_open)

                # 0.5秒維持一次表情
                current_time = time.time()
                if current_time - last_expression_time > 0.4:
                    self.vmm_service.send_expression(emote, level)
                    last_expression_time = current_time

            # 重置VMM表情
            self.vmm_service.send_expression("Neutral", 1.0)
            self.vmm_service.send_lip_sync(0.0)

        except Exception as e:
            print("Error on perform:", e)
        finally:
            # Clean up audio resources
            if stream is not None:
                stream.stop_stream()
                stream.close()

    def _cal_mouth_open(self, chunk: bytes, volume: float) -> float:
        """依照接收音訊計算開口大小"""
        # 把二進制音訊轉成 numpy array 數值
        audio_data = np.frombuffer(chunk, dtype=np.int16)

        # 計算音量 (RMS - Root Mean Square)
        audio_volume = np.linalg.norm(audio_data) / np.sqrt(len(audio_data)) / volume
        
        # 將音量映射到 0.0 ~ 1.0 的嘴巴張開度
        # 這裡的 3000 是最大值，依實際音量調整
        mouth_open = min(max(audio_volume / 3000, 0), 1.0)
        
        # 公式： 新位置 = (舊位置 * 平滑係數) + (目標位置 * (1 - 平滑係數))
        self.current_mouth_open = (self.current_mouth_open * self.smooth_factor) + (mouth_open * (1 - self.smooth_factor))

        return self.current_mouth_open

    def export_emote(self, raw_text: str):
        """
        處理 LLM 回傳的原始文字：
        1. 解析表情標籤並發送至 VMM
        2. 清理標籤，將乾淨的文字送往 TTS
        """
        # 使用正規表達式搜尋 [EXP: Name]
        match = re.search(r"\[EXP:\s*(\w+)\]", raw_text)
        
        # 預設表情
        emote = "Neutral"
        clean_text = raw_text
        
        if match:
            emote = match.group(1)
            # 移除標籤，避免 TTS 唸出 "[EXP: Joy]"
            clean_text = re.sub(r"\[EXP:\s*\w+\]", "", raw_text).strip()
            
            # 檢查解析出的表情是否在允許名單內，避免 LLM 亂噴字
            valid_emotes = ["Neutral", "Joy", "Angry", "Sorrow", "Fun", "Surprised"]
            if emote not in valid_emotes:
                emote = "Neutral"
        
        return clean_text, emote
