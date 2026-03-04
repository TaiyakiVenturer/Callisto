# SPEC: Memory Layer Integration

## Task Description
將 CallistoMemory_Test 沙盒中已驗證的記憶層（Phase 1-3）完整移植進 Callisto 主專案，
使 Callisto 具備長期記憶能力。整合後 `VoiceChatService` 的對話流程將支援：
- **主動記憶搜尋**（LLM 透過 `SearchMemory` tool call 查詢過去記憶）
- **背景記憶寫入**（每輪對話結束後非阻塞地保存有價值的資訊）
- **自動記憶遺忘**（啟動時執行 forgetting cycle，移除低活躍度記憶）

## Tech Stack
- SQLite + SQLAlchemy（結構化儲存 + FTS5 全文搜尋）
- ChromaDB（向量儲存，語義搜尋）
- Ollama `nomic-embed-text-v2-moe`（embedding 服務）
- Groq API `llama-3.3-70b-versatile`（記憶分析 / 寫入判斷）
- FastAPI Background Tasks（非阻塞記憶寫入）
- Python `concurrent.futures.ThreadPoolExecutor`（在 background thread 中 fire-and-forget 記憶寫入）

## Acceptance Criteria
- [x] `backend/services/memory/` 下存在完整六個服務模組（sql, embedding_service, vector_store, retrieval, memory_writer, forgetting）及 `__init__.py`
- [x] `backend/services/tools.py` 與 `backend/services/tool_calling_handler.py` 存在並與沙盒一致
- [x] `VoiceChatService.__init__` 成功初始化所有記憶服務實例
- [x] `VoiceChatService._get_tools()` 回傳 `SearchMemory` tool definition
- [x] `VoiceChatService._execute_tool()` 正確路由到 `ToolCallingHandler.handle()`
- [x] `VoiceChatService._speak()` 在每輪 TTS 後透過 executor 非阻塞觸發 `MemoryWriter.write()`
- [x] `api_server.py` lifespan 在啟動時執行 forgetting cycle
- [x] `backend/config.yaml` 包含完整 `memory` 設定區塊（含 `writer_system_prompt`）
- [x] `backend/config.example.yaml` 包含完整 `memory` 設定區塊（含說明注解）
- [x] `backend/pyproject.toml` 新增 `chromadb`, `httpx`, `sqlalchemy`, `pyyaml` 依賴
- [x] `backend/config.py` 加入全局 `_cache` + `reset_cache()`，確保同 process 只讀一次 yaml
- [x] `get_errors` 無 compile/import 錯誤（sqlalchemy/chromadb 的 unresolved import 屬套件未安裝，非程式碼錯誤）

## Target Files
- **修改（沙盒）**：`CallistoMemory_Test/services/memory/memory_writer.py`
- **修改（沙盒）**：`CallistoMemory_Test/config.yaml`
- **修改（沙盒）**：`CallistoMemory_Test/config.example.yaml`
- 新建：`backend/services/memory/sql.py`
- 新建：`backend/services/memory/embedding_service.py`
- 新建：`backend/services/memory/vector_store.py`
- 新建：`backend/services/memory/retrieval.py`
- 新建：`backend/services/memory/memory_writer.py`
- 新建：`backend/services/memory/forgetting.py`
- 新建：`backend/services/tools.py`
- 新建：`backend/services/tool_calling_handler.py`
- 修改：`backend/services/core/voice_chat_service.py`
- 修改：`backend/api_server.py`（lifespan）
- 修改：`backend/config.yaml`
- 修改：`backend/config.example.yaml`
- 修改：`backend/pyproject.toml`
- 修改：`backend/config.py`

---

## Implementation

### [x] Step 0. 先在沙盒提取 writer_system_prompt 至 config
**Goal**: 在 CallistoMemory_Test 中，將 `memory_writer.py` 的 `_SYSTEM_PROMPT` 移至 `config.yaml`，讓沙盒本身就是已提取版本，後續複製到 Callisto 時直接正確  
**Reason**: 若先複製再改，等於要改兩份；在沙盒修改後複製，只需改一次。同時讓沙盒保持可獨立執行且設定集中  
**Implementation Details**:
- `CallistoMemory_Test/config.yaml`：在 `memory.llm` 下新增 `writer_system_prompt: |` 欄位，內容為原 `_SYSTEM_PROMPT` 字串（附警告注解：此 prompt 與記憶 DB schema 強耦合，修改前請確認理解程式執行流程，後果自負）
- `CallistoMemory_Test/config.example.yaml`：同步加入 `writer_system_prompt` 欄位（內容可為提示性範本文字，或直接附上完整預設值）
- `CallistoMemory_Test/services/memory/memory_writer.py`：刪除模組層 `_SYSTEM_PROMPT` 常數，改在 `__init__` 讀取 `load_config()["memory"]["llm"]["writer_system_prompt"]` 存為 `self.writer_system_prompt`，並在 `analyze()` 中替換使用

### [x] Step 1. 複製六個記憶服務模組到 Callisto
**Goal**: 建立 `sql.py`, `embedding_service.py`, `vector_store.py`, `retrieval.py`, `memory_writer.py`, `forgetting.py`  
**Reason**: 這些模組來自已通過全測試套件的沙盒，可直接複用；唯一需要確認的是 import 路徑（沙盒與 Callisto 均使用相同的 `config.load_config()` 介面）  
**Implementation Details**:
- 直接以 `create_file` 複製六個檔案，`from config import load_config` 路徑不變
- `memory_writer.py` 的 `async_write` 在複製時**直接刪除**：該方法使用 `asyncio.get_event_loop()`（Python 3.12 已棄用），且 Callisto 的 `process_voice` 跑在 background thread 而非 async coroutine，不適用。背景寫入改由 `ThreadPoolExecutor.submit(writer.write, ...)` 取代
- `memory_writer.py` 的 `_SYSTEM_PROMPT` 提取至 `config.yaml` 的 `memory.llm.writer_system_prompt` 欄位，透過 `load_config()` 讀取；在 config 中加上警告注解，說明此 prompt 與 DB schema 強耦合，修改後果自行負責

### [x] Step 2. 建立 tools.py 與 tool_calling_handler.py
**Goal**: 複製 `SearchMemory` Pydantic tool 定義與 `ToolCallingHandler` 路由邏輯  
**Reason**: 讓 `VoiceChatService._get_tools()` 和 `_execute_tool()` 有具體實作對象  
**Implementation Details**:
- `tools.py` → `backend/services/tools.py`（import 路徑不變）
- `tool_calling_handler.py` → `backend/services/tool_calling_handler.py`（從 `services.memory.retrieval` import）

### [x] Step 3. 修改 VoiceChatService 整合記憶層
**Goal**: 在 `__init__` 初始化記憶服務；填入 `_get_tools()`, `_execute_tool()`；在 `_speak()` 觸發背景記憶寫入  
**Reason**: 這是記憶層整合的核心銜接點，main.py 已示範完整 pipeline  
**Implementation Details**:
- `__init__`: 依序普通實例化 MemoryDB → EmbeddingService → VectorStore → RetrievalService → ToolCallingHandler → MemoryWriter → ForgettingService；另建 `self._executor = ThreadPoolExecutor(max_workers=1)` 供背景記憶寫入使用（非用於初始化服務）
- `_get_tools()`: 呼叫 `get_tools()` 回傳 tool definitions list
- `_execute_tool()`: 解析 `arguments_json`，呼叫 `self.tool_handler.handle(name, args)`
- `_speak()`: 在最後加入 `self._executor.submit(self.memory_writer.write, user_msg, full_response)`；但需要從 `generate_response` 傳入 `user_message`（目前 `_speak` 不知道 user msg，需要小幅調整）
  - 方案：在 `generate_response` 內於 `_speak(full_response)` 前存 `self._last_user_message = user_message`，再在 `_speak` 中使用

### [x] Step 4. 更新 api_server.py lifespan 執行 forgetting cycle
**Goal**: 在 FastAPI 啟動時執行一次 forgetting cycle  
**Reason**: 與沙盒 main.py 行為一致，確保每次重啟後先清理低活躍度記憶  
**Implementation Details**:
- 在 lifespan 的 `chat_service = VoiceChatService()` 之後，呼叫 `chat_service.forgetting_service.run_cycle()`
- 以 try/except 包覆，失敗只記錄 warning 不影響啟動

### [x] Step 5. 更新 Callisto config.yaml + config.example.yaml + pyproject.toml + config.py
**Goal**: 補充 memory 設定值、依賴套件，並為 `load_config()` 加入全局快取  
**Reason**: 各服務 `__init__` 各自呼叫 `load_config()`，若無快取則每次 init 都重讀磁碟；`memory` 區塊缺失會 KeyError  
**Implementation Details**:
- `config.yaml`: 在 `max_cache_length` 後追加完整 `memory` 區塊，包含 `llm.writer_system_prompt`（附警告注解：此 prompt 與記憶 DB schema 強耦合，修改前請確認理解程式執行流程，後果自負）
- `config.example.yaml`: 加入帶說明注解的 `memory` 範本區塊
- `pyproject.toml`: 追加 `chromadb>=1.5.2`, `httpx>=0.28.1`, `sqlalchemy>=2.0.46`, `pyyaml>=6.0.3`
- `config.py`: 加入 `_cache: dict | None = None` 全局變數、`reset_cache()` 函式，`load_config()` 改為只讀一次後快取，與沙盒版本完全對齊

---

## Quiz Record

| # | Question | Answer Summary | Result |
|---|----------|----------------|--------|
| 1 | YAML `\|` block scalar 行為 | 保留 `\n`，與原 `_SYSTEM_PROMPT` 行為相同 | ✅ |
| 2 | `async_write` 刪除理由 | `get_event_loop()` 在 background thread 無 running loop，Python 3.12 raise RuntimeError | ✅ |
| 3 | `user_message` 如何傳進 `_speak()` | `generate_response` 存 `self._last_user_message`，`_speak` 讀取 | ✅ |
| 4 | `_execute_tool` arguments 處理 | `_stream_once` 回傳 `dict[int, dict]`，`arguments` 欄位仍是 JSON 字串，`json.loads` 在 `_execute_tool` 內處理 | ❌（方向正確，但誤描述為 stream 直接回傳字串，實為 dict 結構）|
| 5 | `forgetting_service` 屬性名稱 | `self.forgetting_service`，lifespan 呼叫 `chat_service.forgetting_service.run_cycle()` | ✅ |
| 6 | `reset_cache()` 用途 | 測試 teardown 用；生產不呼叫，第一次 `load_config()` 後即快取 | ✅ |

**Score**: 5/6 &nbsp; **Overall**: PASS &nbsp; **Rounds taken**: 1

---

## Test Generate

### Test Plan
1. **`MemoryCache.get_recent_turns()` 基本功能**：單輪、多輪、n 限制、n 超過可用數、空歷史
2. **Tool call 過濾**：跳過 content=None 的 assistant、跳過 role=tool、中間有 tool call 的多輪、連續 tool calls
3. **邊界情況**：時間順序確認、尚無 assistant 回覆、n=0

### Mock 策略
- `load_config`: `unittest.mock.patch` 替換，避免依賴真實 config.yaml
- `chat_history`: 測試中直接賦值（繞過 `add_history` 驗證，確保測試目標單一）

---

## Unit Test

### Callisto `tests/test_memory_cache.py` — 第 1 次執行
- [✅] test_single_turn_returns_one_pair - PASS
- [✅] test_multiple_turns_returns_in_order - PASS
- [✅] test_n_limits_returned_pairs - PASS
- [✅] test_n_larger_than_available_returns_all - PASS
- [✅] test_empty_history_returns_empty - PASS
- [✅] test_skips_assistant_with_no_content - PASS
- [✅] test_skips_tool_role_messages - PASS
- [✅] test_multi_turn_with_tool_call_in_middle - PASS
- [✅] test_consecutive_tool_calls_before_final_response - PASS
- [✅] test_returns_chronological_order - PASS
- [✅] test_no_assistant_response_yet - PASS
- [✅] test_n_zero_returns_empty - PASS

**12/12 PASS** — 0.17s

### CallistoMemory_Test `tests/test_memory_writer.py` — 簽名更新後驗證
- [✅] TestAnalyze — 6 tests PASS
- [✅] TestWrite — 7 tests PASS（含新增 test_write_returns_false_on_empty_turns）

**13/13 PASS** — 3.06s

### Callisto `tests/test_embedding_service.py` + CallistoMemory_Test `tests/test_embedding_service.py` — ollama SDK 遷移後測試

**背景**：embedding_service.py 從 httpx 直接呼叫改為 ollama Python SDK（`ollama>=0.4.7`），  
新增 `embed_batch()`，錯誤處理改為 `ollama.ResponseError` 與 `Exception`。

Mock 策略：`patch.object(service._client, "embed", return_value={"embeddings": [...]})` 替代舊的 `patch("httpx.post", ...)`

**Callisto — 第 1 次執行**
- [✅] TestEmbedSuccess::test_embed_returns_list_of_floats - PASS
- [✅] TestEmbedSuccess::test_embed_calls_with_correct_model_and_input - PASS
- [✅] TestEmbedSuccess::test_embed_returns_first_vector - PASS
- [✅] TestEmbedValidation::test_empty_string_raises_value_error - PASS
- [✅] TestEmbedValidation::test_whitespace_only_raises_value_error - PASS
- [✅] TestEmbedFailures::test_connection_error_raises_embedding_unavailable - PASS
- [✅] TestEmbedFailures::test_response_error_raises_embedding_unavailable - PASS
- [✅] TestEmbedFailures::test_empty_embeddings_list_raises_unavailable - PASS
- [✅] TestEmbedFailures::test_empty_first_vector_raises_unavailable - PASS
- [✅] TestEmbedBatch::test_embed_batch_returns_multiple_vectors - PASS
- [✅] TestEmbedBatch::test_embed_batch_empty_input_returns_empty - PASS
- [✅] TestEmbedBatch::test_embed_batch_calls_sdk_with_list - PASS
- [✅] TestEmbedBatch::test_embed_batch_connection_error_raises_unavailable - PASS

**13/13 PASS** — 12.34s

**CallistoMemory_Test — 第 1 次執行（完全重寫）**：同上 13/13 PASS — 12.89s

---

## Spec Amendments

### 2026-03-04 - Multi-turn Batch Write + MemoryCache.get_recent_turns + Few-shot Prompt

#### Reason
原實作中 `_last_user_message` 每輪覆蓋，`write_interval=3` 時只有第 3 輪的訊息被傳入 writer，第 1、2 輪永久丟失。同時發現 `MemoryCache` 已持有完整 `chat_history`，可直接提供近 N 輪對話，無需額外維護 buffer 狀態。

#### Changes
1. **`MemoryCache.get_recent_turns(n)`**：新增方法，從 `chat_history` 倒序提取最近 n 輪有效 `(user, assistant)` 對，跳過 `content=None` 的 tool_calls 中繼訊息與 `role=tool` 訊息
2. **`MemoryWriter.write()` / `analyze()` 改為多輪簽名**：`write(turns: list[tuple[str, str]])` + `analyze(turns: list[tuple[str, str]])`，`user_content` 格式改為 `[Turn N]\nUser: ...\nAssistant: ...`
3. **`voice_chat_service.py` 移除 `_last_user_message`**：`_speak()` 觸發時改呼叫 `self.memory_cache.get_recent_turns(self._memory_write_interval)`，取得整批後送入 `memory_writer.write()`
4. **`writer_system_prompt` 更新（兩邊 config）**：描述改為多輪輸入格式，加入 4 個 few-shot 範例（明確 save、邊緣 save 跨輪次習慣、明確 skip 閒聊、邊緣 skip 一次性念頭）
5. **沙盒同步**：`CallistoMemory_Test/services/memory/memory_writer.py`、`config.yaml`、`config.example.yaml`、`main.py`、`tests/test_memory_writer.py` 全部同步

#### Code Changes
**Before** (`voice_chat_service.py`):
```python
self._last_user_message: str = ""
# ...
self._last_user_message = user_message
# ...
self._executor.submit(self.memory_writer.write, self._last_user_message, full_response)
```

**After**:
```python
# __init__ 移除 _last_user_message
# _speak() 改為：
turns = self.memory_cache.get_recent_turns(self._memory_write_interval)
if turns:
    self._executor.submit(self.memory_writer.write, turns)
```

#### Impact
- 修改檔案：`memory_cache.py`, `memory_writer.py`（兩邊）, `voice_chat_service.py`, `config.yaml`（兩邊）, `config.example.yaml`（兩邊）, `main.py`（沙盒）, `test_memory_writer.py`（沙盒）
- 修復 bug：第 1、2 輪對話不再丟失
- 提升記憶品質：跨輪次習慣（如 Turn 1 提到不習慣滑鼠、Turn 2 點出用 vim 多年）現在可被正確識別為值得保存
- Few-shot 範例：`write_interval=3` 時 LLM 接收完整 3 輪對話批次 + 4 個邊界範例，判斷準確度上升

#### Test Results
- 沙盒 `test_memory_writer.py`：所有呼叫簽名更新完畢，新增 `test_write_returns_false_on_empty_turns`（空列表防呆測試）
- Callisto 端 `MemoryCache.get_recent_turns()` 為新功能，尚未有對應測試（待 Phase 4）

---

### 2026-03-05 - EmbeddingService 遷移至 ollama Python SDK

#### Reason
原實作使用 `httpx.post` 直接呼叫 `/api/embeddings` REST endpoint，回傳格式為 `{"embedding": [...]}` 單數鍵。ollama 官方 Python SDK 已成熟，提供 `ollama.Client.embed()` 方法，回傳 `{"embeddings": [[...]]}` 複數鍵，支援單筆與批次輸入，並有型別安全與更新維護保障。

#### Changes
1. **`embedding_service.py`（兩邊）**：移除 `import httpx`，改用 `import ollama`；`__init__` 建立 `self._client = ollama.Client(host, timeout)`；`embed()` 改呼叫 `self._client.embed(model, input)`；新增 `embed_batch(texts)` 批次方法
2. **錯誤處理更新**：移除 `httpx.ConnectError` / `TimeoutException` / `HTTPStatusError` 三種捕捉，改為 `ollama.ResponseError`（API 錯誤）+ 通用 `Exception`（含連線錯誤）
3. **pyproject.toml（兩邊）**：移除 `httpx>=0.28.1`，加入 `ollama>=0.4.7`
4. **測試重寫**：沙盒 `test_embedding_service.py` 全面重寫（mock 策略改為 `patch.object(service._client, "embed", ...)`）；Callisto `tests/test_embedding_service.py` 新建

#### Code Changes
**Before** (`embed()`):
```python
response = httpx.post(url, json={"model": ..., "prompt": text}, timeout=...)
data = response.json()
return data.get("embedding")
```

**After**:
```python
result = self._client.embed(model=self.model, input=text)
return result["embeddings"][0]
```

#### Impact
- 修改檔案：`embedding_service.py`（兩邊）、`pyproject.toml`（兩邊）、`tests/test_embedding_service.py`（兩邊重寫/新建）
- 新功能：`embed_batch(texts)` 批次向量化，可一次呼叫 SDK 處理多筆文字
- 移除 httpx 直接依賴（ollama SDK 內部已使用 httpx，但這是 SDK 實作細節）

#### Test Results
- Callisto `tests/test_embedding_service.py`：**13/13 PASS** — 12.34s
- CallistoMemory_Test `tests/test_embedding_service.py`：**13/13 PASS** — 12.89s
- 覆蓋：成功路徑 3 cases、輸入驗證 2 cases、錯誤處理 4 cases、批次 4 cases

