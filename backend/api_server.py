"""
FastAPI 應用主程式
提供語音對話 API 服務
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
import os
import tempfile
import shutil
from typing import Optional
from datetime import datetime

from services.core.voice_chat_service import VoiceChatService
from services.monitoring.voice_monitor_websocket_service import VoiceMonitorWebSocketService
from config import load_config

# 設定日誌 - 強制即時輸出（無緩衝）
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
# 禁用日誌緩衝
for handler in logging.root.handlers:
    handler.setStream(sys.stdout)
    if hasattr(handler.stream, 'reconfigure'):
        handler.stream.reconfigure(line_buffering=True)
        
logger = logging.getLogger(__name__)

# 語音對話服務（於 lifespan 初始化，避免模組二次 import 時重複建立）
chat_service: Optional[VoiceChatService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global chat_service
    chat_service = VoiceChatService()
    try:
        result = chat_service.forgetting_service.run_cycle()
    except Exception as e:
        logger.warning(f"Forgetting cycle failed (non-critical): {e}")
    yield


# 建立 FastAPI 應用
app = FastAPI(title="Callisto Voice API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本機開發，允許所有來源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response Models
class StatusResponse(BaseModel):
    is_done: bool
    transcript: str
    response: str
    error: Optional[str] = None
    tts_done: bool = True


class UploadResponse(BaseModel):
    status: str
    message: str


@app.post("/api/chat/text", response_model=UploadResponse)
def upload_text(text: str):
    """測試用端點：直接傳送文字並獲取回應（模擬語音轉文字後的流程）"""
    chat_service.generate_response(text)

    return UploadResponse(
        status="processing",
        message="\n".join(message for message in chat_service.memory_cache.show_history())
    )


@app.post("/api/chat/voice", response_model=UploadResponse)
async def upload_voice(
    background_tasks: BackgroundTasks,
    audio: UploadFile = File(...)
):
    """
    上傳語音並啟動對話處理
    
    Args:
        audio: 音訊檔案 (WAV/WebM)
        
    Returns:
        上傳狀態
    """
    try:
        # 驗證檔案類型
        if not audio.content_type or not audio.content_type.startswith("audio/"):
            raise HTTPException(
                status_code=400,
                detail=f"無效的檔案類型: {audio.content_type}，請上傳音訊檔案"
            )
        
        # 檢查是否正在處理中
        if not chat_service.app_state.is_done:
            raise HTTPException(
                status_code=409,
                detail="正在處理中，請稍後再試"
            )
        
        # 根據 content_type 決定副檔名
        temp_dir = tempfile.gettempdir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 判斷檔案格式
        if "webm" in audio.content_type:
            extension = ".webm"
        elif "ogg" in audio.content_type:
            extension = ".ogg"
        elif "wav" in audio.content_type:
            extension = ".wav"
        elif "mp4" in audio.content_type or "m4a" in audio.content_type:
            extension = ".m4a"
        else:
            # 預設使用 webm（Chrome/Edge 常用）
            extension = ".webm"
        
        audio_path = os.path.join(temp_dir, f"voice_{timestamp}{extension}")
        
        with open(audio_path, "wb") as buffer:
            shutil.copyfileobj(audio.file, buffer)
        
        logger.info(f"音訊檔案已儲存: {audio_path} (格式: {audio.content_type})")
        
        # 啟動背景任務處理語音對話（格式轉換在 service 層處理）
        background_tasks.add_task(chat_service.process_voice, audio_path)
        
        return UploadResponse(
            status="processing",
            message="音訊已接收，正在處理中..."
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上傳音訊失敗: {e}")
        raise HTTPException(status_code=500, detail=f"伺服器錯誤: {str(e)}")


@app.websocket("/ws/voice-monitor")
async def voice_monitor_endpoint(websocket: WebSocket):
    """
    WebSocket 端點：語音監聽與喚醒詞檢測
    
    前端連接後持續發送音訊流（binary, 16kHz mono int16 PCM）
    後端實時檢測並推送事件（JSON）：
    - connected: 連接成功
    - speech: 檢測到語音
    - keyword: 檢測到喚醒詞
    - error: 錯誤訊息
    """
    await websocket.accept()
    
    service = VoiceMonitorWebSocketService(websocket, chat_service)
    try:
        await service.start()
        await service.handle_audio_stream()
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 連接已斷開: {websocket.client}")
    except Exception as e:
        logger.error(f"❌ WebSocket 發生異常: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": f"伺服器錯誤: {str(e)}"
            })
        except:
            pass
    finally:
        await service.cleanup()


@app.get("/api/status", response_model=StatusResponse)
async def get_status():
    """
    查詢當前處理狀態（整合版）
    包含處理狀態和 player queue 狀態
    前端只需輪詢此端點即可獲取所有必要資訊
    
    Returns:
        處理狀態、轉換文字、AI 回應、player 狀態
    """
    status = chat_service.get_status()
    return StatusResponse(**status)


@app.get("/")
async def root():
    """
    健康檢查端點
    檢查所有外部服務的連線狀態和播放器狀態
    """
    health_status = {
        "status": "ok",
        "message": "Callisto Voice API is running",
        "services": {},
        "processing": {}
    }
    
    # 檢查 Groq API 連線
    try:
        # 使用 models.list() 檢查連線，不消耗請求次數
        models = chat_service.groq_client.models.list()
        model_list = [model.id for model in models.data]
        health_status["services"]["groq"] = {
            "status": "connected",
            "available_models": len(model_list),
            "using_model": "llama-3.1-8b-instant"
        }
    except Exception as e:
        health_status["services"]["groq"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # 檢查 TTS 服務連線
    try:
        import requests
        tts_response = requests.get(f"{chat_service.tts_client.base_url}/api/ready", timeout=2)
        if tts_response.status_code == 200:
            health_status["services"]["tts"] = {
                "status": "connected",
                "url": chat_service.tts_client.base_url
            }
        else:
            health_status["services"]["tts"] = {
                "status": "error",
                "error": f"HTTP {tts_response.status_code}"
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["services"]["tts"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # 檢查 STT 服務狀態（只檢查是否已載入）
    stt = chat_service.stt_service
    health_status["services"]["stt"] = {
        "status": "loaded" if stt is not None else "not_loaded",
        "model": f"faster-whisper {stt.model_size} ({stt.compute_type}) on {stt.device}" if stt else None
    }
    
    # 檢查處理狀態
    health_status["processing"] = {
        "is_done": chat_service.app_state.is_done,
        "has_error": chat_service.app_state.error is not None,
        "status": "idle" if chat_service.app_state.is_done else "processing"
    }
    
    return health_status


if __name__ == "__main__":
    import uvicorn

    _cfg = load_config()["server"]
    uvicorn.run(
        "api_server:app",
        host=_cfg["host"],
        port=_cfg["port"],
        reload=_cfg["reload"],
    )
