# SPEC: 喚醒詞回應與錄音期間暫停監聽

## Task Description

在檢測到喚醒詞後，立即播放 TTS 歡迎詞（「我有聽到，請說」），給用戶思考緩衝時間。同時在錄音上傳到後端處理期間，暫停 WebSocket 音訊輸入，避免不必要的傳輸開銷和錯誤觸發。

**當前流程**：
```
1. 持續監聽（WebSocket streaming PCM）
2. 檢測到喚醒詞 → 立即切換到 vad_only 模式
3. VAD 檢測 3 秒靜音 → 停止錄音
4. 上傳 WebM 到後端 → STT → LLM → TTS 播放
5. 前端收到響應 → 恢復監聽模式
```

**問題**：
- 用戶說完喚醒詞後不知道系統是否已響應（沒有反饋）
- 錄音上傳到後端處理期間，WebSocket 仍在接收和發送音訊數據（浪費資源）
- 用戶可能在 AI 處理期間再次觸發喚醒詞（造成混亂）

**改進目標**：
- **立即反饋**：檢測到喚醒詞後立即播放 TTS 歡迎詞（給用戶確認感）
- **暫停 VAD**：播放歡迎詞期間暫停 VAD 靜音檢測（避免誤觸發）
- **暫停輸入**：錄音上傳後端處理期間，前端停止發送音訊到 WebSocket（減少開銷）
- **恢復監聽**：TTS 播放完成後自動恢復監聽模式

## Tech Stack

- **後端**：FastAPI WebSocket, SileroVADService, TTSPlayerQueue, AllTalkTTS
- **前端**：Vue 3, TypeScript, MediaRecorder API, AudioWorklet
- **現有服務**：復用現有的 TTS 和 WebSocket 架構

## Acceptance Criteria

### 喚醒詞即時反饋
- [ ] 檢測到喚醒詞後，後端立即生成 TTS 歡迎詞
- [ ] 歡迎詞從預設列表中隨機選擇（目前先固定：「我有聽到，請說」）
- [ ] TTS 播放期間，VAD 靜音檢測暫停（避免誤判）
- [ ] 前端收到 `keyword_detected` 事件時顯示視覺反饋（可選）

### 錄音期間暫停輸入
- [ ] 錄音上傳到後端開始，前端停止發送音訊數據到 WebSocket
- [ ] WebSocket 連接保持（不斷開），但前端拒絕處理 AudioWorklet 輸出
- [ ] 後端處理期間（STT → LLM → TTS），前端保持暫停狀態

### 自動恢復監聽
- [ ] TTS 播放完成後，後端推送 `resume_monitoring` 事件（或前端輪詢狀態）
- [ ] 前端收到事件後，恢復 AudioWorklet 音訊傳送
- [ ] 自動發送 `start_monitoring` 命令，恢復喚醒詞檢測

### 錯誤處理
- [ ] TTS 生成失敗時，依然繼續錄音流程（不中斷）
- [ ] 後端處理超時時，前端自動恢復監聽（60 秒保護）
- [ ] WebSocket 斷線時，清理狀態並提示用戶

## Target Files

### 後端
- **修改**：
  - `backend/services/voice_monitor_websocket_service.py` - 喚醒詞檢測後播放 TTS、推送恢復事件
  - `backend/api_server.py` - `/api/chat/voice` 處理完成後推送 WebSocket 事件（可選）

### 前端
- **修改**：
  - `frontend/src/composables/useVoiceMonitor.ts` - 處理 `keyword_detected` 事件、暫停/恢復音訊輸入
  - `frontend/src/composables/useVoiceRecorder.ts` - 添加暫停狀態標記（可選）

---

## Implementation

### [ ] Step 1. 後端喚醒詞檢測後播放 TTS 歡迎詞
**Goal**: 在 `VoiceMonitorWebSocketService` 檢測到喚醒詞後，立即生成並播放 TTS 歡迎詞

**Reason**: 給用戶即時反饋，確認系統已響應；播放期間暫停 VAD 檢測，避免誤觸發

**Implementation Details**:
- **1.1 定義歡迎詞列表**（在 `voice_monitor_websocket_service.py`）：
  ```python
  import random
  
  # 喚醒詞回應列表（未來可擴展）
  ACKNOWLEDGMENT_MESSAGES = [
      "我有聽到，請說",
      # "有什麼事嗎？",
      # "我在聽",
  ]
  ```

- **1.2 添加 TTS 播放標記**：
  ```python
  class VoiceMonitorWebSocketService:
      def __init__(self, ...):
          # ... 現有代碼
          self.is_playing_acknowledgment = False  # TTS 播放中標記
  ```

- **1.3 修改喚醒詞檢測邏輯**（`handle_audio_stream` 方法）：
  ```python
  # 檢測到喚醒詞
  if keyword:
      logger.info(f"🎯 檢測到喚醒詞: {keyword}")
      
      # 🔥 立即播放歡迎詞
      await self._play_acknowledgment()
      
      # 推送事件給前端
      await self.websocket.send_json({
          "type": "keyword_detected",
          "keyword": keyword,
          "confidence": confidence,
          "timestamp": time.time()
      })
      
      # 切換到 VAD 錄音模式
      await self.switch_mode("vad_only")
  ```

- **1.4 實作 `_play_acknowledgment` 方法**：
  ```python
  async def _play_acknowledgment(self):
      """播放喚醒詞回應（阻塞式）"""
      try:
          self.is_playing_acknowledgment = True
          
          # 隨機選擇歡迎詞（目前固定一個）
          message = random.choice(ACKNOWLEDGMENT_MESSAGES)
          logger.info(f"🎤 播放歡迎詞: {message}")
          
          # 使用 TTSPlayerQueue 生成並播放（阻塞直到播放完成）
          # 注意：需要同步等待播放完成，避免與錄音重疊
          player_queue = self.monitor_service.voice_chat_service.player_queue
          
          player_queue.add_text(
              text=message,
              voice="female_06.wav",
              language="zh-cn",
              volume=0.02
          )
          
          # 等待播放完成（最多 5 秒）
          if player_queue.wait_until_done(timeout=5):
              logger.info("✅ 歡迎詞播放完成")
          else:
              logger.warning("⏰ 歡迎詞播放超時")
              
      except Exception as e:
          logger.error(f"❌ 播放歡迎詞失敗: {e}")
      finally:
          self.is_playing_acknowledgment = False
  ```

- **1.5 修改 VAD 檢測邏輯**（跳過播放期間）：
  ```python
  async def _handle_vad_only(self, data: bytes):
      # 播放歡迎詞期間，跳過 VAD 檢測
      if self.is_playing_acknowledgment:
          return
      
      # 增加 chunk 計數器
      self.vad_chunk_counter += 1
      
      # ... 現有的 VAD 檢測邏輯
  ```

- **設計要點**：
  - TTS 播放是**阻塞式**的（等待播放完成），避免與錄音重疊
  - 播放期間 VAD 檢測暫停（`is_playing_acknowledgment` 標記）
  - 失敗時不中斷流程，繼續錄音
  - 使用現有的 `TTSPlayerQueue`，不需要新建實例

---

### [ ] Step 2. 前端錄音期間暫停音訊輸入 + 後端 WebSocket 推送完成事件
**Goal**: 錄音上傳到後端處理期間，前端停止發送音訊到 WebSocket；後端處理完成後，通過 WebSocket 主動推送事件通知前端恢復監聽

**Reason**: 
- 減少不必要的網路傳輸開銷，避免後端處理期間誤觸發喚醒詞
- 使用 WebSocket 推送比輪詢更高效、實時（無延遲）
- 符合 WebSocket 長連接的設計理念

**Implementation Details**:

#### 架構設計說明
**問題**：WebSocket 連接（`/ws/voice-monitor`）和 HTTP 上傳（`/api/chat/voice`）是兩個獨立通道，如何關聯？

**解決方案**：
1. 前端生成唯一 `client_id`（UUID）
2. WebSocket 連接時帶上 `client_id`（通過 query parameter）
3. HTTP 上傳時帶上 `client_id`（通過 header）
4. 後端維護 `client_id` → WebSocket 的映射
5. 處理完成後，通過 `client_id` 找到 WebSocket 推送事件

#### 後端實現

- **2.1 修改 `api_server.py` 維護 WebSocket 連接池**：
  ```python
  from typing import Dict
  from fastapi import WebSocket
  
  # 🔥 全局 WebSocket 連接池（key: client_id, value: WebSocket）
  active_websockets: Dict[str, WebSocket] = {}
  
  @app.websocket("/ws/voice-monitor")
  async def voice_monitor_websocket(
      websocket: WebSocket,
      client_id: str = Query(None)  # 從 query parameter 獲取
  ):
      await websocket.accept()
      
      # 🔥 註冊到連接池
      if client_id:
          active_websockets[client_id] = websocket
          logger.info(f"✅ WebSocket 已註冊: client_id={client_id}")
      
      try:
          service = VoiceMonitorWebSocketService(
              websocket=websocket,
              monitor_service=monitor_service
          )
          await service.handle_audio_stream()
      finally:
          # 🔥 清理連接池
          if client_id and client_id in active_websockets:
              active_websockets.pop(client_id)
              logger.info(f"🗑️ WebSocket 已移除: client_id={client_id}")
  ```

- **2.2 修改 `/api/chat/voice` 端點，處理完成後推送事件**：
  ```python
  @app.post("/api/chat/voice")
  async def chat_voice(
      background_tasks: BackgroundTasks,
      audio: UploadFile = File(...),
      client_id: str = Header(None, alias="x-client-id")  # 從 header 獲取
  ):
      # ... 保存音訊文件
      
      # 後台處理任務
      def process_callback():
          try:
              # 執行語音處理流程（STT → LLM → TTS）
              voice_chat_service.process_voice(audio_path)
              
              # 🔥 處理完成後，推送 WebSocket 事件
              if client_id and client_id in active_websockets:
                  ws = active_websockets[client_id]
                  try:
                      # 使用 asyncio 發送 WebSocket 消息
                      import asyncio
                      loop = asyncio.new_event_loop()
                      asyncio.set_event_loop(loop)
                      loop.run_until_complete(ws.send_json({
                          "type": "processing_complete",
                          "timestamp": time.time()
                      }))
                      logger.info(f"✅ 已推送 processing_complete 事件: client_id={client_id}")
                  except Exception as e:
                      logger.error(f"❌ 推送 WebSocket 事件失敗: {e}")
              else:
                  logger.warning(f"⚠️ 找不到 WebSocket 連接: client_id={client_id}")
                  
          except Exception as e:
              logger.error(f"❌ 語音處理失敗: {e}")
      
      background_tasks.add_task(process_callback)
      
      return {"status": "processing"}
  ```

#### 前端實現

- **2.3 生成唯一 `client_id` 並連接 WebSocket**（`useVoiceMonitor.ts`）：
  ```typescript
  import { ref } from 'vue'
  
  export function useVoiceMonitor() {
      // 🔥 生成唯一 client_id
      const clientId = ref(crypto.randomUUID())
      let isAudioInputPaused = false  // 音訊輸入暫停標記
      
      const startMonitoring = async () => {
          // 連接 WebSocket 時帶上 client_id
          const ws = new WebSocket(
              `ws://localhost:8000/ws/voice-monitor?client_id=${clientId.value}`
          )
          
          websocket.value = ws
          
          // ... 現有的 AudioWorklet 初始化
          
          // 修改 Worklet 訊息處理
          workletNode.port.onmessage = (event) => {
              const pcmData = event.data  // ArrayBuffer (int16)
              
              // 🔥 暫停期間不發送音訊
              if (isAudioInputPaused) {
                  return
              }
              
              if (websocket.value?.readyState === WebSocket.OPEN) {
                  websocket.value.send(pcmData)
              }
          }
      }
  ```

- **2.4 處理 `keyword_detected` 和 `processing_complete` 事件**：
  ```typescript
  const setupWebSocket = () => {
      ws.onmessage = (event) => {
          const data = JSON.parse(event.data)
          
          // 檢測到喚醒詞
          if (data.type === 'keyword_detected') {
              console.log('🎯 檢測到喚醒詞，啟動錄音...')
              handleAutoRecording()
              return
          }
          
          // 🔥 後端處理完成（新增）
          if (data.type === 'processing_complete') {
              console.log('✅ 後端處理完成，恢復監聽')
              resumeMonitoring()
              return
          }
          
          // ... 其他事件
      }
  }
  ```

- **2.5 修改 `handleAutoRecording` 方法**：
  ```typescript
  const handleAutoRecording = async () => {
      try {
          // 🔥 暫停音訊輸入（錄音上傳前）
          isAudioInputPaused = true
          logger.debug('⏸️ 音訊輸入已暫停')
          
          // 啟動錄音（VAD 自動停止）
          await startRecording({
              enableVAD: true,
              websocket: websocket.value!,
              onVADStop: async () => {
                  // VAD 檢測到靜音，停止錄音並上傳
                  await stopRecording()
                  
                  // 注意：此時音訊輸入仍然暫停，等待後端推送 processing_complete 事件
              }
          })
          
      } catch (error) {
          logger.error('自動錄音失敗:', error)
          
          // 🔥 錯誤時恢復音訊輸入
          isAudioInputPaused = false
          
          // 恢復監聽
          if (websocket.value?.readyState === WebSocket.OPEN) {
              websocket.value.send(JSON.stringify({ type: 'start_monitoring' }))
          }
      }
  }
  ```

- **2.6 在 `uploadAudio` 時帶上 `client_id` header**：
  ```typescript
  const uploadAudio = async (audioBlob: Blob) => {
      try {
          const formData = new FormData()
          formData.append('audio', audioBlob, 'recording.webm')
          
          // 🔥 帶上 client_id header
          const response = await fetch('/api/chat/voice', {
              method: 'POST',
              headers: {
                  'x-client-id': clientId.value  // 與 WebSocket 相同的 ID
              },
              body: formData
          })
          
          // 上傳完成，等待後端推送 processing_complete 事件（不需要輪詢）
          logger.info('✅ 音訊已上傳，等待後端處理...')
          
      } catch (error) {
          logger.error('上傳音訊失敗:', error)
          
          // 🔥 錯誤時恢復音訊輸入
          isAudioInputPaused = false
          
          if (websocket.value?.readyState === WebSocket.OPEN) {
              websocket.value.send(JSON.stringify({ type: 'start_monitoring' }))
          }
      }
  }
  ```

- **2.7 實作 `resumeMonitoring` 方法**（收到事件後恢復）：
  ```typescript
  const resumeMonitoring = () => {
      // 🔥 恢復音訊輸入
      isAudioInputPaused = false
      logger.debug('▶️ 音訊輸入已恢復')
      
      // 發送恢復監聽命令
      if (websocket.value?.readyState === WebSocket.OPEN) {
          websocket.value.send(JSON.stringify({ type: 'start_monitoring' }))
          logger.info('👂 已恢復持續監聽模式')
      }
  }
  ```

- **設計要點**：
  - 使用 `client_id` 關聯 WebSocket 和 HTTP 通道（簡單可靠）
  - WebSocket 推送是**實時**的（無延遲），比輪詢高效
  - 音訊輸入暫停是**前端實現**的（不發送數據），減少網路開銷
  - 後端推送失敗不影響流程（前端有超時保護）
  - 前端保留超時保護（90 秒），避免永久暫停

---

### [ ] Step 3. 錯誤處理與超時保護
**Goal**: 處理 TTS 失敗、後端超時等異常情況

**Reason**: 確保系統在錯誤情況下能自動恢復，不會永久卡住

**Implementation Details**:
- **3.1 後端 TTS 失敗處理**（`voice_monitor_websocket_service.py`）：
  ```python
  async def _play_acknowledgment(self):
      try:
          # ... TTS 播放邏輯
      except Exception as e:
          logger.error(f"❌ 播放歡迎詞失敗: {e}")
          # 不中斷流程，繼續錄音
      finally:
          self.is_playing_acknowledgment = False  # 確保標記被重置
  ```

- **3.2 前端超時保護**（`useVoiceMonitor.ts`）：
  ```typescript
  const handleAutoRecording = async () => {
      // 設置總體超時（90 秒 = 30s 錄音 + 60s 處理）
      const timeoutId = setTimeout(() => {
          logger.warn('⏰ 錄音流程超時，強制恢復監聽')
          isAudioInputPaused = false
          
          if (websocket.value?.readyState === WebSocket.OPEN) {
              websocket.value.send(JSON.stringify({ type: 'start_monitoring' }))
          }
      }, 90000)
      
      try {
          // ... 錄音邏輯
      } finally {
          clearTimeout(timeoutId)
      }
  }
  ```

- **3.3 WebSocket 斷線處理**：
  ```typescript
  const setupWebSocket = () => {
      ws.onclose = () => {
          logger.warn('WebSocket 斷線')
          
          // 清理狀態
          isAudioInputPaused = false
          isMonitoring.value = false
          
          // 嘗試重連（現有邏輯）
      }
  }
  ```

- **設計要點**：
  - 多層超時保護（錄音 30s、處理 60s、總體 90s）
  - 錯誤時優先恢復監聽（不讓系統卡住）
  - 所有異常都記錄日誌（方便調試）

---

## Test Plan

### 手動測試計劃

#### 1. 基本流程測試
- [ ] 啟動監聽 → 說喚醒詞 → 聽到「我有聽到，請說」→ 說話 → AI 回應 → 自動恢復監聽
- [ ] 檢查歡迎詞播放期間，VAD 不會誤觸發
- [ ] 檢查錄音上傳期間，WebSocket 不發送音訊數據
- [ ] 檢查 TTS 播放完成後，自動恢復監聽

#### 2. 錯誤情況測試
- [ ] TTS 服務失敗時，依然能正常錄音和處理
- [ ] 後端處理超時（60 秒）時，前端自動恢復監聽
- [ ] WebSocket 斷線時，狀態正確清理

#### 3. 邊界條件測試
- [ ] 連續說兩次喚醒詞（第二次應該被暫停期間忽略）
- [ ] 極短語音（< 1 秒）
- [ ] 極長語音（> 10 秒）

### Mock 策略
- 手動功能測試為主（涉及音訊和 WebSocket，單元測試困難）
- 可選：Mock TTSPlayerQueue 測試歡迎詞邏輯

---

## Unit Test

### 手動功能測試（預計 2026-01-21）

**測試環境**：
- 後端：Python 3.12, FastAPI, AllTalkTTS
- 前端：Vue 3, WebSocket

**測試項目**：
- [ ] 1. 喚醒詞回應播放
- [ ] 2. 播放期間 VAD 暫停
- [ ] 3. 錄音期間音訊輸入暫停
- [ ] 4. TTS 播放完成後自動恢復監聽
- [ ] 5. 錯誤處理（TTS 失敗、超時）

---

## 實現時間估算

- Step 1（後端喚醒詞 TTS 回應）：1.5 小時
- Step 2（前端暫停音訊輸入）：2 小時
- Step 3（錯誤處理與超時）：1 小時
- 測試與除錯：1.5 小時

**總計：約 6 小時**

---

## 方案 B 分析：TTS 開始播放時恢復監聽

### 實現方式
如您所說，只需要**移除** `voice_chat_service.py` 中的：
```python
# 移除這段
if self.player_queue.wait_until_done(timeout=60):
    logger.info("TTS 播放完成")
```

### 架構變更
1. **後端**：`process_voice` 方法在 LLM streaming 完成後立即返回（不等 TTS）
2. **前端**：收到 `/api/chat/voice` 響應後立即恢復監聽（TTS 可能還在播放）

### 潛在問題分析

#### ⚠️ 問題 1：用戶在 AI 說話時觸發新對話
**場景**：
```
1. 用戶說：「今天天氣如何？」
2. AI 開始播放：「今天天氣不錯，氣溫大約...」（約 5 秒）
3. 前端恢復監聽（TTS 還在播放）
4. 用戶立即說：「Hey Jarvis」（AI 還沒說完）
5. 系統檢測到喚醒詞 → 中斷當前 TTS → 開始新對話
```

**影響**：
- ✅ 優點：用戶可以打斷 AI（更自然的對話）
- ❌ 缺點：可能造成混亂（AI 話說一半被打斷）
- ❌ 缺點：用戶可能不是故意打斷，只是測試系統（造成意外中斷）

#### ⚠️ 問題 2：TTS 播放與麥克風錄音衝突
**場景**：
```
1. AI 正在播放語音（通過揚聲器）
2. 前端恢復監聽，麥克風開始錄音
3. 麥克風可能會錄到「AI 自己的聲音」（回音）
4. KWS 或 VAD 可能誤識別 AI 聲音為用戶輸入
```

**影響**：
- ❌ 嚴重問題：可能觸發「回音循環」（AI 聽到自己的聲音，誤認為喚醒詞）
- ❌ 需要「回音消除」技術（複雜，需要硬體支持或演算法）

#### ⚠️ 問題 3：前端狀態不一致
**場景**：
```
1. 前端恢復監聽（發送 start_monitoring）
2. TTS 還在播放（佇列中可能還有 3-5 個文本片段）
3. 用戶看到「監聽中」狀態，但聽到 AI 還在說話
4. 用戶體驗困惑：「到底我現在能不能說話？」
```

**影響**：
- ❌ UX 問題：狀態指示不清晰（監聽中 vs AI 說話中）
- ❌ 需要複雜的 UI 設計（同時顯示「AI 說話中」+「可以打斷」）

#### ⚠️ 問題 4：競態條件（Race Condition）
**場景**：
```
1. `/api/chat/voice` 返回響應（前端恢復監聽）
2. 幾乎同時，TTS 佇列最後一個片段播放完成
3. 兩個「恢復監聽」指令可能同時發送
4. WebSocket 狀態可能混亂
```

**影響**：
- ⚠️ 小概率問題：需要加鎖或去重邏輯

#### ⚠️ 問題 5：測試與除錯困難
**場景**：
- 方案 A：流程清晰，容易重現問題（錄音 → 處理 → TTS 完成 → 恢復）
- 方案 B：TTS 和監聽並行，時序複雜，難以調試

**影響**：
- ❌ 開發成本增加（需要處理並行問題）
- ❌ 未來維護困難（邏輯不直觀）

---

### 方案 B 建議

如果要實現方案 B，需要額外處理：

1. **回音消除**（必須）：
   - 軟體方案：使用 WebRTC AEC（回音消除演算法）
   - 硬體方案：使用支持 AEC 的麥克風/耳機

2. **TTS 播放狀態通知**（建議）：
   - 後端推送 `tts_started` 事件（LLM 完成，TTS 開始）
   - 前端顯示「AI 說話中，可打斷」

3. **喚醒詞靈敏度調整**（建議）：
   - TTS 播放期間，提高 KWS 閾值（減少誤觸發）
   - 或完全禁用 KWS，只允許手動停止 TTS

4. **UI 明確指示**（必須）：
   - 顯示「AI 說話中（可打斷）」
   - 或添加「停止」按鈕（手動中斷 TTS）

---

### 結論

**方案 A（推薦）**：
- ✅ 邏輯簡單，穩定可靠
- ✅ 無回音問題
- ✅ 對話禮儀清晰（等 AI 說完）
- ❌ 無法打斷 AI

**方案 B（複雜）**：
- ✅ 可以打斷 AI（更靈活）
- ❌ 需要回音消除（技術門檻高）
- ❌ 狀態管理複雜（並行問題）
- ❌ 用戶體驗可能混亂（何時能說話？）

**建議**：先實現方案 A，穩定後再評估是否需要方案 B。如果實現方案 B，必須先解決「回音消除」問題。
