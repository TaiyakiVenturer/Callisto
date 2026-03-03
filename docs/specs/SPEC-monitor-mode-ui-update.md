# SPEC: 監聽模式 WebSocket 狀態推送

## Task Description

修復監聽模式下後端不發送處理狀態事件的問題，讓前端能實時接收 transcript、response 和 speaking 狀態。

**目前問題**：
1. 監聽模式下，前端上傳音頻到 `/api/chat/voice`，後端調用 `process_voice()` 處理
2. **後端只發送 `keyword` 和 `speech` 事件**，不發送 `transcript`、`response`、`speaking`、`done` 事件
3. 前端 `useVoiceMonitor.ts` 已經寫好接收邏輯，但收不到這些事件
4. 結果：
   - 前端只能看到監聽狀態（keyword/speech）
   - **看不到 transcript（轉錄文字）**
   - **看不到 response（AI 回應）**
   - **看不到 speaking 狀態（TTS 播放）**
   - 聊天訊息列表無更新

**根本原因**：
- `VoiceChatService.process_voice()` 只更新 `app_state`，沒有 WebSocket 連接
- `VoiceMonitorWebSocketService` 不知道音頻處理的進度

**預期行為**：
- 音頻上傳後，後端透過 WebSocket 實時推送：
  - `transcribing` → STT 開始
  - `transcript` → STT 完成，推送文字
  - `generating` → LLM 開始
  - `response` → LLM streaming，實時累積推送回應
  - `speaking` → TTS 開始播放
  - `done` → 全部完成，恢復監聽

## Tech Stack

- **後端**：FastAPI, asyncio, WebSocket
- **前端**：Vue 3, TypeScript, WebSocket (已就緒)
- **架構**：`VoiceMonitorWebSocketService` 監控 `VoiceChatService.app_state` 變化並推送

## Acceptance Criteria

- [x] 後端發送 `transcribing` 事件（STT 開始）
- [x] 後端發送 `transcript` 事件（STT 完成，附帶文字）
- [x] 後端發送 `generating` 事件（LLM 開始）
- [x] 後端發送 `response` 事件（LLM streaming，實時累積）
- [x] 後端發送 `speaking` 事件（TTS 播放開始）
- [x] 後端發送 `done` 事件（全部完成）
- [x] 前端正確接收並顯示訊息到聊天列表（與按鈕錄音模式一致）
- [x] 不影響按鈕錄音模式（輪詢 `/api/status` 的流程）
- [x] 手動測試驗證完整流程

## Target Files

- 主要：`backend/services/voice_monitor_websocket_service.py`
- 次要：`backend/services/voice_chat_service.py`（如需調整）

---

## Implementation

### [x] Step 1. 後端添加狀態監控任務
**Goal**: 在 `VoiceMonitorWebSocketService` 中創建背景任務，監控 `voice_chat_service.app_state` 變化

**Implementation**:
- ✅ 添加實例變數：`_tracking_task`, `is_tracking`, `_last_transcript`, `_last_response`, `_last_is_done`, `_was_playing`
- ✅ 創建 `_start_status_tracking()` 異步方法，每 200ms 檢查狀態變化
- ✅ 創建 `start_tracking()` 公開方法，啟動追蹤任務

### [x] Step 2. 實現狀態變化檢測與事件推送
**Goal**: 檢測 `app_state` 的 `transcript`、`response`、`is_done` 變化，推送對應事件

**Implementation**:
- ✅ 檢測 `transcript` 變化 → 發送 `transcribing` / `transcript` 事件
- ✅ 檢測 `response` 變化 → 發送 `generating` / `response` 事件（實時累積）
- ✅ 檢測 `is_done` 變化 → 發送 `done` 事件

### [x] Step 3. 添加 TTS 播放狀態檢測
**Goal**: 檢測 TTS 開始播放時發送 `speaking` 事件

**Implementation**:
- ✅ 檢查 `voice_service.player_queue.is_all_done()` 狀態
- ✅ 從 `True` → `False` 時發送 `speaking` 事件

### [x] Step 4. 停止追蹤與清理
**Goal**: 處理完成後停止追蹤任務，恢復監聽模式

**Implementation**:
- ✅ `is_done = True` 且 TTS 播放完成時，停止追蹤
- ✅ 在 `cleanup()` 中取消 `_tracking_task`
- ✅ 添加 WebSocket 命令 `start_tracking` 處理

### [x] Step 5. 前端觸發追蹤
**Goal**: 音頻上傳後通知後端啟動追蹤

**Implementation**:
- ✅ 前端在 `stopRecording()` 後發送 `{ type: 'start_tracking' }` 命令
- ✅ 後端在 `_handle_command()` 中處理 `start_tracking` 命令

### [x] Step 6. 前端接收 WebSocket 事件並更新聊天列表
**Goal**: 監聽 WebSocket 事件變化，添加訊息到聊天列表（與按鈕錄音模式一致）

**Implementation**:
- ✅ 添加 `watch(lastKeyword)` - 檢測到喚醒詞時重置標記
- ✅ 添加 `watch(monitorTranscript)` - 收到 transcript 時調用 `store.addMessage({ type: 'user' })`
- ✅ 添加 `watch(monitorAiResponse)` - 收到 response 時調用 `store.addMessage({ type: 'ai' })` 或 `store.updateLastMessage()`（實時更新）
- ✅ 添加 `watch(monitorStatus)` - 狀態變化時更新 `store.setState()`（speaking/idle/thinking）

### [x] Step 7. 修正監聽恢復時機
**Goal**: 避免麥克風接收 TTS 輸出，等待對話完成後才恢復監聽

**Implementation**:
- ✅ 前端：移除 `stopRecording()` 後立即發送的 `start_monitoring` 命令
- ✅ 前端：音頻上傳後設置 `status = MonitorStatus.PROCESSING` 顯示「處理中...」
- ✅ 後端：在追蹤任務發送 `done` 事件後，自動調用 `switch_mode("monitoring")` 恢復監聽
- ✅ 後端：同時重置 `monitor_service` 確保乾淨狀態

---

## Test Generate

### Test Plan
1. **手動測試**：啟動監聽模式，說出喚醒詞和對話內容
2. **驗證 WebSocket 事件**：
   - 檢測到喚醒詞 → `keyword` 事件
   - STT 開始 → `transcribing` 事件
   - STT 完成 → `transcript` 事件（附帶文字）
   - LLM 開始 → `generating` 事件
   - LLM streaming → `response` 事件（實時累積）
   - TTS 播放 → `speaking` 事件
   - 全部完成 → `done` 事件
3. **驗證前端接收**：使用瀏覽器開發者工具監控 WebSocket 訊息
4. **驗證 UI 更新**：確認聊天列表正確顯示（前端邏輯已就緒）

### Mock Strategy
- 本任務主要修改後端 WebSocket 推送邏輯
- 測試使用真實環境：後端 + 前端 + AllTalk TTS
- 可選：編寫單元測試模擬 `app_state` 變化

---

## Unit Test

### 測試方式
- 主要使用**手動測試**（啟動前端 + 後端，實際對話）
- 原因：涉及 WebSocket 事件、狀態管理、UI 更新，手動測試更直觀

### 測試步驟
1. 啟動後端：`cd backend && source .venv/Scripts/activate && uv run api_server.py`
2. 啟動前端：`cd frontend && pnpm dev`
3. 點擊「持續監聽」按鈕
4. 說出喚醒詞（如「Hey Callisto」）
5. 說出對話內容（如「你好」）
6. 觀察：
   - [x] 聊天列表是否添加 user 訊息
   - [x] 聊天列表是否添加 AI 訊息
   - [x] AI 訊息是否實時更新
   - [x] 狀態是否切換到 speaking
   - [x] TTS 播放完後狀態是否恢復 idle

### 已知問題與修正
- ✅ 修正：移除獨立的 conversation-display div（訊息已顯示在主聊天列表）
- ✅ 說明：標記變數分為兩組
  - 按鈕錄音模式：`hasAddedMessages`, `hasAddedTranscript`, `hasAddedResponse`（輪詢 API）
  - 監聽模式：`hasAddedMonitorTranscript`, `hasAddedMonitorResponse`（watch WebSocket 事件）
  - 原因：兩種模式的觸發機制不同，需要獨立管理

---

## Spec Amendments

### 2026-01-25 - 移除監聽模式獨立顯示區域

#### Reason
監聽模式的 transcript 和 response 已經通過 watch 添加到主聊天列表，獨立的 conversation-display div 變成多餘，造成訊息重複顯示。

#### Changes
1. **移除模板**：刪除 `<div class="conversation-display">` 及其內容
2. **移除樣式**：刪除 `.conversation-display`, `.transcript`, `.ai-response` 相關 CSS
3. **添加註釋**：說明標記變數的用途（按鈕模式 vs 監聽模式）

#### Impact
- 修改文件：[VoiceRecorder.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/VoiceRecorder.vue)
- 用戶體驗：訊息統一顯示在主聊天列表，不再重複

---

### 2026-01-25 - 修正監聽恢復時機

#### Reason
前端上傳音頻後立即發送 `start_monitoring` 恢復監聽，導致麥克風接收到自己的 TTS 輸出音訊，造成干擾。應該等到對話處理完成（收到 `done` 事件）後才恢復監聽。

#### Changes
1. **前端**：移除 `stopRecording()` 後立即發送的 `start_monitoring` 命令
2. **前端**：音頻上傳後設置 `status = MonitorStatus.PROCESSING` 顯示「處理中...」
3. **後端**：在狀態追蹤完成（發送 `done` 事件）後，自動發送 `start_monitoring` 命令切換回監聽模式

#### Code Changes

**Before** (frontend):
```typescript
await stopRecording()
websocket.send(JSON.stringify({ type: 'start_tracking' }))
websocket.send(JSON.stringify({ type: 'start_monitoring' }))  // ❌ 過早恢復
```

**After** (frontend):
```typescript
await stopRecording()
websocket.send(JSON.stringify({ type: 'start_tracking' }))
// ✅ 等待後端處理完成後自動恢復監聽
```

**After** (backend):
```python
# 在 _start_status_tracking() 中
if app_state.is_done and not self._last_is_done:
    if not is_playing:
        await self.websocket.send_json({"type": "done"})
        # ✅ 自動恢復監聽模式
        await self.switch_mode("monitoring")
```

#### Impact
- 修改文件：[useVoiceMonitor.ts](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/composables/useVoiceMonitor.ts), [voice_monitor_websocket_service.py](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/backend/services/voice_monitor_websocket_service.py)
- 避免麥克風接收 TTS 輸出，減少干擾

---

### 2026-01-25 - 修正無效請求時的狀態恢復

#### Reason
當後端收到無效請求（靜音、太短、STT 失敗）時，`is_done = True` 但沒有 response，追蹤任務會一直等待 TTS 播放完成才發送 `done` 事件，導致前端卡在「處理中」狀態，無法恢復監聽。

#### Changes
1. **後端**：追蹤任務檢測到錯誤或無 response 時，立即發送 `done` 並恢復監聽，不等待 TTS
2. **後端**：有錯誤時先發送 `error` 事件，再發送 `done` 事件
3. **前端**：收到 `error` 事件後，3 秒後自動恢復到監聽狀態

#### Code Changes

**Before** (backend):
```python
if app_state.is_done and not self._last_is_done:
    if not is_playing:  # ❌ 一直等待 TTS 完成
        await self.websocket.send_json({"type": "done"})
```

**After** (backend):
```python
if app_state.is_done and not self._last_is_done:
    has_error = app_state.error is not None
    has_no_response = not app_state.response
    should_finish = has_error or has_no_response or not is_playing
    
    if should_finish:  # ✅ 有錯誤或無回應時立即結束
        if has_error:
            await self.websocket.send_json({"type": "error", "message": app_state.error})
        await self.websocket.send_json({"type": "done"})
        await self.switch_mode("monitoring")
```

**After** (frontend):
```typescript
case 'error':
    status.value = MonitorStatus.ERROR
    error.value = event.message
    // ✅ 3 秒後自動恢復監聽
    setTimeout(() => {
        status.value = MonitorStatus.LISTENING
        error.value = null
    }, 3000)
```

#### Impact
- 修改文件：[voice_monitor_websocket_service.py](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/backend/services/voice_monitor_websocket_service.py), [useVoiceMonitor.ts](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/composables/useVoiceMonitor.ts)
- 解決無效請求導致前端卡住的問題
- 錯誤狀態會顯示 3 秒後自動恢復

---

### 2026-01-25 - 修正追蹤狀態初始值邏輯錯誤

#### Reason
檢查流程時發現：當 VAD 檢測無語音時，`is_done = True` 在 `start_tracking()` 被調用前已設置。但 `start_tracking()` 重置 `_last_is_done = True`，導致條件 `if app_state.is_done and not self._last_is_done` 變成 `True and not True = False`，永遠不會觸發，前端無法收到 `done` 事件。

#### Changes
1. **後端**：`_last_is_done` 初始值改為 `False`（表示「還沒處理過任何完成狀態」）
2. **後端**：`start_tracking()` 重置時也改為 `False`

#### Code Changes

**Before**:
```python
# __init__
self._last_is_done = True

# start_tracking()
self._last_is_done = True  # ❌ 錯誤：導致條件永遠不成立
```

**After**:
```python
# __init__
self._last_is_done = False  # ✅ 初始為 False，表示未處理過任何完成狀態

# start_tracking()
self._last_is_done = False  # ✅ 重置為 False，準備檢測新的完成狀態
```

#### Flow Verification

**Before (錯誤流程)**:
```
1. process_voice() 開始 → is_done = False
2. VAD 無語音 → is_done = True, return
3. start_tracking() → _last_is_done = True
4. 檢查: True and not True = False ❌ 條件不成立
5. 前端永遠收不到 done 事件
```

**After (正確流程)**:
```
1. process_voice() 開始 → is_done = False
2. VAD 無語音 → is_done = True, return
3. start_tracking() → _last_is_done = False
4. 檢查: True and not False = True ✅ 條件成立
5. 發送 done 事件，前端恢復監聽
```

#### Impact
- 修改文件：[voice_monitor_websocket_service.py](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/backend/services/voice_monitor_websocket_service.py) (2 處)
- 修正關鍵邏輯錯誤，確保無效請求能正確結束流程

---
### 2026-01-25 - 清除追蹤邏輯中的冗餘代碼

#### Reason
測試完成後檢查代碼，發現追蹤邏輯中有一段多餘的處理：
```python
elif not app_state.is_done:
    self._last_is_done = False
```
此段代碼完全沒有必要，因為：
1. `start_tracking()` 時已將 `_last_is_done` 重置為 `False`
2. 檢查條件 `if app_state.is_done and not self._last_is_done` 只會觸發一次
3. 觸發後立即停止追蹤（`self.is_tracking = False`），不會再循環
4. 該 `elif` 分支對邏輯無任何影響

#### Changes
1. **後端**：移除追蹤邏輯中的 `elif not app_state.is_done` 分支

#### Code Changes

**Before**:
```python
if should_finish:
    # ...發送 done 事件
    self.is_tracking = False
    logger.info("🛑 停止狀態追蹤")
elif not app_state.is_done:  # ❌ 冗餘代碼
    self._last_is_done = False
```

**After**:
```python
if should_finish:
    # ...發送 done 事件
    self.is_tracking = False
    logger.info("🛑 停止狀態追蹤")
# ✅ 移除冗餘的 elif 分支
```

#### Impact
- 修改文件：[voice_monitor_websocket_service.py](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/backend/services/voice_monitor_websocket_service.py) (line 467-468)
- 簡化邏輯，移除無效代碼

---

### 2026-01-25 - 修正錄音模式超時自動上傳後按鈕卡住問題

#### Reason
測試發現**錄音模式**（按鈕模式）30秒超時自動上傳後出現多個問題：
1. **前端停在「thinking」狀態，錄音按鈕鎖住**
2. **後端正常處理並生成 TTS，但前端沒有更新狀態、沒有顯示消息**
3. **輪詢請求發送兩次**（第二次被擋掉）

**根本原因**：
1. **超時後沒有觸發輪詢**：
   - 手動點擊發送：`stopRecording()` → `startPolling()` ✅
   - 超時自動上傳：`stopRecording()` → ❌ 缺少輪詢
2. **混淆了兩種模式的處理邏輯**：
   - 錄音模式：HTTP 輪詢 `/api/status` 端點
   - 監聽模式：WebSocket 接收事件，調用 `onVADStop` 發送 `start_tracking`
3. **重複調用回調**：
   - 超時回調中調用 `onRecordingComplete`
   - `stopRecording` 上傳成功後也調用 `onRecordingComplete`
4. **監聽模式的無效代碼**：
   - error 處理中的 setTimeout 永遠不會執行（被 done 事件立即覆蓋）

#### Changes
**核心修改**：
1. **新增 `onRecordingComplete` 回調**（錄音模式專用）：錄音完成並上傳後調用
2. **保留 `onVADStop` 回調**（監聽模式專用）：VAD 檢測到靜音時調用
3. **只在 `stopRecording` 內部調用回調**：統一處理，避免重複
4. **提取輪詢邏輯**：供手動發送和超時使用
5. **移除無效代碼**：監聽模式 error 處理的 setTimeout

#### Code Changes

**useVoiceRecorder.ts**:
```typescript
// 1. 新增 onRecordingComplete 回調
export interface VoiceRecorderOptions {
    onVADStop?: () => void               // 監聽模式專用
    onRecordingComplete?: () => void     // 錄音模式專用（新增）
}

// 2. 保存 options 到函數作用域
let currentRecordingOptions: VoiceRecorderOptions | null = null

// 3. startRecording 時保存 options
const startRecording = async (options?: VoiceRecorderOptions) => {
    currentRecordingOptions = options || null
    // ...
}

// 4. 超時處理（不調用回調，由 stopRecording 統一處理）
recordingTimeout = setTimeout(async () => {
    await stopRecording()  // ✅ 內部會調用 onRecordingComplete
}, 30000)

// 5. stopRecording 上傳成功後調用回調
const response = await uploadAudio(audioBlob)
if (currentRecordingOptions?.onRecordingComplete) {
    currentRecordingOptions.onRecordingComplete()
}
resolve(response)

// 6. cancelRecording 時清理
currentRecordingOptions = null
```

**VoiceRecorder.vue**:
```typescript
// 1. 提取輪詢邏輯為獨立函數
const handlePolling = () => {
    startPolling(/* 完整的輪詢邏輯 */)
}

// 2. 手動發送使用提取的函數
const handleSendRecording = async () => {
    await stopRecording()
    handlePolling()
}

// 3. 開始錄音時傳入回調
await startRecording({
    onRecordingComplete: () => {
        handlePolling()  // ✅ 超時後觸發輪詢
    }
})
```

**useVoiceMonitor.ts**:
```typescript
// 簡化 error 處理（移除無效的 setTimeout）
case 'error':
    status.value = MonitorStatus.ERROR
    error.value = event.message
    // 後端立即發送 done，狀態會被覆蓋為 LISTENING
    break
```

#### Flow Verification

**Before (錯誤流程)**:
```
錄音模式 → 超時自動上傳:
  setTimeout → stopRecording() → ❌ 沒有輪詢 → 按鈕卡住
  
錄音模式 → 第一次修正嘗試:
  setTimeout → stopRecording() → onRecordingComplete() [超時回調]
  stopRecording 內部 → onRecordingComplete() [上傳成功]
  結果：輪詢請求發送兩次 ❌
```

**After (正確流程)**:
```
錄音模式 → 手動點擊發送:
  stopRecording() → onRecordingComplete() → handlePolling() ✅

錄音模式 → 超時自動上傳:
  setTimeout → stopRecording() → onRecordingComplete() → handlePolling() ✅
  (只調用一次，避免重複)

監聽模式 → VAD 自動停止:
  WebSocket Event → stopRecording() + onVADStop() → start_tracking ✅
  (兩種回調分離，互不干擾)
```

#### Why currentRecordingOptions is Necessary

**問題**：為什麼需要 `currentRecordingOptions` 而不能直接傳參？

**原因**：
- `stopRecording()` 是獨立函數，沒有 `options` 參數
- 需要在 `stopRecording()` 內部訪問回調函數
- `startRecording(options)` 和 `stopRecording()` 是分開調用的
- 必須在函數作用域外保存 `options` 才能跨函數訪問

#### Impact
**修改文件**：
- [useVoiceRecorder.ts](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/composables/useVoiceRecorder.ts)
  - 新增 `onRecordingComplete` 回調定義
  - 新增 `currentRecordingOptions` 變量
  - 修改 `startRecording`：保存 options
  - 修改 `stopRecording`：調用 `onRecordingComplete`
  - 修改 `cancelRecording`：清理 options
  - 修改超時處理：移除重複調用
- [VoiceRecorder.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/VoiceRecorder.vue)
  - 新增 `handlePolling` 函數
  - 修改 `handleStartRecording`：傳入回調
  - 修改 `handleSendRecording`：使用 `handlePolling`
- [useVoiceMonitor.ts](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/composables/useVoiceMonitor.ts)
  - 簡化 error 處理：移除無效 setTimeout

**解決的問題**：
1. ✅ 錄音模式超時後正確觸發輪詢
2. ✅ 避免輪詢請求重複發送
3. ✅ 釐清錄音模式和監聽模式的處理邏輯
4. ✅ 移除監聽模式的無效代碼

---

### 2026-01-25 - 禁止監聽模式處理期間中斷連線

#### Reason
測試發現監聽模式送出音訊後，在處理期間（PROCESSING、SPEAKING 狀態）仍可以點擊「停止監聽」按鈕中斷連線，導致：
1. TTS 播放被中斷
2. 用戶體驗不佳（無法聽完 AI 回應）

#### Changes
- **VoiceRecorder.vue**：監聽按鈕在 `PROCESSING` 或 `SPEAKING` 狀態時禁用

#### Code Changes

**Before**:
```vue
<button
    :disabled="isRecording"
    @click="toggleMonitoring"
>
    {{ isMonitoring ? '停止監聽' : '持續監聽' }}
</button>
```

**After**:
```vue
<button
    :disabled="isRecording || monitorStatus === MonitorStatus.PROCESSING || monitorStatus === MonitorStatus.SPEAKING"
    @click="toggleMonitoring"
>
    {{ isMonitoring ? '停止監聽' : '持續監聽' }}
</button>
```

#### Impact
- 修改文件：[VoiceRecorder.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/VoiceRecorder.vue) (1 處)
- 防止用戶在處理期間意外中斷連線
- 確保 TTS 播放完成後才能停止監聽

---

### 2026-01-25 - 修正監聽模式靜音時狀態不更新和後端錯誤日誌問題

#### Reason
測試發現兩個小問題：
1. **監聽模式靜音時前端狀態卡住**：
   - 傳到後端的是靜音（VAD 無有效語音）
   - 前端其他都正常，但 store.state 還卡在 thinking，沒有切換回 idle
   - 原因：watch 只監聽了 `SPEAKING -> LISTENING` 的轉換，沒有監聽 `PROCESSING -> LISTENING` 的轉換

2. **後端 TTS 錯誤輸出太多 Traceback**：
   - TTS 服務器未開啟時，`logger.error()` 使用 `exc_info=True` 輸出完整堆棧追蹤
   - 日誌過於冗長，只需要錯誤訊息即可

#### Changes
1. **VoiceRecorder.vue**：添加 `PROCESSING -> LISTENING` 狀態轉換處理
2. **tts_player_queue.py**：移除兩處 `exc_info=True`，只輸出錯誤訊息

#### Code Changes

**VoiceRecorder.vue - Before**:
```typescript
watch(monitorStatus, (newStatus, oldStatus) => {
    if (newStatus === MonitorStatus.SPEAKING) {
        store.setState('speaking')
    }
    
    // 只處理 SPEAKING -> LISTENING
    if (oldStatus === MonitorStatus.SPEAKING && newStatus === MonitorStatus.LISTENING) {
        store.setState('idle')
    }
})
```

**VoiceRecorder.vue - After**:
```typescript
watch(monitorStatus, (newStatus, oldStatus) => {
    if (newStatus === MonitorStatus.SPEAKING) {
        store.setState('speaking')
    }
    
    // SPEAKING -> LISTENING（正常完成）
    if (oldStatus === MonitorStatus.SPEAKING && newStatus === MonitorStatus.LISTENING) {
        store.setState('idle')
    }
    
    // PROCESSING -> LISTENING（無語音/靜音）✅ 新增
    if (oldStatus === MonitorStatus.PROCESSING && newStatus === MonitorStatus.LISTENING) {
        store.setState('idle')
    }
})
```

**tts_player_queue.py - Before**:
```python
except Exception as e:
    logger.error(f"生成 TTS 時發生錯誤: {e}", exc_info=True)  # ❌ 輸出完整 Traceback
```

**tts_player_queue.py - After**:
```python
except Exception as e:
    logger.error(f"生成 TTS 時發生錯誤: {e}")  # ✅ 只輸出錯誤訊息
```

#### Flow Verification

**靜音情況的狀態流轉**：

**Before**:
```
監聽模式 → 檢測到關鍵詞 → 開始錄音
→ 錄音結束上傳 → PROCESSING (store: thinking)
→ 後端 VAD 檢測無語音 → 發送 done
→ 前端收到 done → LISTENING
→ ❌ store 仍為 thinking（沒有觸發狀態更新）
```

**After**:
```
監聽模式 → 檢測到關鍵詞 → 開始錄音
→ 錄音結束上傳 → PROCESSING (store: thinking)
→ 後端 VAD 檢測無語音 → 發送 done
→ 前端收到 done → LISTENING
→ ✅ watch 檢測到 PROCESSING -> LISTENING → store: idle
```

#### Impact
- 修改文件：
  - [VoiceRecorder.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/VoiceRecorder.vue) (1 處)
  - [tts_player_queue.py](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/backend/services/tts_player_queue.py) (2 處)
- 修正監聽模式靜音時前端狀態不更新的問題
- 簡化後端錯誤日誌，移除冗長的 Traceback

---
