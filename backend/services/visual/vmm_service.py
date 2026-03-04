import pyaudio
from pythonosc import udp_client
from typing import Literal
import logging

from config import load_config

# 設定日誌
logger = logging.getLogger(__name__)

class VMMController:
    """負責傳送VMM訊號的控制類別"""
    def __init__(self):
        config = load_config()["vmm"]
        self.client = udp_client.SimpleUDPClient(config["host"], config["port"])

        self.last_expression_time = None

    def find_cable_index(self) -> int:
        """掃描尋找虛擬輸出裝置 CABLE Input 的 Index"""
        p = pyaudio.PyAudio()
        try:
            # 列出所有裝置來尋找虛擬輸出裝置
            for i in range(p.get_device_count()):
                dev_info = p.get_device_info_by_index(i)
                # 注意：VB-Audio Virtual Cable 的輸入端叫 "CABLE Input"
                if "CABLE Input" in dev_info.get('name'):
                    return i
            logger.warning("⚠️ 警告: 找不到 CABLE Input，將使用預設輸出裝置。")
            return None
        finally:
            p.terminate()

    def send_lip_sync(self, value: int) -> None:
        """向 VMM 傳送開口訊號"""
        # 控制 VMM 的 "MouthOpen" 參數 (這是標準 BlendShape)
        # 或者嘗試用 "A" (母音 A)
        self.client.send_message("/VMC/Ext/Blend/Val", ["A", float(value)])
        self.client.send_message("/VMC/Ext/Blend/Apply", [])
    
    def send_expression(self, emote: Literal["Neutral", "Joy", "Angry", "Sorrow", "Fun", "Surprised", "Blink"] = "Neutral", level: float = 1.0) -> None:
        """向 VMM 傳送表情訊號"""
        # 1. 發送數值
        self.client.send_message("/VMC/Ext/Blend/Val", [emote, level])
        # 2. 立即套用
        self.client.send_message("/VMC/Ext/Blend/Apply", [])