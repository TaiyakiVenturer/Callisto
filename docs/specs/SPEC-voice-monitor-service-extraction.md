# SPEC: Voice Monitor WebSocket Service 抽取重構

## Task Description

將 `api_server.py` 中的 WebSocket 業務邏輯抽取到獨立的 Service 層，實現路由邏輯與業務邏輯分離。

**目標**：
- 將 `voice_monitor_endpoint()` 中的 200+ 行業務邏輯抽取到獨立服務
- 保持原有功能不變（Producer-Consumer、VAD Debounce、Serial KWS）
- 為未來的 `vad_only` 模式擴展奠定基礎
- 提升代碼可測試性和可維護性

**使用場景**：
1. 當前：持續音訊監聽（VAD + KWS 檢測）
2. 未來：支援兩種模式切換（monitoring / vad_only）

## Tech Stack

- **Backend**: FastAPI, asyncio, WebSocket
- **Architecture**: Producer-Consumer Pattern
- **Services**: AudioMonitorService (已存在)
- **Testing**: pytest, pytest-asyncio, pytest-mock

## Acceptance Criteria

- [x] 創建 `VoiceMonitorWebSocketService` 類別
- [x] 抽取 `audio_processor()` / `event_sender()` 到服務內
- [x] 抽取 AudioMonitorService 初始化邏輯
- [x] 抽取佇列管理、任務生命週期管理
- [x] `api_server.py` 的 WebSocket endpoint 簡化為 < 30 行
- [x] 原有功能保持不變（VAD、KWS、cooldown）
- [x] 支援未來的模式切換介面（預留 `switch_mode()` 方法）
- [x] 單元測試覆蓋率 > 80%（實際達成 93%）
- [x] 整合測試確認 WebSocket 連接正常運作

## Target Files

**新增**：
- `backend/services/voice_monitor_websocket_service.py`（主要服務類別）

**修改**：
- `backend/api_server.py`（簡化 WebSocket endpoint）
- `backend/services/__init__.py`（匯出新服務）

**測試**：
- `backend/tests/test_voice_monitor_websocket_service.py`（新增）
- `backend/tests/test_api_server.py`（更新）

---

## Implementation

### [x] Step 1. 創建 VoiceMonitorWebSocketService 類別骨架

**Goal**: 建立服務類別的基本結構，定義初始化參數和核心方法簽名

**Reason**: 先定義清晰的介面，確保設計符合需求後再實作細節

**Implementation Details**:
- 在 `backend/services/voice_monitor_websocket_service.py` 創建新文件
- 類別初始化參數：`websocket: WebSocket`, `mode: str = 'monitoring'`
- 核心方法：
  * `async def start()` - 啟動服務（初始化佇列、啟動背景任務）
  * `async def handle_audio_stream()` - 主循環處理音訊
  * `async def switch_mode(mode: str)` - 切換模式（預留介面）
  * `async def cleanup()` - 清理資源
- 內部屬性：
  * `self.audio_queue: asyncio.Queue` - 音訊處理佇列
  * `self.event_queue: asyncio.Queue` - 事件發送佇列
  * `self.monitor_service: AudioMonitorService` - 音訊監聽服務
  * `self._processor_task: asyncio.Task` - processor 背景任務
  * `self._sender_task: asyncio.Task` - sender 背景任務

### [x] Step 2. 抽取 AudioMonitorService 初始化邏輯

**Goal**: 將 AudioMonitorService 的創建和配置邏輯移到服務內部

**Reason**: 隱藏初始化細節，endpoint 不需要知道具體的 VAD/KWS 配置參數

**Implementation Details**:
- 從 `api_server.py` 複製 AudioMonitorService 初始化代碼（lines 332-345）
- 在 `VoiceMonitorWebSocketService.__init__()` 中初始化
- 配置參數：
  * `vad_threshold=0.6` - VAD 閾值
  * `kws_threshold=0.7` - KWS 閾值
  * `buffer_duration=1.5` - 環形 buffer 持續時間
  * `keyword_cooldown=1.0` - KWS cooldown 時間
- 調用 `self.monitor_service.reset()` 初始化狀態
- 保持配置參數可自訂（可選：作為 `__init__` 參數）

### [x] Step 3. 抽取 audio_processor() 消費者邏輯

**Goal**: 將音訊處理的 Consumer 邏輯封裝為服務的私有方法

**Reason**: 解耦音訊處理流程，便於單獨測試和維護

**Implementation Details**:
- 從 `api_server.py` 複製 `audio_processor()` 函數（lines 250-304）
- 重構為 `async def _audio_processor(self)` 私有方法
- 依賴調整：
  * `audio_queue` → `self.audio_queue`
  * `event_queue` → `self.event_queue`
  * `monitor_service` → `self.monitor_service`
- 保持原有邏輯不變：
  * 從 audio_queue 取音訊塊
  * 呼叫 `monitor_service.process_audio_chunk()`
  * 接收事件並轉發到 event_queue
- 日誌保持原樣（`logger.info/warning`）

### [x] Step 4. 抽取 event_sender() 消費者邏輯

**Goal**: 將事件發送的 Consumer 邏輯封裝為服務的私有方法

**Reason**: 統一管理 WebSocket 事件發送，減少 endpoint 的職責

**Implementation Details**:
- 從 `api_server.py` 複製 `event_sender()` 函數（lines 307-327）
- 重構為 `async def _event_sender(self)` 私有方法
- 依賴調整：
  * `event_queue` → `self.event_queue`
  * `websocket` → `self.websocket`
- 保持原有邏輯不變：
  * 從 event_queue 取事件
  * 通過 WebSocket 發送 JSON
  * 日誌記錄發送狀態
- 錯誤處理保持一致（catch WebSocketDisconnect）

### [x] Step 5. 實作 start() 和 handle_audio_stream() 方法

**Goal**: 實現服務的啟動和音訊流處理主循環

**Reason**: 這是服務的核心功能，負責整個 WebSocket 連接的生命週期管理

**Implementation Details**:
- `start()` 方法：
  * 初始化 `asyncio.Queue` (audio_queue maxsize=50, event_queue maxsize=20)
  * 使用 `asyncio.create_task()` 啟動 `_audio_processor()` 和 `_event_sender()`
  * 保存 task 引用到 `self._processor_task` 和 `self._sender_task`
  * 發送 "connected" 事件到客戶端
  * 日誌記錄連接建立
- `handle_audio_stream()` 方法：
  * 從 `api_server.py` 複製主循環邏輯（lines 376-402）
  * 使用 `asyncio.wait_for()` 接收 WebSocket 訊息（timeout=0.1）
  * 檢查訊息類型（bytes），非音訊則中斷
  * 使用 `audio_queue.put_nowait()` 非阻塞放入佇列
  * 處理 QueueFull 異常（計數並記錄警告）
  * 檢查 WebSocket 連接狀態
- 錯誤處理保持原有邏輯（TimeoutError、WebSocketDisconnect）

### [x] Step 6. 實作 cleanup() 資源清理方法

**Goal**: 確保 WebSocket 關閉時正確清理所有資源

**Reason**: 避免資源洩漏，確保背景任務正常終止

**Implementation Details**:
- 從 `api_server.py` 複製 finally 區塊邏輯（lines 418-445）
- `cleanup()` 方法內容：
  * 取消背景任務：`self._processor_task.cancel()` 和 `self._sender_task.cancel()`
  * 等待任務結束：`await asyncio.gather(..., return_exceptions=True)`
  * 重置 AudioMonitorService：`self.monitor_service.reset()`
  * 關閉 WebSocket：`await self.websocket.close()`（catch 異常）
  * 日誌記錄清理完成
- 確保所有步驟在 try-except 中執行（容錯）
- 清空佇列（可選優化）

### [x] Step 7. 預留 switch_mode() 模式切換介面

**Goal**: 為未來的 vad_only 模式擴展預留介面

**Reason**: 按鈕錄音功能需要在 monitoring 和 vad_only 之間切換

**Implementation Details**:
- 定義 `async def switch_mode(self, mode: str)` 方法
- 參數驗證：確保 mode 為 'monitoring' 或 'vad_only'
- 更新 `self.mode` 屬性
- 調用 `self.monitor_service.configure_for_mode(mode)`（預留方法，暫不實作）
- 日誌記錄模式切換
- Docstring 說明：
  * 'monitoring': VAD + KWS 檢測
  * 'vad_only': 僅 VAD 檢測（用於按鈕錄音）
- 目前實作為 placeholder，實際切換邏輯在後續 SPEC 中完成

### [x] Step 8. 簡化 api_server.py 的 WebSocket endpoint

**Goal**: 將 voice_monitor_endpoint 簡化為薄薄的路由層

**Reason**: 實現關注點分離，endpoint 只負責 WebSocket 連接管理

**Implementation Details**:
- 修改 `voice_monitor_endpoint()` 函數（簡化為 ~25 行）
- 導入新服務：`from services.voice_monitor_websocket_service import VoiceMonitorWebSocketService`
- 新的 endpoint 結構：
  ```python
  @app.websocket("/ws/voice-monitor")
  async def voice_monitor_endpoint(websocket: WebSocket):
      await websocket.accept()
      
      service = VoiceMonitorWebSocketService(websocket)
      try:
          await service.start()
          await service.handle_audio_stream()
      except WebSocketDisconnect:
          logger.info("WebSocket 連接已斷開")
      except Exception as e:
          logger.error(f"WebSocket 異常: {e}")
      finally:
          await service.cleanup()
  ```
- 刪除原有的 `audio_processor()` 和 `event_sender()` 輔助函數
- 刪除原有的 AudioMonitorService 初始化代碼
- 保留必要的導入（WebSocket, WebSocketDisconnect, logger）

### [x] Step 9. 更新 services/__init__.py 匯出新服務

**Goal**: 確保新服務可以被其他模組正確導入

**Reason**: 維護統一的服務匯出介面

**Implementation Details**:
- 修改 `backend/services/__init__.py`
- 新增匯出：
  ```python
  from .voice_monitor_websocket_service import VoiceMonitorWebSocketService
  
  __all__ = [
      # 現有服務...
      "VoiceMonitorWebSocketService",
  ]
  ```
- 確保文件編碼和格式一致

---

## Test Generate

### Test Plan

#### 單元測試（test_voice_monitor_websocket_service.py）

1. **初始化測試**
   - `test_init_default_mode` - 測試預設模式為 'monitoring'
   - `test_init_custom_mode` - 測試自訂模式參數
   - `test_monitor_service_initialization` - 驗證 AudioMonitorService 正確初始化

2. **生命週期測試**
   - `test_start_creates_queues` - 驗證 start() 創建佇列
   - `test_start_launches_background_tasks` - 驗證背景任務啟動
   - `test_cleanup_cancels_tasks` - 驗證 cleanup() 取消任務
   - `test_cleanup_resets_monitor_service` - 驗證清理重置 AudioMonitorService

3. **音訊處理測試**
   - `test_audio_processor_processes_chunks` - 測試音訊塊處理流程
   - `test_audio_processor_handles_queue_full` - 測試佇列滿時的處理
   - `test_event_sender_sends_events` - 測試事件發送

4. **模式切換測試**
   - `test_switch_mode_updates_mode_attribute` - 測試模式屬性更新
   - `test_switch_mode_invalid_mode_raises` - 測試無效模式拋出異常

5. **錯誤處理測試**
   - `test_handle_websocket_disconnect` - 測試 WebSocket 斷線處理
   - `test_handle_audio_stream_timeout` - 測試接收超時處理

#### 整合測試（test_api_server.py 更新）

6. **WebSocket 端點測試**
   - `test_voice_monitor_endpoint_connection` - 測試連接建立
   - `test_voice_monitor_endpoint_audio_stream` - 測試音訊流處理
   - `test_voice_monitor_endpoint_disconnection` - 測試正常斷線
   - `test_voice_monitor_endpoint_service_integration` - 測試與服務層整合

### Mock Strategy

- **Mock 對象**：
  * `WebSocket` - 模擬 WebSocket 連接（accept, send_json, receive, close）
  * `AudioMonitorService` - 模擬音訊監聽服務（process_audio_chunk, reset）
  * `asyncio.Queue` - 使用真實佇列（不需 mock）
  * `asyncio.create_task` - 部分測試需 mock 以控制任務

- **工具**：
  * pytest-asyncio - 支援 async/await 測試
  * pytest-mock - 提供 mocker fixture
  * unittest.mock - AsyncMock for async methods

- **測試資料**：
  * 模擬音訊塊：`b'\x00' * 512` (16-bit PCM)
  * 模擬事件：`{"type": "keyword_detected", "keyword": "test"}`

---

## Unit Test

### 1st Execution - 測試通過
- ✅ **20 個測試全部通過**
- ✅ **覆蓋率: 93%** (超過目標 80%)
- 執行時間: 9.07 秒

**測試類別分佈**:
1. 初始化測試 (3 個) - ✅ PASS
2. 生命週期測試 (5 個) - ✅ PASS  
3. 音訊處理測試 (4 個) - ✅ PASS
4. 音訊流測試 (5 個) - ✅ PASS
5. 模式切換測試 (2 個) - ✅ PASS
6. 錯誤處理測試 (1 個) - ✅ PASS

**未覆蓋代碼**:
- Line 180-181: silence 事件處理（無需發送，故意跳過）
- Line 227-235: error 事件處理（低頻路徑）

**結論**: 核心功能 100% 覆蓋，包含關鍵的 `handle_audio_stream()` 主循環邏輯

---

## Spec Amendments

### 2026-01-21 - 補充 handle_audio_stream 測試覆蓋

#### Reason
初始測試覆蓋率 73%，缺少對 `handle_audio_stream()` 主循環的測試覆蓋。這是服務的核心邏輯，必須確保完整測試。

#### Changes
1. **新增 TestVoiceMonitorWebSocketServiceAudioStream 測試類別**
   - 測試音訊流接收處理
   - 測試 WebSocket 斷線處理
   - 測試超時處理
   - 測試佇列滿時的處理
   - 測試客戶端斷線檢測

#### Impact
- 測試數量: 15 個 → 20 個 (+5)
- 覆蓋率: 73% → **93%** (+20%)
- 關鍵函數 `handle_audio_stream()` 完整覆蓋

#### Test Results
- 所有測試通過: 20/20 ✅
- 覆蓋率達標: 93% > 80% ✅
- 核心邏輯覆蓋: handle_audio_stream、_audio_processor、_event_sender 全部測試

