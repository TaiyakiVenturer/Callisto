# SPEC: 語音喚醒功能 - 前端實現

> **狀態**: 🚧 進行中 (50% - Steps 5-6 完成)  
> **後端狀態**: ✅ 已完成

---

## 📑 導航

- **🏠 [返回總覽](./SPEC-voice-wake-word-overview.md)** - 查看完整專案進度
- **📘 [後端規格](./SPEC-voice-wake-word-backend.md)** - Steps 1-4（已完成）

---

## Task Description

本規格描述語音喚醒功能的前端實現部分（Steps 5-10），包括 Vue 3 Composable、UI 整合、測試與文件。

**前端核心功能**：
- ~~使用 MediaRecorder API 錄製麥克風音訊（16kHz 單聲道）~~
- **使用 AudioContext + ScriptProcessor 處理原始 PCM 音訊**（MediaRecorder 無法提供 PCM 格式）
- 通過 WebSocket 即時傳輸音訊到後端（int16 PCM binary）
- 接收並顯示後端檢測事件（監聽中、檢測到語音、喚醒詞）
- 整合現有的語音對話流程

---

## Tech Stack

- **Vue 3** - UI 框架
- **TypeScript** - 類型安全
- **Composition API** - 邏輯封裝
- **AudioContext + ScriptProcessor** - 原始音訊處理（取代 MediaRecorder）
- **WebSocket** - 即時通信
- **Vitest** (可選) - 單元測試

---

## Target Files

### 前端
- **新增**：
  - `frontend/src/types/voice.ts` - 類型定義 ✅
  - `frontend/src/composables/useVoiceMonitor.ts` - 語音監聽 Composable ✅
- **修改**：
  - `frontend/src/components/VoiceRecorder.vue` - 新增監聽按鈕和狀態顯示 ✅
- **測試** (可選)：
  - `frontend/__tests__/useVoiceMonitor.spec.ts`

---

## Implementation

<a id="step5"></a>
### [x] Step 5. 前端 Composable 實現
**Goal**: 封裝語音監聽邏輯為可複用的 Composable

**Reason**: 分離業務邏輯和 UI，提高程式碼可維護性和可測試性

**Implementation Details**: (已完成)
- 創建 `frontend/src/types/voice.ts`：
  - `MonitorStatus` enum（9 種狀態）
  - `BackendEvent` interface（所有後端事件類型）
  - `VoiceMonitorConfig` interface（配置選項）
- 創建 `frontend/src/composables/useVoiceMonitor.ts`：
  - **WebSocket 連接管理**：
    * 自動重連機制（最多 3 次）
    * 心跳檢測（30s 超時）
    * 斷線自動清理資源
  - **AudioContext 音訊處理**（現代化架構）：
    * ~~MediaRecorder~~ → ~~ScriptProcessor~~ → **AudioWorkletNode**
    * 原因：ScriptProcessorNode 已淘汰，使用現代 Web Audio API
    * 採樣率: 16kHz 單聲道
    * 音訊處理: 獨立 worklet 線程（`audio-processor.js`）
    * 批次發送: 累積 512 samples（32ms）後發送
    * 軟體 AGC: 2.0x 增益（彌補麥克風音量不足）
  - **後端事件處理**：connected, keyword, speech, error 等
  - **響應式狀態管理**：isMonitoring, status, error, lastKeyword, transcript, aiResponse
  - **錯誤處理**：麥克風權限、連接失敗、網路斷線
- 創建 `frontend/public/audio-processor.js`：
  - **AudioWorklet Processor**（音訊處理 worklet）
  - **功能**：
    * 接收瀏覽器音訊流（128 samples @ 16kHz, 每 8ms）
    * 軟體 AGC：2.0x 增益放大（可調整）
    * 累積 buffer：累積到 512 samples 才發送
    * Float32 → int16 PCM 轉換
    * 通過 `port.postMessage()` 發送到主線程
  - **為什麼放在 public/**：
    * AudioWorklet 只能加載 URL 路徑（靜態資源）
    * 無法像普通模組 import
  - **為什麼用 JS 不是 TS**：
    * AudioWorklet 運行在獨立 worklet scope
    * 無 TypeScript 運行時，只能執行原生 JS
- 實現功能：
  - `startMonitoring()` - 開始監聽
    * 請求麥克風權限：`navigator.mediaDevices.getUserMedia()`
      - 啟用瀏覽器內建 AGC、降噪、回音消除
    * 連接 WebSocket：`ws://localhost:8000/ws/voice-monitor`
    * 啟動 AudioWorklet：
      - 加載 `/audio-processor.js`
      - 創建 AudioWorkletNode
      - 監聽 `port.onmessage` 接收處理後的音訊
      - 通過 WebSocket 發送 PCM binary data
  - `stopMonitoring()` - 停止監聽
    * 停止 AudioWorklet
    * 關閉 WebSocket 連接
    * 釋放麥克風資源
  - `handleBackendEvent(event)` - 處理後端推送的事件
    * 解析 JSON 事件
    * 更新狀態：idle / listening / speech / keyword / processing / speaking / error
    * KEYWORD 狀態鎖定 3 秒（防止被 speech 覆蓋）
- **Reactive 狀態**：
  - `isMonitoring: Ref<boolean>` - 是否正在監聽
  - `status: Ref<MonitorStatus>` - 當前狀態
  - `error: Ref<string | null>` - 錯誤訊息
  - `lastKeyword: Ref<string | null>` - 最後檢測到的喚醒詞
- **錯誤處理**：
  - 麥克風權限被拒：顯示友好提示
  - WebSocket 連接失敗：自動重連（最多 3 次）
  - 網路斷線：顯示錯誤並停止監聽
- **類型定義**：
  ```typescript
  enum MonitorStatus {
    IDLE = 'idle',
    CONNECTING = 'connecting',
    LISTENING = 'listening',
    SPEECH = 'speech',
    KEYWORD = 'keyword',
    PROCESSING = 'processing',
    SPEAKING = 'speaking',
    ERROR = 'error'
  }
  
  interface BackendEvent {
    type: 'connected' | 'keyword' | 'speech' | 'error';
    timestamp?: number;
    keyword?: string;
    confidence?: number;
    duration?: number;
    message?: string;
  }
  ```

---

<a id="step6"></a>
### [x] Step 6. 前端 UI 整合
**Goal**: 在 VoiceRecorder 元件中新增監聽按鈕和狀態顯示

**Reason**: 提供用戶友好的操作界面，清晰展示當前狀態

**Implementation Details**: (已完成)
- 修改 `frontend/src/components/VoiceRecorder.vue`：
  - **新增 UI 元素**：
    * 「開始監聽」/「停止監聽」切換按鈕
    * 狀態指示器（綠/黃/紫/藍/紅色圓點）
    * 狀態文字描述
    * 對話內容顯示（轉錄文字 + AI 回應）
  - **互斥邏輯**：
    * 監聽模式啟動時禁用「按住說話」按鈕
    * 「按住說話」使用時禁用「開始監聽」按鈕
  - **CSS 動畫**：
    * 脈動動畫（監聽中）
    * 閃爍動畫（檢測到喚醒詞）
    * 平滑的狀態過渡效果

---

<a id="step7"></a>
### [ ] Step 7. 語音對話流程整合
**Goal**: 整合 STT → LLM → TTS 完整流程，並推送進度事件

**Reason**: 檢測到喚醒詞後需要自動處理用戶命令並給出回應

**Implementation Details**:
    message?: string;
  }
  ```

---

<a id="step6"></a>
### [ ] Step 6. 前端 UI 整合
**Goal**: 在 VoiceRecorder 元件中新增監聽按鈕和狀態顯示

**Reason**: 提供用戶友好的操作界面，清晰展示當前狀態

**Implementation Details**:
- 修改 `frontend/src/components/VoiceRecorder.vue`
- **新增 UI 元素**：
  - 「開始監聽」切換按鈕
    * 設計：圓形按鈕，麥克風圖標
    * 狀態變化：idle → listening (顏色、圖標變化)
    * 位置：在「按住說話」按鈕旁邊
  - **狀態指示器**：
    * 🟢 監聽中 (listening) - 綠色脈動動畫
    * 🟡 檢測到語音 (speech) - 黃色
    * 🟣 檢測到喚醒詞 (keyword) - 紫色閃爍
    * 🔵 處理中 (processing) - 藍色旋轉
    * 🔴 錯誤 (error) - 紅色 + 錯誤訊息
  - **狀態文字**：顯示當前狀態描述
- **使用 Composable**：
  ```vue
  <script setup lang="ts">
  import { useVoiceMonitor } from '@/composables/useVoiceMonitor'
  
  const { isMonitoring, status, error, startMonitoring, stopMonitoring } = useVoiceMonitor()
  
  const toggleMonitoring = () => {
    if (isMonitoring.value) {
      stopMonitoring()
    } else {
      startMonitoring()
    }
  }
  </script>
  ```
- **互斥邏輯**：
  - 監聽模式啟動時：
    * 禁用「按住說話」按鈕
    * 按鈕顯示禁用樣式 + tooltip 說明
  - 「按住說話」使用時：
    * 禁用「開始監聽」按鈕
- **樣式設計**：
  - 按鈕狀態清晰，顏色區分不同狀態
  - 脈動動畫表示正在監聽
  - 平滑的狀態過渡動畫

---

<a id="step7"></a>
### [ ] Step 7. 語音對話流程整合
**Goal**: 整合 STT → LLM → TTS 完整流程，並推送進度事件

**Reason**: 檢測到喚醒詞後需要自動處理用戶命令並給出回應

**Implementation Details**:

#### 後端修改：
- 修改 `backend/services/voice_chat_service.py`：
  - `process_voice()` 新增參數 `websocket: Optional[WebSocket] = None`
  - 在各個步驟完成時推送事件：
    ```python
    if websocket:
        await websocket.send_json({"type": "transcribing"})
        await websocket.send_json({"type": "transcript", "text": text})
        await websocket.send_json({"type": "generating"})
        await websocket.send_json({"type": "response", "text": response})
        await websocket.send_json({"type": "speaking"})
        await websocket.send_json({"type": "done"})
    ```

#### WebSocket 端點修改：
- 修改 `backend/api_server.py` 中的 `/ws/voice-monitor`：
  - 檢測到喚醒詞後的處理流程：
    1. 推送 `{"type": "keyword", "keyword": "..."}` 事件
    2. 切換到「命令接收模式」
    3. 繼續接收音訊直到 VAD 檢測靜音持續 > 1.5 秒
    4. 將累積的音訊保存為 WAV 檔案
    5. 調用 `voice_service.process_voice(audio_path, websocket)`
    6. STT/LLM/TTS 進度事件自動推送給前端
    7. 完成後自動恢復監聽模式

#### 前端修改：
- 擴展 `useVoiceMonitor.ts`：
  - 新增事件處理：
    * `transcribing` → 更新狀態為 "正在轉錄..."
    * `transcript` → 顯示轉錄文字
    * `generating` → 更新狀態為 "AI 思考中..."
    * `response` → 顯示 AI 回應文字
    * `speaking` → 更新狀態為 "播放回應中..."
    * `done` → 恢復監聽狀態
- 修改 UI 顯示：
  - 顯示對話內容（用戶問題 + AI 回應）
  - 顯示處理進度條或載入動畫

#### 錯誤處理：
- STT/LLM/TTS 失敗時推送錯誤事件
- 超時處理（30 秒無回應）
- 自動恢復監聽模式

---

<a id="step8"></a>
### [ ] Step 8. 單元測試實現
**Goal**: 為前端核心邏輯編寫單元測試

**Reason**: 確保前端功能正確，提供回歸測試保障

**Implementation Details**:
- 創建 `frontend/__tests__/useVoiceMonitor.spec.ts`
- 使用 Vitest + Vue Test Utils
- **測試案例**：
  1. **初始化測試**：
     - `test_initialization` - Composable 初始化狀態
     - `test_default_values` - 預設值正確
  
  2. **監聽控制測試**：
     - `test_start_monitoring_success` - 成功開始監聽
     - `test_start_monitoring_no_permission` - 麥克風權限被拒
     - `test_stop_monitoring` - 正確停止監聽
     - `test_stop_before_start` - 停止前未開始
  
  3. **WebSocket 測試**：
     - `test_websocket_connection` - WebSocket 連接
     - `test_websocket_disconnect` - WebSocket 斷開
     - `test_websocket_reconnect` - 自動重連機制
  
  4. **事件處理測試**：
     - `test_handle_connected_event` - 處理 connected 事件
     - `test_handle_keyword_event` - 處理 keyword 事件
     - `test_handle_speech_event` - 處理 speech 事件
     - `test_handle_error_event` - 處理 error 事件
  
  5. **狀態管理測試**：
     - `test_status_transitions` - 狀態轉換正確
     - `test_error_state_handling` - 錯誤狀態處理

- **Mock 策略**：
  - Mock `navigator.mediaDevices.getUserMedia()`
  - Mock `WebSocket` API
  - Mock `MediaRecorder` API
  
- **測試工具**：
  ```bash
  # 安裝測試依賴
  pnpm add -D vitest @vue/test-utils jsdom
  
  # 執行測試
  pnpm test
  ```

---

<a id="step9"></a>
### [ ] Step 9. 整合測試與除錯
**Goal**: 完整流程測試，確保前後端協同工作

**Reason**: 單元測試無法覆蓋模組間的互動，需要端到端測試

**Implementation Details**:

#### 自動化測試（可選）：
- 使用 Playwright 或 Cypress 進行 E2E 測試
- 測試完整流程：
  1. 啟動前端應用
  2. 點擊「開始監聽」
  3. 模擬音訊輸入（使用錄製的音訊檔案）
  4. 驗證狀態變化和事件推送
  5. 驗證最終回應

#### 手動測試清單：
1. **基礎流程**：
   - [ ] 啟動前後端服務
   - [ ] 點擊「開始監聽」按鈕
   - [ ] 確認狀態變為「監聽中」
   - [ ] 說「嘿 Jarvis」（當前使用的喚醒詞）
   - [ ] 確認狀態變為「檢測到喚醒詞」
   - [ ] 繼續說一個問題
   - [ ] 驗證：STT → LLM → TTS → 恢復監聽
   - [ ] 確認對話內容正確顯示

2. **邊界情況**：
   - [ ] 連續多次喚醒（不停止監聽）
   - [ ] 環境噪音干擾測試
   - [ ] 快速說話 / 輕聲說話
   - [ ] 說話中間長時間暫停
   - [ ] 喚醒後不說話（超時處理）

3. **錯誤處理**：
   - [ ] 拒絕麥克風權限 → 顯示錯誤提示
   - [ ] 後端服務未啟動 → WebSocket 連接失敗提示
   - [ ] 監聽中斷開網路 → 自動停止並顯示錯誤
   - [ ] 後端服務異常 → 接收 error 事件並顯示

4. **UI/UX 測試**：
   - [ ] 狀態指示器正確顯示和變化
   - [ ] 按鈕互斥邏輯正確
   - [ ] 動畫流暢，無卡頓
   - [ ] 錯誤訊息清晰易懂
   - [ ] 響應式設計（不同螢幕尺寸）

5. **效能測試**：
   - [ ] 長時間監聽（1 小時）- 無記憶體洩漏
   - [ ] CPU 使用率合理（前端 < 15%）
   - [ ] 網路頻寬使用（約 32-50 KB/s）
   - [ ] 檢測延遲 < 500ms

6. **相容性測試**：
   - [ ] Chrome（最新版本）
   - [ ] Edge（最新版本）
   - [ ] Firefox（最新版本）
   - [ ] Safari（macOS，如果可用）
   - [ ] Windows 10/11
   - [ ] macOS（如果可用）

#### 除錯工具：
- 瀏覽器開發者工具
  - Console：查看日誌和錯誤
  - Network：監控 WebSocket 通信
  - Performance：分析效能瓶頸
- Vue Devtools：檢查元件狀態和事件
- 後端日誌：查看 VAD/KWS 檢測記錄

---

<a id="step10"></a>
### [ ] Step 10. 文件撰寫
**Goal**: 更新技術文件和使用說明

**Reason**: 為後續維護和用戶提供參考

**Implementation Details**:

#### 更新 `backend/README_API.md`：
- 新增 WebSocket 端點說明：
  ```markdown
  ## WebSocket 端點

  ### WS /ws/voice-monitor
  
  語音監聽 WebSocket 端點，用於即時音訊傳輸和事件推送。
  
  **連接**：
  - URL: `ws://localhost:8000/ws/voice-monitor`
  - 協議：WebSocket
  
  **接收資料格式**：
  - 類型：binary frames
  - 音訊格式：int16 PCM, 16kHz, mono
  - 發送頻率：每 80-100ms 一個 chunk
  
  **發送事件格式**：JSON
  
  | 事件類型 | 欄位 | 說明 |
  |---------|------|------|
  | connected | timestamp, message | 連接成功 |
  | keyword | keyword, confidence, timestamp | 檢測到喚醒詞 |
  | speech | duration, timestamp | 檢測到語音 |
  | error | message | 錯誤訊息 |
  | transcribing | - | STT 進行中 |
  | transcript | text | 轉錄結果 |
  | generating | - | LLM 生成中 |
  | response | text | LLM 回應 |
  | speaking | - | TTS 播放中 |
  | done | - | 流程完成 |
  ```

#### 更新 `frontend/README.md`：
- 新增語音喚醒功能說明：
  ```markdown
  ## 語音喚醒功能
  
  ### 使用方式
  
  1. **開始監聽**：
     - 點擊「開始監聽」按鈕
     - 授予麥克風權限
     - 狀態指示器變為綠色「監聽中」
  
  2. **喚醒助理**：
     - 說出喚醒詞：「嘿 Jarvis」
     - 狀態指示器變為紫色「檢測到喚醒詞」
  
  3. **提問**：
     - 繼續說出你的問題
     - 系統會自動處理：轉錄 → AI 回應 → 語音播放
  
  4. **停止監聽**：
     - 點擊「停止監聽」按鈕
     - 或等待流程完成後自動恢復監聽
  
  ### 模式對比
  
  | 特性 | 模式 A：按住說話 | 模式 B：語音喚醒 |
  |------|----------------|----------------|
  | 操作方式 | 按住按鈕說話 | 說出喚醒詞 |
  | 持續監聽 | ❌ | ✅ |
  | 自動啟動 | ❌ | ✅ |
  | 延遲 | 低 | 極低 (<500ms) |
  | 適用場景 | 快速提問 | 免手操作 |
  
  ### 狀態指示器
  
  - 🟢 **監聽中**：系統正在監聽，等待喚醒詞
  - 🟡 **檢測到語音**：檢測到人聲，但不是喚醒詞
  - 🟣 **檢測到喚醒詞**：準備接收你的問題
  - 🔵 **處理中**：正在處理你的問題（STT/LLM/TTS）
  - 🔴 **錯誤**：發生錯誤，請檢查錯誤訊息
  
  ### 常見問題 FAQ
  
  **Q: 喚醒詞是什麼？**  
  A: 當前使用「嘿 Jarvis」。未來會支援自定義「嘿 Callisto」。
  
  **Q: 為什麼一直顯示「監聽中」但沒反應？**  
  A: 請確認：
  - 麥克風權限已授予
  - 後端服務正在運行
  - WebSocket 連接成功（檢查 Console）
  
  **Q: 可以同時使用兩種模式嗎？**  
  A: 不可以。兩種模式互斥，使用一種時另一種會被禁用。
  
  **Q: 喚醒詞檢測不準確怎麼辦？**  
  A: 請嘗試：
  - 提高音量，清晰發音
  - 減少環境噪音
  - 調整麥克風位置
  ```

#### 新增架構圖（可選）：
- 語音監聽流程圖（已在總覽中）
- WebSocket 通信時序圖
- 前端狀態機圖

---

## 進度追蹤

| 步驟 | 狀態 | 預計時間 | 實際時間 | 完成日期 |
|------|------|---------|---------|----------|
| Step 5 - 前端 Composable | ✅ | 1-2 小時 | ~2.5 小時 | 2026-01-20 |
| Step 6 - 前端 UI 整合 | ✅ | 1-2 小時 | ~1 小時 | 2026-01-20 |
| Step 7 - 對話流程整合 | ⏳ | 2-3 小時 | - | - |
| Step 8 - 單元測試 | ⏳ | 2-3 小時 | - | - |
| Step 9 - 整合測試 | ⏳ | 2-3 小時 | - | - |
| Step 10 - 文件撰寫 | ⏳ | 1-2 小時 | - | - |

**總預計時間**: 9-15 小時  
**已完成時間**: ~3.5 小時

---

## Spec Amendments

### 2026-01-20 - 音訊格式與模型限制修正

#### Reason
實測發現 Silero VAD ONNX 模型對音訊塊大小有嚴格限制，且前端 MediaRecorder 無法直接產生 PCM 格式。

#### Changes
1. **前端音訊處理方式**：
   - 原方案：MediaRecorder (WebM/Opus) → 發現無法轉 PCM
   - 新方案：AudioContext + ScriptProcessor → 直接處理原始音訊

2. **音訊塊大小限制**：
   - 測試發現：512 samples ✅, 1024 samples ❌, 2048 samples ❌
   - 模型錯誤：`Input X must have 3 dimensions only. Actual:{1,1,1,128,N}`
   - 結論：Silero VAD ONNX 模型**只支援 512 samples 固定長度**
   - 前端 bufferSize：2048 → **512 samples**
   - 音訊塊時長：128ms → **32ms**

3. **日誌級別調整**：
   - VAD 服務調試日誌從 INFO 改回 DEBUG，減少輸出干擾

#### Code Changes

**Frontend - useVoiceMonitor.ts**:
```typescript
// Before: MediaRecorder
const mediaRecorder = new MediaRecorder(mediaStream, { 
  mimeType: 'audio/webm;codecs=opus' 
})

// After: AudioContext + ScriptProcessor
const audioContext = new AudioContext({ sampleRate: 16000 })
const processor = audioContext.createScriptProcessor(512, 1, 1) // 固定 512
processor.onaudioprocess = (e) => {
  const inputData = e.inputBuffer.getChannelData(0)
  const int16Data = new Int16Array(inputData.length)
  // Float32 → int16 轉換
  for (let i = 0; i < inputData.length; i++) {
    const s = Math.max(-1, Math.min(1, inputData[i]))
    int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
  }
  websocket.send(int16Data.buffer) // 發送 binary PCM
}
```

**Backend - silero_vad_service.py**:
```python
# 音訊長度檢查更新
if len(audio_float32) < 512:
    logger.warning(f"音訊塊過短 ({len(audio_float32)} samples)，建議至少 512 samples")
    return False

# 模型只支援 512 samples（註解更新）
# Silero VAD ONNX 模型要求固定 512 samples
```

#### Impact
- 修改文件：
  - `frontend/src/composables/useVoiceMonitor.ts`
  - `backend/services/silero_vad_service.py`
- 受影響功能：音訊即時檢測（延遲降低，響應更快）
- 優點：
  - 延遲從 128ms 降低到 32ms
  - 消除音訊格式轉換問題
  - 符合模型要求，避免 ONNX 錯誤

#### Test Results
- WebSocket 連接：✅ 成功
- 音訊傳輸：✅ 正常（512 samples/chunk）
- VAD 檢測：✅ 無錯誤（修正後）
- 前端 UI：✅ 狀態顯示正常

---

### 2026-01-20 (3) - 後端日誌緩衝與 WebSocket 延遲修正

#### Reason
用戶報告兩個即時性問題：
1. 後端日誌沒有即時輸出（日誌出現時間與用戶操作不符）
2. WebSocket 關閉延遲過高（從最後檢測到關閉花費 22 秒）

這兩個問題導致無法準確評估系統響應速度，影響語音互動體驗。

#### Changes
1. **Python 日誌強制即時輸出**：
   - 設定 `logging.basicConfig(stream=sys.stdout, force=True)`
   - 啟用行緩衝：`handler.stream.reconfigure(line_buffering=True)`
   - 移除所有手動 `sys.stdout.flush()`（已無需要）

2. **前端時間戳記錄**（已完成）：
   - `startMonitoring()`：顯示 `[HH:MM:SS.mmm] ===== 開始監聽 =====`
   - `stopMonitoring()`：顯示 `[HH:MM:SS.mmm] ===== 停止監聽 =====`
   - 方便對比前後端時間差異

3. **WebSocket 超時優化**（已完成）：
   - 從 5 秒降低到 0.1 秒（100ms）
   - 提高關閉響應速度

#### Code Changes

**Before** (api_server.py):
```python
# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
```

**After** (api_server.py):
```python
# 設定日誌 - 強制即時輸出（無緩衝）
import sys
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
    force=True
)
# 禁用日誌緩衝
for handler in logging.root.handlers:
    handler.setStream(sys.stdout)
    if hasattr(handler.stream, 'reconfigure'):
        handler.stream.reconfigure(line_buffering=True)
        
logger = logging.getLogger(__name__)
```

#### Impact
- 修改文件：
  - `backend/api_server.py`（日誌配置）
  - `frontend/src/composables/useVoiceMonitor.ts`（時間戳，已完成）
- 受影響功能：所有後端日誌輸出
- 效果：
  - 日誌即時顯示（無延遲）
  - WebSocket 響應更快（100ms 超時）
  - 可準確測量系統延遲

#### Implementation Notes
**為什麼需要 `force=True`？**
- Python 預設日誌可能被其他模組設定覆蓋
- `force=True` 強制移除舊 handler 並重新設定

**為什麼需要 `line_buffering=True`？**
- Python 預設使用 block buffering（等待緩衝區滿才輸出）
- `line_buffering=True` 改為行緩衝（每行立即輸出）
- Windows/Linux 通用（比 `PYTHONUNBUFFERED=1` 更可靠）

**為什麼移除 `sys.stdout.flush()`？**
- 啟用行緩衝後，每個 `logger.info()` 自動觸發 flush
- 不再需要手動刷新

#### Test Results
⏳ **待測試**（需要用戶重啟後端並驗證）

**測試步驟**：
1. 重啟後端：`uv run api_server.py`
2. 前端點擊「開始監聽」
3. 說出 "hey jarvis"
4. 觀察前端 console 時間戳
5. 觀察後端日誌出現時間
6. 點擊「停止監聽」
7. 測量 WebSocket 關閉延遲

**預期結果**：
- 後端日誌即時出現（與前端時間差 <1 秒）
- WebSocket 關閉延遲 <1 秒（不再是 22 秒）

**測試結果**（2026-01-20）：
- ⏳ **日誌延遲**：已修復配置，待用戶重啟驗證
- ⏳ **WebSocket 延遲**：新增客戶端狀態檢測，待驗證
- ❌ **Cooldown 未生效**：用戶尚未重啟後端，舊代碼仍在運行

**後續修復**：
- 添加 `websocket.client_state.name == 'DISCONNECTED'` 檢查
- 移除不必要的 `sys.stdout.flush()`（已配置行緩衝）

---
| Step 8 - 單元測試 | ⏳ | 2-3 小時 | - | - |
| Step 9 - 整合測試 | ⏳ | 2-3 小時 | - | - |
| Step 10 - 文件撰寫 | ⏳ | 1-2 小時 | - | - |

**總預計時間**: 9-15 小時

---

### 2026-01-20 (4) - 喚醒詞重複檢測問題（冷卻期機制）

#### Reason
用戶報告：說一次 "hey jarvis" 後端檢測到 3 次觸發（85ms 內）：
1. `05:42:40,048` - 信心度 0.896，VAD 0.987 ✅
2. `05:42:40,083` - 信心度 0.996，VAD 0.002 ❌（被過濾）
3. `05:42:40,133` - 信心度 0.998，VAD 0.000 ❌（被過濾）

原因：openWakeWord 對連續的音訊塊（每 32ms 一個）都會輸出高信心度，導致「一次語音 → 多次觸發」問題。雖然後 2 次被 VAD 過濾，但會產生大量日誌和不必要的處理。

#### Changes
**添加檢測冷卻期（Cooldown）機制**：
- 成功檢測喚醒詞後，啟動 1.5 秒冷卻期
- 冷卻期內的檢測直接忽略（返回 silence 事件）
- 新增統計項：`cooldown_ignored`（冷卻期內被忽略的檢測次數）

#### Code Changes

**Before** (audio_monitor_service.py):
```python
# 狀態追蹤
self.current_state = MonitorState.IDLE
self.last_event_time = time.time()
self.speech_start_time: Optional[float] = None

# 統計資訊
self.stats = {
    "total_chunks": 0,
    "speech_chunks": 0,
    "silence_chunks": 0,
    "keyword_detections": 0,
    "false_alarms": 0
}
```

**After** (audio_monitor_service.py):
```python
# 狀態追蹤
self.current_state = MonitorState.IDLE
self.last_event_time = time.time()
self.speech_start_time: Optional[float] = None

# 喚醒詞檢測冷卻期（避免短時間內重複觸發）
self.keyword_cooldown = 1.5  # 秒
self.last_keyword_time: Optional[float] = None

# 統計資訊
self.stats = {
    "total_chunks": 0,
    "speech_chunks": 0,
    "silence_chunks": 0,
    "keyword_detections": 0,
    "false_alarms": 0,
    "cooldown_ignored": 0  # 冷卻期內被忽略的檢測
}
```

**協調檢測邏輯**：
```python
# 情況 1: KWS 檢測到喚醒詞
if detected_keyword:
    # 檢查冷卻期（避免同一次語音重複觸發）
    if self.last_keyword_time and (current_time - self.last_keyword_time) < self.keyword_cooldown:
        time_since_last = current_time - self.last_keyword_time
        self.stats["cooldown_ignored"] += 1
        logger.debug(
            f"🕐 喚醒詞 '{detected_keyword}' 在冷卻期內 "
            f"({time_since_last:.2f}s < {self.keyword_cooldown}s)，忽略"
        )
        # 返回靜音事件（不觸發）
        self.stats["silence_chunks"] += 1
        return {"event": "silence"}
    
    # 不在冷卻期，繼續處理...
    # 成功檢測時記錄時間：
    self.last_keyword_time = current_time
```

#### Impact
- 修改文件：`backend/services/audio_monitor_service.py`
- 受影響功能：喚醒詞檢測流程
- 效果：
  - ✅ 避免同一次語音重複觸發（減少日誌噪音）
  - ✅ 降低不必要的處理開銷
  - ✅ 用戶體驗更自然（不會連續收到多次 keyword 事件）

#### Implementation Notes
**為什麼選擇 1.5 秒？**
- 一次完整的 "hey jarvis" 發音約 0.5-1.0 秒
- 加上餘音和緩衝，1.5 秒足夠涵蓋整個語音過程
- 不影響用戶快速連續喚醒（間隔 >1.5s）

**冷卻期與 VAD 過濾的區別**：
- VAD 過濾：檢查是否為真實語音（防止噪音誤觸發）
- 冷卻期：防止同一次語音重複檢測（時間維度）
- 兩者互補，共同提升檢測準確性

**何時重置冷卻期？**
- 每次 `reset()` 時重置（新連接開始）
- 冷卻期自動過期（1.5 秒後）
- 不需要手動清除

#### Test Results
⏳ **待測試**（需要用戶重啟後端並驗證）

**測試步驟**：
1. 重啟後端：`uv run api_server.py`
2. 前端點擊「開始監聽」
3. 說出 "hey jarvis"
4. 觀察後端日誌

**預期結果**：
- 只觸發 1 次 `🎯 喚醒詞檢測成功`
- 後續 85ms 內的重複檢測應該出現：`🕐 喚醒詞 'hey_jarvis' 在冷卻期內 (0.03s < 1.5s)，忽略`
- 統計資訊：`cooldown_ignored` 應該 > 0

---

## 快速連結

- 🏠 [返回總覽](./SPEC-voice-wake-word-overview.md)
- 📘 [後端規格](./SPEC-voice-wake-word-backend.md) - 已完成
- 📗 當前：前端規格

---

**建立日期**: 2026-01-20  
**最後更新**: 2026-01-20  
**當前狀態**: 待開始
