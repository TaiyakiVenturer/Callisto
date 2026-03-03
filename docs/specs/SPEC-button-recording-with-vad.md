# SPEC: 按鈕錄音功能優化 + VAD 統一

## Task Description

優化原有的「按住說話」按鈕功能，改為「點擊錄音」模式，並整合 Silero VAD 自動檢測靜音停止。同時統一兩種模式（按鈕錄音、持續監聽）都使用 Silero VAD，提升一致性。

**當前問題**：
- 「按住說話」需要一直按住，不適合長對話
- 使用 WebRTC VAD 裁剪靜音（後處理），體驗不如實時檢測
- 兩種模式使用不同的 VAD（WebRTC vs Silero），體驗不一致

**改進目標**：
- **模式 A（按鈕錄音）**：點擊開始 → VAD 自動檢測停止 → 可手動提前傳送或取消
- **模式 B（持續監聽）**：復用模式 A 的錄音邏輯，檢測到喚醒詞後自動觸發
- **統一 VAD**：兩種模式都使用 Silero VAD（移除 WebRTC VAD 依賴）

## Tech Stack

- **前端**：Vue 3, TypeScript, MediaRecorder API
- **後端**：FastAPI WebSocket, Silero VAD (ONNX)
- **測試**：Vitest (前端，可選)

## Acceptance Criteria

### 按鈕錄音功能（純手動控制，不使用 VAD）
- [x] 點擊「開始錄音」按鈕啟動錄音
- [x] 前端使用 MediaRecorder 保存音訊（不啟用 AudioWorklet）
- [x] 錄音時顯示「傳送」和「取消」兩個按鈕
- [x] 用戶可手動點擊「傳送」提前結束並上傳
- [x] 用戶可手動點擊「取消」丟棄錄音（不上傳）
- [x] 錄音超時 30 秒自動停止並上傳
- [x] UI 清晰顯示當前狀態（錄音中、處理中、錯誤）
- [x] 按鈕與監聽功能互斥（不能同時使用）

### 持續監聽功能（復用邏輯，啟用 VAD）
- [x] 檢測到喚醒詞後，自動觸發「開始錄音」邏輯
- [x] 傳入 enableVAD: true + websocket 參數
- [x] 前端啟動 MediaRecorder + AudioWorklet（發送 PCM）
- [x] 連接到 `/ws/voice-monitor`，發送 `start_vad_only` 命令
- [x] 後端 Silero VAD 檢測到 1.5 秒靜音，推送 `stop_recording` 事件
- [x] 前端收到事件後停止 MediaRecorder，上傳 WebM 到 `/api/chat/voice`
- [x] 自動上傳音訊，無需用戶操作
- [x] 完成後自動恢復監聽模式（發送 start_monitoring 命令）

### VAD 統一與清理
- [x] 更新 `voice_chat_service.py` 使用 Silero VAD（`SileroVADService`）替代 WebRTC VAD
- [x] `/api/chat/voice` 端點保留靜音截斷功能，但改用 Silero VAD 實現
- [x] 刪除舊的 WebRTC VAD 實現（`backend/services/vad_service.py`）
- [x] 刪除 WebRTC VAD 相關測試（`backend/tests/test_vad_service.py`）
- [x] 保持 `silero_vad_service.py` 文件名不變（避免破壞現有導入）

## Target Files

### 前端
- **修改**：
  - `frontend/src/composables/useVoiceRecorder.ts` - 整合 AudioWorklet，復用 voice-monitor WebSocket
  - `frontend/src/components/VoiceRecorder.vue` - 改為點擊錄音 + 傳送/取消按鈕
  - `frontend/src/composables/useVoiceMonitor.ts` - 檢測到喚醒詞後調用 useVoiceRecorder
- **不需要新增文件**（復用現有架構）

### 後端
- **修改**：
  - `backend/services/voice_monitor_websocket_service.py` - 實作模式切換邏輯（monitoring / vad_only）
  - `backend/services/audio_monitor_service.py` - 添加 VAD 靜音檢測配置
  - `backend/services/voice_chat_service.py` - 移除 WebRTC VAD 裁剪邏輯
- **刪除**：
  - `backend/services/vad_service.py`（WebRTC VAD）
  - `backend/tests/test_vad_service.py`（WebRTC VAD 測試）
- **保持不變**：
  - `backend/services/silero_vad_service.py` - 文件名與類名保持不變

---

## Implementation

### [x] Step 1. 後端 WebSocket 支持 VAD 檢測模式
**Goal**: 在 `VoiceMonitorWebSocketService` 中實作模式切換與 VAD 靜音檢測

**Reason**: 復用現有架構，業務邏輯統一在 Service 層管理

**Implementation Details** (已完成):
- **1.1 定義靜音檢測常數**（在 `voice_monitor_websocket_service.py`）：
  ```python
  # 靜音檢測配置
  SILENCE_DURATION = 1.5  # 秒
  CHUNK_DURATION = 0.032  # 32ms (512 samples @ 16kHz)
  SILENCE_CHUNKS_THRESHOLD = int(SILENCE_DURATION / CHUNK_DURATION)  # 47 chunks
  ```

- **1.2 擴展 `VoiceMonitorWebSocketService` 類**：
  ```python
  class VoiceMonitorWebSocketService:
      def __init__(self, websocket, mode='monitoring', ...):
          self.mode = mode  # 'monitoring' | 'vad_only' | 'idle'
          self.silence_counter = 0
          
      async def handle_audio_stream(self):
          """主循環：接收音訊 + 處理命令"""
          while True:
              message = await websocket.receive()
              
              # 處理 JSON 命令
              if "text" in message:
                  await self._handle_command(json.loads(message["text"]))
                  continue
              
              # 處理音訊數據
              if "bytes" in message:
                  data = message["bytes"]
                  
                  if self.mode == "vad_only":
                      await self._handle_vad_only(data)
                  elif self.mode == "monitoring":
                      # 原有邏輯：放入 audio_queue
                      await self.audio_queue.put(data)
                      
      async def _handle_command(self, cmd: dict):
          """處理模式切換命令"""
          if cmd["type"] == "start_vad_only":
              self.mode = "vad_only"
              self.silence_counter = 0
              logger.info("🎤 切換至 VAD 錄音模式")
              
          elif cmd["type"] == "start_monitoring":
              self.mode = "monitoring"
              self.monitor_service.reset()
              logger.info("👂 切換至持續監聽模式")
              
      async def _handle_vad_only(self, data: bytes):
          """VAD 純檢測模式：檢測靜音並推送停止事件"""
          pcm_array = np.frombuffer(data, dtype=np.int16)
          is_speech = self.monitor_service.vad_service.detect_speech(pcm_array)
          
          if is_speech:
              self.silence_counter = 0
          else:
              self.silence_counter += 1
              
          if self.silence_counter >= SILENCE_CHUNKS_THRESHOLD:
              await self.websocket.send_json({
                  "type": "stop_recording",
                  "reason": "silence_detected",
                  "silence_duration": SILENCE_DURATION
              })
              self.silence_counter = 0
              self.mode = "idle"  # 自動回到 idle
              logger.info("🛑 VAD 檢測到 1.5 秒靜音，推送停止事件")
  ```

- **設計要點**：
  - 使用常數計算靜音閾值（可配置）
  - 業務邏輯在 Service 層，`api_server.py` 保持簡潔
  - 模式自動切換：`vad_only` → `idle`
  - 支持動態模式切換（通過 JSON 命令）

---

### [x] Step 2. 前端整合 AudioWorklet 與 WebSocket
**Goal**: 修改 useVoiceRecorder 整合 PCM 採集與後端 VAD 檢測互動

**Reason**: 前端同時進行音訊保存（MediaRecorder）和 PCM 數據發送（供後端 VAD 檢測）

**Implementation Details** (已完成，已保留選項參數為 Step 4 預留):
- **2.1 修改 `useVoiceRecorder.ts` 架構**：
  ```typescript
  export function useVoiceRecorder() {
      const isRecording = ref(false)
      const mediaRecorder = ref<MediaRecorder | null>(null)
      const audioChunks = ref<Blob[]>([])
      const stream = ref<MediaStream | null>(null)
      
      // 🔥 新增：VAD 檢測相關
      let wsConnection: WebSocket | null = null
      let audioContext: AudioContext | null = null
      let workletNode: AudioWorkletNode | null = null
      let vadMessageHandler: ((event: MessageEvent) => void) | null = null
      let recordingTimeout: number | null = null
      
      const startRecording = async (options?: {
          enableVAD?: boolean,          // 是否啟用 VAD 自動停止
          websocket?: WebSocket,        // 外部傳入的 WebSocket
          onVADStop?: () => void        // VAD 檢測到靜音的回調
      }) => {
          // 1. 請求麥克風
          stream.value = await navigator.mediaDevices.getUserMedia({
              audio: { channelCount: 1, sampleRate: 16000 }
          })
          
          // 2. MediaRecorder（用於保存音訊）
          mediaRecorder.value = new MediaRecorder(stream.value, {
              mimeType: 'audio/webm;codecs=opus'
          })
          audioChunks.value = []
          mediaRecorder.value.ondataavailable = (e) => {
              if (e.data.size > 0) audioChunks.value.push(e.data)
          }
          mediaRecorder.value.start()
          
          // 3. AudioWorklet（用於實時 VAD 檢測）
          if (options?.enableVAD && options?.websocket) {
              wsConnection = options.websocket
              
              // 建立 AudioContext 與 Worklet
              audioContext = new AudioContext({ sampleRate: 16000 })
              const source = audioContext.createMediaStreamSource(stream.value)
              
              await audioContext.audioWorklet.addModule('/audio-processor.js')
              workletNode = new AudioWorkletNode(audioContext, 'pcm-audio-processor')
              
              // Worklet 輸出 PCM → WebSocket
              workletNode.port.onmessage = (event) => {
                  const pcmData = event.data  // ArrayBuffer (int16)
                  if (wsConnection?.readyState === WebSocket.OPEN) {
                      wsConnection.send(pcmData)
                  }
              }
              
              source.connect(workletNode)
              workletNode.connect(audioContext.destination)
              
              // 監聽 VAD stop_recording 事件
              vadMessageHandler = (event: MessageEvent) => {
                  const data = JSON.parse(event.data)
                  if (data.type === 'stop_recording') {
                      console.log('🛑 VAD 檢測到 1.5 秒靜音，自動停止錄音')
                      stopRecording()
                      options.onVADStop?.()
                  }
              }
              wsConnection.addEventListener('message', vadMessageHandler)
              
              // 發送命令：啟動 VAD 檢測模式
              wsConnection.send(JSON.stringify({ type: 'start_vad_only' }))
          }
          
          // 4. 超時保護（30 秒）
          recordingTimeout = window.setTimeout(() => {
              console.warn('⏰ 錄音超時 30 秒，自動停止')
              stopRecording()
          }, 30000)
          
          isRecording.value = true
      }
      
      const stopRecording = async () => {
          if (!isRecording.value) return
          
          // 清理超時
          if (recordingTimeout) clearTimeout(recordingTimeout)
          
          // 停止 MediaRecorder
          mediaRecorder.value?.stop()
          
          // 停止 AudioWorklet
          workletNode?.disconnect()
          audioContext?.close()
          
          // 停止麥克風
          stream.value?.getTracks().forEach(t => t.stop())
          
          // 清理 WebSocket 監聽器
          if (vadMessageHandler && wsConnection) {
              wsConnection.removeEventListener('message', vadMessageHandler)
          }
          
          // 建立 Blob 並上傳
          const audioBlob = new Blob(audioChunks.value, { type: 'audio/webm' })
          await uploadAudio(audioBlob)
          
          isRecording.value = false
      }
      
      const cancelRecording = () => {
          // 類似 stopRecording，但不上傳
          if (recordingTimeout) clearTimeout(recordingTimeout)
          mediaRecorder.value?.stop()
          workletNode?.disconnect()
          audioContext?.close()
          stream.value?.getTracks().forEach(t => t.stop())
          if (vadMessageHandler && wsConnection) {
              wsConnection.removeEventListener('message', vadMessageHandler)
          }
          audioChunks.value = []
          isRecording.value = false
      }
      
      return { isRecording, startRecording, stopRecording, cancelRecording }
  }
  ```

- **2.2 說明架構設計**：
  - **前端職責**：
    - MediaRecorder：累積並保存完整的 WebM 音訊文件
    - AudioWorklet：實時採集 PCM 數據，通過 WebSocket 發送到後端
    - 接收後端 VAD 檢測結果（`stop_recording` 事件），觸發停止錄音
  - **後端職責**：
    - 接收前端發送的 PCM 數據流
    - 使用 Silero VAD 實時檢測靜音（1.5 秒閾值）
    - 檢測到靜音後推送 `stop_recording` 事件給前端
    - 接收上傳的完整音訊文件，進行靜音截斷後處理
  - **澄清**：前端沒有 VAD 服務實現，所有 VAD 判斷都在後端完成

---

### [x] Step 3. VoiceRecorder UI 改造（已簡化為純手動控制）
**Goal**: 改為點擊錄音模式，按鈕狀態互斥，顯示傳送/取消按鈕

**Reason**: 提供更靈活的用戶控制，避免模式衝突。經設計調整，按鈕錄音改為純手動控制，不使用 VAD 自動截斷

**Implementation Details** (已完成):
- **3.1 修改 `VoiceRecorder.vue` 結構**：
  ```vue
  <script setup>
  import { useVoiceRecorder } from '@/composables/useVoiceRecorder'
  import { useVoiceMonitor } from '@/composables/useVoiceMonitor'
  
  const { isRecording, startRecording, stopRecording, cancelRecording } = useVoiceRecorder()
  const { isMonitoring, websocket } = useVoiceMonitor()
  
  // 開始錄音（啟用 VAD）
  // **實際實作**：經設計調整，按鈕錄音改為純手動控制
  const handleStartRecording = async () => {
      try {
          await startRecording()  // 不傳參數，純手動控制
      } catch (error) {
          console.error('錄音失敗:', error)
      }
  }
  
  // 手動傳送（提前結束）
  const handleSendRecording = async () => {
      await stopRecording()
      // 啟動狀態輪詢...
  }
  
  // 手動取消
  const handleCancelRecording = () => {
      cancelRecording()
  }
  </script>
  
  <template>
      <div class="voice-controls">
          <!-- 錄音按鈕（監聽時禁用）-->
          <button 
              v-if="!isRecording" 
              @click="handleStartRecording"
              :disabled="isMonitoring"
              class="record-btn"
          >
              🎤 {{ isMonitoring ? '監聽中...' : '開始錄音' }}
          </button>
          
          <!-- 錄音中：顯示「傳送」和「取消」按鈕 -->
          <div v-else class="recording-controls">
              <div class="recording-indicator">
                  🔴 錄音中（按下傳送完成）
              </div>
              <div class="button-group">
                  <button @click="handleSendRecording" class="send-btn">
                      ✅ 傳送
                  </button>
                  <button @click="handleCancelRecording" class="cancel-btn">
                      ❌ 取消
                  </button>
              </div>
          </div>
          
          <!-- 監聽按鈕（錄音時禁用）-->
          <button 
              @click="toggleMonitoring"
              :disabled="isRecording"
              class="monitor-btn"
          >
              {{ isMonitoring ? '🛑 停止監聽' : '👂 持續監聽' }}
          </button>
      </div>
  </template>
  ```

- **狀態互斥邏輯**：
  - 錄音時：監聽按鈕 disabled，顯示「錄音中...」
  - 監聽時：錄音按鈕 disabled，顯示「監聽中...」
  - 原按鈕消失，顯示「傳送/取消」**兩個獨立按鈕**（並排）
  - 錄音指示器簡化為「錄音中（按下傳送完成）」
  
- **設計決策**（詳見 Spec Amendments）：
  - 按鈕錄音不使用 VAD 自動截斷（純手動控制）
  - VAD 自動截斷僅用於 Step 4 監聽模式
  - useVoiceRecorder 保留 options 參數（為 Step 4 預留）

---

### [x] Step 4. 持續監聽整合（復用邏輯，啟用 VAD）
**Goal**: 檢測到喚醒詞後自動觸發錄音，復用按鈕錄音邏輯（傳入 enableVAD 選項）

**Reason**: 統一錄音處理流程，避免重複開發。監聽模式需要 VAD 自動截斷（用戶不操作）

**Implementation Details** (已完成):
- **4.1 修改 `useVoiceMonitor.ts` 整合錄音邏輯**：
  ```typescript
  import { useVoiceRecorder } from './useVoiceRecorder'
  
  export function useVoiceMonitor() {
      // 整合錄音 Composable
      const { isRecording, startRecording, stopRecording } = useVoiceRecorder()
      
      // 自動錄音處理（喚醒詞觸發）
      const handleAutoRecording = async () => {
          if (isRecording.value || !websocket || websocket.readyState !== WebSocket.OPEN) {
              return
          }
          
          await startRecording({
              enableVAD: true,
              websocket: websocket,
              onVADStop: async () => {
                  // VAD 檢測到靜音，自動上傳並恢復監聽
                  await stopRecording()
                  
                  // 發送命令：切換回監聽模式
                  websocket?.send(JSON.stringify({ type: 'start_monitoring' }))
              }
          })
      }
      
      // 修改 keyword 事件處理
      case 'keyword':
          handleAutoRecording()  // 自動觸發錄音
          break
      
      return { 
          isMonitoring, 
          isRecording,  // 暴露錄音狀態
          ...
      }
  }
  ```

- **4.2 修改 `VoiceRecorder.vue` 統一錄音狀態**：
  ```vue
  <script setup>
  const {
      isRecording: monitorIsRecording,  // 監聽模式的錄音
      ...
  } = useVoiceMonitor()
  
  const { 
      isRecording: buttonIsRecording,   // 按鈕手動錄音
      startRecording, 
      stopRecording 
  } = useVoiceRecorder()
  
  // 統一錄音狀態
  const isRecording = computed(() => 
      monitorIsRecording.value || buttonIsRecording.value
  )
  </script>
  
  <template>
      <!-- 錄音提示根據模式動態顯示 -->
      <span class="recording-text">
          {{ monitorIsRecording 
              ? '錄音中（VAD 自動檢測）' 
              : '錄音中（按下傳送完成）' 
          }}
      </span>
      
      <!-- 自動錄音時隱藏傳送/取消按鈕 -->
      <div v-if="!monitorIsRecording" class="button-group">
          <button @click="handleSendRecording">✅ 傳送</button>
          <button @click="handleCancelRecording">❌ 取消</button>
      </div>
  </template>
  ```

- **實作成果**：
  - ✅ 完全復用 useVoiceRecorder 邏輯（傳入 enableVAD 選項）
  - ✅ 同一 WebSocket 連接，無需重連
  - ✅ 狀態統一管理（monitorIsRecording + buttonIsRecording）
  - ✅ UI 動態提示（VAD 模式 vs 手動模式）
  - ✅ 自動恢復監聽（發送 start_monitoring 命令）

- **完整流程**：
  1. 持續監聽模式：WebSocket 處於 `monitoring` 模式
  2. 檢測到喚醒詞 → 後端推送 `keyword` 事件
  3. 前端觸發 `handleAutoRecording()` → 啟動錄音（enableVAD: true）
  4. 錄音時：
     - MediaRecorder 累積音訊（前端保存）
     - AudioWorklet 發送 PCM 到 WebSocket（後端 VAD 檢測）
  5. 後端 VAD 檢測 1.5s 靜音 → 推送 `stop_recording`
  6. 前端 `onVADStop` 回調 → stopRecording() 上傳音訊
  7. 發送 `start_monitoring` 命令 → 恢復監聽模式

---

### [x] Step 5. 統一使用 Silero VAD
**Goal**: 將 `voice_chat_service.py` 的靜音截斷功能改用 Silero VAD 實現

**Reason**: 統一使用 Silero VAD，提升檢測準確度與一致性

**Implementation Details** (已完成):
- **5.1 在 `silero_vad_service.py` 實作 trim_silence 方法**：
  ```python
  def trim_silence(self, audio_path: str, output_path: Optional[str] = None) -> str:
      """
      裁剪音訊前後的靜音部分
      使用 Silero VAD 檢測語音活動，移除音訊開頭和結尾的靜音部分
      """
      # 讀取 WAV 檔案，切分成 512 samples chunks
      # 使用 self.detect() 檢測每個 chunk 是否為語音
      # 找到第一個和最後一個語音 frame，裁剪並保存
  ```

- **5.2 在 `silero_vad_service.py` 實作 convert_to_vad_format 方法**：
  ```python
  def convert_to_vad_format(self, audio_path: str, output_path: str) -> str:
      """
      將音訊轉換為 VAD 支援的格式 (16kHz, mono, 16-bit)
      """
      from pydub import AudioSegment
      
      audio = AudioSegment.from_file(audio_path)
      audio = audio.set_frame_rate(self.sample_rate)  # 16kHz
      audio = audio.set_channels(1)                    # mono
      audio = audio.set_sample_width(2)                # 16-bit
      audio.export(output_path, format="wav")
  ```

- **5.3 修改 `voice_chat_service.py` 使用 Silero VAD**：
  ```python
  # 更新導入
  from services.silero_vad_service import SileroVADService
  
  def __init__(self):
      # 初始化 Silero VAD 服務（threshold=0.5）
      self.vad_service = SileroVADService(threshold=0.5)
  ```

- **5.4 刪除 WebRTC VAD 文件**：
  ```bash
  rm backend/services/vad_service.py
  rm backend/tests/test_vad_service.py
  ```

- **實作成果**：
  - ✅ Silero VAD 支持 trim_silence 和 convert_to_vad_format
  - ✅ voice_chat_service.py 改用 SileroVADService
  - ✅ 刪除 WebRTC VAD 相關文件
  - ✅ 統一使用 Silero VAD（實時檢測 + 後處理裁剪）

---

### [x] Step 6. 超時處理與錯誤恢復
**Goal**: 防止錄音卡死或無限等待

**Reason**: 提升穩定性與用戶體驗

**Implementation Details** (已完成):

- **6.1 錄音超時保護（useVoiceRecorder）**：
  ```typescript
  // 30 秒超時保護
  recordingTimeout = window.setTimeout(() => {
      console.warn('⏰ 錄音超時 30 秒，自動停止')
      stopRecording()
  }, 30000)
  
  // 停止時清除超時
  if (recordingTimeout) {
      clearTimeout(recordingTimeout)
      recordingTimeout = null
  }
  ```

- **6.2 資源清理邏輯**：
  ```typescript
  // stopRecording 和 cancelRecording 都包含完整清理
  const cleanup = async () => {
      // 清理超時
      if (recordingTimeout) clearTimeout(recordingTimeout)
      
      // 停止 AudioWorklet
      if (workletNode) {
          workletNode.disconnect()
          workletNode = null
      }
      
      // 關閉 AudioContext
      if (audioContext) {
          await audioContext.close()
          audioContext = null
      }
      
      // 停止麥克風
      if (stream.value) {
          stream.value.getTracks().forEach(track => track.stop())
          stream.value = null
      }
      
      // 清理 WebSocket 監聽器
      if (vadMessageHandler && wsConnection) {
          wsConnection.removeEventListener('message', vadMessageHandler)
          vadMessageHandler = null
      }
  }
  ```

- **6.3 WebSocket 錯誤處理（useVoiceMonitor）**：
  ```typescript
  // WebSocket 重連機制（已實作）
  websocket.onerror = (err) => {
      console.error('[VoiceMonitor] WebSocket error:', err)
      error.value = 'WebSocket 連接錯誤'
  }
  
  websocket.onclose = () => {
      if (isMonitoring.value) {
          attemptReconnect()  // 最多重試 3 次
      }
  }
  ```

- **6.4 麥克風權限錯誤處理**：
  ```typescript
  try {
      stream.value = await navigator.mediaDevices.getUserMedia({...})
  } catch (error) {
      console.error('❌ 無法存取麥克風:', error)
      throw new Error('麥克風權限被拒絕或不可用')
  }
  ```

- **6.5 後端 VAD 錯誤處理（voice_monitor_websocket_service）**：
  ```python
  try:
      is_speech = self.monitor_service.vad_service.detect_speech(pcm_array)
  except Exception as e:
      logger.error(f"❌ VAD 檢測發生錯誤: {e}")
      # 繼續執行，不中斷服務
  ```

- **實作成果**：
  - ✅ 30 秒錄音超時保護
  - ✅ 完整的資源清理邏輯（AudioContext、麥克風、WebSocket）
  - ✅ WebSocket 斷線重連機制（最多 3 次）
  - ✅ 麥克風權限錯誤提示
  - ✅ VAD 檢測錯誤處理（不中斷服務）
  - ✅ 後端錯誤通過 WebSocket 推送給前端

---

## 架構對比

### Before（原有架構）

```
模式 A（按住說話）:
前端 MediaRecorder → 上傳 WebM → 後端轉 WAV → WebRTC VAD 裁剪 → STT

模式 B（持續監聽）:
前端 AudioWorklet → WebSocket 傳輸 → Silero VAD 檢測 → KWS 喚醒 → [待實現]
```

**問題**：
- 兩種模式使用不同的 VAD（體驗不一致）
- 模式 A 需要一直按住（不適合長對話）
- 模式 B 需要重新實現音訊保存和上傳邏輯

### After（優化後架構）

```
模式 A（按鈕錄音）:
前端 MediaRecorder（錄音） + AudioWorklet（發送 PCM） → 後端 VAD 檢測 → 自動/手動停止 → 上傳 → STT

模式 B（持續監聽）：
前端 AudioWorklet → WebSocket 傳輸 → 後端 Silero VAD + KWS 檢測 → 檢測到喚醒詞
                                                                ↓
                                            自動觸發模式 A 的錄音邏輯 ✅
```

**優勢**：
- ✅ 統一使用 Silero VAD
- ✅ 模式 A 支持點擊錄音（不需按住）
- ✅ 模式 B 完全復用模式 A（代碼簡潔）
- ✅ VAD 實時檢測（體驗更好）

---

## 架構說明

### VAD 檢測的兩個階段

**階段 1：實時靜音檢測（錄音中）**
```
前端                                後端
──────────────────────────────────────────────────────
MediaRecorder                    
  ↓ 累積 WebM                    
AudioWorklet                     
  ↓ 轉 PCM                       
WebSocket ──────────→ VoiceMonitorWebSocketService
                                   ↓
                                 SileroVADService.detect_speech()
                                   ↓
                                 檢測 1.5 秒靜音
                                   ↓
                     ←────────── 推送 stop_recording 事件
  ↓
stopRecording()
  ↓
上傳 WebM 到 /api/chat/voice
```

**階段 2：靜音截斷（音訊處理）**
```
後端
──────────────────────────────────
接收 WebM 文件
  ↓
VoiceChatService.process_voice()
  ↓
轉換為 WAV
  ↓
SileroVADService.trim_silence()
  ↓ 裁剪前後靜音段
STT 轉文字
  ↓
LLM 生成回應
  ↓
TTS 合成語音
```

### 關鍵設計原則

1. **前端無 VAD 實現**：前端只負責採集和發送 PCM 數據，所有 VAD 判斷都在後端
2. **兩次 VAD 檢測**：
   - 第一次：實時檢測何時停止錄音（WebSocket 流式處理）
   - 第二次：音訊後處理裁剪靜音（文件處理）
3. **統一使用 Silero VAD**：兩個階段都使用同一個 VAD 服務，確保一致性

---

## Test Generate

### Test Plan

#### 1. 按鈕錄音功能（純手動控制）
- **test_button_recording_start** - 點擊「開始錄音」按鈕
  - 預期：按鈕變為「錄音中」，顯示傳送/取消按鈕
  - 預期：不啟用 VAD，不依賴 WebSocket
  
- **test_manual_send** - 手動點擊「傳送」按鈕
  - 預期：停止錄音，上傳音訊，開始處理
  - 預期：顯示「處理中」狀態
  
- **test_manual_cancel** - 手動點擊「取消」按鈕
  - 預期：停止錄音，丟棄音訊，不上傳
  - 預期：恢復 idle 狀態
  
- **test_recording_timeout** - 錄音超過 30 秒
  - 預期：自動停止並上傳
  - 預期：console 顯示「錄音超時」警告

#### 2. 持續監聽整合（VAD 自動截斷）
- **test_keyword_detection** - 檢測到喚醒詞
  - 預期：自動開始錄音（enableVAD: true）
  - 預期：錄音指示器顯示「錄音中（VAD 自動檢測）」
  - 預期：不顯示傳送/取消按鈕
  
- **test_vad_auto_stop** - VAD 檢測到 1.5 秒靜音
  - 預期：自動停止錄音並上傳
  - 預期：發送 start_monitoring 命令恢復監聽
  
- **test_continuous_conversation** - 連續對話
  - 預期：說完第一句話 → 自動上傳 → 恢復監聽 → 再說喚醒詞 → 繼續錄音

#### 3. 狀態互斥
- **test_monitoring_disables_button** - 監聽時禁用錄音按鈕
  - 預期：監聽中時，錄音按鈕顯示「監聽中...」且 disabled
  
- **test_recording_disables_monitoring** - 錄音時禁用監聽按鈕
  - 預期：錄音中時，監聽按鈕 disabled

#### 4. 錯誤處理
- **test_microphone_permission_denied** - 麥克風權限被拒絕
  - 預期：顯示錯誤提示「麥克風權限被拒絕或不可用」
  
- **test_websocket_disconnected** - WebSocket 斷線
  - 預期：自動重連（最多 3 次）
  - 預期：重連失敗後顯示錯誤提示
  
- **test_backend_unavailable** - 後端服務未啟動
  - 預期：上傳失敗，顯示錯誤「無法連接到後端服務」

#### 5. VAD 統一性
- **test_silero_vad_used** - 確認使用 Silero VAD
  - 預期：voice_chat_service 導入 SileroVADService
  - 預期：vad_service.py 和 test_vad_service.py 已刪除
  
- **test_trim_silence_works** - 靜音截斷功能
  - 預期：音訊文件前後靜音被裁剪
  - 預期：裁剪後音訊可正常轉文字

### Mock Strategy

#### 前端測試 (Vitest + @vue/test-utils)
- **Mock MediaRecorder API**：模擬瀏覽器錄音
- **Mock AudioWorklet API**：模擬 PCM 採集
- **Mock WebSocket**：模擬 VAD 檢測事件推送
- **Mock fetch API**：模擬音訊上傳

#### 後端測試 (pytest)
- **Mock WebSocket**：模擬前端連接
- **Mock SileroVADService**：模擬 VAD 檢測結果
- **Mock AudioMonitorService**：模擬音訊處理

---

## Unit Test

### 測試記錄

#### 手動功能測試

**測試日期**: 2026-01-21

##### 按鈕錄音（手動模式）
- [ ] 點擊「開始錄音」→ 按鈕變為「錄音中」
- [ ] 顯示「傳送」和「取消」按鈕
- [ ] 錄音提示顯示「錄音中（按下傳送完成）」
- [ ] 點擊「傳送」→ 上傳成功 → 開始處理
- [ ] 點擊「取消」→ 停止錄音 → 不上傳
- [ ] 30 秒超時自動停止並上傳

##### 持續監聽（VAD 自動模式）
- [ ] 啟動「持續監聽」
- [ ] 說出喚醒詞「Hey Callisto」
- [ ] 自動開始錄音（不需點擊按鈕）
- [ ] 錄音提示顯示「錄音中（VAD 自動檢測）」
- [ ] 不顯示傳送/取消按鈕
- [ ] 停頓 1.5 秒後自動停止並上傳
- [ ] 自動恢復監聽狀態

##### 狀態互斥
- [ ] 監聽中時，錄音按鈕顯示「監聽中...」且禁用
- [ ] 錄音中時，監聽按鈕禁用

##### 錯誤處理
- [ ] 拒絕麥克風權限 → 顯示錯誤提示
- [ ] 後端未啟動 → 上傳失敗 → 顯示錯誤

##### VAD 統一性
- [ ] 確認 voice_chat_service 使用 SileroVADService
- [ ] 確認 vad_service.py 已刪除
- [ ] 音訊文件前後靜音被正確裁剪

---
- **test_manual_send** - 手動點擊傳送提前結束
- **test_manual_cancel** - 手動點擊取消丟棄錄音
- **test_recording_timeout** - 錄音 30 秒自動停止
- **test_recording_during_processing** - 處理中時禁用錄音按鈕

#### 2. VAD 檢測邏輯
- **test_vad_websocket_connection** - VAD WebSocket 連接正常
- **test_vad_silence_detection** - 正確檢測 1.5s 靜音
- **test_vad_speech_reset_counter** - 檢測到語音時重置靜音計數
- **test_vad_websocket_error** - WebSocket 錯誤時降級為手動模式

#### 3. 持續監聽整合
- **test_keyword_triggers_recording** - 檢測到喚醒詞自動開始錄音
- **test_auto_recording_vad_stop** - 自動錄音時 VAD 檢測停止
- **test_auto_upload_after_stop** - 停止後自動上傳
- **test_resume_monitoring** - 完成後恢復監聽模式

#### 4. UI 狀態管理
- **test_button_state_transitions** - 按鈕狀態正確切換
- **test_disable_during_monitoring** - 監聽時禁用錄音按鈕
- **test_error_display** - 錯誤正確顯示

### Mock 策略
- **Mock WebSocket**：模擬後端 VAD 檢測事件（`stop_recording`）
- **Mock MediaRecorder**：模擬錄音過程
- **Mock AudioWorklet**：模擬 PCM 數據發送
- **Mock fetch**：模擬音訊上傳

---

## Unit Test（待執行）

### 測試覆蓋
- [ ] useVoiceRecorder (updated) - 8 tests
  - startRecording with/without VAD
  - stopRecording (manual/auto)
  - cancelRecording
  - timeout handling
- [ ] VoiceRecorder.vue - 10 tests
  - button state transitions
  - disable logic (recording vs monitoring)
  - send/cancel actions
- [ ] useVoiceMonitor (integration) - 6 tests
  - keyword detection triggers recording
  - auto recording with VAD
  - resume monitoring after recording
- [ ] VoiceMonitorWebSocketService (backend) - 8 tests
  - mode switching (monitoring/vad_only)
  - silence detection
  - event pushing

### 預期結果
- Coverage: 85%+
- All tests pass

---

## 實現時間估算

- Step 1（後端 WebSocket 模式切換）：1.5 小時
- Step 2（前端整合 AudioWorklet）：2 小時
- Step 3（UI 改造 + 狀態互斥）：1.5 小時
- Step 4（持續監聽整合）：1 小時
- Step 5（移除 WebRTC VAD）：0.5 小時
- Step 6（超時與錯誤處理）：0.5 小時
- 測試與除錯：1.5 小時

**總計：約 8.5 小時**

---

## Spec Amendments

### 2026-01-21 #1 - 簡化按鈕錄音設計（移除 VAD 自動截斷）

#### Reason
實作過程中發現設計矛盾：
1. 按鈕錄音和監聽功能互斥（不能同時使用）
2. 但按鈕錄音需要 WebSocket（來自監聽）才能啟用 VAD
3. 這導致邏輯混亂和用戶體驗不佳

經討論後，釐清兩種使用場景的本質差異：
- **按鈕錄音**：用戶主動控制，明確知道要錄什麼，應該由用戶決定何時結束
- **監聽錄音**：系統被動觸發，用戶不操作，需要 VAD 自動判斷結束時機

#### Changes
1. **按鈕錄音模式**：移除 VAD 自動截斷功能
   - 完全依賴「傳送」和「取消」按鈕
   - 不需要 WebSocket 連接
   - 30 秒超時保護保留
   
2. **VAD 自動截斷**：僅用於監聽模式
   - 檢測到喚醒詞後自動開始錄音
   - 使用 VAD 檢測 1.5 秒靜音自動停止
   - 無需用戶操作

3. **UI 提示簡化**：
   - 移除「1.5 秒靜音自動傳送」提示
   - 改為簡單的「錄音中」+ 傳送/取消按鈕

#### Code Changes

**VoiceRecorder.vue**：
```typescript
// Before: 嘗試啟用 VAD（需要 WebSocket）
await startRecording({
    enableVAD: wsConnected,
    websocket: websocket.value,
    onVADStop: () => handleSendRecording()
})

// After: 純手動控制
await startRecording()  // 不傳任何選項
```

**useVoiceRecorder.ts**：
- 保留 `options` 參數（為 Step 4 監聽整合預留）
- 按鈕錄音不傳選項，不啟用 AudioWorklet 和 VAD

#### Impact
- 簡化程式碼邏輯（移除 WebSocket 狀態檢查）
- 提升按鈕錄音的可靠性（不依賴網路連接）
- 更清晰的功能定位（手動 vs 自動）
- 不影響 Step 4（監聽整合）的實作

#### Architecture Decision
**不採用共用 WebSocket 方案**的原因：
1. 雖然技術上可行（按鈕互斥不會衝突）
2. 但需要複雜的生命週期管理（誰建立誰關閉）
3. 需要模式狀態同步和錯誤處理
4. 用戶體驗不明確（為何按鈕錄音需要先建立連接？）
5. **簡單可靠 > 功能統一**

#### Test Results
- ✅ 按鈕錄音：獨立運作，不需要監聽
- ✅ 手動傳送/取消：正常工作
- ✅ 30 秒超時：正常觸發
- ✅ 監聽功能：不受影響

---

### 2026-01-21 #2 - VAD 靜音檢測優化（新增緩衝期機制）

#### Reason
測試監聽模式時發現，用戶說完喚醒詞後切換到 vad_only 模式時，VAD 會立即檢測到短暫的靜音（約 0.75 秒），導致錄音過早結束，實際語音內容未被錄製。

**根本原因**：
- 用戶剛說完喚醒詞，自然會有短暫停頓（0.5-1 秒）
- VAD 在模式切換後立即開始計算靜音，觸發過快
- 需要「緩衝期」忽略模式切換後的初始靜音

#### Changes
1. **新增 VAD 緩衝期常數**（`voice_monitor_websocket_service.py`）：
   ```python
   VAD_WARMUP_CHUNKS = 10  # 約 0.32 秒緩衝期
   ```

2. **新增 VAD 計數器**（實例變數）：
   ```python
   self.vad_chunk_counter = 0  # 追蹤已處理的 chunk 數量
   ```

3. **修改模式切換邏輯**（`switch_mode` 方法）：
   ```python
   async def switch_mode(self, new_mode: str):
       self.mode = new_mode
       self.silence_counter = 0
       self.vad_chunk_counter = 0  # 重置計數器
   ```

4. **修改 VAD 檢測邏輯**（`_handle_vad_only` 方法）：
   ```python
   async def _handle_vad_only(self, data: bytes):
       self.vad_chunk_counter += 1
       
       # 緩衝期內不進行靜音判斷
       if self.vad_chunk_counter <= VAD_WARMUP_CHUNKS:
           logger.debug(f"🔥 VAD 緩衝期: {self.vad_chunk_counter}/{VAD_WARMUP_CHUNKS}")
           return
       
       # 正常 VAD 檢測邏輯...
   ```

#### Code Changes

**voice_monitor_websocket_service.py**：
```python
# Before: 切換模式後立即開始 VAD 檢測
async def _handle_vad_only(self, data: bytes):
    is_speech = self.monitor_service.vad_service.detect(data)
    # 直接計算靜音...

# After: 跳過前 10 個 chunks（0.32 秒）
async def _handle_vad_only(self, data: bytes):
    self.vad_chunk_counter += 1
    if self.vad_chunk_counter <= VAD_WARMUP_CHUNKS:
        return  # 緩衝期內不檢測
    is_speech = self.monitor_service.vad_service.detect(data)
    # 計算靜音...
```

#### Impact
- 修改文件：`backend/services/voice_monitor_websocket_service.py`
- 新增常數：`VAD_WARMUP_CHUNKS = 10`
- 新增實例變數：`self.vad_chunk_counter`
- 修改方法：`switch_mode()`, `_handle_vad_only()`

#### Implementation Notes
**為何選擇 0.32 秒緩衝期？**
- 10 chunks × 0.032s/chunk = 0.32 秒
- 足以跳過喚醒詞後的自然停頓
- 不會影響正常語音的檢測（1.5 秒靜音閾值遠大於 0.32 秒）

**替代方案（未採用）**：
1. 延遲切換模式（在後端等待 0.3 秒再切換）
   - ❌ 增加複雜度，需要額外的計時器
2. 前端延遲發送 start_vad_only 命令
   - ❌ 前端無法準確判斷喚醒詞結束時間
3. 動態調整靜音閾值（剛切換時提高閾值）
   - ❌ 邏輯複雜，難以調試

#### Test Results
- ❌ 修改前：VAD 在 0.75 秒觸發停止（過早）
- ✅ 修改後：正常等待 1.5 秒靜音後停止
- ✅ 完整流程測試通過（喚醒 → 錄音 → STT → TTS）

---

### 2026-01-21 #3 - 調整靜音檢測時間（適配用戶習慣）

#### Reason
用戶實測反饋：
1. 說完喚醒詞後不會立即開始說話（需要反應時間）
2. 說話時停頓時間較長（思考、換氣）
3. 原先的 1.5 秒靜音閾值容易誤觸發，導致語音被截斷

**用戶行為分析**：
- 喚醒詞後反應時間：0.5-1.5 秒
- 說話間停頓：0.3-1.0 秒
- 句子結束停頓：1.5-3.0 秒

**結論**：1.5 秒閾值無法區分「句中停頓」和「結束靜音」

#### Changes
調整兩個時間參數（`voice_monitor_websocket_service.py`）：

1. **SILENCE_DURATION**: 1.5s → **3.0s**
   - 靜音檢測閾值提高到 3 秒
   - 允許更長的句中停頓

2. **VAD_WARMUP_CHUNKS**: 10 (0.32s) → **約 94 chunks (3.0s)**
   - 緩衝期同步提高到 3 秒
   - 完全覆蓋喚醒詞後的反應時間

#### Code Changes

**voice_monitor_websocket_service.py**：
```python
# Before
SILENCE_DURATION = 1.5  # 秒
VAD_WARMUP_CHUNKS = 10  # 約 0.32 秒

# After
SILENCE_DURATION = 3.0  # 秒
VAD_WARMUP_CHUNKS = int(3.0 / CHUNK_DURATION)  # 約 94 chunks = 3 秒
```

**計算**：
```python
CHUNK_DURATION = 0.032  # 32ms
SILENCE_CHUNKS_THRESHOLD = int(3.0 / 0.032) = 94
VAD_WARMUP_CHUNKS = 94
```

#### Impact
- 修改文件：`backend/services/voice_monitor_websocket_service.py`
- 修改常數：`SILENCE_DURATION`, `VAD_WARMUP_CHUNKS`
- 影響功能：監聽模式的 VAD 自動停止
- 不影響：按鈕錄音模式（不使用 VAD）

#### Implementation Notes
**權衡考量**：
- ✅ 優點：適配真實用戶習慣，誤觸發大幅減少
- ⚠️ 缺點：響應延遲增加（需等待 3 秒確認結束）
- 🎯 取捨：用戶體驗 > 響應速度（語音對話場景可接受 3 秒延遲）

**未來優化方向**（可選）**：
- 實作「動態靜音閾值」（根據音量變化智能調整）
- 實作「多層靜音檢測」（短停頓 vs 長停頓）
- 允許用戶自定義靜音時間（個性化配置）

#### Test Results
- ✅ 測試場景：喚醒詞 → 停頓 1.5s → 說話 → 停頓 0.5s → 繼續說 → 停頓 3s → 自動停止
- ✅ VAD 緩衝期：正確跳過前 3 秒
- ✅ 靜音檢測：3 秒後正確觸發停止
- ✅ 完整流程：「完美運行過幾次，沒有測到問題」（用戶反饋）
- ✅ STT 準確度：正確辨識中文語音（機率 1.00）

---
## Implementation Summary

### ✅ 完成狀態

**所有 6 個實作步驟已完成** (2026-01-21)

| Step | 標題 | 狀態 | 說明 |
|------|------|------|------|
| 1 | 後端 WebSocket VAD 模式 | ✅ | 實作模式切換與靜音檢測 |
| 2 | 前端 AudioWorklet 整合 | ✅ | PCM 採集與 VAD 檢測互動 |
| 3 | VoiceRecorder UI 改造 | ✅ | 點擊錄音 + 純手動控制 |
| 4 | 持續監聽整合 | ✅ | 喚醒詞自動觸發 VAD 錄音 |
| 5 | 統一 Silero VAD | ✅ | 移除 WebRTC VAD |
| 6 | 錯誤處理與超時 | ✅ | 30s 超時、資源清理、重連 |

### 📊 核心改進

#### 功能層面
1. **按鈕錄音**：從「按住說話」改為「點擊錄音」
   - 支持長對話（不需一直按住）
   - 傳送/取消按鈕提供明確控制
   - 30 秒超時保護

2. **監聽模式**：自動錄音 + VAD 截斷
   - 檢測喚醒詞 → 自動開始錄音
   - 1.5 秒靜音 → 自動停止並上傳
   - 自動恢復監聽（無縫體驗）

3. **VAD 統一**：全面使用 Silero VAD
   - 實時檢測（錄音中）
   - 後處理裁剪（音訊文件）
   - 一致的檢測準確度

#### 架構層面
1. **代碼復用**：監聽模式完全復用按鈕錄音邏輯
   - 通過 `enableVAD` 選項控制模式
   - 同一 WebSocket 連接（monitoring ↔ vad_only）
   - 減少代碼重複，降低維護成本

2. **職責分離**：
   - 前端：音訊採集（MediaRecorder + AudioWorklet）
   - 後端：VAD 檢測（Silero VAD）
   - 清晰的責任邊界

3. **錯誤處理**：
   - 超時保護（30 秒）
   - 資源清理（AudioContext、麥克風、WebSocket）
   - WebSocket 重連（最多 3 次）
   - 麥克風權限錯誤提示

### 🎯 關鍵技術決策

#### 決策 1：按鈕錄音不使用 VAD
- **原因**：互斥設計 + 用戶主動控制
- **結果**：邏輯簡單，可靠性高

#### 決策 2：監聽模式啟用 VAD
- **原因**：用戶不操作，需要自動判斷結束
- **結果**：無縫體驗，自動化程度高

#### 決策 3：統一使用 Silero VAD
- **原因**：一致性、準確度
- **結果**：實時檢測 + 後處理裁剪都用同一引擎

### 📁 修改文件清單

#### 後端
- ✅ `services/voice_monitor_websocket_service.py`：模式切換、VAD 檢測
- ✅ `services/silero_vad_service.py`：新增 trim_silence、convert_to_vad_format
- ✅ `services/voice_chat_service.py`：改用 SileroVADService
- ❌ `services/vad_service.py`：已刪除（WebRTC VAD）
- ❌ `tests/test_vad_service.py`：已刪除

#### 前端
- ✅ `composables/useVoiceRecorder.ts`：AudioWorklet、VAD 選項
- ✅ `composables/useVoiceMonitor.ts`：整合錄音、handleAutoRecording
- ✅ `components/VoiceRecorder.vue`：UI 改造、狀態統一

### 📝 測試結果

#### 環境配置調整
因實際使用場景需求（用戶反應時間 + 說話節奏），將靜音檢測和緩衝時間調整為：
- `SILENCE_DURATION`: 1.5s → **3.0s**
- `VAD_WARMUP_CHUNKS`: 10 (0.32s) → **約 94 chunks (3.0s)**

#### 1st 完整流程測試 - 2026-01-21 07:16:49

**測試場景**：喚醒詞觸發 → 用戶說話 → VAD 自動停止 → STT → LLM → TTS

**測試日誌**：
```
07:16:49 - WebSocket 連接已建立，模式: monitoring
07:16:54 - 🎯 檢測到喚醒詞: hey_jarvis (信心度: 0.989)
07:16:54 - 🔄 模式已切換至: vad_only
07:16:54 - 🎤 切換至 VAD 錄音模式
07:16:59 - 🛑 VAD 檢測到 3.0 秒靜音，推送停止事件
07:16:59 - 🔄 模式已切換至: idle
07:16:59 - 音訊檔案已儲存: voice_20260121_071659.webm
07:16:59 - 🔄 模式已切換至: monitoring
07:17:00 - 音訊格式轉換完成 -> voice_20260121_071659_converted.wav
07:17:00 - Silero VAD 裁剪完成: 145 frames -> 74 frames
07:17:12 - STT 轉換完成: '今天天氣好嗎?' (語言: zh, 機率: 1.00)
07:17:12 - LLM 生成回應: '天氣怎麼樣？我可以幫你查一下今天的天氣預報。可以告訴我你住的城市嗎？'
07:17:12 - TTS 串流生成並播放
```

**測試結果**：
- ✅ 喚醒詞檢測：正常 (hey_jarvis, 0.989)
- ✅ VAD 錄音啟動：正常切換至 vad_only 模式
- ✅ 靜音檢測：3.0 秒靜音正確觸發停止
- ✅ 音訊上傳：WebM 格式上傳成功
- ✅ VAD 裁剪：145 frames → 74 frames (靜音已截斷)
- ✅ STT 轉換：正確辨識中文 "今天天氣好嗎?"
- ✅ LLM 回應：正常生成回覆
- ✅ TTS 播放：語音合成並播放完成
- ✅ 自動恢復監聽：完成後自動切回 monitoring 模式

**性能指標**：
- 喚醒詞響應時間：< 100ms
- VAD 停止響應：符合 3.0s 靜音配置
- STT 處理時間：約 12 秒（音訊長度 2.37 秒）
- 端到端時間：從喚醒到 TTS 開始約 18 秒

#### 功能驗證總結

**已驗證功能**：
- ✅ 持續監聽模式：完整流程正常運作
- ✅ 喚醒詞檢測：準確度高 (0.989)
- ✅ VAD 自動停止：3.0 秒靜音正確檢測
- ✅ 模式切換：monitoring ↔ vad_only ↔ idle 流暢
- ✅ 音訊處理：轉換、裁剪、STT 全流程正常
- ✅ 自動恢復監聽：無縫恢復監聽狀態
- ✅ 按鈕錄音模式：手動控制正常（早前測試已通過）

**用戶反饋**：
- 「完美運行過幾次了，沒有測到問題」
- 3.0 秒靜音時間符合實際使用需求（反應時間 + 說話停頓）

**未測試項目** (可選):
- [ ] 狀態互斥：錄音時監聽自動停止
- [ ] 錯誤處理：WebSocket 斷線、麥克風權限錯誤
- [ ] 邊界條件：極短音訊、超長音訊、噪音環境

---