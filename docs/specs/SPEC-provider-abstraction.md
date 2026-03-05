# SPEC: Provider Abstraction（LLM Factory + TTS Base Class）

## Task Description

目標：提升專案適配性、降低硬體需求，並減少外部服務的硬依賴。

- **LLM 端**：把 `Groq()` client 的硬編碼抽出，改為工廠函式，根據 `config.yaml` 的 `llm.provider` 欄位動態建立 OpenAI-compatible client（支援 `groq` / `ollama`）
- **TTS 端**：建立 `BaseTTSClient` 抽象基底類，讓 `GPTSoVITSV2Client` 繼承，並新增 `EdgeTTSClient` 作為輕量 fallback / 預設服務；config 加入 `tts.provider` 切換欄位

解決的問題：
1. 沒有 GPT-SoVITS server 就無法跑任何對話（TTS 硬依賴）
2. `groq` client 散落在多個服務檔案，測試 / 切換困難
3. clone 下來的使用者需要額外架設 Local TTS server 才能體驗

---

## Tech Stack

- Python 3.12
- `openai`（新增，同時用於 Groq 和 Ollama，兩者都支援 OpenAI-compatible endpoint）
- ~~`groq>=1.0.0`~~（移除，改由 `openai` SDK 指向 Groq endpoint 取代）
- `edge-tts`（新增，輕量雲端 TTS）
- `asyncio`（async → sync 橋接，edge-tts generator 用）

---

## Acceptance Criteria

### LLM Factory
- [ ] `config.yaml` 的 `llm` 區塊新增 `provider` 欄位，附支援清單註解
- [ ] `services/llm_factory.py` 提供 `create_llm_client(config)` 工廠函式
  - `provider: groq` → `openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)`
  - `provider: ollama` → `openai.OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")`
  - 回傳型別均為 `openai.OpenAI`，呼叫端完全透明
- [ ] `voice_chat_service.py` 移除 `from groq import Groq`，改用工廠函式，`self.groq_client` 重命名為 `self.llm_client`
- [ ] `memory_writer.py` 移除 `from groq import Groq`，型別改為 `openai.OpenAI`，參數 `groq_client` 重命名為 `llm_client`
- [ ] `pyproject.toml` 移除 `groq` 依賴，加入 `openai` 依賴

### GPT-SoVITS 清理
- [ ] 刪除 `gpt_sovits_service.py` 中不再使用的函式：
  - `play_stream()`、`save_to_file()`、`_write_wav_file()`、`_fix_wav_header()`
  - module-level `play_tts()`、`save_tts()`
- [ ] 更新 module docstring（移除已刪函式的範例）

### TTS Base Class
- [ ] `services/audio_processing/base_tts.py` 定義 `BaseTTSClient` 抽象類
  - **唯一**必須實作的抽象方法：`get_chunk_generator(text, volume) -> Generator[bytes, None, None]`
  - 必須有屬性：`sample_rate: int`
  - `generate_stream` 「不」在 base class：它是 GPT-SoVITS 的實作細節（回傳 `requests.Response`），edge-tts 完全沒有這個概念；base class 只規定呼叫點看得到的介面
- [ ] `GPTSoVITSV2Client` 繼承 `BaseTTSClient`；`get_stream_generator` 重命名為 `get_chunk_generator`，內部合併 `generate_stream()` 呼叫（呼叫端只傳 `text`）；`__init__` 加入 startup 連線檢查，無法連線時輸出 `logger.warning` 附修復提示（**不拋例外**，讓 app 正常啟動）
- [ ] `services/audio_processing/edge_tts_service.py` 實作 `EdgeTTSClient(BaseTTSClient)`
  - 內部使用 `edge_tts.Communicate.stream()` async generator，橋接為同步 bytes generator
  - 音量控制邏輯與 GPT-SoVITS 一致（numpy PCM 處理）
- [ ] `config.yaml` 的 `tts` 區塊新增：
  - `provider` 欄位（`gptsovits` / `edge_tts`）
  - `playback_volume` 欄位（取代 hardcode `0.03`，附說明）
  - `gptsovits.language` 欄位（取代 hardcode `"zh"`，附可選值）
  - `edge_tts` 設定區塊，附完整中文語音清單註解
- [ ] `avatar_controller.py` 型別改為 `BaseTTSClient`；`perform()` 簽名從 `response: requests.Request` 改為 `text: str`
- [ ] `voice_chat_service.py` 根據 `tts.provider` 選擇 TTS 實作；`_speak()` 改為直接呼叫 `avatar_service.perform(clean_text, ...)` 而非先呼叫 `generate_stream()`（`generate_stream` 將移至 GPT-SoVITS 內部，`voice_chat_service` 不再直接接觸）

### 不在本 Spec 範圍內
- `monitoring/` 資料夾保持原位（職責與 `core/` 不同，不合併）
- 音訊播放移至前端（Web Audio API 方向，待獨立開 `SPEC-frontend-audio-playback`）

---

## Target Files

- **新增**：`backend/services/llm_factory.py`
- **新增**：`backend/services/audio_processing/base_tts.py`
- **新增**：`backend/services/audio_processing/edge_tts_service.py`
- **修改**：`backend/config.yaml`（新增 `llm.provider`、`tts.provider`、`tts.edge_tts` 欄位）
- **修改**：`backend/config.example.yaml`（同步）
- **修改**：`backend/pyproject.toml`（移除 `groq`，加 `openai`）
- **修改**：`backend/services/audio_processing/gpt_sovits_service.py`（刪除無用函式、繼承 base、更名）
- **修改**：`backend/services/core/voice_chat_service.py`
- **修改**：`backend/services/memory/memory_writer.py`
- **修改**：`backend/services/visual/avatar_controller.py`

---

## Key Design Decisions

### LLM：工廠函式 vs Base Class

選擇**工廠函式**（`create_llm_client`）而非 base class，理由：

- Groq 和 Ollama 都支援 OpenAI-compatible REST endpoint，直接用 `openai.OpenAI(base_url=...)` 指向不同 URL 即可，不需要兩個 SDK
- 工廠回傳統一的 `openai.OpenAI` instance，呼叫端 `client.chat.completions.create(**kwargs)` 完全不變
- `groq` SDK 可以從 `pyproject.toml` 完全移除，降低依賴數量
- Groq endpoint：`https://api.groq.com/openai/v1`（需要 `GROQ_API_KEY` 環境變數）
- Ollama endpoint：`http://localhost:11434/v1`，`api_key="ollama"`（dummy value，Ollama 不驗證）
- Ollama 的 host/port **不需要** config 欄位：Ollama 本地 port 固定 `11434`，host 不會變；若有需要再加

### TTS：必須有 Base Class

- GPT-SoVITS 是 HTTP 同步 streaming（`requests.Response`）
- edge-tts 是 Python async generator（`edge_tts.Communicate.stream()`）
- 兩者底層差異太大，`AvatarController` 需要統一的 `get_chunk_generator()` 介面

### edge-tts async → sync 橋接方式

**問題根源**：`edge_tts.Communicate.stream()` 是 Python async generator，必須在 event loop 裡執行。但 `AvatarController.perform()` 是同步函式（普通 `for` 迴圈），且 FastAPI/uvicorn 已有一個 event loop 在跑，直接呼叫 `asyncio.run()` 會拋 `RuntimeError: This event loop is already running`。

**對比現況**：GPT-SoVITS 的 `_generate_stream()` 是普通 `requests.get(..., stream=True)`，完全同步，沒有這個問題。

**解法**：`asyncio.new_event_loop()` 開一個獨立 loop，收集所有 audio bytes 後再 yield，與 FastAPI 的 event loop 完全隔離。

```python
def get_chunk_generator(self, text: str, volume: float = 1.0) -> Generator:
    async def _collect_audio() -> list[bytes]:
        chunks = []
        comm = edge_tts.Communicate(text, self.voice, rate=self.rate)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return chunks

    loop = asyncio.new_event_loop()
    try:
        audio_chunks = loop.run_until_complete(_collect_audio())
    finally:
        loop.close()

    for data in audio_chunks:
        # 音量控制（與 GPT-SoVITS 相同的 numpy PCM 處理）
        yield _apply_volume(data, volume)
```

**代價**：需等所有音訊收到才開始播放（延遲約 500-800ms），但 edge-tts 定位是 fallback/輕量服務，延遲可接受。

### TTS Fallback 機制

**不實作對話中途的 runtime auto-fallback**。理由：
- 靜默切換會讓聲音突然從 clone 語音變成 Microsoft 語音，用戶不知道發生什麼事
- 對話中途 GPT-SoVITS 掛掉是非預期故障，不是本 Spec 要解決的問題

**Startup 連線檢查（warning）**

`GPTSoVITSV2Client.__init__()` 初始化時對 server 發一次 ping，若失敗則輸出 warning 附修復指引而非拋例外：

```python
logger.warning(
    f"GPT-SoVITS server at {self.base_url} is unreachable. "
    "TTS will fail at runtime. "
    "Start the server, or set `tts.provider: edge_tts` in config.yaml"
)
```

理由：TTS 失敗只是無聲，LLM 回應仍然完整（pipeline 不會完全斷掉），因此不需要 fail fast。用戶看到 warning 清楚知道原因即可修復。

**LLM startup health check（fail fast）**：`create_llm_client()` 建立 client 後立刻呼叫 `client.models.list()`（GET 請求，不耗 token，不計費），若失敗（key 無效、endpoint 不通）立刻拋出清楚的錯誤。避免使用者說完話等到 LLM 呼叫才發現 bad request。

**語音切換方式**：在 `config.yaml` 改 `tts.provider: edge_tts` 即可，一行切換。Edge-tts 的語音永遠從 `tts.edge_tts.voice` config 欄位讀取，不 hardcode。

---

## Implementation

### [x] Step 1. 更新 `pyproject.toml` 依賴
**Goal**: 移除 `groq` SDK，加入 `openai` SDK 作為唯一 LLM client  
**Reason**: Groq 支援 OpenAI-compatible endpoint，不需要獨立 SDK；統一用 `openai` 可減少依賴數量  
**Implementation Details**:
- 執行 `uv remove groq && uv add openai`
- 確認 `pyproject.toml` 的 `dependencies`：移除 `groq>=1.0.0`，加入 `openai>=1.0.0`

---

### [x] Step 2. 更新 `config.yaml` 和 `config.example.yaml`
**Goal**: 加入 LLM provider 切換欄位 + TTS provider 切換欄位 + edge-tts 語音設定  
**Reason**: 所有 provider 切換邏輯的來源依據都在 config  
**Implementation Details**:

`llm` 區塊新增：
```yaml
llm:
  provider: "groq"   # groq / ollama
  model: "openai/gpt-oss-20b"
  ...
```

`tts` 區塊新增：
```yaml
tts:
  provider: "gptsovits"   # gptsovits / edge_tts
  playback_volume: 0.03   # pyaudio 播放音量乘數（0.0-2.0）
  gptsovits:
    language: "zh"        # TTS 語言：zh / en / ja
  edge_tts:
    voice: "zh-TW-HsiaoChenNeural"
    # 可用中文語音：
    # zh-TW: HsiaoChenNeural(F) / YunJheNeural(M) / HsiaoYuNeural(F)
    # zh-CN: XiaoxiaoNeural(F) / YunxiNeural(M) / XiaoyiNeural(F) / YunyangNeural(M-新語)
    # zh-HK: HiuMaanNeural(F) / HiuGaaiNeural(F) / WanLungNeural(M)
    rate: "+0%"      # 語速調整，如 +10% / -5%
    volume: "+0%"    # 音量調整（edge-tts 層，與 playback_volume 分開）
```

---

### [x] Step 3. 建立 `services/llm_factory.py`
**Goal**: 工廠函式 `create_llm_client(config)` 根據 provider 欄位回傳 `openai.OpenAI` instance，並做 startup health check  
**Reason**: 統一使用 `openai` SDK；startup `models.list()` 確保 key 有效，避免使用者說完話才遇到 bad request  
**Implementation Details**:
- 函式簽名：`def create_llm_client(config: dict) -> OpenAI:`
- `provider == "groq"` → `OpenAI(base_url="https://api.groq.com/openai/v1", api_key=os.getenv("GROQ_API_KEY"))`
- `provider == "ollama"` → `OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")`
- 建立 client 後立刻呼叫 `client.models.list()`（GET 請求，不耗 token），失敗則拋 `RuntimeError` 附 provider 名稱與修復提示
- Ollama 同樣走 `models.list()` 驗證（OpenAI-compatible endpoint 支援）
- 未知 provider 拋出 `ValueError`

---

### [x] Step 4. 建立 TTS `BaseTTSClient` 抽象基底類
**Goal**: 定義所有 TTS service 必須實作的統一介面  
**Reason**: `AvatarController` 需要不感知底層差異地呼叫 TTS  
**Implementation Details**:
- 實際路徑：`services/tts/base_tts.py`（後續目錄重組移至此）
- `from abc import ABC, abstractmethod`
- 抽象方法：`get_chunk_generator(self, text: str, volume: float = 1.0) -> Generator[bytes, None, None]`
- 抽象屬性：`sample_rate: int`
- 不定義 `generate_stream()`（這是 GPT-SoVITS 的實作細節，不應進 base class；呼叫端 `AvatarController` 只看到 `get_chunk_generator`）

---

### [x] Step 4.5. 清理 `gpt_sovits_service.py` 無用函式
**Goal**: 刪除所有不再被外部呼叫的函式，縮減檔案從 517 行至約 182 行  
**Reason**: 這些函式是 AllTalk 時代的遺留，播放邏輯已整合進 `AvatarController`，繼續存在只增加維護負擔  
**Implementation Details**:
- 刪除以下方法（確認沒有外部呼叫點）：
  - `play_stream()` — 播放已由 `AvatarController.perform()` 負責
  - `save_to_file()` — 無外部呼叫
  - `_write_wav_file()` — 僅被 `save_to_file()` 呼叫
  - `_fix_wav_header()` — 僅被 `save_to_file()` 呼叫
  - module-level `play_tts()` — standalone utility，無外部呼叫
  - module-level `save_tts()` — standalone utility，無外部呼叫
- 更新 module docstring：移除 `play_tts`/`save_tts` 的使用範例
- 移除因刪除函式而不再需要的 import（`struct`、`pyaudio`）

---

### [x] Step 5. `GPTSoVITSV2Client` 繼承 `BaseTTSClient`
**Goal**: 讓現有 TTS client 符合統一介面，並加入 startup health check  
**Reason**: base class 規定 `get_chunk_generator(text, volume)`，不暴露 HTTP response 細節給呼叫端；startup warning 讓錯誤在啟動時就被發現而非對話途中  
**Implementation Details**:
- class 宣告改為 `class GPTSoVITSV2Client(BaseTTSClient):`
- `__init__` 加入連線檢查：對 `{base_url}/` 發一次 `GET`，timeout 2s，如果連線失敗則輸出 `logger.warning`（**不拋例外**）：
  ```python
  logger.warning(
      f"GPT-SoVITS server at {self.base_url} is unreachable. "
      "TTS will fail at runtime. "
      "Start the server, or set `tts.provider: edge_tts` in config.yaml"
  )
  ```
- `__init__` 新增讀取 `config["tts"]["gptsovits"]["language"]` 儲存為 `self.language`（取代 hardcode `"zh"`）
- **重新命名** `get_stream_generator` → `get_chunk_generator`，并將內部 `generate_stream()` 呼叫內化至方法內
  - 新簽名：`def get_chunk_generator(self, text: str, volume: float = 1.0) -> Generator[bytes, None, None]:`
  - 方法內部先呼叫 `self._generate_stream(text, language=self.language)` 取得 response，再 yield chunks（邏輯不變）
- `generate_stream()` 改為 private `_generate_stream()`（僅供內部 `get_chunk_generator` 呼叫）
- `sample_rate` 屬性已存在，確認符合 base class 要求

---

### [x] Step 6. 建立 `EdgeTTSClient`
**Goal**: 實作輕量 TTS fallback，符合 `BaseTTSClient` 介面  
**Reason**: 讓系統在沒有 GPT-SoVITS server 的環境下也能正常運作；edge-tts 無需本地 GPU，只需網路連線  
**Implementation Details**:
- 檔案：`services/tts/edge_tts_service.py`（目錄重組後從 `audio_processing/` 移至 `services/tts/`）
- `class EdgeTTSClient(BaseTTSClient):`
- `__init__`：從 `config["tts"]["edge_tts"]` 讀取 `voice`, `rate`, `volume` 欄位；`sample_rate = 24000`（edge-tts 輸出固定 24kHz）
- `get_chunk_generator(text, volume)` 實作：
  1. 建立 `edge_tts.Communicate(text, voice=self.voice, rate=self.rate)`
  2. async generator → 同步：用 `asyncio.new_event_loop()` + 自訂 async fn 收集所有 audio bytes
  3. 音量控制：與 GPT-SoVITS 相同的 numpy PCM 處理邏輯（16-bit int）
  4. 逐 chunk yield bytes

---

### [x] Step 7. 更新 `voice_chat_service.py`
**Goal**: 使用工廠函式初始化 LLM / TTS client  
**Reason**: 這是所有 provider 切換的最終接線點，統一透過工廠讓初始化邏輯不散落在業務層  
**Implementation Details**:
- 新增 `from services.llm.llm_factory import create_llm_client`
- 新增 `from services.tts.tts_factory import create_tts_client`
- 移除 `from groq import Groq`、`from services.audio_processing.gpt_sovits_service import GPTSoVITSV2Client`
- 新增 `from openai import OpenAI` 型別用途
- LLM 初始化：`self.groq_client = Groq()` → `self.llm_client = create_llm_client(cfg["llm"])`
- TTS 初始化：`self.tts_client = create_tts_client(cfg["tts"])`（工廠函式取代 if-elif，原始設計為：
  ```python
  provider = cfg["tts"]["provider"]
  if provider == "gptsovits":
      self.tts_client = GPTSoVITSV2Client()
  elif provider == "edge_tts":
      self.tts_client = EdgeTTSClient()
  else:
      raise ValueError(f"Unknown TTS provider: {provider}")
  ```
  後來抽為 `tts_factory.py` 與 `llm_factory.py` 對稱）
- `self.tts_volume: float = cfg["tts"]["playback_volume"]`（新增，取代 hardcode `0.03`）
- `_stream_once()` 中所有 `self.groq_client` → `self.llm_client`
- `self.memory_writer = MemoryWriter(..., groq_client=...)` → `llm_client=self.llm_client`
- `_speak()` 改為：移除 `tts_response = self.tts_client.generate_stream(...)` 準行，改為直接 `self.avatar_service.perform(clean_text, volume=self.tts_volume, emote=emote)`

---

### [x] Step 8. 更新 `memory_writer.py`
**Goal**: 解耦 MemoryWriter 對 Groq SDK 的直接依賴  
**Reason**: MemoryWriter 只使用 `client.chat.completions.create()`，openai SDK 的相同介面可完全取代，不需要知道底層是哪個 provider  
**Implementation Details**:
- 移除 `from groq import Groq`
- 新增 `from openai import OpenAI`
- 建構子參數重新命名：`groq_client: Groq` → `llm_client: OpenAI`
- `self.groq_client` 全域替換為 `self.llm_client`
- 所有 `self.groq_client.chat.completions.create(...)` → `self.llm_client.chat.completions.create(...)`

---

### [x] Step 9. 更新 `avatar_controller.py`
**Goal**: 改為依賴 `BaseTTSClient`，並更新 `perform()` 簽名  
**Reason**: `AvatarController` 是 TTS 的唯一消費者，型別解耦後換 provider 不需要修改 controller；`tts_client.sample_rate` 確保 pyaudio 以正確的採樣率開啟串流  
**Implementation Details**:
- `from services.tts.base_tts import BaseTTSClient`（目錄重組後從 `audio_processing/` 移至 `services/tts/`）
- 建構子型別標注：`tts_client: GPTSoVITSV2Client` → `tts_client: BaseTTSClient`
- `perform()` 中 `self.tts_client.get_stream_generator(response, volume)` → `self.tts_client.get_chunk_generator(text, volume)`
  - 注意：呼叫介面改變，`get_chunk_generator` 不需要先呼叫 `generate_stream()`，text 直接傳入
  - 這意味著 `perform()` 的簽名也需要改：移除 `response: requests.Request` 參數，改為 `text: str`
  - 同步修改 `voice_chat_service.py` 中呼叫 `avatar_service.perform()` 的地方

---

## Quiz Record

| # | Type | Question | Answer Summary | Result |
|---|------|----------|----------------|--------|
| 1 | Design Decision | pyaudio `rate` 如何取得正確的 sample_rate | `tts_client.sample_rate` 傳入 `pyaudio.open(rate=...)` | ✅ |
| 2 | Edge Case | edge-tts async 橋接中途網路失敗，`finally` 和 bytes 怎處理 | `finally` 必執行 loop.close()，收到的 bytes 被 GC 回收 | ✅ |
| 3 | Consequence | 不做 startup check 的後果 | 整條pipeline斷，用戶不知原因；早發現早修復 | ✅ |
| 4 | Background Knowledge | `openai.OpenAI()` 初始化是否驗證 key | 誤認初始化時會驗證 | ❌ |
| 4b | Background Knowledge | `@abstractmethod` 子類未實作，何時報錯 | 献測為 class 定義時 | ❌ |
| 4c | Background Knowledge | streaming 與 non-streaming 回傳物件差異 | `Stream[ChatCompletionChunk]` 迭代器，每 chunk 只有 `delta`，不是完整 `message` | ✅ |
| 5 | Rollback | Step 4.5 刪到一半需還原 | 實作和測試都可以刪除，該函式已不需要 | ✅ |
| 6 | Acceptance Criteria | Step 3 完成後如何快速驗證工廠函式 | 對 Groq 初始化一次 OpenAI 物件，或用 `models.list()` 驗證相容性 | ✅ |

**Score**: 5/6 &nbsp; **Overall**: Pass ✅ &nbsp; **Rounds taken**: 3（Q4 第三輪通過）

---

## Test Generate

### Test Plan
1. **`test_llm_factory.py`**: provider 驗證（missing/empty/unknown）、base_url 對應（groq/ollama）、health check（成功/失敗/錯誤訊息）
2. **`test_tts_factory.py`**: provider 驗證（missing/empty/unknown）、provider → class 型別對應（gptsovits/edge_tts）、回傳型別為 BaseTTSClient 子類
3. **`test_base_tts.py`**: ABC 無法直接實例化、未實作抽象方法的子類無法實例化、正確實作的子類行為驗證

### Mock 策略
- `OpenAI()` → `patch("services.llm.llm_factory.OpenAI")`，回傳 MagicMock
- `client.models.list()` → `mock_client.models.list.return_value` / `.side_effect`
- `GPTSoVITSV2Client.__init__` / `EdgeTTSClient.__init__` → `patch.object(..., "__init__", return_value=None)`，避免觸發 config 讀取與 startup ping
- `BaseTTSClient` 測試：純 Python ABC，無需 Mock

---

## Unit Test

### 1st Execution（2026-03-06）
- ✅ test_llm_factory.py — 11 passed
- ✅ test_tts_factory.py — 7 passed
- ✅ test_base_tts.py — 6 passed
- **總計：24/24 passed**

---

## Spec Amendments

### 2026-03-06 - 目錄結構重組與新增 tts_factory.py

#### Reason
實作過程中為提升可維護性，將 LLM 相關檔案歸入 `services/llm/`，TTS 相關檔案從 `audio_processing/` 獨立出來至 `services/tts/`，並新增 `tts_factory.py` 與 `llm_factory.py` 對稱。

#### Changes
1. **新增 `services/tts/tts_factory.py`**: 與 `llm_factory.py` 對稱的 `create_tts_client(config)` 工廠函式，以 `_PROVIDER_MAP` 取代 if-elif
2. **新增 `services/llm/` 目錄**: 移入 `llm_factory.py`, `tools.py`, `tool_calling_handler.py`
3. **新增 `services/tts/` 目錄**: 移入 `base_tts.py`, `gpt_sovits_service.py`, `edge_tts_service.py`, `tts_factory.py`
4. **config 結構調整**: `tts.host/port/...` 全部歸入 `tts.gptsovits.*` 子區塊
5. **llm_factory.py 改良**: `_PROVIDER_MAP` const dict 取代 if-elif，provider 改為必填（缺失 ValueError）

#### Impact
- 修改 import 路徑的檔案：`voice_chat_service.py`, `avatar_controller.py`, `gpt_sovits_service.py`, `edge_tts_service.py`, `tts_factory.py`
- 最終 `services/` 結構：`llm/ | tts/ | audio_processing/ | core/ | memory/ | visual/ | monitoring/`
