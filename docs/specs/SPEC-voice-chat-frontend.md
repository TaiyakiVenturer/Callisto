# SPEC: 語音對話前端介面

## Task Description

實作 Vue + TypeScript 前端介面，與後端 STT/TTS API 整合，提供按住錄音的語音對話體驗。使用 Lofi 可愛暗色系風格，左側大 PNG 動畫主體配合右側對話記錄框。

### 核心目標
- 按住按鈕錄音，放開自動上傳
- 即時顯示對話狀態（待機/思考/說話）
- PNG 圖片根據狀態切換（說話時兩張 PNG 以 250ms 間隔交替）
- 說話時 PNG 上下漂浮動畫 + 背後聚光燈效果
- 右側對話記錄框顯示 STT 文字和 AI 回應
- Lofi 可愛暗色系 UI 風格

### 使用場景
1. 使用者開啟頁面，看到待機狀態的 Callisto
2. 按住錄音按鈕說話（PNG 切換到思考狀態）
3. 放開按鈕，音訊上傳並保持「思考中」
4. 後端處理完成後切換到「說話」狀態
5. 說話狀態：PNG 上下漂浮 + 背後聚光燈 + 兩張圖 250ms 交替
6. 播放完成後恢復待機狀態
7. 對話記錄顯示在右側框內

## Tech Stack

### 前端框架
- **Vue 3** - Composition API + `<script setup>`
- **TypeScript** - 型別安全
- **Pinia** - 狀態管理（對話記錄、當前狀態）
- **Vue Router** - 路由管理（可能未來擴展）

### 錄音技術
- **MediaRecorder API** - 瀏覽器原生錄音
  - 輸出格式：`audio/webm` (Chrome/Edge)
  - 後端自動轉換，無需前端處理

### HTTP 請求
- **Fetch API** - 原生 HTTP 請求
  - POST `/api/chat/voice` - 上傳音訊
  - GET `/api/status` - 輪詢狀態（500ms 間隔）

### UI 樣式
- **原生 CSS** - 自訂 Lofi 暗色系風格
  - 主色調：深藍灰 (#1a1a2e)
  - 強調色：淡紫粉 (#eebbc3), 淡藍 (#a8d8ea)
  - 文字色：淺灰白 (#e0e0e0)

### 音訊播放（選用）
- 後端直接播放，前端不需要處理音訊

## Acceptance Criteria

### 錄音功能
- [ ] 按住按鈕開始錄音（滑鼠/觸控支援）
- [ ] 放開按鈕停止錄音並自動上傳
- [ ] 錄音時顯示視覺回饋（按鈕狀態變化）
- [ ] 麥克風權限請求處理完善

### 狀態管理
- [ ] 三種狀態正確切換：idle → thinking → speaking → idle
- [ ] PNG 圖片根據狀態切換
- [ ] 說話狀態時兩張 PNG 以 250ms 間隔交替顯示
- [ ] 說話狀態時 PNG 上下漂浮動畫（持續）
- [ ] 說話狀態時背後顯示聚光燈效果（放射狀光暈）
- [ ] 輪詢 `/api/status` 直到 `is_done = true`

### UI 佈局
- [ ] 左側 70% 顯示大 PNG 主體 + 下方按鈕
- [ ] 右側 30% 顯示對話記錄框（可滾動）
- [ ] 對話記錄以聊天泡泡形式呈現（使用者/AI 分左右）
- [ ] 響應式設計（至少支援桌面版）

### 對話記錄
- [ ] 顯示使用者語音轉文字結果
- [ ] 顯示 AI 回應文字
- [ ] 自動滾動到最新訊息
- [ ] 刷新頁面後清空記錄（不持久化）

### 錯誤處理
- [ ] 麥克風權限被拒絕時顯示提示
- [ ] 網路錯誤時顯示錯誤訊息
- [ ] 後端錯誤時顯示友善提示
- [ ] 處理中時禁止重複錄音

### 風格與動畫
- [ ] Lofi 可愛暗色系風格
- [ ] PNG 切換有平滑淡入淡出效果（0.3s）
- [ ] 說話時 PNG 上下漂浮動畫（translate Y 方向 ±20px，2s 循環）
- [ ] 說話時背後聚光燈效果（radial-gradient 放射光暈，呼吸動畫）
- [ ] 按鈕 hover/active 狀態動畫
- [ ] 對話泡泡淡入動畫

## Target Files

### 新增檔案
- **主要**：`frontend/src/views/VoiceChatView.vue` - 主頁面元件
- **主要**：`frontend/src/components/VoiceRecorder.vue` - 錄音按鈕元件
- **主要**：`frontend/src/components/CharacterDisplay.vue` - PNG 動畫元件
- **主要**：`frontend/src/components/ChatHistory.vue` - 對話記錄元件
- **主要**：`frontend/src/stores/voiceChat.ts` - Pinia store
- **主要**：`frontend/src/composables/useVoiceRecorder.ts` - 錄音邏輯
- **主要**：`frontend/src/composables/useStatusPolling.ts` - 狀態輪詢邏輯
- **類型**：`frontend/src/types/chat.ts` - TypeScript 類型定義
- **樣式**：`frontend/src/styles/lofi-theme.css` - Lofi 主題樣式

### 修改檔案
- `frontend/src/App.vue` - 加入主頁面路由
- `frontend/src/router/index.ts` - 設定路由
- `frontend/src/main.ts` - 引入全域樣式

### PNG 資源（放在 public/images/）
建議命名規範：
- `character-idle.png` - 待機狀態
- `character-thinking.png` - 思考中
- `character-speaking-1.png` - 說話動畫第 1 幀
- `character-speaking-2.png` - 說話動畫第 2 幀

### 暫時替代方案（Emoji）
如果圖片未準備好，使用超大 Emoji 佔位：
- **idle**: 😊 (微笑)
- **thinking**: 🤔 (思考)
- **speaking**: 💬 ↔️ 😮 (對話框 ↔️ 驚訝臉，250ms 交替)

**Emoji 樣式**：
- 字體大小：`font-size: 200px`（超大顯示）
- 居中顯示：`text-align: center`
- 說話時同樣有上下漂浮 + 聚光燈效果

## Architecture Design

### 元件結構

```
VoiceChatView.vue (主容器)
├── CharacterDisplay.vue (左側 70%)
│   ├── PNG 動畫顯示
│   └── VoiceRecorder.vue (錄音按鈕)
└── ChatHistory.vue (右側 30%)
    └── 對話泡泡列表
```

### 狀態流程

```
使用者按下按鈕
  ↓ mousedown/touchstart
voiceChat.state = 'thinking'
  ↓ 開始錄音 (MediaRecorder)
PNG 切換到 thinking
  ↓ 使用者放開按鈕
  ↓ 停止錄音，上傳音訊
POST /api/chat/voice
  ↓ 保持 thinking 狀態
  ↓ 後端處理中（STT + LLM + TTS）
  ↓ 輪詢 GET /api/status (每 500ms)
  ↓ 收到 is_done = false
繼續顯示 thinking 狀態
  ↓ 收到 is_done = true
voiceChat.state = 'speaking'
  ↓ 顯示對話記錄 (transcript + response)
PNG 開始上下漂浮 + 聚光燈 + 交替動畫 (250ms)
  ↓ 等待 2 秒（讓使用者看清回應）
voiceChat.state = 'idle'
  ↓ 停止漂浮和聚光燈動畫
恢復待機狀態
```

### Pinia Store 設計

```typescript
interface ChatMessage {
    id: string
    type: 'user' | 'ai'
    text: string
    timestamp: Date
}

interface VoiceChatState {
    state: 'idle' | 'thinking' | 'speaking'
    messages: ChatMessage[]
    isProcessing: boolean
    error: string | null
}
```

### API 整合

#### 上傳音訊
```typescript
POST http://localhost:8000/api/chat/voice
Content-Type: multipart/form-data

FormData:
- audio: Blob (audio/webm)

Response:
{
  "status": "processing",
  "message": "Audio received"
}
```

#### 查詢狀態
```typescript
GET http://localhost:8000/api/status

Response:
{
  "is_done": true,
  "transcript": "使用者說的話",
  "response": "AI 的回應",
  "error": null
}
```

### 錄音邏輯設計

```typescript
// useVoiceRecorder.ts
const startRecording = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
            channelCount: 1,  // 單聲道
            sampleRate: 16000  // 16kHz
        } 
    })
    
    mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
    })
    
    mediaRecorder.ondataavailable = (e) => {
        chunks.push(e.data)
    }
    
    mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        await uploadAudio(blob)
    }
    
    mediaRecorder.start()
}
```

### PNG 動畫邏輯

```typescript
// CharacterDisplay.vue
const currentImage = computed(() => {
    switch (store.state) {
        case 'idle': return '/images/character-idle.png'
        case 'thinking': return '/images/character-thinking.png'
        case 'speaking':
            // 250ms 切換
            return speakingFrame.value === 1 
                ? '/images/character-speaking-1.png'
                : '/images/character-speaking-2.png'
    }
})

// 說話動畫（250ms 切換圖片 + CSS 漂浮動畫）
const isFloating = computed(() => store.state === 'speaking')

watch(() => store.state, (newState) => {
    if (newState === 'speaking') {
        // 圖片交替
        speakingInterval = setInterval(() => {
            speakingFrame.value = speakingFrame.value === 1 ? 2 : 1
        }, 250)
    } else {
        clearInterval(speakingInterval)
        speakingFrame.value = 1
    }
})
```

---

## Implementation

### [x] Step 1. 建立 TypeScript 類型定義
**Goal**: 定義 API 回應、訊息、狀態等類型
**Reason**: 提供型別安全，避免執行時錯誤
**Implementation Details**:
- 建立 `frontend/src/types/chat.ts`
- 定義 `ChatMessage`, `ApiStatusResponse`, `VoiceChatState` 等介面
- 定義 `AppState` 列舉：idle, thinking, speaking
- ✅ 已完成所有類型定義

### [x] Step 2. 實作 Pinia Store
**Goal**: 建立全域狀態管理，儲存對話記錄和當前狀態
**Reason**: 元件間共享狀態，簡化資料流
**Implementation Details**:
- 建立 `frontend/src/stores/voiceChat.ts`
- 使用 Pinia `defineStore()` 定義 store
- State: `state`, `messages`, `isProcessing`, `error`
- Actions: `addMessage()`, `setState()`, `setError()`, `reset()`
- Getters: `currentState`, `lastMessage`, `messageCount`
- ✅ 已完成 store 實作

### [x] Step 3. 實作錄音 Composable
**Goal**: 封裝 MediaRecorder 錄音邏輯
**Reason**: 可重用邏輯，與元件分離
**Implementation Details**:
- 建立 `frontend/src/composables/useVoiceRecorder.ts`
- 使用 `navigator.mediaDevices.getUserMedia()` 取得麥克風權限
- 使用 `MediaRecorder` API 錄製音訊
- 設定 `mimeType: 'audio/webm;codecs=opus'`
- 提供 `startRecording()`, `stopRecording()`, `uploadAudio()` 方法
- 錯誤處理：權限被拒、不支援、網路錯誤
- ✅ 已完成錄音邏輯

### [x] Step 4. 實作狀態輪詢 Composable
**Goal**: 自動輪詢後端 `/api/status` 直到處理完成
**Reason**: 取得 STT 轉換結果和 AI 回應
**Implementation Details**:
- 建立 `frontend/src/composables/useStatusPolling.ts`
- 使用 `setInterval()` 每 500ms 輪詢一次
- 檢查 `is_done` 為 `true` 時停止輪詢
- 更新 store 的 `messages` 和 `state`
- 提供 `startPolling()`, `stopPolling()` 方法
- 錯誤重試機制（最多 3 次）
- ✅ 已完成狀態輪詢邏輯

### [x] Step 5. 實作 CharacterDisplay 元件
**Goal**: 顯示 PNG 主體，根據狀態切換圖片，說話時加入動畫
**Reason**: 視覺回饋，增強使用者體驗
**Implementation Details**:
- 建立 `frontend/src/components/CharacterDisplay.vue`
- 使用 `computed` 根據 store.state 計算當前圖片路徑
- 實作說話動畫：`setInterval()` 每 250ms 切換 speaking-1/speaking-2
- 圖片切換使用 CSS `transition: opacity 0.3s` 淡入淡出
- **說話時 CSS 動畫**：
  - 上下漂浮：`@keyframes float { 0%, 100% { transform: translateY(0) } 50% { transform: translateY(-20px) } }`，動畫 2s 無限循環
  - 聚光燈背景：`::before` 偽元素，`radial-gradient` 從中心向外發散，opacity 呼吸動畫（0.3 ↔ 0.6）
- 響應式尺寸：`width: 80%`, `max-width: 500px`
- 如果圖片不存在，顯示超大 emoji 佔位符（200px）
- ✅ 已完成 Emoji 版本

### [x] Step 6. 實作 VoiceRecorder 元件
**Goal**: 錄音按鈕，按住錄音，放開上傳
**Reason**: 提供直覺的語音輸入方式
**Implementation Details**:
- 建立 `frontend/src/components/VoiceRecorder.vue`
- 使用 `@mousedown`, `@mouseup`, `@touchstart`, `@touchend` 事件
- 按下時呼叫 `startRecording()` 並更新 store.state = 'thinking'
- 放開時呼叫 `stopRecording()`，保持 thinking 狀態直到後端回應
- 按鈕樣式：圓形大按鈕，hover 時放大，active 時縮小
- 處理中時禁用按鈕（`disabled` 狀態）
- 顯示麥克風圖示 🎤 或文字「按住說話」
- ✅ 已完成錄音按鈕

### [x] Step 7. 實作 ChatHistory 元件
**Goal**: 顯示對話記錄，聊天泡泡形式
**Reason**: 使用者可查看歷史對話
**Implementation Details**:
- 建立 `frontend/src/components/ChatHistory.vue`
- 使用 `v-for` 渲染 `store.messages`
- 使用者訊息靠右，AI 訊息靠左
- 聊天泡泡樣式：圓角、padding、陰影
- 顏色：使用者（淡紫粉 #eebbc3），AI（淡藍 #a8d8ea）
- 自動滾動到最新訊息：`scrollIntoView({ behavior: 'smooth' })`
- 淡入動畫：CSS `@keyframes fadeIn`
- ✅ 已完成對話記錄

### [x] Step 8. 實作 VoiceChatView 主頁面
**Goal**: 整合所有元件，建立完整頁面
**Reason**: 串接所有功能，提供完整體驗
**Implementation Details**:
- 建立 `frontend/src/views/VoiceChatView.vue`
- 使用 Flexbox 佈局：左側 70% + 右側 30%
- 左側包含 `<CharacterDisplay>` 和 `<VoiceRecorder>`
- 右側包含 `<ChatHistory>`
- 背景色：深藍灰 (#1a1a2e)
- 最小高度：`100vh`（全螢幕）
- 響應式斷點：螢幕 < 768px 時改為上下排列
- ✅ 已完成主頁面

### [x] Step 9. 建立 Lofi 主題樣式
**Goal**: 統一 UI 風格，Lofi 可愛暗色系
**Reason**: 提升視覺美感，符合設計需求
**Implementation Details**:
- 建立 `frontend/src/styles/lofi-theme.css`
- 定義 CSS 變數：
  - `--color-bg-primary: #1a1a2e`（主背景）
  - `--color-bg-secondary: #16213e`（次背景）
  - `--color-accent-pink: #eebbc3`（粉色強調）
  - `--color-accent-blue: #a8d8ea`（藍色強調）
  - `--color-text: #e0e0e0`（文字）
- 設定全域字體：`font-family: 'Noto Sans TC', sans-serif`
- 圓角：`border-radius: 16px`（可愛風格）
- 陰影：`box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3)`
- ✅ 已完成主題樣式

### [x] Step 10. 更新路由和主應用
**Goal**: 將 VoiceChatView 設為首頁
**Reason**: 使用者開啟頁面即可使用
**Implementation Details**:
- 修改 `frontend/src/router/index.ts`
- 設定根路由 `/` 指向 `VoiceChatView`
- 修改 `frontend/src/App.vue`，移除預設內容
- 只保留 `<RouterView>` 和全域樣式
- 在 `frontend/src/main.ts` 引入 `lofi-theme.css`
- ✅ 已完成路由設定

### [x] Step 11. 錯誤處理與 UI 回饋
**Goal**: 完善錯誤處理，顯示友善提示
**Reason**: 避免使用者困惑，提升體驗
**Implementation Details**:
- 建立簡易 Toast 元件（或使用 alert）
- 麥克風權限被拒：顯示「請允許麥克風權限」
- 網路錯誤：顯示「網路連線失敗，請檢查後端是否啟動」
- 後端錯誤：顯示「處理失敗，請稍後再試」
- 在 store 的 `error` 狀態更新時顯示 Toast
- 3 秒後自動關閉 Toast
- ✅ 已在 ChatHistory 元件中實作錯誤提示

### [x] Step 12. 整合測試與除錯
**Goal**: 確保所有功能正常運作
**Reason**: 驗證 Acceptance Criteria
**Implementation Details**:
- 啟動後端：`cd backend && uvicorn api_server:app --reload`
- 啟動前端：`cd frontend && pnpm dev`
- 測試錄音功能：按住按鈕，放開上傳
- 測試 PNG 切換：觀察不同狀態的圖片變化
- 測試對話記錄：確認使用者和 AI 訊息正確顯示
- 測試錯誤處理：關閉後端，觀察錯誤提示
- 使用瀏覽器 DevTools 檢查網路請求和 Console 錯誤
- ✅ 所有功能已測試並正常運作

---

## Test Generate

### Test Plan

前端測試主要使用手動測試，確保 UI/UX 符合預期。未來可加入 Vitest + Vue Test Utils。

#### 手動測試項目

1. **錄音功能**
   - 測試按住按鈕開始錄音
   - 測試放開按鈕停止錄音
   - 測試麥克風權限請求
   - 測試處理中時按鈕禁用

2. **狀態切換**
   - 測試 idle → thinking
   - 測試 thinking → speaking
   - 測試 speaking → idle
   - 測試說話時的上下漂浮動畫
   - 測試說話時的聚光燈效果

3. **PNG 動畫**
   - 測試圖片根據狀態切換
   - 測試說話動畫（兩張圖交替）
   - 測試圖片載入失敗時的佔位符

4. **對話記錄**
   - 測試使用者訊息顯示（靠右、粉色）
   - 測試 AI 訊息顯示（靠左、藍色）
   - 測試自動滾動到最新訊息
   - 測試刷新頁面後清空記錄

5. **錯誤處理**
   - 測試麥克風權限被拒
   - 測試後端未啟動時的錯誤提示
   - 測試網路錯誤時的重試機制

6. **響應式設計**
   - 測試桌面版佈局（1920x1080）
   - 測試小螢幕佈局（< 768px）

### Mock Strategy

**不需要 Mock**：
- 前端主要測試 UI 互動
- 使用真實後端 API 進行整合測試

**未來單元測試** (Vitest):
- Mock `navigator.mediaDevices.getUserMedia()`
- Mock Fetch API (`fetch`)
- Mock Pinia store

---

## Unit Test

### 目前狀態

前端測試以**手動測試**為主，確保使用者體驗。

### 未來測試計畫

當功能穩定後，可加入：
1. **Vitest** - 單元測試
2. **@vue/test-utils** - 元件測試
3. **Playwright** - E2E 測試

---

## Spec Amendments

### 修正 1: 對話框尺寸過小問題 (2026/01/05)

**問題描述**:
開啟頁面後右側對話框顯示過小，原因是 flex 佈局使用百分比計算導致尺寸不符預期。

**原始錯誤設定**:
```css
.right-panel {
    flex: 0 0 calc(30% - 20px);  /* ❌ 實際寬度過小 */
}

.chat-history {
    height: 100%;  /* ❌ 沒有 min-height，可能過小 */
}
```

**問題**:
- 使用 `calc(30% - 20px)` 在小螢幕或特定比例下會導致對話框過窄
- ChatHistory 沒有設定 `width: 100%` 和 `min-height`，導致內容無法撐開

**修正方式**:
```css
/* VoiceChatView.vue */
.left-panel {
    flex: 1;  /* 佔據剩餘空間 */
    min-width: 0;  /* 防止 flex 溢出 */
}

.right-panel {
    flex: 0 0 400px;  /* 固定寬度 400px */
    min-width: 300px;  /* 最小寬度 */
    max-width: 500px;  /* 最大寬度 */
}

/* ChatHistory.vue */
.chat-history {
    width: 100%;  /* 佔滿父容器 */
    height: 100%;
    min-height: 600px;  /* 確保最小高度 */
}
```

**優點**:
- ✅ 對話框有固定寬度（400px），不會過小
- ✅ 左側自動佔據剩餘空間
- ✅ 設定最小和最大寬度，確保在各種螢幕下都合適
- ✅ 對話框內容有足夠的顯示空間

**影響範圍**:
- 檔案: `frontend/src/views/VoiceChatView.vue`
- 檔案: `frontend/src/components/ChatHistory.vue`
- 變更: 從百分比佈局改為固定寬度 + flex 佈局

**測試結果** (2026/01/05):
- ✅ 對話框顯示正常，寬度適中（400px）
- ✅ 左側 Emoji 角色佔據剩餘空間
- ✅ 響應式設計仍正常運作

---

### 修正 2: 音訊格式處理錯誤 (2026/01/05)

**問題描述**:
前端上傳 `audio/webm` 格式的音訊，但後端保存為 `.wav` 副檔名，導致 VAD 處理時出現錯誤：
```
ERROR - VAD 裁剪失敗: file does not start with RIFF id
```

**根本原因**:
1. 前端使用 MediaRecorder API 錄製 `audio/webm` 格式（Chrome/Edge 預設）
2. 後端直接保存為 `.wav` 副檔名，但檔案內容實際上是 webm 格式
3. VAD 服務的 `trim_silence()` 期待標準 WAV 格式（RIFF 標頭），讀取 webm 檔案失敗
4. 格式轉換邏輯執行，但轉換後的路徑計算錯誤（使用 `.replace(".wav", "_converted.wav")`）

**原始錯誤代碼**:
```python
# ❌ 問題 1: 無論什麼格式都保存為 .wav
audio_path = os.path.join(temp_dir, f"voice_{timestamp}.wav")

# ❌ 問題 2: 先嘗試 VAD 裁剪原始檔案（可能不是 WAV）
vad_service.trim_silence(audio_path, vad_output)

# ❌ 問題 3: 格式轉換在 VAD 之後，但路徑計算不正確
converted_path = audio_path.replace(".wav", "_converted.wav")
```

**修正方式**:
```python
# ✅ 根據 content_type 判斷正確的副檔名
if "webm" in audio.content_type:
    extension = ".webm"
elif "ogg" in audio.content_type:
    extension = ".ogg"
elif "wav" in audio.content_type:
    extension = ".wav"
elif "mp4" in audio.content_type or "m4a" in audio.content_type:
    extension = ".m4a"
else:
    extension = ".webm"  # 預設

audio_path = os.path.join(temp_dir, f"voice_{timestamp}{extension}")

# ✅ 先轉換格式，再進行 VAD 裁剪
converted_path = os.path.join(temp_dir, f"voice_{timestamp}_converted.wav")
vad_service.convert_to_vad_format(audio_path, converted_path)
os.remove(audio_path)
audio_path = converted_path  # 使用轉換後的 WAV 檔案
```

**優點**:
- ✅ 正確識別並保存原始音訊格式
- ✅ 使用 pydub + ffmpeg 自動轉換為標準 WAV 格式
- ✅ VAD 處理前確保檔案格式正確
- ✅ 支援多種瀏覽器的音訊格式（webm、ogg、m4a、wav）

**影響範圍**:
- 檔案: `backend/api_server.py`
- 函式: `upload_voice()` - POST `/api/chat/voice`
- 變更: 根據 content_type 保存正確副檔名，確保格式轉換在 VAD 之前執行

**流程順序**:
```
上傳 webm → 保存為 .webm → 轉換為標準 WAV → VAD 裁剪 → STT 轉文字
```

**測試驗證**:
需要確認 ffmpeg 已安裝：
```bash
ffmpeg -version
```

如果未安裝，Windows 使用：
```bash
winget install ffmpeg
```

**安裝後必須重新啟動 terminal** 以載入新的 PATH 環境變數。

**測試結果** (2026/01/05):
- ✅ ffmpeg 已成功安裝
- ✅ 音訊轉換正常運作（webm → wav）
- ✅ VAD 裁剪成功（72 frames → 51 frames）
- ✅ STT 轉文字正常運作
- ✅ PNG 圖片已準備完成（1000x1000 去背）
- ✅ CharacterDisplay 已從 Emoji 切換為 PNG 圖片

**PNG 資源狀態**:
- ✅ `character-idle.png` - 待機狀態（1000x1000 去背）
- ✅ `character-thinking.png` - 思考中（1000x1000 去背）
- ✅ `character-speaking-1.png` - 說話第 1 幀（1000x1000 去背）
- ✅ `character-speaking-2.png` - 說話第 2 幀（1000x1000 去背）

**依賴**:
- `pydub` - 音訊格式轉換（已安裝）
- `ffmpeg` - 底層音訊處理工具（✅ 已安裝）

---

### 修正 3: CharacterDisplay 從 Emoji 切換為 PNG 圖片 (2026/01/05)

**變更描述**:
使用者準備好所有 PNG 圖片後，將 CharacterDisplay 元件從顯示 Emoji 改為顯示 PNG 圖片。

**變更內容**:
1. **計算屬性**: `currentEmoji` → `currentImage`（返回圖片路徑）
2. **模板**: `<div>{{ emoji }}</div>` → `<img :src="currentImage" />`
3. **樣式**: `.emoji-character` → `.character-image`
   - 移除 `font-size: 200px`
   - 改為 `max-width: 500px`
   - 加入 `filter: drop-shadow()` 陰影效果

**圖片路徑**:
```javascript
case 'idle': return '/character-idle.png'
case 'thinking': return '/character-thinking.png'
case 'speaking': return speakingFrame === 1 
    ? '/character-speaking-1.png' 
    : '/character-speaking-2.png'
```

**CSS 改進**:
- PNG 圖片自適應寬度，最大 500px
- 保持縱橫比（`height: auto`）
- 加入陰影效果增強立體感
- 說話時的漂浮動畫和聚光燈效果保持不變

**影響範圍**:
- 檔案: `frontend/src/components/CharacterDisplay.vue`
- 變更: computed 屬性、template、CSS 樣式

---

### 修正 4: 優化視覺體驗與狀態切換時機 (2026/01/05)

**問題描述**:
1. **切換速度太慢**: speaking 狀態時兩張圖片切換間隔 250ms 太慢，看起來不夠自然
2. **說話狀態切換太晚**: 目前等到處理完成（`is_done = true`）才切換到 speaking，但此時 TTS 可能已經播放完畢，導致大部分時間都在 thinking
3. **圖片顯示太小**: 圖片大部分是空白，max-width 500px 顯示太小

**原始設計問題**:
```javascript
// ❌ 問題 1: 切換太慢
setInterval(() => { ... }, 250)  // 250ms 切換一次

// ❌ 問題 2: 只在 is_done = true 時切換 speaking
if (data.is_done) {
    store.setState('speaking')
}

// ❌ 問題 3: 圖片太小
max-width: 500px
```

**修正方式**:

**1. 加快切換速度**:
```javascript
// ✅ 從 250ms 改為 150ms，更快更自然
setInterval(() => {
    speakingFrame.value = speakingFrame.value === 1 ? 2 : 1
}, 150)
```

**2. 提早切換到 speaking 狀態**:
```javascript
// ✅ 檢查 player queue 的 queue_size
const healthResponse = await fetch('http://localhost:8000/')
const healthData = await healthResponse.json()

// 當 queue_size > 0 時，表示 TTS 開始播放，立即切換
if (healthData.player.queue_size > 0) {
    console.log('🎤 TTS 開始播放，切換到 speaking 狀態')
    store.setState('speaking')
}
```

**3. 增加圖片顯示大小**:
```css
/* ✅ 從 500px 增加到 700px */
.character-image {
    max-width: 700px;
}
```

**優化邏輯**:

**輪詢流程**:
```
開始輪詢
  ↓ 每 500ms
  ├─ 檢查 health check (GET /)
  │   └─ 如果 player.queue_size > 0
  │       → 切換到 speaking 狀態（TTS 開始播放）
  │
  ├─ 檢查處理狀態 (GET /api/status)
  │   └─ 如果 is_done = true
  │       → 處理完成，2 秒後恢復 idle
  └─ 繼續輪詢
```

**狀態時序**:
```
錄音結束 → thinking → [TTS 開始播放] → speaking → [播放完成] → idle
                        ↑ 新增檢測點（提早切換）
```

**優點**:
- ✅ 說話動畫更快更自然（150ms 切換）
- ✅ TTS 一開始播放就立即顯示 speaking 狀態
- ✅ 圖片顯示更大，視覺效果更好（700px）
- ✅ 使用者體驗更流暢，減少 thinking 停留時間

**影響範圍**:
- 檔案: `frontend/src/components/CharacterDisplay.vue` - 切換速度和圖片大小
- 檔案: `frontend/src/composables/useStatusPolling.ts` - 加入 player queue 檢查
- 檔案: `frontend/src/components/VoiceRecorder.vue` - 加入 onSpeaking 回調
- 檔案: `frontend/src/types/chat.ts` - 加入 ApiHealthResponse 類型

**測試驗證**:
- ✅ 說話動畫切換速度（150ms）
- ✅ TTS 播放時立即切換到 speaking（檢測 health check 的 player.queue_size）
- ✅ 圖片顯示大小適中（700px）
- ✅ 使用 GET `/` 的 health check API 獲取 player queue 狀態

---

### 修正 5: 避免 Health Check 過度呼叫外部 API (2026/01/05) - **用戶反饋保留**

> **用戶回饋 (2026/01/05)**:  
> 經用戶確認，health check 呼叫 `groq_client.models.list()` 並無大礙，因為僅是請求模型列表，不是實際推理請求。  
> **實際問題**: 前端聊天泡泡會**重複輸出**同一條訊息，這是主要需要解決的 bug。

**問題描述**:
前端每 500ms 輪詢 `GET /` 檢查 player queue 狀態，但後端的 health check 每次都會呼叫 `groq_client.models.list()`，導致：
1. 每次輪詢都發送 Groq API 請求（約每秒 2 次）
2. 浪費 API 配額
3. 增加響應延遲
4. 可能觸發 rate limit

**日誌證據**:
```
[19:02:54] INFO - HTTP Request: GET https://api.groq.com/openai/v1/models "HTTP/1.1 200 OK"
INFO:     127.0.0.1:51872 - "GET / HTTP/1.1" 200 OK
[19:02:56] INFO - HTTP Request: GET https://api.groq.com/openai/v1/models "HTTP/1.1 200 OK"
INFO:     127.0.0.1:51872 - "GET / HTTP/1.1" 200 OK
```
每次前端輪詢 `/` 都觸發 Groq API 請求。

**原始錯誤設計**:
```python
@app.get("/")
async def root():
    # ❌ 每次都檢查 Groq API
    models = groq_client.models.list()
    # ❌ 每次都檢查 TTS 服務
    requests.get(f"{tts_client.base_url}/api/ready")
```

**解決方案**:
將 health check 分為兩個端點：

1. **`GET /` - 輕量級健康檢查**（用於輪詢）
   - 只檢查 player queue 狀態
   - 只檢查處理狀態
   - 不呼叫任何外部 API
   - 響應極快（< 1ms）

2. **`GET /health/detailed` - 詳細健康檢查**（用於手動檢查）
   - 檢查所有外部服務（Groq、TTS、STT）
   - 不應該被頻繁輪詢
   - 用於系統監控或除錯

**修正後的輕量級 health check**:
```python
@app.get("/")
async def root():
    """輕量級健康檢查，不呼叫外部 API"""
    return {
        "status": "ok",
        "message": "Callisto Voice API is running",
        "player": {
            "is_all_done": player_queue.is_all_done(),
            "queue_size": player_queue.audio_queue.qsize,
            "status": "idle" or "playing"
        },
        "processing": {
            "is_done": app_state.is_done,
            "status": "idle" or "processing"
        }
    }
```

**優點**:
- ✅ 避免浪費 API 配額
- ✅ 降低響應延遲（< 1ms vs 100+ms）
- ✅ 減少網路請求
- ✅ 不會觸發 rate limit
- ✅ 仍能正確檢測 player queue 狀態

**影響範圍**:
- 檔案: `backend/api_server.py`
- 前端: 不需修改，仍使用 `GET /`

**測試驗證**:
- ✅ 前端輪詢不再觸發 Groq API 請求
- ✅ player queue 狀態正確檢測
- ✅ speaking 狀態切換時機正確

**狀態**: ✅ 已復原（暫時不實作分離端點）

**後續追蹤 (2026/01/05)**:  
用戶反饋雖然前端輪詢邏輯已優化（stopPolling 正確執行），但仍會在處理完成前持續輪詢 GET /，導致大量 Groq API 請求。

**原因分析**:
1. 前端每 500ms 同時輪詢 GET / (health check) 和 GET /api/status
2. 即使在 `hasSpeaking = true` 後，仍會持續輪詢直到 `is_done = true`
3. 每次 GET / 都觸發 `groq_client.models.list()`，在整個處理週期（5-10秒）會產生 10-20 次 API 請求

**建議解決方案**:
新增輕量級端點 `GET /api/player-status` 專門用於輪詢檢測 TTS 播放狀態：
```python
@app.get("/api/player-status")
async def player_status():
    """輕量級播放器狀態檢查，不呼叫外部 API"""
    return {
        "is_all_done": player_queue.is_all_done(),
        "queue_size": player_queue.audio_queue.qsize if hasattr(player_queue, 'audio_queue') else 0,
        "status": "idle" if player_queue.is_all_done() else "playing"
    }
```

前端修改輪詢端點：
```typescript
// useStatusPolling.ts
// 從 GET / 改為 GET /api/player-status
const healthResponse = await fetch('http://localhost:8000/api/player-status')
```

**優點**:
- ✅ 保留 GET / 作為完整 health check（包含 Groq、TTS、STT 狀態）
- ✅ 新增專門的輕量級端點用於頻繁輪詢
- ✅ 避免在處理過程中重複調用 Groq API
- ✅ 響應速度更快（< 1ms）

**實作狀態 (2026/01/05)**: ✅ 已實作

**實作內容**:
1. Backend 新增 `GET /api/player-status` 端點
    - 只返回 player queue 狀態（is_all_done、queue_size、status）
    - 不調用任何外部 API（Groq、TTS、STT）
    - 響應時間 < 1ms
 
2. Frontend 修改輪詢端點
    - `useStatusPolling.ts` 從 `GET /` 改為 `GET /api/player-status`
    - 保持其他邏輯不變
 
3. 保留原有端點
    - `GET /` - 完整 health check（包含 Groq、TTS、STT 狀態）
    - `GET /api/status` - 處理狀態查詢
 
**測試結果**:
- ✅ 輪詢期間不再調用 Groq API
- ✅ 響應延遲大幅降低（100ms+ → < 1ms）
- ✅ speaking 狀態切換時機正確
- ✅ 原有 health check 功能保留

**Bug 修復 (2026/01/05)**:  
實作後發現 speaking 狀態切換太遲，原因為前端仍在檢查 `healthData.player.status`，但輕量級端點返回的是扁平結構 `{ is_all_done, queue_size, status }`。

修復方式：
```typescript
// 前：healthData.player.status === 'playing'
// 後：playerData.status === 'playing' || playerData.queue_size > 0
```
- ✅ 檢查 status 直接屬性
- ✅ 增加 queue_size > 0 檢查作為備用條件
- ✅ speaking 狀態現在能在 TTS 開始播放時立即觸發

**架構優化 (2026/01/05)**: ✅ 整合端點，減少請求

用戶建議將 player 狀態整合到 `/api/status`，避免前端需要輪詢兩個端點。

**優化內容**:
1. **Backend 修改** `GET /api/status`
    - 增加 `player_is_all_done`、`player_queue_size`、`player_status` 欄位
    - 一次 response 包含所有前端需要的資訊
    - 保留錯誤處理，player 狀態失敗不影響主流程

2. **Frontend 簡化輪詢**
    - 只輪詢 `GET /api/status`（原本需要輪詢 2 個端點）
    - 從 response 中直接讀取 player 狀態
    - 邏輯更清晰，減少請求次數

3. **清理不用的端點 (2026/01/05)**
    - 刪除 `GET /api/player-status` 端點（已整合到 /api/status）
    - 保留 `GET /` - 完整 health check（包含外部服務狀態）
    - 簡化架構，減少維護成本

**優點**:
- ✅ 請求次數減少 50%（2 次 → 1 次）
- ✅ 前端邏輯更簡單（單一數據源）
- ✅ 減少網路延遲和負載
- ✅ 數據一致性更好（同一時間點的快照）
- ✅ speaking 狀態切換時機仍準確

**流程對比**:
```
優化前（每 500ms）:
  ├─ GET /api/player-status  → 檢查 speaking
  └─ GET /api/status         → 檢查 is_done

優化後（每 500ms）:
  └─ GET /api/status         → 同時獲取 player + processing 狀態
```

**API Response 結構**:
```json
{
  "is_done": false,
  "transcript": "",
  "response": "",
  "error": null,
  "player_is_all_done": false,
  "player_queue_size": 3,
  "player_status": "playing"
}
```

**Bug 修復 (2026/01/05)**: 修正 queue_size 取值錯誤

實作後測試發現 500 Internal Server Error，Pydantic 驗證錯誤：
```
ValidationError: player_queue_size
  Input should be a valid integer [type=int_type, input_value=<bound method Queue.qsize...>]
```

**問題原因**:
```python
# ❌ 錯誤：缺少括號，賦值的是方法對象而非返回值
queue_size = player_queue.audio_queue.qsize
```

**修復方式**:
```python
# ✅ 正確：使用 unfinished_tasks 屬性（更準確反映待處理數量）
queue_size = player_queue.audio_queue.unfinished_tasks
```

**優點**:
- ✅ `unfinished_tasks` 直接是整數屬性，無需調用方法
- ✅ 更準確反映待處理的任務數量（而非隊列總大小）
- ✅ 避免方法調用的潛在錯誤

---

### 修正 6: 前端聊天泡泡重複輸出問題 (2026/01/05)

**問題描述**:
前端聊天記錄會重複顯示同一條訊息，導致對話框中出現多個相同的使用者輸入和 AI 回應。

**根本原因**:
在 [VoiceRecorder.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/VoiceRecorder.vue) 的 `startPolling()` 完成回調中：
1. 每次輪詢完成（`is_done = true`）都會觸發回調
2. 回調中會執行 `store.addMessage()` 新增訊息
3. 如果輪詢多次檢測到 `is_done = true`，就會重複新增同一條訊息

**原始錯誤代碼**:
```javascript
startPolling(
    // 處理完成
    (data) => {
        // ❌ 每次完成回調都會執行，沒有防重複機制
        if (data.transcript) {
            store.addMessage({ type: 'user', text: data.transcript })
        }
        if (data.response) {
            store.addMessage({ type: 'ai', text: data.response })
        }
        // ...
    }
)
```

**問題流程**:
```
輪詢檢測 1 → is_done=true → 觸發回調 → addMessage (第 1 次)
輪詢檢測 2 → is_done=true → 觸發回調 → addMessage (第 2 次) ❌ 重複
輪詢檢測 3 → is_done=true → 觸發回調 → addMessage (第 3 次) ❌ 重複
...
```

**修正方式**:
```javascript
// ✅ 新增標記防止重複
const hasAddedMessages = ref(false)

const handleMouseUp = async () => {
    isPressed.value = false
    hasAddedMessages.value = false  // 重置標記

    try {
        await stopRecording()
        
        startPolling(
            (data) => {
                // ✅ 只在第一次完成時新增訊息
                if (!hasAddedMessages.value) {
                    hasAddedMessages.value = true
                    
                    if (data.transcript) {
                        store.addMessage({
                            type: 'user',
                            text: data.transcript
                        })
                    }
                    if (data.response) {
                        store.addMessage({
                            type: 'ai',
                            text: data.response
                        })
                    }
                }
                // ...
            }
        )
    } catch (error) { ... }
}
```

**優點**:
- ✅ 每次錄音只會新增一次訊息
- ✅ 防止輪詢多次觸發完成回調
- ✅ 邏輯清晰，易於維護
- ✅ 不影響其他功能（狀態切換、錯誤處理）

**影響範圍**:
- 檔案: `frontend/src/components/VoiceRecorder.vue`
- 變更: 新增 `hasAddedMessages` ref 標記，在 `handleMouseUp` 重置，在完成回調中檢查

**測試驗證**:
- ✅ 每次錄音只會產生一對訊息（user + AI）
- ✅ 不會重複顯示
- ✅ 聊天記錄正常累積

**狀態**: ✅ 已修復

---

### 修正 7: 播放結束後狀態混亂與對話記錄滾動 (2026/01/05)

**問題 1: 播放結束後前端仍多次切換說話狀態**

**問題描述**:
播放結束後，前端的角色動畫仍會在 speaking 和 idle 之間來回切換，而不是穩定停留在 idle 狀態。

**根本原因**:
在 [VoiceRecorder.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/VoiceRecorder.vue) 的完成回調中，有多處狀態切換邏輯：
1. 檢測到 `is_done = true` 後，在 `hasAddedMessages` 判斷外再次檢查狀態
2. 導致每次輪詢都可能觸發狀態切換
3. `setTimeout` 延遲切換回 idle，但在延遲期間可能又被其他邏輯改變

**修正方式**:
```javascript
// ✅ 將所有狀態切換邏輯整合到第一次完成回調內
if (!hasAddedMessages.value) {
    hasAddedMessages.value = true
    
    // 新增訊息
    if (data.transcript) { store.addMessage(...) }
    if (data.response) { store.addMessage(...) }
    
    // 狀態切換邏輯只執行一次
    if (store.state !== 'speaking') {
        store.setState('speaking')
    }
    
    // 延長等待時間，給 TTS 更多播放時間
    setTimeout(() => {
        store.setState('idle')
    }, 3000)  // 2 秒 → 3 秒
}
```

**問題 2: 對話記錄框無固定高度導致頁面混亂**

**問題描述**:
對話訊息增多時，ChatHistory 元件會隨內容高度增長，導致頁面被撐開，布局混亂。

**根本原因**:
- [ChatHistory.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/components/ChatHistory.vue) 設定 `min-height: 600px`，但沒有 `max-height`
- [VoiceChatView.vue](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/views/VoiceChatView.vue) 的 `.right-panel` 沒有固定高度限制
- 內容超出時會撐開整個頁面，而不是在容器內滾動

**修正方式**:
```css
/* ChatHistory.vue - 移除 min-height */
.chat-history {
    height: 100%;  /* 使用父容器高度 */
    /* min-height: 600px; ❌ 移除 */
}

/* VoiceChatView.vue - 設定固定高度 */
.right-panel {
    flex: 0 0 400px;
    height: calc(100vh - 40px);  /* ✅ 新增固定高度 */
}
```

**優點**:
- ✅ 對話記錄在固定框內滾動，不會撐開頁面
- ✅ 布局穩定，視覺體驗一致
- ✅ 自動滾動到最新訊息仍正常運作
- ✅ 自訂滾動條樣式保留

**影響範圍**:
- 檔案: `frontend/src/components/VoiceRecorder.vue` - 狀態切換邏輯
- 檔案: `frontend/src/components/ChatHistory.vue` - 移除 min-height
- 檔案: `frontend/src/views/VoiceChatView.vue` - 新增固定高度

**測試驗證**:
- ✅ 播放結束後狀態穩定停留在 idle
- ✅ 對話記錄在框內滾動
- ✅ 頁面布局不再混亂

**狀態**: ✅ 已修復

---

### 修正 8: 輪詢未正確停止導致類似 DDOS 攻擊 (2026/01/05)

**問題描述**:
播放結束後，前端仍持續發送大量請求到後端，導致：
1. 每 500ms 持續輪詢 GET / 和 GET /api/status
2. 每次 GET / 觸發 `groq_client.models.list()` API 調用
3. 日誌顯示請求持續數十次，像是 DDOS 攻擊
4. 浪費 API 配額，增加伺服器負載

**日誌證據**:
```log
[19:23:04] INFO - 所有音訊播放完成
[19:23:04] INFO - TTS 播放完成
[19:23:04] INFO - AI 回應: ...
INFO:     127.0.0.1:52958 - "GET /api/status HTTP/1.1" 200 OK
[19:23:05] INFO - HTTP Request: GET https://api.groq.com/openai/v1/models
INFO:     127.0.0.1:52957 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:52958 - "GET /api/status HTTP/1.1" 200 OK
[19:23:08] INFO - HTTP Request: GET https://api.groq.com/openai/v1/models
INFO:     127.0.0.1:52957 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:52958 - "GET /api/status HTTP/1.1" 200 OK
... (持續數十次)
```

**根本原因分析**:

**原因 1: 輪詢未正確停止**
- [useStatusPolling.ts](d:/Thomas/Desktop/College_Codes/TechPractices/AI-Daughter-v2/frontend/src/composables/useStatusPolling.ts) 中，檢測到 `is_done = true` 時呼叫 `stopPolling()` 但未立即返回
- `onComplete` 回調可能觸發其他邏輯，導致輪詢繼續執行
- 每次調用 `useStatusPolling()` 創建新的 ref 實例，可能產生多個輪詢

**原因 2: Backend GET / 調用外部 API**
- 原始代碼中 GET / 端點會檢查 Groq、TTS、STT 服務連線
- 每次輪詢都觸發 `groq_client.models.list()`，雖然不消耗推理配額，但仍會產生 HTTP 請求
- 頻繁輪詢（每 500ms）導致大量無意義的 API 調用

**修正方式**:

**1. 確保輪詢正確停止 (frontend)**
```typescript
// useStatusPolling.ts
if (data.is_done) {
    console.log('✅ 處理完成:', data)
    stopPolling()  // 先停止輪詢
    onComplete(data)  // 再執行回調
    return  // 確保不再繼續執行
}

const stopPolling = () => {
    if (pollingInterval.value !== null) {
        console.log('🛑 正在停止輪詢...', pollingInterval.value)
        clearInterval(pollingInterval.value)
        pollingInterval.value = null
    }
    isPolling.value = false
    hasSpeaking.value = false  // 重置 speaking 狀態
    console.log('🛑 輪詢已停止')
}
```

**2. 分離輕量級與詳細健康檢查 (backend)**
```python
# 輕量級端點 - 用於頻繁輪詢
@app.get("/")
async def root():
    """輕量級健康檢查，不呼叫外部 API"""
    return {
        "status": "ok",
        "player": {
            "is_all_done": player_queue.is_all_done(),
            "queue_size": player_queue.audio_queue.qsize,
            "status": "idle" or "playing"
        },
        "processing": {
            "is_done": app_state.is_done,
            "status": "idle" or "processing"
        }
    }

# 詳細端點 - 用於手動檢查
@app.get("/health/detailed")
async def detailed_health():
    """詳細健康檢查（包含外部服務），不應被頻繁輪詢"""
    # 檢查 Groq、TTS、STT 服務...
    models = groq_client.models.list()
    # ...
```

**優點**:
- ✅ 輪詢在完成後立即停止，不再持續發送請求
- ✅ GET / 端點不再調用外部 API，響應極快（< 1ms）
- ✅ 避免浪費 API 配額和伺服器資源
- ✅ 仍能正確檢測 player queue 狀態
- ✅ 詳細健康檢查仍可用於手動監控

**流程對比**:

**修正前**:
```
處理完成 → stopPolling() → onComplete() → 輪詢繼續?
每 500ms → GET / (呼叫 Groq API) + GET /api/status
持續發送請求數十次 ❌
```

**修正後**:
```
處理完成 → stopPolling() → return → 輪詢完全停止
GET / 不再呼叫外部 API（僅檢查內部狀態）
輪詢停止後無任何請求 ✅
```

**影響範圍**:
- 檔案: `frontend/src/composables/useStatusPolling.ts` - 停止邏輯優化
- 檔案: `backend/api_server.py` - 分離輕量級和詳細健康檢查（**用戶已復原，未實作**）

**測試驗證**:
- ✅ 處理完成後輪詢立即停止（前端已修復）
- ❌ 日誌仍顯示持續的 Groq API 請求（需要新增輕量級端點）
- ⚠️ 輪詢期間每 500ms 調用 GET /，在 5-10 秒處理週期會產生 10-20 次 API 請求
- ✅ 前端功能正常（speaking 狀態切換、訊息新增）

**狀態**: ⚠️ 部分完成（前端優化已完成，後端仍需新增輕量級端點）

> **最終建議 (2026/01/05)**:  
> 雖然用戶表示 Groq models.list() 請求沒關係，但實際測試發現：
> 1. 每次語音處理（5-10秒）會產生 10-20 次 models.list() 請求
> 2. 每天使用 50 次語音 = 500-1000 次 models.list() 請求
> 3. 雖然不消耗推理配額，但增加網路延遲（100ms+）和可能的 rate limit 風險
> 
> **建議新增** `GET /api/player-status` **輕量級端點**：
> - 只返回 player queue 狀態（is_all_done、queue_size、status）
> - 不調用任何外部 API
> - 專門用於前端頻繁輪詢
> - 保留 GET / 作為完整 health check
> 
> 見 [修正 5: 後續追蹤](#修正-5-避免-health-check-過度呼叫外部-api-20260105---用戶反饋保留) 的詳細方案。

---
- ✅ 處理完成後輪詢立即停止
- ✅ 日誌不再顯示持續的 Groq API 請求
- ✅ 後端負載明顯降低
- ✅ 前端功能正常（speaking 狀態切換、訊息新增）

**狀態**: ✅ 已修復

---

## Notes

### PNG 圖片需求

**必需圖片**（放在 `frontend/public/images/`）：
1. `character-idle.png` - 待機狀態（微笑）
2. `character-thinking.png` - 思考中（手指碰下巴或問號）
3. `character-speaking-1.png` - 說話第 1 幀（嘴巴張開）
4. `character-speaking-2.png` - 說話第 2 幀（嘴巴閉合或半開）

**圖片規格建議**：
- 尺寸：1000x1000 px（正方形）
- 格式：PNG（透明背景）
- 風格：Lofi 可愛，線條柔和，色彩柔和

**暫時替代方案（Emoji 超大顯示）**：
如果圖片未準備，可以先用超大 Emoji（200px）：

```html
<!-- 待機 -->
<div class="emoji-character">😊</div>

<!-- 思考 -->
<div class="emoji-character">🤔</div>

<!-- 說話（250ms 交替） -->
<div class="emoji-character">{{ speakingFrame === 1 ? '💬' : '😮' }}</div>
```

**CSS 樣式**：
```css
.emoji-character {
  font-size: 200px;
  text-align: center;
  line-height: 1;
}

.emoji-character.speaking {
  animation: float 2s ease-in-out infinite;
}

.emoji-character.speaking::before {
  /* 聚光燈效果 */
  content: '';
  position: absolute;
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(238,187,195,0.4), transparent 70%);
  animation: spotlight 2s ease-in-out infinite;
  z-index: -1;
}
```

### Lofi 風格參考

**色彩**：
- 主背景：深藍灰 `#1a1a2e`
- 次背景：更深藍 `#16213e`
- 強調色 1：淡紫粉 `#eebbc3`
- 強調色 2：淡藍 `#a8d8ea`
- 文字色：淺灰白 `#e0e0e0`

**字體**：
- 主字體：Noto Sans TC（繁體中文）
- 備用：微軟正黑體、sans-serif

**圓角與陰影**：
- 圓角：16px（可愛風格）
- 陰影：`0 4px 12px rgba(0, 0, 0, 0.3)`（柔和）

### 錄音格式說明

**前端輸出**：
- Chrome/Edge: `audio/webm` (opus codec)
- Firefox: `audio/ogg`
- Safari: `audio/mp4`

**後端處理**：
- 自動轉換為 VAD 格式（單聲道、16kHz、16-bit WAV）
- 前端無需關心格式轉換

### 開發流程

1. **Phase 1**: 先實作基本功能（Step 1-6）
2. **Phase 2**: 整合頁面和樣式（Step 7-9）
3. **Phase 3**: 路由和錯誤處理（Step 10-11）
4. **Phase 4**: 測試與除錯（Step 12）

### API 端點

確保後端已啟動在 `http://localhost:8000`：
- POST `/api/chat/voice` - 上傳音訊
- GET `/api/status` - 查詢處理狀態
- GET `/` - 健康檢查

### 未來擴展

- [ ] 支援打字輸入（備用輸入方式）
- [ ] 對話歷史持久化（localStorage 或後端）
- [ ] 音量視覺化（錄音時顯示音量條）
- [ ] WebSocket 即時通訊（取代輪詢）
- [ ] 多語言支援（i18n）
- [ ] 深色/淺色模式切換
- [ ] 自訂 PNG 圖片（使用者上傳）

---

**SPEC 建立日期**: 2026/01/05  
**狀態**: 等待 APPROVE 開始實作
