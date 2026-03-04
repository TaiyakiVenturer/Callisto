"""
VoiceMonitorWebSocketService - WebSocket 音訊監聽服務

負責管理 WebSocket 連接的音訊流處理，包含：
- Producer-Consumer 架構的佇列管理
- AudioMonitorService 的生命週期管理
- VAD 與 KWS 檢測事件的推送
- 模式切換支援（monitoring / vad_only）
"""

import asyncio
import logging
import time
import json
from typing import Optional
from fastapi import WebSocket

from services.monitoring.audio_monitor_service import AudioMonitorService
from services.core.voice_chat_service import VoiceChatService
from config import load_config

logger = logging.getLogger(__name__)

_wake_words: list[str] = load_config()["kws"]["wake_words"]

# 靜音檢測配置常數
SILENCE_DURATION = 3.0  # 秒
CHUNK_DURATION = 0.032  # 32ms (512 samples @ 16kHz)
SILENCE_CHUNKS_THRESHOLD = int(SILENCE_DURATION / CHUNK_DURATION)  # 94 chunks

VAD_WARMUP_DURATION = 3.0  # VAD 模式啟動後的緩衝期（秒）
VAD_WARMUP_CHUNKS = int(VAD_WARMUP_DURATION / CHUNK_DURATION)  # 94 chunks


class VoiceMonitorWebSocketService:
    """
    WebSocket 音訊監聽服務
    
    支援兩種模式：
    - 'monitoring': 持續監聽模式（VAD + KWS 檢測）
    - 'vad_only': 僅 VAD 檢測模式（用於按鈕錄音）
    """
    
    def __init__(
        self,
        websocket: WebSocket,
        voice_service: VoiceChatService,
        mode: str = 'monitoring',
        vad_threshold: float = 0.6,
        kws_threshold: float = 0.7,
        buffer_duration: float = 1.5,
        keyword_cooldown: float = 1.0
    ):
        """
        初始化 WebSocket 音訊監聽服務

        Args:
            websocket: FastAPI WebSocket 連接
            voice_service: VoiceChatService 實例（依賴注入）
            mode: 運行模式 ('monitoring' 或 'vad_only')
            vad_threshold: VAD 檢測閾值
            kws_threshold: KWS 檢測閾值
            buffer_duration: 環形 buffer 持續時間（秒）
            keyword_cooldown: KWS cooldown 時間（秒）
        """
        self.websocket = websocket
        self.voice_service = voice_service
        self.mode = mode
        
        # VAD 靜音檢測計數器
        self.silence_counter = 0
        self.vad_chunk_counter = 0  # 用於 VAD 模式的緩衝期計數
        
        # 初始化 AudioMonitorService
        self.monitor_service = AudioMonitorService(
            wake_words=_wake_words,
            vad_threshold=vad_threshold,
            kws_threshold=kws_threshold,
            buffer_duration=buffer_duration,
            keyword_cooldown=keyword_cooldown
        )
        self.monitor_service.reset()
        
        # 佇列（會在 start() 中初始化）
        self.audio_queue: Optional[asyncio.Queue] = None
        self.event_queue: Optional[asyncio.Queue] = None
        
        # 背景任務
        self._processor_task: Optional[asyncio.Task] = None
        self._sender_task: Optional[asyncio.Task] = None
        self._tracking_task: Optional[asyncio.Task] = None  # 狀態追蹤任務
        
        # 追蹤狀態
        self.is_tracking = False
        self._last_transcript = ""
        self._last_response = ""
        self._last_is_done = False

        # 統計計數器
        self._queue_full_count = 0
        
    async def start(self):
        """
        啟動服務：初始化佇列、啟動背景任務、發送連接成功事件
        """
        # 初始化佇列
        self.audio_queue = asyncio.Queue(maxsize=50)
        self.event_queue = asyncio.Queue(maxsize=20)
        
        # 啟動背景任務
        self._processor_task = asyncio.create_task(
            self._audio_processor()
        )
        self._sender_task = asyncio.create_task(
            self._event_sender()
        )
        
        # 發送連接成功事件
        await self.websocket.send_json({
            "type": "connected",
            "timestamp": time.time(),
            "message": "WebSocket 連接已建立"
        })
        
        logger.info(f"✅ WebSocket 連接已建立: {self.websocket.client}, 模式: {self.mode}")
        
    async def handle_audio_stream(self):
        """
        主循環：接收 WebSocket 音訊流，放入處理佇列
        
        這是 Producer，負責接收前端發送的音訊數據
        同時支持 JSON 命令處理（模式切換）
        """
        while True:
            try:
                # 設定接收超時（快速檢測關閉）
                message = await asyncio.wait_for(
                    self.websocket.receive(),
                    timeout=0.1
                )
                
                # 處理 JSON 命令（模式切換）
                if "text" in message:
                    try:
                        cmd = json.loads(message["text"])
                        await self._handle_command(cmd)
                    except json.JSONDecodeError as e:
                        logger.warning(f"⚠️ 無法解析 JSON 命令: {e}")
                    continue
                
                # 檢查消息類型
                if "bytes" not in message:
                    logger.info(f"🔌 收到關閉訊息，中斷連接: {message}")
                    break
                    
                data = message["bytes"]
                
                # 根據模式處理音訊
                if self.mode == "vad_only":
                    await self._handle_vad_only(data)
                elif self.mode == "monitoring":
                    # 原有邏輯：放入處理佇列
                    try:
                        self.audio_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        self._queue_full_count += 1
                        if self._queue_full_count % 10 == 1:
                            logger.warning(f"⚠️ Audio queue 已滿，已丟棄 {self._queue_full_count} 個音訊塊")
                
            except asyncio.TimeoutError:
                # 超時是正常的（用於檢查連接狀態）
                if self.websocket.client_state.name != 'CONNECTED':
                    logger.info(f"🔌 檢測到客戶端已關閉: {self.websocket.client}")
                    break
                continue
                
    async def switch_mode(self, mode: str):
        """
        切換服務模式
        
        Args:
            mode: 'monitoring' (VAD + KWS) 或 'vad_only' (僅 VAD) 或 'idle'
        """
        if mode not in ['monitoring', 'vad_only', 'idle']:
            raise ValueError(f"無效的模式: {mode}，僅支持 'monitoring', 'vad_only' 或 'idle'")
            
        self.mode = mode
        self.vad_chunk_counter = 0  # 重置 VAD 緩衝期計數器
        self.silence_counter = 0  # 重置靜音計數器
        logger.info(f"🔄 模式已切換至: {mode}")
        
    async def cleanup(self):
        """
        清理資源：取消背景任務、重置服務、關閉 WebSocket
        """
        # 停止追蹤
        self.is_tracking = False
        
        # 取消背景任務
        if self._processor_task:
            self._processor_task.cancel()
        if self._sender_task:
            self._sender_task.cancel()
        if self._tracking_task:
            self._tracking_task.cancel()
            
        # 等待任務結束
        tasks_to_wait = []
        if self._processor_task:
            tasks_to_wait.append(self._processor_task)
        if self._sender_task:
            tasks_to_wait.append(self._sender_task)
        if self._tracking_task:
            tasks_to_wait.append(self._tracking_task)
            
        if tasks_to_wait:
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)
        
        # 重置 AudioMonitorService
        if self.monitor_service:
            self.monitor_service.reset()
            logger.info("🧹 AudioMonitorService 已重置")
        
        # 關閉 WebSocket
        try:
            await self.websocket.close()
        except:
            pass  # 連接可能已關閉
            
    # ===== 私有方法：Consumer 邏輯 =====
    
    async def _handle_command(self, cmd: dict):
        """
        處理模式切換命令
        
        Args:
            cmd: JSON 命令對象，包含 type 欄位
        """
        cmd_type = cmd.get("type")
        
        if cmd_type == "start_vad_only":
            await self.switch_mode("vad_only")
            logger.info("🎤 切換至 VAD 錄音模式")
            
        elif cmd_type == "start_monitoring":
            await self.switch_mode("monitoring")
            self.monitor_service.reset()
            logger.info("👂 切換至持續監聽模式")
            
        elif cmd_type == "start_tracking":
            # 啟動狀態追蹤（音頻上傳後）
            self.start_tracking()
            logger.info("🚀 收到啟動追蹤命令")
            
        elif cmd_type == "stop":
            await self.switch_mode("idle")
            logger.info("🚦 切換至空閒模式")
            
        else:
            logger.warning(f"⚠️ 未知的命令類型: {cmd_type}")
    
    async def _handle_vad_only(self, data: bytes):
        """
        VAD 純檢測模式：檢測靜音並推送停止事件
        
        Args:
            data: PCM 音訊數據 (bytes)
        """
        try:
            # 增加 chunk 計數器
            self.vad_chunk_counter += 1
            
            # 緩衝期內不進行靜音判斷（避免喚醒詞後的短暫靜音誤觸發）
            if self.vad_chunk_counter <= VAD_WARMUP_CHUNKS:
                logger.debug(f"🔥 VAD 緩衝期: {self.vad_chunk_counter}/{VAD_WARMUP_CHUNKS}")
                return
            
            # 使用 AudioMonitorService 的 VAD 服務檢測
            # SileroVADService.detect() 接受 bytes 參數
            is_speech = self.monitor_service.vad_service.detect(data)
            
            if is_speech:
                self.silence_counter = 0
            else:
                self.silence_counter += 1
            
            # 檢測到靜音閾值
            if self.silence_counter >= SILENCE_CHUNKS_THRESHOLD:
                await self.websocket.send_json({
                    "type": "stop_recording",
                    "reason": "silence_detected",
                    "silence_duration": SILENCE_DURATION,
                    "timestamp": time.time()
                })
                logger.info(f"🛑 VAD 檢測到 {SILENCE_DURATION} 秒靜音，推送停止事件")
                await self.switch_mode("idle")  # 自動回到 idle
                self.silence_counter = 0  # 重置計數器
                
        except Exception as e:
            logger.error(f"❌ VAD 檢測發生錯誤: {e}")
    
    # ===== Consumer 邏輯 =====
    
    async def _audio_processor(self):
        """
        音訊處理器 (Consumer)
        從 audio_queue 取出音訊塊，處理後將事件放入 event_queue
        僅在 'monitoring' 模式下使用
        """
        try:
            while True:
                chunk = await self.audio_queue.get()
                result = self.monitor_service.process_audio_chunk(chunk)
                if result:
                    await self.event_queue.put(result)
        except asyncio.CancelledError:
            logger.info("Audio processor 已停止")
            raise
            
    async def _event_sender(self):
        """
        事件發送器 (Consumer)
        從 event_queue 取出事件，發送到前端
        """
        try:
            while True:
                result = await self.event_queue.get()
                
                try:
                    if result["event"] == "keyword_detected":
                        await self.websocket.send_json({
                            "type": "keyword",
                            "keyword": result["keyword"],
                            "confidence": result.get("confidence", 0.0),
                            "timestamp": result["timestamp"]
                        })
                        logger.info(f"🎯 檢測到喚醒詞: {result['keyword']}")
                        
                    elif result["event"] == "speech":
                        await self.websocket.send_json({
                            "type": "speech",
                            "duration": result.get("duration", 0.0),
                            "timestamp": time.time()
                        })
                        logger.debug(f"🗣️ 檢測到語音 (持續 {result.get('duration', 0):.1f}s)")
                        
                    elif result["event"] == "silence":
                        pass
                        
                    elif result["event"] == "error":
                        await self.websocket.send_json({
                            "type": "error",
                            "message": result.get("message", "未知錯誤")
                        })
                        logger.error(f"❌ 處理音訊時發生錯誤: {result.get('message')}")
                        
                except Exception as send_error:
                    logger.error(f"❌ 發送事件失敗: {send_error}, 事件類型: {result.get('event')}")
                    # 繼續處理下一個事件，不要停止整個 sender
                    
        except asyncio.CancelledError:
            logger.info("Event sender 已停止")
            raise
    
    # ===== 狀態追蹤 =====
    
    async def _start_status_tracking(self):
        """
        狀態追蹤器
        監控 voice_chat_service.app_state 的變化，並發送對應的 WebSocket 事件。

        TTS 現為同步阻塞（GPT-SoVITS 內部串流），is_done=True 時 TTS 已播完，
        無需額外追蹤 player_queue 狀態。
        """
        logger.info("🔍 開始追蹤 voice_chat_service 狀態...")

        try:
            while self.is_tracking:
                await asyncio.sleep(0.2)  # 每 200ms 檢查一次

                try:
                    app_state = self.voice_service.app_state

                    # 檢查 transcript 變化
                    if app_state.transcript != self._last_transcript:
                        if app_state.transcript and not self._last_transcript:
                            await self.websocket.send_json({
                                "type": "transcribing",
                                "timestamp": time.time()
                            })
                            logger.info("📝 STT 開始轉錄")

                        if app_state.transcript:
                            await self.websocket.send_json({
                                "type": "transcript",
                                "text": app_state.transcript,
                                "timestamp": time.time()
                            })
                            logger.info(f"✅ STT 完成: {app_state.transcript}")

                        self._last_transcript = app_state.transcript

                    # 檢查 response 變化（LLM streaming）
                    if app_state.response != self._last_response:
                        if app_state.response and not self._last_response:
                            await self.websocket.send_json({
                                "type": "generating",
                                "timestamp": time.time()
                            })
                            logger.info("🤖 LLM 開始生成回應")

                        if app_state.response:
                            await self.websocket.send_json({
                                "type": "response",
                                "text": app_state.response,
                                "timestamp": time.time()
                            })
                            logger.debug(f"💬 LLM 回應更新 ({len(app_state.response)} 字)")

                        self._last_response = app_state.response

                    # 檢查是否完成（TTS 同步阻塞，is_done=True 表示含 TTS 全部完成）
                    if app_state.is_done and not self._last_is_done:
                        if app_state.error:
                            await self.websocket.send_json({
                                "type": "error",
                                "message": app_state.error,
                                "timestamp": time.time()
                            })
                            logger.warning(f"⚠️ 處理失敗: {app_state.error}")

                        await self.websocket.send_json({
                            "type": "done",
                            "timestamp": time.time()
                        })
                        logger.info("✅ 對話處理完成")
                        self._last_is_done = True

                        # 自動恢復監聽模式
                        await self.switch_mode("monitoring")
                        self.monitor_service.reset()
                        logger.info("🔄 自動恢復監聽模式")

                        # 停止追蹤
                        self.is_tracking = False
                        logger.info("🛑 停止狀態追蹤")

                except Exception as e:
                    logger.error(f"❌ 狀態追蹤發生錯誤: {e}")

        except asyncio.CancelledError:
            logger.info("狀態追蹤器已停止")
            raise
    
    def start_tracking(self):
        """
        啟動狀態追蹤
        在音頻上傳後調用此方法，開始監控 voice_chat_service 的處理進度
        """
        if self.is_tracking:
            logger.warning("⚠️ 狀態追蹤已在運行中")
            return
        
        # 重置追蹤狀態
        self._last_transcript = ""
        self._last_response = ""
        self._last_is_done = False
        
        # 啟動追蹤任務
        self.is_tracking = True
        self._tracking_task = asyncio.create_task(self._start_status_tracking())
        logger.info("🚀 已啟動狀態追蹤任務")
