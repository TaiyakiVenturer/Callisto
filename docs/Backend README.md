# 📋 Callisto 語音助理後端服務

> 基於 VAD + KWS 的智能語音對話系統  
> Version: 0.3.0 | Updated: 2026-03-05

## 🎯 系統概述

Callisto 是一個智能語音助理後端服務，整合了語音活動檢測（VAD）、喚醒詞檢測（KWS）、語音轉文字（STT）、大型語言模型（LLM）和文字轉語音（TTS）等技術，並透過 VMagicMirror 控制虛擬形象，提供完整的語音對話體驗。

**核心特性**：
- 🎤 **即時語音監聽**: WebSocket 即時音訊流處理
- 🔊 **喚醒詞檢測**: 支援自訂喚醒詞（openWakeWord）
- 💬 **智能對話**: 基於 Groq LLM 的自然對話
- 🎵 **同步串流 TTS**: GPT-SoVITS V2 串流生成並即時播放
- 🎭 **虛擬形象控制**: OSC → VMagicMirror → VRM 3D 模型
- 🔄 **雙模式支援**: HTTP API + WebSocket 雙介面
- 🧠 **長期記憶層**: FTS5 + ChromaDB 混合搜尋，LLM 自動判斷是否寫入

---

## 🛠️ 技術棧

### 核心框架
- **FastAPI** 0.128.0+ - 現代 Web 框架
- **Uvicorn** - ASGI 伺服器
- **WebSockets** 16.0+ - 即時通訊

### 語音處理技術
| 技術 | 用途 | 實現 |
|------|------|------|
| **VAD** | 語音活動檢測（含 AGC） | Silero VAD (ONNX Runtime) |
| **KWS** | 喚醒詞檢測 | openWakeWord |
| **STT** | 語音轉文字 | faster-whisper |
| **LLM** | 對話生成 | Groq API |
| **OpenCC** | 簡繁轉換（s2twp 台灣繁體） | opencc |
| **TTS** | 文字轉語音（串流） | GPT-SoVITS V2 |
| **VMM** | 虛擬形象控制 | pythonosc → VMagicMirror |

### 記憶層技術
| 技術 | 用途 | 實現 |
|------|------|------|
| **SQLite + FTS5** | 關鍵字全文搜尋（trigram tokenizer） | SQLAlchemy + SQLite |
| **ChromaDB** | 語義向量搜尋 | chromadb |
| **Ollama Embedding** | 文字向量化 | ollama Python SDK |
| **Groq Writer LLM** | 判斷是否值得記憶並提取摘要 | Groq API |
| **RRF** | FTS5 + Vector 混合排序 | Reciprocal Rank Fusion |

### 音訊處理
- **PyAudio** - 音訊串流播放（TTS 即時輸出）
- **SoundFile** - 音訊檔案處理
- **Pydub** - 音訊格式轉換
- **NumPy** + **SciPy** - 訊號處理

### 依賴套件
完整套件清單請參考 [pyproject.toml](pyproject.toml)

---

##  系統架構

### HTTP API 語音對話流程

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#4a9eff','primaryTextColor':'#fff','primaryBorderColor':'#7CB9E8','lineColor':'#7CB9E8','secondaryColor':'#6c5ce7','tertiaryColor':'#00b894','noteBkgColor':'#2d3748','noteTextColor':'#fff'}}}%%
sequenceDiagram
    participant Frontend as 前端
    participant API as FastAPI Server
    participant VAD as SileroVADService
    participant STT as STTService
    participant LLM as Groq API
    participant TTS as GPTSoVITSV2Client
    participant VMM as VMMController

    Frontend->>API: POST /api/chat/voice<br/>(WebM/WAV)
    API->>API: 儲存暫存檔案
    API-->>Frontend: 200 {status: "processing"}

    Note over API,VAD: Step 0: 格式轉換 (WebM/OGG/M4A → WAV)
    API->>VAD: convert_to_vad_format()
    VAD-->>API: 16kHz mono WAV

    Note over API,VAD: Step 1: VAD 裁剪靜音
    API->>VAD: trim_silence()
    VAD-->>API: 裁剪後音訊

    Note over API,STT: Step 2: STT 語音轉文字
    API->>STT: transcribe()
    STT-->>API: 轉換文字

    Note over API,LLM: Step 3: LLM 生成回應 (streaming)
    API->>LLM: chat.completions.create()

    Note over API,LLM: Step 4: LLM 串流生成回應
    loop LLM Streaming
        LLM-->>API: 回應文字片段
        API->>API: 累積 full_response
    end

    Note over API: Step 5: OpenCC 簡繁轉換
    API->>API: opencc.convert() (s2twp)

    Note over API,VMM: Step 6: TTS 串流播放 + 虛擬形象同步
    API->>TTS: generate_stream()
    TTS->>TTS: 串流接收 → PyAudio 即時播放
    API->>VMM: perform() (表情 + 動作同步)

    API->>API: is_done = True, tts_done = True

    loop 前端輪詢
        Frontend->>API: GET /api/status
        API-->>Frontend: {is_done, tts_done, transcript, response}
    end
```

### WebSocket 即時監聽流程

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#4a9eff','primaryTextColor':'#fff','primaryBorderColor':'#7CB9E8','lineColor':'#7CB9E8','secondaryColor':'#6c5ce7','tertiaryColor':'#00b894'}}}%%
flowchart TB
    Start([前端連接 WebSocket]) --> Connected[/connected 事件/]
    Connected --> Mode{選擇模式}
    
    Mode -->|start_monitoring| Monitor[監聽模式]
    Mode -->|start_vad_only| VADOnly[VAD 錄音模式]
    Mode -->|stop| Idle[空閒模式]
    
    Monitor --> AudioStream[接收音訊串流<br/>前端: AudioWorklet 16kHz PCM]
    AudioStream --> Queue[audio_queue]
    
    Queue --> Processor[Audio Processor<br/>Consumer Thread]
    Processor --> AddBuffer[加入環形 buffer<br/>deque 1.5s]
    AddBuffer --> VADCheck[Step 1: Silero VAD<br/>語音檢測]
    
    VADCheck -->|靜音| SilenceEvent[/silence 事件/]
    VADCheck -->|語音| Debounce[Step 2: VAD Debounce<br/>連續 3 個 chunk]
    
    Debounce -->|未達閾值| SilenceEvent
    Debounce -->|達閾值| KWSCheck[Step 3: openWakeWord<br/>喚醒詞檢測<br/>讀取環形 buffer 1.5s]
    
    KWSCheck -->|未檢測到| SpeechEvent[/speech 事件/]
    KWSCheck -->|檢測到| KeywordEvent[/keyword 事件/]
    
    SilenceEvent --> EventQueue[event_queue]
    SpeechEvent --> EventQueue
    KeywordEvent --> EventQueue
    
    EventQueue --> Sender[Event Sender<br/>Consumer Thread]
    Sender --> Frontend[推送至前端]
    
    VADOnly --> VADStream[接收音訊串流<br/>前端: MediaRecorder + AudioWorklet]
    VADStream --> WarmUp{緩衝期?<br/>3 秒 94 chunks}
    WarmUp -->|緩衝期內| WarmUp
    WarmUp -->|緩衝期後| VADDetect[VAD 靜音檢測]
    VADDetect -->|語音| ResetCounter[重置靜音計數器]
    ResetCounter --> VADDetect
    VADDetect -->|3秒靜音<br/>94 chunks| StopEvent[/stop_recording 事件/]
    StopEvent --> AutoIdle[自動切換至 idle]
    
    Idle --> Wait[等待命令]
    Wait --> Mode
    
    Frontend --> Disconnect([斷開連接])
    Disconnect --> Cleanup[清理資源]
    
    style Monitor fill:#00b894,stroke:#00d9a5,stroke-width:3px,color:#fff
    style VADOnly fill:#fdcb6e,stroke:#ffeaa7,stroke-width:3px,color:#2d3436
    style Idle fill:#636e72,stroke:#b2bec3,stroke-width:3px,color:#fff
    style KeywordEvent fill:#ff6b6b,stroke:#ff8787,stroke-width:3px,color:#fff
    style SpeechEvent fill:#4a9eff,stroke:#74b9ff,stroke-width:3px,color:#fff
```

---

## 🔌 API 端點

### 1. POST /api/chat/text

直接傳入文字訊息觸發對話管線（調試用）。

**端點**: `POST /api/chat/text`

**Query 參數**:

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| text | string | ✅ | 使用者輸入文字 |

**Response**: `UploadResponse`

```json
{
  "status": "processing",
  "message": "User: ...\nAssistant: ..."
}
```

> `message` 欄位回傳當前對話記憶快取內容（`memory_cache.show_history()`），方便直接確認 pipeline 是否正常運作。

**使用範例**:
```bash
curl -X POST "http://localhost:8000/api/chat/text?text=你好"
```

---

### 2. POST /api/chat/voice

上傳語音檔案並啟動對話處理（背景任務）。

**端點**: `POST /api/chat/voice`

**Content-Type**: `multipart/form-data`

**Request 參數**:

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| audio | File | ✅ | 音訊檔案 (WAV/WebM/OGG/M4A) |

**Response**: `UploadResponse`

```json
{
  "status": "processing",
  "message": "音訊已接收，正在處理中..."
}
```

**錯誤碼**:
- `400` - 無效的檔案類型
- `409` - 正在處理中，請稍後再試
- `500` - 伺服器錯誤

**使用範例**:

```bash
curl -X POST http://localhost:8000/api/chat/voice \
  -F "audio=@test.wav"
```

---

### 3. GET /api/status

查詢當前處理狀態。

**端點**: `GET /api/status`

**Response**: `StatusResponse`

```json
{
  "is_done": true,
  "transcript": "使用者說的話",
  "response": "AI 回應的內容",
  "error": null,
  "tts_done": true
}
```

**欄位說明**:

| 欄位 | 類型 | 說明 |
|------|------|------|
| is_done | boolean | 整個 pipeline（STT+LLM+TTS）是否完成 |
| transcript | string | STT 轉換的文字 |
| response | string | LLM 生成的回應 |
| error | string\|null | 錯誤訊息 |
| tts_done | boolean | TTS 播放是否完成（True = 未播放中） |

**使用範例**:

```python
import requests, time

while True:
    data = requests.get("http://localhost:8000/api/status").json()
    if data["is_done"] and data["tts_done"]:
        print(f"轉換文字: {data['transcript']}")
        print(f"AI 回應: {data['response']}")
        break
    time.sleep(0.5)
```

---

### 4. GET /

健康檢查端點，回傳各外部服務連線狀態與目前處理狀態。

**端點**: `GET /`

**Response**:

```json
{
  "status": "ok",
  "message": "Callisto Voice API is running",
  "services": {
    "groq": {
      "status": "connected",
      "available_models": 15,
      "using_model": "llama-3.1-8b-instant"
    },
    "tts": {
      "status": "connected",
      "url": "http://localhost:9880"
    },
    "stt": {
      "status": "loaded",
      "model": "faster-whisper medium (int8) on cpu"
    }
  },
  "processing": {
    "is_done": true,
    "has_error": false,
    "status": "idle"
  }
}
```

> `status` 為 `"ok"` 表示所有服務正常；-`"degraded"` 表示部分服務異常但仍可運行。

---

### 5. WebSocket /ws/voice-monitor

即時語音監聽端點，支援 VAD + KWS 並行檢測。

**端點**: `WebSocket /ws/voice-monitor`

**連接**: `ws://localhost:8000/ws/voice-monitor`

#### 接收資料格式

**音訊串流** (binary):
- 格式: PCM
- 位深: 16-bit signed integer
- 採樣率: 16000 Hz
- 聲道: 單聲道 (mono)

**命令** (JSON text):

```json
// 切換至監聽模式 (VAD + KWS)
{"type": "start_monitoring"}

// 切換至 VAD 錄音模式 (僅 VAD)
{"type": "start_vad_only"}

// 停止監聽
{"type": "stop"}
```

#### 發送事件格式

**連接成功**:
```json
{
  "type": "connected",
  "timestamp": 1737609600.123,
  "message": "WebSocket 連接已建立"
}
```

**檢測到語音**:
```json
{
  "type": "speech",
  "duration": 1.5,
  "timestamp": 1737609601.456
}
```

**檢測到喚醒詞**:
```json
{
  "type": "keyword",
  "keyword": "hey_jarvis",
  "confidence": 0.85,
  "timestamp": 1737609602.789
}
```

**VAD 檢測到靜音停止** (vad_only 模式):
```json
{
  "type": "stop_recording",
  "reason": "silence_detected",
  "silence_duration": 3.0,
  "timestamp": 1737609605.012
}
```

**錯誤訊息**:
```json
{
  "type": "error",
  "message": "錯誤描述"
}
```

#### 使用範例

```javascript
// JavaScript (前端)
const ws = new WebSocket('ws://localhost:8000/ws/voice-monitor');

// 連接建立
ws.onopen = () => {
  console.log('WebSocket 已連接');
  
  // 切換至監聽模式
  ws.send(JSON.stringify({type: 'start_monitoring'}));
  
  // 開始發送音訊流
  navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
      const audioContext = new AudioContext({sampleRate: 16000});
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(512, 1, 1);
      
      processor.onaudioprocess = (e) => {
        const pcmData = e.inputBuffer.getChannelData(0);
        const int16Data = new Int16Array(pcmData.length);
        for (let i = 0; i < pcmData.length; i++) {
          int16Data[i] = Math.max(-32768, Math.min(32767, pcmData[i] * 32768));
        }
        ws.send(int16Data.buffer);
      };
      
      source.connect(processor);
      processor.connect(audioContext.destination);
    });
};

// 接收事件
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'keyword':
      console.log(`檢測到喚醒詞: ${data.keyword} (${data.confidence})`);
      break;
    case 'speech':
      console.log('檢測到語音');
      break;
    case 'stop_recording':
      console.log('VAD 檢測到靜音，停止錄音');
      break;
  }
};
```

---

## 🎯 核心服務模組

### VoiceChatService

**檔案**: `services/core/voice_chat_service.py`

**功能**: 語音對話主服務，串聯完整 pipeline

**處理流程**:
1. 音訊格式轉換為 VAD 格式 (16kHz mono WAV)
2. VAD 裁剪靜音 (Silero VAD)
3. STT 語音轉文字 (faster-whisper)
4. Groq LLM 生成回應 (streaming，含 tool calling loop)
   - 每輪 LLM 呼叫前先透過 `RetrievalService.search()` 查詢長期記憶，注入 context
5. OpenCC 簡繁轉換 (s2twp 台灣繁體)
6. TTS 串流生成與直接播放 (GPT-SoVITS V2 + PyAudio)
7. VMMController 同步表情動作
8. 每 `write_interval` 輪觸發一次記憶寫入（背景 thread，不阻塞對話）

**依賴服務**:
- `SileroVADService` - VAD 處理
- `STTService` - 語音轉文字
- `Groq API` - LLM 對話生成
- `GPTSoVITSV2Client` - TTS 串流生成與播放
- `VMMController` - 虛擬形象動作控制
- `MemoryCache` - Context Window 對話歷史管理
- `RetrievalService` - 長期記憶搜尋注入
- `MemoryWriter` - 背景記憶寫入（ThreadPoolExecutor）

**狀態管理**: `AppState`
- `is_done`: 整個 pipeline 是否完成
- `transcript`: STT 轉換文字
- `response`: LLM 生成回應
- `error`: 錯誤訊息
- `tts_done`: TTS 播放是否完成

---

## 🧠 記憶層服務

記憶層位於 `services/memory/`，提供長期記憶的寫入、搜尋與遺忘機制，讓 Callisto 能記住跨對話的個人資訊。

### 記憶層架構

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#4a9eff','primaryTextColor':'#fff','primaryBorderColor':'#7CB9E8','lineColor':'#7CB9E8','secondaryColor':'#6c5ce7','tertiaryColor':'#00b894','noteBkgColor':'#2d3748','noteTextColor':'#fff'}}}%%
flowchart TB
    subgraph WRITE["📝 記憶寫入路徑（每 write_interval 輪，背景 Thread）"]
        direction TB
        W1["對話輪次結束\nturn_count % write_interval == 0"] --> W2
        W2["MemoryCache\n.get_recent_turns(N)\n取最近 N 輪 user/assistant 對"] --> W3
        W3["MemoryWriter.analyze()\nGroq LLM 判斷是否值得保存\nJSON: {save, topic, summary, keywords, content}"] --> W4{save?}
        W4 -->|false| W5["放棄 ❌"]
        W4 -->|true| W6["MemoryDB.add / update_memory()\nSQLite upsert（以 topic 為鍵）"]
        W6 --> W7["VectorStore.add / update()\nChromaDB 向量寫入\nOllama embed()"]
    end

    subgraph RETRIEVE["🔍 記憶查詢路徑（每輪對話，tool calling）"]
        direction TB
        R1["使用者說話\n→ LLM tool calling 觸發 search_memory"] --> R2
        R2["RetrievalService.search(query, top_k)"] --> R3
        R2 --> R4
        R3["FTS5 搜尋\nMemoryDB.search_memory()\ntrigram 全文搜尋"] --> R5
        R4["Vector 搜尋\nVectorStore.search()\nCosometic similarity"] --> R5
        R5["RRF 合併排序\nscore = Σ 1/(60+rank)\n取 Top-K"] --> R6
        R6["bump_access(top_k_ids)\n更新 last_accessed + access_count"] --> R7
        R7["format_for_injection()\n格式化為 [記憶 N] 字串"] --> R8
        R8["注入 system context\n→ Groq LLM 生成含記憶的回應"]
        R4 -->|"Ollama 不可用"| R3
    end

    subgraph FORGET["🕰️ 遺忘週期（每次服務啟動時執行）"]
        direction TB
        F1["ForgettingService.run_cycle()"] --> F2
        F2["對每筆記憶計算分數\nscore = e^(-λ·days) × log(1 + count/scale)"] --> F3{分數}
        F3 -->|"< 0.1\n(delete_threshold)"| F4["MemoryDB.delete_memory()\nVectorStore.delete()"]
        F3 -->|"0.1 ~ 0.3\n(compress_threshold)"| F5["Groq LLM 重新摘要\nMemoryDB.compress_memory()"]
        F3 -->|">= 0.3"| F6["保留不動 ✅"]
    end

    style WRITE fill:#1a2a1a,stroke:#00b894,stroke-width:2px
    style RETRIEVE fill:#1a1a2e,stroke:#4a9eff,stroke-width:2px
    style FORGET fill:#2a1a1a,stroke:#e17055,stroke-width:2px
    style W5 fill:#636e72,stroke:#b2bec3,color:#fff
    style W6 fill:#00b894,stroke:#00d9a5,color:#fff
    style W7 fill:#00b894,stroke:#00d9a5,color:#fff
    style R8 fill:#4a9eff,stroke:#74b9ff,color:#fff
    style F4 fill:#d63031,stroke:#ff7675,color:#fff
    style F5 fill:#e17055,stroke:#fab1a0,color:#fff
    style F6 fill:#00b894,stroke:#00d9a5,color:#fff
```

### MemoryCache

**檔案**: `services/memory/memory_cache.py`

**功能**: Context Window 對話歷史管理，作為 `VoiceChatService` 的記憶快取與 `MemoryWriter` 的資料來源

**設計要點**:
- `max_cache_length`（config）= **真實對話輪數**（以 user 訊息數計算），tool calling 中繼訊息不計入輪數
- 超過上限時 `_drop_oldest_turn()` 一次移除整個舊輪次（含 tool_calls 步驟 + tool 結果），避免孤立的 tool 訊息導致 API 錯誤
- `get_recent_turns(n)` 從歷史倒序提取最近 n 個有效 (user, assistant) 文字對，跳過 content=None 的純 tool_calls 訊息與 role=tool 訊息，供 MemoryWriter 使用

**主要方法**:
```python
add_history(message: dict) -> None       # 新增訊息，超限時 drop 最舊輪次
get_api_history() -> list[dict]          # 回傳可直接傳給 Groq API 的清單
get_recent_turns(n: int) -> list[tuple]  # 提取最近 n 輪 (user_msg, assistant_msg)
reset_history() -> None                  # 重置（保留 system prompt）
```

---

### MemoryDB

**檔案**: `services/memory/sql.py`

**功能**: SQLite 記憶資料庫，使用 FTS5 trigram 全文搜尋

**Schema**:
```
Memory: id, topic (unique slug), summary, keywords, content,
        last_accessed, access_count
```

**FTS5 設計**: 外部 content table 模式，`memory_fts` 索引 `summary + keywords`；  
`after_insert / after_update / after_delete` event 自動同步

**主要方法**:
```python
add_memory(topic, summary, keywords, content) -> Memory
update_memory(topic, summary, keywords, content) -> Memory  # upsert
search_memory(keyword, top_k) -> list[Memory]               # FTS5 僅查詢，不更新 access
bump_access(memory_ids: list[int]) -> None                  # 更新 last_accessed + access_count
delete_memory(memory_id) -> bool
compress_memory(memory_id, new_content) -> Memory
get_all() -> list[Memory]
```

> `bump_access()` 由 `RetrievalService` 在組完最終 Top-K 後統一呼叫，確保 FTS5 和 vector-only 命中都被正確計數。

---

### EmbeddingService

**檔案**: `services/memory/embedding_service.py`

**功能**: Ollama embedding 抽象層，透過 ollama Python SDK 呼叫本機 Ollama 服務

**主要方法**:
```python
embed(text: str) -> list[float]              # 單筆向量化
embed_batch(texts: list[str]) -> list[list[float]]  # 批次向量化
```

**錯誤處理**: `EmbeddingUnavailableError`（包裝 `ollama.ResponseError` 與連線錯誤），  
`RetrievalService` 捕捉後自動降級為純 FTS5 搜尋

**設定**（`config.yaml`）:
```yaml
embedding:
  host: "localhost"
  port: 11434
  model: "nomic-embed-text-v2-moe"
  timeout: 10.0
```

---

### VectorStore

**檔案**: `services/memory/vector_store.py`

**功能**: ChromaDB 向量資料庫封裝，以 `memory_id` 為主鍵同步 SQLite

**主要方法**:
```python
add(memory_id, content) -> None
update(memory_id, content) -> None
delete(memory_id) -> None
search(query, top_k) -> list[dict]  # [{'id', 'distance'}, ...]
```

---

### RetrievalService

**檔案**: `services/memory/retrieval.py`

**功能**: FTS5 + ChromaDB 混合搜尋，RRF 排序

**搜尋流程**:
1. FTS5 `search_memory(query, top_k*2)` 取候選
2. ChromaDB `vector_store.search(query, top_k*2)` 取候選
3. RRF 合併兩個排名列表（`score = Σ 1/(k+rank)`，k=60）
4. 取 Top-K，呼叫 `bump_access()` 更新命中統計

**Graceful Degradation**: Ollama 不可用時自動降級為純 FTS5

**主要方法**:
```python
search(query: str, top_k: int) -> list[dict]       # 混合搜尋，回傳 {id, topic, summary, content, rrf_score}
format_for_injection(results: list[dict]) -> str   # 格式化為注入 context 的字串
```

**設定**（`config.yaml`）:
```yaml
retrieval:
  rrf_k: 60
  default_top_k: 3
  write_interval: 3  # 每幾輪觸發一次記憶寫入
```

---

### MemoryWriter

**檔案**: `services/memory/memory_writer.py`

**功能**: 分析多輪對話批次，判斷是否值得保存並寫入 SQLite + ChromaDB

**觸發機制**: `VoiceChatService` 每 `write_interval` 輪呼叫一次，透過 `ThreadPoolExecutor` 在背景執行，不阻塞對話

**輸入格式**: `list[tuple[str, str]]`（最近 N 輪 (user_msg, assistant_msg)），由 `MemoryCache.get_recent_turns()` 提供

**Writer LLM**（Groq）輸出 JSON schema:
```json
// save=true
{"save": true, "topic": "slug", "summary": "...", "keywords": "...", "content": "..."}
// save=false
{"save": false}
```

**記憶更新策略**: topic 已存在 → `update_memory()`（upsert）；不存在 → `add_memory()`

**Few-shot prompt**（`config.yaml` 中可自訂）包含 5 種典型案例：明確 save（技術知識）、邊緣 save（跨輪次習慣）、明確 skip（閒聊）、邊緣 skip（一次性念頭）、邊緣 save（待辦委託混在閒聊中）

**設定**（`config.yaml`）:
```yaml
llm:
  writer_model: "llama-3.3-70b-versatile"
  writer_temperature: 0.2
  writer_system_prompt: |   # few-shot prompt，詳見 config.yaml
    ...
```

---

### ForgettingService

**檔案**: `services/memory/forgetting.py`

**功能**: 依分數決定記憶的壓縮或刪除（每次啟動時執行一次）

**分數公式**:
$$
\text{score} = e^{-\lambda \cdot days\_since\_access} \times \log(1 + \frac{access\_count}{scale})
$$

- `days_since_access`: 距上次存取的天數
- `access_count`: 累計存取次數
- `λ`（lambda_decay）= 0.05（14 天後 decay ≈ 0.5）
- `scale` = 10（access_count=10 時 boost=1.0）

**分支決策**:
| 分數 | 動作 |
|------|------|
| < `delete_threshold` (0.1) | 刪除（`MemoryDB.delete_memory()` + ChromaDB 同步）|
| < `compress_threshold` (0.3) | 壓縮（Groq LLM 重新摘要後 `MemoryDB.compress_memory()`）|
| ≥ 0.3 | 保留不動 |

**設定**（`config.yaml`）:
```yaml
forgetting:
  lambda_decay: 0.05
  scale: 10
  compress_threshold: 0.3
  delete_threshold: 0.1
```

---

### VoiceMonitorWebSocketService

**檔案**: `services/monitoring/voice_monitor_websocket_service.py`

**功能**: WebSocket 音訊監聽服務

**架構**: Producer-Consumer 模式
- **Producer**: 接收前端音訊串流，放入 `audio_queue`
- **Consumer 1**: `_audio_processor` 處理音訊，將事件放入 `event_queue`
- **Consumer 2**: `_event_sender` 發送事件至前端

**支援模式**:
- `monitoring` - VAD + KWS 並行檢測
- `vad_only` - 僅 VAD 檢測（錄音模式）
- `idle` - 空閒模式

**特性**:
- 非阻塞音訊處理
- 模式動態切換
- VAD 緩衝期機制 (避免誤觸發)
- 3 秒靜音自動停止

---

### AudioMonitorService

**檔案**: `services/monitoring/audio_monitor_service.py`

**功能**: VAD + KWS 協調服務

**檢測機制**:
- **VAD (Silero)**: 作為「驗證器」，確認真實語音
- **KWS (openWakeWord)**: 並行運行，檢測喚醒詞

**技術細節**:
- **環形緩衝區**: 保留最近 1.5 秒音訊
- **VAD Debounce**: 連續 3 個 chunk 才確認語音
- **KWS Cooldown**: 1 秒內忽略重複檢測

**統計資訊**:
- `total_chunks`: 總處理數
- `speech_chunks`: 語音塊數
- `keywords_detected`: 喚醒詞次數
- `cooldown_ignored`: Cooldown 忽略次數

---

### STTService

**檔案**: `services/audio_processing/stt_service.py`

**功能**: 語音轉文字服務

**技術**: faster-whisper

**特性**:
- CUDA Fallback 機制（自動偵測 GPU）
- 繁體中文優化 prompt
- Beam search (beam_size=5)

**API**:
```python
transcribe(audio_path, language="zh", beam_size=5) -> str
```

---

### GPTSoVITSV2Client

**檔案**: `services/audio_processing/gpt_sovits_service.py`

**功能**: TTS 串流生成與直接播放客戶端

**技術**: GPT-SoVITS V2 API + PyAudio 直接播放

**API 端點**: `http://localhost:9880/tts`

**主要方法**:
```python
# 串流生成並直接播放（同步）
speak(text, language) -> None
```

**注意**: 採用同步串流播放，不使用獨立播放佇列；`VoiceChatService` 在 TTS 播放完成後才將 `tts_done` 設為 `True`。

---

### SileroVADService

**檔案**: `services/audio_processing/silero_vad_service.py`

**功能**: 語音活動檢測與音訊處理

**技術**: Silero VAD (ONNX Runtime)

**主要功能**:
1. **VAD 檢測**: `detect(audio_chunk) -> bool`
2. **靜音裁剪**: `trim_silence(input_path, output_path) -> str`
3. **格式轉換**: `convert_to_vad_format(input_path, output_path)`
   - 支援: WebM, OGG, M4A, WAV 等
   - 輸出: 16kHz mono 16-bit WAV

**閾值**: 預設 0.5 (可調整)

---

### KeywordSpottingService

**檔案**: `services/audio_processing/kws_service.py`

**功能**: 喚醒詞檢測服務

**技術**: openWakeWord

**喚醒詞**: 預設使用 `hey_jarvis` 模型；如需自訂模型，請於 `config.yaml` 中指定模型路徑

**API**:
```python
# 檢測喚醒詞
detect(audio_chunk: bytes) -> Optional[Dict]

# 返回格式
{
  "keyword": "hey_jarvis",
  "confidence": 0.85
}
```

**閾值**: 預設 0.5

---

### VMMController

**檔案**: `services/visual/vmm_service.py`

**功能**: VMagicMirror 虛擬形象控制服務

**通訊**: 透過 HTTP API 發送動作指令至 VMagicMirror

**主要方法**:
```python
# 播放表情
play_expression(expression_name: str) -> None

# 播放動作
play_motion(motion_name: str) -> None
```

---

## ⚙️ 配置說明

### 環境變數

| 變數 | 必填 | 說明 | 範例 |
|------|------|------|------|
| GROQ_API_KEY | ✅ | Groq API 金鑰 | gsk_xxx |

### 系統需求

**硬體**:
- CPU: 任意 (建議多核心)
- RAM: 8GB+ (建議 16GB)
- GPU: 可選 (GTX 1060 6GB 以上)
- VRAM: TTS 佔用 4.5-5GB, Whisper 佔用 ~500MB

**作業系統**:
- Windows 10/11
- Linux (Ubuntu 20.04+)
- macOS (未測試)

**外部服務**:
- GPT-SoVITS V2 Server (`http://localhost:9880`)
- VMagicMirror (`http://localhost:39539`)

---

## ⚠️ 錯誤處理與常見問題

### API 錯誤碼

| HTTP 碼 | 說明 | 解決方法 |
|---------|------|----------|
| 400 | 無效的檔案類型 | 確認上傳音訊格式 (WAV/WebM/OGG/M4A) |
| 409 | 正在處理中 | 等待當前任務完成後再試 |
| 500 | 伺服器錯誤 | 檢查日誌，確認外部服務狀態 |

### 常見問題

**Q: Groq API 連線失敗**
```
A: 檢查 .env 檔案中的 GROQ_API_KEY 是否正確
```

**Q: TTS 服務無法連線**
```
A: 確認 GPT-SoVITS V2 Server 是否在 http://localhost:9880 運行
   curl http://localhost:9880/
```

**Q: STT 轉換失敗**
```
A: 確認音訊檔案格式正確，檢查 faster-whisper 模型是否已下載
```

**Q: WebSocket 連線斷開**
```
A: 檢查前端音訊格式是否為 16kHz mono int16 PCM
   確認網路連線穩定
```

**Q: GPU 記憶體不足**
```
A: 系統已設定 STT 使用 CPU 模式
   TTS 需要 4.5-5GB VRAM，無法降級
```

---

## 🧪 測試範例

### 測試語音上傳

```bash
# 1. 錄製測試音訊（使用系統麥克風）
ffmpeg -f dshow -i audio="麥克風" -t 5 -ar 16000 -ac 1 test.wav

# 2. 上傳測試
curl -X POST http://localhost:8000/api/chat/voice \
  -F "audio=@test.wav"

# 3. 輪詢狀態
while true; do
  curl http://localhost:8000/api/status | jq
  sleep 1
done
```

### 測試 WebSocket

**Python 測試腳本**:

```python
import asyncio
import websockets
import numpy as np

async def test_websocket():
    uri = "ws://localhost:8000/ws/voice-monitor"
    
    async with websockets.connect(uri) as websocket:
        # 接收連接事件
        response = await websocket.recv()
        print(f"連接: {response}")
        
        # 切換至監聽模式
        await websocket.send('{"type": "start_monitoring"}')
        
        # 模擬發送音訊數據
        for i in range(100):
            # 生成隨機音訊塊 (512 samples, 16kHz, int16)
            audio = np.random.randint(-1000, 1000, 512, dtype=np.int16)
            await websocket.send(audio.tobytes())
            await asyncio.sleep(0.032)  # 32ms
            
            # 檢查事件
            try:
                event = await asyncio.wait_for(
                    websocket.recv(),
                    timeout=0.001
                )
                print(f"事件: {event}")
            except asyncio.TimeoutError:
                pass

asyncio.run(test_websocket())
```

---

## 📝 日誌

伺服器會在終端機輸出詳細的處理日誌：

```
2026-03-04 10:00:00 - INFO - 正在啟動 FastAPI 應用...
2026-03-04 10:00:01 - INFO - ✅ STT 服務初始化完成 (CPU 模式)
2026-03-04 10:00:01 - INFO - ✅ GPT-SoVITS V2 TTS 服務就緒
2026-03-04 10:00:01 - INFO - ✅ FastAPI 應用啟動完成
2026-03-04 10:01:00 - INFO - 音訊檔案已儲存: /tmp/voice_20260304_100100.webm
2026-03-04 10:01:01 - INFO - Step 0: 音訊格式轉換
2026-03-04 10:01:02 - INFO - Step 1: VAD 裁剪靜音
2026-03-04 10:01:03 - INFO - Step 2: STT 轉文字
2026-03-04 10:01:05 - INFO - 使用者說: 今天天氣如何？
2026-03-04 10:01:05 - INFO - Step 3: Groq LLM 生成回應
2026-03-04 10:01:07 - INFO - Step 4: TTS 串流生成並播放
2026-03-04 10:01:10 - INFO - AI 回應已生成完成: 今天天氣晴朗，溫度約 25 度...
2026-03-04 10:01:15 - INFO - TTS 播放完成
```

---

## 📚 相關文檔

- [pyproject.toml](pyproject.toml) - 套件依賴清單
- [docs/specs/](../docs/specs/) - 功能規格文檔

---

**Last Updated**: 2026-03-05  
**Version**: 0.3.0  
**Maintained by**: TaiyakiVenturer
