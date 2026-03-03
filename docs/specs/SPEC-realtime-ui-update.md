# SPEC: 實時 UI 更新優化

## Task Description

優化語音對話的 UI 更新時機，讓用戶在 LLM 生成內容時就能立即看到文字，而不需要等待 TTS 播放完成。

**問題**：
- 原有邏輯：只有當 `is_done = true`（TTS 播放完成）時，前端才會顯示 transcript 和 response
- 延遲體驗：用戶需要等待整個流程結束（STT → LLM → TTS 播放完）才能看到文字

**目標**：
- STT 完成後，立即顯示 transcript
- LLM streaming 時，實時累積顯示 response
- TTS 播放時，文字已完整顯示（只播放音訊）

## Tech Stack

- **後端**：FastAPI, Python asyncio
- **前端**：Vue 3, TypeScript, Pinia

## Acceptance Criteria

- [x] STT 完成後，transcript 立即顯示在 UI
- [x] LLM streaming 過程中，response 逐字累積顯示
- [x] 同一個 AI 訊息泡泡被更新，不會產生多個泡泡
- [x] TTS 播放時，文字已完整顯示
- [x] 不影響原有的錯誤處理和狀態管理

## Target Files

### 後端
- `backend/services/voice_chat_service.py` - 實時更新 app_state.response

### 前端
- `frontend/src/composables/useStatusPolling.ts` - 新增實時更新回調
- `frontend/src/components/VoiceRecorder.vue` - 實時更新邏輯
- `frontend/src/stores/voiceChat.ts` - 新增 updateLastMessage 方法

---

## Implementation

### [x] Step 1. 後端實時更新 response
**Goal**: LLM streaming 時立即更新 app_state

**Implementation Details**:
- 修改 `voice_chat_service.py` 的 LLM streaming 循環：
  ```python
  for chunk in stream:
      content = chunk.choices[0].delta.content
      current_response += content
      full_response += content
      
      # 🔥 實時更新 app_state，讓前端可以立即看到
      self.app_state.response = full_response
      
      # 後續 TTS 處理...
  ```

- **效果**：前端輪詢 `/api/status` 時，每次都能看到最新的 response（不等 TTS 播放完）

---

### [x] Step 2. 前端新增實時更新回調
**Goal**: useStatusPolling 支持輪詢過程中的資料更新

**Implementation Details**:
- 修改 `useStatusPolling.ts`，新增第 4 個參數：
  ```typescript
  const startPolling = (
      onComplete: (data) => void,      // is_done 時觸發
      onError: (error) => void,
      onSpeaking?: () => void,
      onDataUpdate?: (data) => void    // 🔥 每次輪詢都觸發
  )
  ```

- 在輪詢循環中調用：
  ```typescript
  const data = await response.json()
  
  // 🔥 實時更新資料（不等 is_done）
  if (onDataUpdate) {
      onDataUpdate(data)
  }
  
  // 檢查是否完成
  if (data.is_done) {
      onComplete(data)
  }
  ```

---

### [x] Step 3. VoiceRecorder 實時更新邏輯
**Goal**: 只添加一次訊息泡泡，後續更新它

**Implementation Details**:
- 新增追蹤標記：
  ```typescript
  const hasAddedTranscript = ref(false)  // transcript 是否已添加
  const hasAddedResponse = ref(false)    // response 是否已添加
  ```

- 實現 onDataUpdate 回調：
  ```typescript
  onDataUpdate: (data) => {
      // Transcript: 只添加一次
      if (data.transcript && !hasAddedTranscript.value) {
          store.addMessage({ type: 'user', text: data.transcript })
          hasAddedTranscript.value = true
      }
      
      // Response: 第一次添加，後續更新
      if (data.response) {
          if (!hasAddedResponse.value) {
              store.addMessage({ type: 'ai', text: data.response })
              hasAddedResponse.value = true
          } else {
              store.updateLastMessage(data.response)  // 更新最後一條
          }
      }
  }
  ```

---

### [x] Step 4. Store 新增更新方法
**Goal**: 正確更新 Pinia store 中的訊息

**Implementation Details**:
- 新增 `updateLastMessage` action：
  ```typescript
  updateLastMessage(text: string) {
      if (this.messages.length > 0) {
          const lastIndex = this.messages.length - 1
          const currentMessage = this.messages[lastIndex]
          // 創建新對象，觸發響應式更新
          this.messages[lastIndex] = {
              id: currentMessage.id,
              type: currentMessage.type,
              timestamp: currentMessage.timestamp,
              text: text
          }
      }
  }
  ```

- **關鍵**：創建新對象而非直接修改屬性，確保 Vue 能檢測到變化

---

## 效果對比

### Before（原有邏輯）
```
0s  - 用戶說話完畢，上傳音訊
2s  - STT 完成，transcript 存在但前端看不到 ❌
5s  - LLM 完成，response 存在但前端看不到 ❌
8s  - TTS 播放完成，is_done = true
     → 前端才顯示 transcript 和 response ❌
```

### After（優化後）
```
0s  - 用戶說話完畢，上傳音訊
2s  - STT 完成 → transcript 立即顯示 ✅
2.5s - 前端輪詢 → transcript 出現在 UI ✅
3s  - LLM streaming 開始
3.5s - 前端輪詢 → 部分 response 顯示 ✅
4s  - 前端輪詢 → response 繼續累積 ✅
5s  - LLM 完成 → response 完整顯示 ✅
8s  - TTS 播放完成（文字早已顯示，只播放音訊）✅
```

**時間節省**：用戶可以提前 3-6 秒看到完整文字！

---

## 測試結果

### 手動測試
- [x] STT 完成後，transcript 立即出現
- [x] LLM streaming 時，response 逐字累積（每 0.5s 更新）
- [x] 只有一個 AI 訊息泡泡，內容逐步更新
- [x] TTS 播放時，文字已完整顯示
- [x] 錯誤處理正常（STT/LLM 失敗時顯示錯誤）

### 效能影響
- 輪詢頻率：500ms（不變）
- 網路請求：無增加
- CPU 使用：無明顯增加
- 記憶體：無洩漏（已測試多次對話）

---

## 技術亮點

1. **最小侵入性**：只新增功能，不修改原有邏輯
2. **向後兼容**：onDataUpdate 為可選參數，不影響其他使用 useStatusPolling 的地方
3. **響應式友好**：使用 Pinia 的正確更新方式，確保 Vue 檢測到變化
4. **狀態追蹤清晰**：使用獨立的 ref 追蹤每個步驟，避免邏輯混亂

---

## 相關文件

- 相關 Issue: 實時 UI 更新優化
- 測試日期: 2026-01-21
- 實現時間: 約 1 小時
- 受益功能: 按住說話模式（持續監聽模式暫未應用，待 Step 7）

---
