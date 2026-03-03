# SPEC: 語音喚醒功能（總覽）

> **專案狀態**: 🚧 進行中 (40% 完成)  
> **後端**: ✅ 100% 完成 | **前端**: ⏳ 0% 完成

---

## 📑 規格導航

- **📘 [後端詳細規格](./SPEC-voice-wake-word-backend.md)** - Steps 1-4（已完成）
- **📗 [前端詳細規格](./SPEC-voice-wake-word-frontend.md)** - Steps 5-10（待實施）

---

## Task Description

實現語音喚醒功能，讓 Callisto 語音助理能夠持續監聽麥克風，透過 VAD（語音活動檢測）和 KWS（關鍵字喚醒）技術，在檢測到喚醒詞「嘿 Callisto」時自動啟動對話流程。

**使用場景**：
- **模式 A（原有）**：按住說話按鈕 → 上傳音訊 → 後端處理
- **模式 B（新增）**：開始監聽 → 持續錄音 → VAD 檢測語音 → KWS 檢測喚醒詞 → 自動啟動對話

**核心特性**：
- 持續監聽，前端即時傳輸音訊到後端（WebSocket）
- Silero VAD 實時檢測語音活動
- openWakeWord 檢測喚醒詞「嘿 Callisto」
- 低延遲：音訊流每 100ms 傳輸，檢測延遲 < 500ms
- 雙模式並存，互不影響

---

## Tech Stack

### 後端
- **Silero VAD** (ONNX Runtime) - 實時語音檢測
- **openWakeWord** - 喚醒詞檢測
- **FastAPI WebSocket** - 音訊串流通信

### 前端
- **Vue 3 + TypeScript** - UI 框架
- **MediaRecorder API** - 麥克風錄音（16kHz 單聲道）
- **WebSocket** - 即時音訊傳輸

### 依賴套件
- ✅ 後端: onnxruntime, openwakeword, numpy, scipy, soundfile
- ✅ 前端: Vue 3, TypeScript (已安裝)

---

## Acceptance Criteria

### 後端功能
- [x] Silero VAD 服務正確檢測語音活動（準確率 > 90%）
- [x] openWakeWord 檢測喚醒詞（當前使用 hey_jarvis，準確率 > 95%）
- [x] AudioMonitorService 並行協調 VAD+KWS（false alarm 過濾）
- [x] WebSocket 端點 `/ws/voice-monitor` 正常運作（9/9 tests passed）
- [ ] 檢測到喚醒詞後自動啟動 STT → LLM → TTS
- [ ] 原有上傳端點 `/api/chat/voice` 不受影響

### 前端功能
- [ ] 新增「開始監聽」切換按鈕，UI 清晰
- [ ] 點擊後成功連接 WebSocket 並持續錄音
- [ ] 每 100ms 傳輸一次音訊塊
- [ ] 接收並顯示後端事件（🟢 監聽中 / 🟡 檢測到 / 🔵 處理中）
- [ ] 停止時正確關閉資源
- [ ] 原有「按住說話」功能不受影響
- [ ] 錯誤處理：麥克風權限被拒、連接失敗

### 效能要求
- [ ] VAD CPU < 10%、KWS CPU < 15%
- [ ] 記憶體 < 100MB
- [ ] 網路頻寬 < 50 KB/s
- [ ] 喚醒詞檢測延遲 < 500ms

### 測試覆蓋
- [x] 後端單元測試: 56/56 passed (~28.84s)
- [ ] 前端元件測試
- [ ] 完整流程手動測試

---

## Implementation Roadmap

### 🎯 後端實現（已完成 ✅）
詳細實施細節請查看 **[後端 SPEC](./SPEC-voice-wake-word-backend.md)**

#### [x] Step 1. 實現 Silero VAD 服務
- **Goal**: 建立語音活動檢測服務，實現實時語音/靜音判斷
- **完成時間**: 2026-01-19
- **測試結果**: 12/12 passed in 1.78s
- **[詳細內容 →](./SPEC-voice-wake-word-backend.md#step1)**

#### [x] Step 2. 建立 openWakeWord KWS 服務
- **Goal**: 實現喚醒詞「嘿 Callisto」的檢測功能
- **完成時間**: 2026-01-19
- **測試結果**: 15/15 passed in 8.27s
- **[詳細內容 →](./SPEC-voice-wake-word-backend.md#step2)**

#### [x] Step 3. 音訊監聽協調服務
- **Goal**: 整合 VAD、KWS 和音訊緩衝區，實現完整的監聽邏輯
- **完成時間**: 2026-01-20
- **測試結果**: 20/20 passed in 11.37s
- **[詳細內容 →](./SPEC-voice-wake-word-backend.md#step3)**

#### [x] Step 4. WebSocket 端點實現
- **Goal**: 創建 WebSocket 端點接收音訊流並推送事件
- **完成時間**: 2026-01-20
- **測試結果**: 9/9 passed in 7.42s
- **[詳細內容 →](./SPEC-voice-wake-word-backend.md#step4)**

---

### 🎨 前端實現（待進行 ⏳）
詳細實施細節請查看 **[前端 SPEC](./SPEC-voice-wake-word-frontend.md)**

#### [ ] Step 5. 前端 Composable 實現
- **Goal**: 封裝語音監聽邏輯為可複用的 Composable
- **預計時間**: 1-2 小時
- **[詳細內容 →](./SPEC-voice-wake-word-frontend.md#step5)**

#### [ ] Step 6. 前端 UI 整合
- **Goal**: 在 VoiceRecorder 元件中新增監聽按鈕和狀態顯示
- **預計時間**: 1-2 小時
- **[詳細內容 →](./SPEC-voice-wake-word-frontend.md#step6)**

#### [ ] Step 7. 語音對話流程整合
- **Goal**: 整合 STT → LLM → TTS 完整流程，並推送進度事件
- **預計時間**: 2-3 小時
- **[詳細內容 →](./SPEC-voice-wake-word-frontend.md#step7)**

#### [ ] Step 8. 單元測試實現
- **Goal**: 為核心服務編寫完整的單元測試
- **預計時間**: 2-3 小時
- **[詳細內容 →](./SPEC-voice-wake-word-frontend.md#step8)**

#### [ ] Step 9. 整合測試與除錯
- **Goal**: 完整流程測試，確保所有模組協同工作
- **預計時間**: 2-3 小時
- **[詳細內容 →](./SPEC-voice-wake-word-frontend.md#step9)**

#### [ ] Step 10. 文件撰寫
- **Goal**: 更新技術文件和 API 說明
- **預計時間**: 1-2 小時
- **[詳細內容 →](./SPEC-voice-wake-word-frontend.md#step10)**

---

## 系統架構

### 音訊流程圖

```
前端                                          後端
┌─────────────────┐                    ┌──────────────────┐
│  MediaRecorder  │                    │   WebSocket      │
│  (16kHz mono)   │ ─── binary ───>    │   /ws/voice-    │
│  每 80-100ms    │      frames        │   monitor        │
└─────────────────┘                    └──────────────────┘
        ▲                                       │
        │                                       ▼
        │                              ┌──────────────────┐
        │                              │ AudioMonitor     │
        │                              │ Service          │
        │                              └──────────────────┘
        │                                 ┌───┴───┐
        │                                 │       │
        │                          ┌──────▼─┐  ┌─▼──────┐
        │                          │ Silero │  │ open   │
        │                          │  VAD   │  │ Wake   │
        │                          │ (並行) │  │ Word   │
        │                          └────────┘  └────────┘
        │                                 │
        │                                 ▼
        │                          協調判斷邏輯
        │                                 │
        │                     ┌───────────┼───────────┐
        │                     │           │           │
        └──── JSON ──────  靜音      語音事件    喚醒詞事件
              events         (不推送)               │
                                                    ▼
                                            STT → LLM → TTS
```

### 並行 VAD+KWS 架構

```
音訊塊 → ┌─────────────┐
         │ VAD 檢測    │ ─┐
         │ (驗證器)    │  │
         └─────────────┘  │
                          ├─→ 協調判斷 → 事件輸出
音訊塊 → ┌─────────────┐  │
         │ KWS 檢測    │ ─┘
         │ (持續運行)  │
         └─────────────┘

協調邏輯：
• KWS 檢測到 + VAD 確認語音 = 喚醒詞事件 ✅
• KWS 檢測到 + VAD 判斷靜音 = 忽略 (false alarm)
• 只有 VAD 檢測到語音 = 語音事件
• 都未檢測到 = 靜音
```

---

## 進度總覽

**總體進度**: 4/10 步驟完成 (40%)

| 步驟 | 狀態 | 完成時間 | 測試結果 |
|------|------|----------|----------|
| Step 1 - Silero VAD 服務 | ✅ | 2026-01-19 | 12/12 passed |
| Step 2 - openWakeWord KWS | ✅ | 2026-01-19 | 15/15 passed |
| Step 3 - AudioMonitorService | ✅ | 2026-01-20 | 20/20 passed |
| Step 4 - WebSocket 端點 | ✅ | 2026-01-20 | 9/9 passed |
| Step 5 - 前端 Composable | ⏳ | - | - |
| Step 6 - 前端 UI 整合 | ⏳ | - | - |
| Step 7 - 對話流程整合 | ⏳ | - | - |
| Step 8 - 單元測試 | ⏳ | - | - |
| Step 9 - 整合測試 | ⏳ | - | - |
| Step 10 - 文件撰寫 | ⏳ | - | - |

**後端**: ✅ 100% (56/56 tests passed)  
**前端**: ⏳ 0% (待開始)

---

## 快速連結

- 📘 [後端詳細規格](./SPEC-voice-wake-word-backend.md) - 包含測試記錄、Spec Amendments、實作細節
- 📗 [前端詳細規格](./SPEC-voice-wake-word-frontend.md) - 包含 Vue 3 實作、UI 設計、測試計畫
- 🏠 [返回總覽](#spec-語音喚醒功能總覽)

---

**建立日期**: 2026-01-19  
**最後更新**: 2026-01-20  
**當前狀態**: 後端完成，準備開始前端實施
