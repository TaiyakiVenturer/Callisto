# 🌙 Callisto 語音助理

基於 VAD + KWS 的智能語音對話系統，搭配 VMagicMirror 虛擬形象顯示。

## ✨ 特性

- 🎙️ **語音喚醒**：說出喚醒詞（預設 `hey_jarvis`，可自訓換成自訂詞）即可喚醒助理
- 🗣️ **自然對話**：語音輸入 → STT → LLM → TTS 完整管線
- 🔊 **即時回應**：GPT-SoVITS V2 語音合成，非阻塞串流播放
- 💬 **雙模式**：按鈕錄音 / 持續監聽（喚醒詞觸發）
- 🎭 **虛擬形象**：透過 VMagicMirror（VMM）驅動 VRM 3D 模型；前端目前以暫時圖像作 UI 狀態指示，未來規劃整體移除，僅保留後端控制面板介面
- 🧠 **長期記憶**：FTS5 + ChromaDB 混合搜尋，LLM 自動判斷是否寫入，含遺忘機制
- ⚡ **高效能**：ONNX Runtime CPU 友好推理，無需 GPU

## 🏗️ 技術架構

### 前端（Vue 3 + TypeScript）
- **框架**：Vue 3 Composition API
- **狀態管理**：Pinia
- **路由**：Vue Router
- **音訊錄製**：MediaRecorder API + AudioWorklet
- **即時通訊**：WebSocket
- **建置工具**：Vite 7 + pnpm
- **未來規劃**：遷移至 Tauri（Rust）打包為桌面 APP

### 後端（FastAPI + Python）
- **框架**：FastAPI + uvicorn
- **VAD**：Silero VAD (ONNX Runtime)
- **KWS**：openWakeWord（預設使用開源的 `hey_jarvis` 模型；自訓練的 `hey_callisto` 模型未隨專案發布，可透過 [openWakeWord Colab](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing) 自行訓練）
- **STT**：faster-whisper
- **LLM**：Groq API (llama-3.1-8b-instant)
- **TTS**：GPT-SoVITS V2（本機部署）
- **VMM**：pythonosc → VMagicMirror → VRM 3D 模型控制
- **長期記憶**：SQLite/FTS5 + ChromaDB + Ollama Embedding + RRF 混合搜尋
- **設定**：集中式 `config.yaml`

## 🚀 快速開始

### 環境需求
- **Python**: >= 3.12
- **Node.js**: ^20.19.0 || >=22.12.0
- **外部服務**：GPT-SoVITS V2 本機服務、VMagicMirror（可選）

### 1. 設定後端

```bash
cd backend

# 啟動虛擬環境
source .venv/Scripts/activate  # Windows Git Bash
# 或
.venv\Scripts\activate  # Windows CMD

# 設定 API 金鑰
echo "GROQ_TOKEN=your_groq_api_key" > .env

# 複製設定檔並依需求修改
cp config.example.yaml config.yaml
```

複製後編輯 `config.yaml`，填入你的系統提示詞、語音設定、模型路徑等。

```bash
# 確保 GPT-SoVITS V2 服務已啟動

# 啟動 API 伺服器
uv run api_server.py
```

伺服器將依 `config.yaml` 的 `server` 設定啟動（預設 `http://0.0.0.0:8000`）

### 2. 設定前端

```bash
cd frontend

# 安裝依賴（首次）
pnpm install

# 複製環境變數設定
cp .env.example .env
# 若後端 port 不同，修改 .env 裡的 VITE_API_BASE_URL

# 啟動開發伺服器
pnpm dev
```

前端將在 `http://localhost:5173` 啟動

## 📖 使用方式

### 模式 A：按鈕錄音
1. 點擊「開始錄音」按鈕，進入錄音狀態
2. 對著麥克風說話
3. 點擊「傳送」上傳並處理，或點擊「取消」放棄本次錄音
4. 等待 AI 回應（STT → LLM → TTS 自動完成）

### 模式 B：持續監聽
1. 點擊「開始監聽」按鈕
2. 說出設定的喚醒詞（預設 `hey_jarvis`）
3. 繼續說出你的指令
4. 系統自動處理並回應，回應完畢後自動恢復監聽

## 🗺️ 專案結構

```
Callisto/
├── backend/                    # 後端服務 (FastAPI + Python)
│   ├── services/               # 核心服務模組
│   │   ├── audio_processing/   # 音訊處理
│   │   │   ├── silero_vad_service.py       # VAD 語音活動檢測（含 AGC）
│   │   │   ├── kws_service.py              # 喚醒詞檢測 (openWakeWord)
│   │   │   ├── gpt_sovits_service.py       # GPT-SoVITS V2 TTS 客戶端（含播放功能）
│   │   │   └── stt_service.py              # 語音轉文字 (faster-whisper)
│   │   ├── core/               # 核心邏輯
│   │   │   └── voice_chat_service.py       # 語音對話主服務
│   │   ├── memory/             # 長期記憶層
│   │   │   ├── memory_cache.py             # Context Window 對話歷史管理
│   │   │   ├── sql.py                      # SQLite + FTS5 記憶資料庫
│   │   │   ├── vector_store.py             # ChromaDB 向量資料庫封裝
│   │   │   ├── embedding_service.py        # Ollama embedding 抽象層
│   │   │   ├── retrieval.py                # FTS5 + Vector 混合搜尋（RRF）
│   │   │   ├── memory_writer.py            # LLM 判斷並寫入記憶
│   │   │   └── forgetting.py               # 遺忘週期（壓縮 / 刪除）
│   │   ├── monitoring/         # 監聽服務
│   │   │   ├── audio_monitor_service.py    # VAD+KWS 協調服務
│   │   │   └── voice_monitor_websocket_service.py  # WebSocket 音訊監聽
│   │   ├── visual/             # 形象控制
│   │   │   ├── vmm_service.py              # VMagicMirror OSC 控制（表情）
│   │   │   └── avatar_controller.py        # 虛擬形象狀態控制器
│   │   ├── tools.py                        # Groq tool schema 定義（search_memory）
│   │   └── tool_calling_handler.py         # Tool calling 迴圈處理（解析 / 執行 / 回傳）
│   ├── data/                   # 長期記憶資料（.gitignore 排除，勿上傳）
│   │   ├── memory.db               # SQLite 記憶資料庫
│   │   └── chroma_db/              # ChromaDB 向量索引
│   ├── models/                 # ONNX 模型（大型檔案不上傳，僅 silero_vad.onnx 隨專案）
│   │   └── silero_vad.onnx             # VAD 模型（已上傳）
│   │   # 自訓喚醒詞模型請放於此目錄，並於 config.yaml 的 kws.wake_words 設定
│   ├── api_server.py           # FastAPI 主程式
│   ├── config.py               # 集中式設定載入器
│   ├── config.example.yaml     # 設定範本（複製為 config.yaml 使用）
│   ├── .env.example            # 環境變數範本（複製為 .env，填入 API 金鑰）
│   └── pyproject.toml          # Python 專案設定 (uv)
│
├── frontend/                   # 前端應用 (Vue 3 + TypeScript + Vite)
│   ├── src/
│   │   ├── components/
│   │   │   ├── CharacterDisplay.vue   # 角色狀態顯示（暫用圖片，未來改 VMM）
│   │   │   ├── VoiceRecorder.vue      # 錄音按鈕
│   │   │   └── ChatHistory.vue        # 對話記錄
│   │   ├── composables/
│   │   │   ├── useVoiceRecorder.ts    # 錄音邏輯
│   │   │   ├── useVoiceMonitor.ts     # WebSocket 監聽
│   │   │   └── useStatusPolling.ts    # 狀態輪詢
│   │   ├── stores/
│   │   │   └── voiceChat.ts           # Pinia 語音對話狀態
│   │   ├── views/
│   │   │   └── VoiceChatView.vue      # 主對話頁面
│   │   └── types/                     # TypeScript 型別定義
│   ├── public/
│   │   ├── audio-processor.js         # AudioWorklet 音訊處理器
│   │   └── character-*.png            # 角色圖片（暫用佔位圖）
│   ├── .env.example            # 環境變數範本
│   ├── package.json
│   └── vite.config.ts
│
└── docs/
    ├── Backend README.md       # 後端 API 詳細文檔
    └── specs/                  # 功能規格文檔
```

## 📝 開發狀態

### 已完成功能 ✅

#### 核心語音處理管線
- [x] **VAD 語音活動檢測** - Silero VAD (ONNX Runtime)
- [x] **喚醒詞檢測** - openWakeWord（預設 `hey_jarvis`；自訓練的 `hey_callisto` 模型未隨專案發布）
- [x] **語音轉文字 (STT)** - faster-whisper
- [x] **大型語言模型 (LLM)** - Groq API
- [x] **文字轉語音 (TTS)** - GPT-SoVITS V2 同步串流生成
- [x] **AGC 自動增益控制** - 整合於 Silero VAD，可設定目標 RMS 與噪音門限
- [x] **虛擬形象控制** - pythonosc → VMagicMirror → VRM 3D 模型（表情 OSC）
- [x] **長期記憶層** - FTS5 + ChromaDB 混合搜尋，tool calling 自動注入，背景寫入，遺忘週期

#### 後端架構
- [x] **集中式設定** - `config.yaml` 管理所有連線參數、模型設定、系統提示、few-shot prompt
- [x] **VoiceChatService** - 語音對話主服務，協調 STT / LLM / TTS / VMM / 記憶層完整流程
- [x] **MemoryCache** - 以真實對話輪數計算（tool calling 中繼訊息不計入），原子化 drop 整輪次
- [x] **MemoryDB** - SQLite + FTS5 trigram 全文搜尋；`bump_access()` 於 Top-K 後更新存取統計
- [x] **VectorStore** - ChromaDB 向量資料庫，以 `memory_id` 為主鍵與 SQLite 同步
- [x] **EmbeddingService** - Ollama embedding 封裝，不可用時自動降級為純 FTS5
- [x] **RetrievalService** - FTS5 + Vector RRF 混合搜尋，Graceful Degradation
- [x] **MemoryWriter** - Groq LLM 判斷是否值得保存；topic 已存在則 upsert
- [x] **ForgettingService** - 指數衰減分數，自動壓縮 / 刪除低頻記憶
- [x] **AudioMonitorService** - VAD+KWS 協調服務（環形 buffer、cooldown 管理）
- [x] **GPTSoVITSV2Client** - TTS 客戶端，含同步串流播放（sounddevice）
- [x] **VoiceMonitorWebSocketService** - Producer-Consumer 架構，支援 monitoring / vad_only / idle 三模式
- [x] **VMMController** - VMagicMirror 表情 OSC over UDP 控制
- [x] **FastAPI 端點** - `/api/chat/voice`, `/api/status`, `/`
- [x] **WebSocket 端點** - `/ws/voice-monitor`（monitoring / vad_only / idle 模式）
- [x] **音訊格式轉換** - WebM/OGG/M4A → WAV
- [x] **靜音裁剪** - VAD 自動裁剪音訊靜音
- [x] **錄音與 WebSocket 互鎖** - 上傳期間透過模式切換（vad_only → idle）暫停監聽輸入
- [x] **自動恢復監聽** - TTS 播放完成（is_done）後自動切回 monitoring 模式
- [x] **超時保護** - GPT-SoVITS TTS 同步阻塞，is_done 必定觸發；前端錄音另有 30 秒硬超時

#### 前端功能
- [x] **按鈕錄音模式** - 點擊開始錄音，傳送 / 取消雙按鈕 + 30 秒超時保護
- [x] **持續監聽模式** - WebSocket 串流 + 喚醒詞觸發
- [x] **角色狀態顯示** - idle / thinking / speaking 狀態切換（暫用圖片，未來移除）
- [x] **對話記錄** - 聊天泡泡 + 自動滾動
- [x] **狀態輪詢** - 即時查詢處理進度
- [x] **環境變數** - `VITE_API_BASE_URL` 可自訂後端位址

### 待開發 📋
- [ ] **喚醒詞回應音效** - 檢測到喚醒詞後立即播放提示音（「我有聽到，請說」）
- [ ] **移除佔位圖片** - `CharacterDisplay.vue` 整體移除，改為純控制面板 UI
- [ ] **Tauri 打包** - 前端遷移至 Tauri（Rust），打包為桌面 APP
- [ ] 音量視覺化（錄音時顯示波形）

## 🎯 API 端點

### HTTP

| 端點 | 方法 | 說明 |
|------|------|------|
| `/api/chat/voice` | POST | 上傳語音檔案，啟動對話處理（背景任務） |
| `/api/status` | GET | 查詢當前處理狀態（STT/LLM/TTS/播放器） |
| `/` | GET | 健康檢查，回傳各服務連線狀態 |

### WebSocket

| 端點 | 說明 |
|------|------|
| `/ws/voice-monitor` | 即時音訊串流監聽，支援 VAD + KWS 喚醒詞檢測 |

詳細請參考 [後端詳細說明](docs/Backend%20README.md)

## 🤝 貢獻

本專案目前為個人開發專案。

---

**專案名稱由來**：Callisto（木衛四），木星最外圈的大型衛星。

**最後更新**：2026-03-05
