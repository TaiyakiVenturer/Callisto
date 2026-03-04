"""
語音對話業務邏輯服務
處理 VAD → STT → LLM → TTS 的完整流程
"""

import logging
import os
import re
from typing import Optional
from groq import Groq
from dotenv import load_dotenv
from opencc import OpenCC

from services.audio_processing.stt_service import STTService
from services.audio_processing.silero_vad_service import SileroVADService
from services.audio_processing.gpt_sovits_service import GPTSoVITSV2Client
from services.visual.vmm_service import VMMController
from services.visual.avatar_controller import AvatarController
from services.memory.memory_cache import MemoryCache
from config import load_config

# 載入環境變數
load_dotenv()

# 設定日誌
logger = logging.getLogger(__name__)


class AppState:
    """應用狀態"""
    def __init__(self):
        self.is_done = True
        self.transcript = ""
        self.response = ""
        self.error: Optional[str] = None
        self.tts_done: bool = True  # True = 未在播放；False = TTS 播放中


class VoiceChatService:
    """語音對話服務（VAD → STT → LLM → TTS 完整 pipeline）"""
    
    def __init__(self):
        """初始化服務（只執行一次）"""
        logger.info("創建 VoiceChatService 實例")
        # 狀態
        self.app_state = AppState()

        self.vad_service = SileroVADService()
        self.groq_client = Groq()

        self.tts_client = GPTSoVITSV2Client()
        self.vmm_service = VMMController()
        self.avatar_service = AvatarController(self.tts_client, self.vmm_service)

        self.memory_cache = MemoryCache()
        self.opencc = OpenCC('s2twp')

        self.llm_model: str = load_config()["llm"]["model"]

        try:
            self.stt_service = STTService()
        except Exception as e:
            logger.error(f"STT 服務初始化失敗: {e}")
            raise

        logger.info("VoiceChatService 初始化完成")
    
    def process_voice(self, audio_path: str):
        """
        處理語音對話的背景任務
        
        Args:
            audio_path: 音訊檔案路徑（可能是任何格式：webm, wav, ogg 等）
        """
        try:
            # 重置狀態
            self.app_state.is_done = False
            self.app_state.transcript = ""
            self.app_state.response = ""
            self.app_state.error = None
            
            # Step 0: 音訊格式轉換為 VAD 格式（單聲道、16-bit、16kHz）
            logger.info("Step 0: 音訊格式轉換")
            converted_path = audio_path.replace(os.path.splitext(audio_path)[1], "_converted.wav")
            try:
                self.vad_service.convert_to_vad_format(audio_path, converted_path)
                # 刪除原始檔案
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                audio_path = converted_path
                logger.info(f"音訊已轉換為 VAD 格式: {audio_path}")
            except Exception as e:
                logger.warning(f"音訊格式轉換失敗，使用原始音訊: {e}")
            
            # Step 1: VAD 裁剪靜音
            logger.info("Step 1: VAD 裁剪靜音")
            vad_output = audio_path.replace(".wav", "_vad.wav")
            try:
                vad_output = self.vad_service.trim_silence(audio_path, vad_output)
                audio_to_transcribe = vad_output
            except Exception as e:
                logger.warning(f"VAD 裁剪失敗，使用原始音訊: {e}")
                audio_to_transcribe = audio_path
            
            if vad_output == audio_path:
                logger.warning("VAD 裁剪後無有效語音，不進行後續處理")
                self.app_state.is_done = True
                # 清理暫存檔案
                try:
                    if os.path.exists(audio_path):
                        os.remove(audio_path)
                    logger.info("暫存檔案已清理")
                except Exception as e:
                    logger.warning(f"清理暫存檔案失敗: {e}")
                return

            # Step 2: STT 轉文字
            logger.info("Step 2: STT 轉文字")
            transcript = self.stt_service.transcribe(
                audio_to_transcribe,
                language="zh",
                beam_size=5
            )
            self.app_state.transcript = transcript
            logger.info(f"使用者說: {transcript}")
            
            if not transcript:
                raise ValueError("無法識別語音內容")
            
            self.generate_response(transcript)
            
            # 完成
            self.app_state.is_done = True
            
            # 清理暫存檔案
            try:
                if os.path.exists(audio_path):
                    os.remove(audio_path)
                if os.path.exists(vad_output):
                    os.remove(vad_output)
                logger.info("暫存檔案已清理")
            except Exception as e:
                logger.warning(f"清理暫存檔案失敗: {e}")
            
        except Exception as e:
            logger.error(f"處理語音對話失敗: {e}")
            self.app_state.error = str(e)
            self.app_state.is_done = True
    
    def generate_response(self, user_message: str):
        """
        主流程編排：user message → LLM loop（含 tool calling）→ TTS 播放。
        細節分散在 _stream_once / _handle_tool_calls / _speak。
        """
        self.memory_cache.add_history({"role": "user", "content": user_message})
        logger.info("Step 3: Groq LLM 生成回應")

        try:
            # Tool calling loop（最多 5 輪防死循環）
            # 每輪呼叫一次 LLM；若回傳 tool_calls 則執行並繼續，否則退出
            full_response = ""
            for _ in range(5):
                logger.info("Step 4: LLM 串流輸出")
                full_response, tool_calls_map = self._stream_once()
                if not tool_calls_map:
                    break
                self._handle_tool_calls(tool_calls_map)

            self._speak(full_response)
        except Exception as e:
            logger.error(f"generate_response 失敗: {e}")

    # ── LLM ──────────────────────────────────────────────────────────────────

    def _stream_once(self) -> tuple[str, dict[int, dict]]:
        """
        單次 LLM streaming call。
        回傳 (累積文字, tool_calls_map)；純文字回應時 tool_calls_map 為空 dict。

        Streaming 模式與一般模式的差異：
        - 一般模式（stream=False）：chunk.choices[0].message 是完整訊息，一次拿到全部。
        - Streaming 模式（stream=True）：沒有 message，只有 delta（增量 diff）。
          每個 chunk 的 delta.content 只含幾個字元，需要手動累積成完整的 full_response。

        tool_calls 同理，一個 tool call 會被拆散到多個 chunk 傳回：
        - 某 chunk: delta.tool_calls[0].id="call_abc", .function.name="search_memory"
        - 下個 chunk: delta.tool_calls[0].function.arguments='{"query":'
        - 再下個 chunk: delta.tool_calls[0].function.arguments='"今天發生了什麼"}'
        用 tc.index 作為 key 跨 chunk 累積（arguments 用 +=），loop 結束後才是完整的 tool call。
        """
        create_kwargs: dict = {
            "model": self.llm_model,
            "messages": self.memory_cache.get_api_history(),
            "temperature": 0.8,
            "stream": True,
        }
        tools = self._get_tools()
        if tools:
            create_kwargs["tools"] = tools

        stream = self.groq_client.chat.completions.create(**create_kwargs)

        full_response = ""
        tool_calls_map: dict[int, dict] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta

            if delta.content:
                full_response += delta.content
                # 實時更新前端顯示（只清 EXP tag，不解析 emote）
                self.app_state.response = re.sub(
                    r"\[EXP:\s*\w+\]", "", full_response
                ).strip()

            if delta.tool_calls:
                # 每個 chunk 可能只帶部分欄位，用 index 找到對應 entry 後附加
                for tc in delta.tool_calls:
                    entry = tool_calls_map.setdefault(
                        tc.index, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        entry["id"] = tc.id
                    if tc.function and tc.function.name:
                        entry["name"] = tc.function.name
                    if tc.function and tc.function.arguments:
                        entry["arguments"] += tc.function.arguments

        return full_response, tool_calls_map

    def _handle_tool_calls(self, tool_calls_map: dict[int, dict]) -> None:
        """
        將 assistant tool_calls 訊息存入 history，執行每個 tool，
        再把 tool result 存入 history，供下一輪 LLM 讀取。
        """
        tool_calls_list = [
            {
                "id": v["id"],
                "type": "function",
                "function": {"name": v["name"], "arguments": v["arguments"]},
            }
            for v in tool_calls_map.values()
        ]
        self.memory_cache.add_history({
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls_list,
        })

        for tc in tool_calls_list:
            result = self._execute_tool(
                tc["function"]["name"], tc["function"]["arguments"]
            )
            self.memory_cache.add_history({
                "role": "tool",
                "tool_call_id": tc["id"],
                "name": tc["function"]["name"],
                "content": result,
            })
            logger.info(f"Tool '{tc['function']['name']}' 執行完成")

    # ── TTS ──────────────────────────────────────────────────────────────────

    def _speak(self, full_response: str) -> None:
        """繁體轉換 → 存入 memory → TTS 播放。"""
        logger.info("Step 5: TTS 生成並播放")
        clean_text, emote = self.avatar_service.export_emote(full_response)
        clean_text = self.opencc.convert(clean_text)
        full_response = self.opencc.convert(full_response)

        self.app_state.response = clean_text
        print(f"Calisto 說: {full_response}")
        self.memory_cache.add_history({"role": "assistant", "content": full_response})
        logger.info(f"AI 回應已生成完成: {self.app_state.response}")

        self.app_state.tts_done = False  # TTS 開始播放
        tts_response = self.tts_client.generate_stream(text=clean_text, language="zh")
        self.avatar_service.perform(tts_response, volume=0.03, emote=emote)
        self.app_state.tts_done = True   # TTS 播放完成
        logger.info("TTS 播放完成")

    # ── Tool registry（記憶層整合後填入）────────────────────────────────────

    def _get_tools(self) -> list | None:
        """回傳 Groq tool definitions。記憶層整合後在此加入 search_memory 等工具。"""
        return None

    def _execute_tool(self, name: str, arguments_json: str) -> str:
        """執行 tool call 並回傳結果字串。記憶層整合後實作。"""
        logger.warning(f"_execute_tool: 未實作的 tool '{name}'")
        return f"[Tool '{name}' 尚未實作]"

    def get_status(self) -> dict:
        """獲取當前處理狀態。"""
        return {
            "is_done": self.app_state.is_done,
            "transcript": self.app_state.transcript,
            "response": self.app_state.response,
            "error": self.app_state.error,
            "tts_done": self.app_state.tts_done,
        }



