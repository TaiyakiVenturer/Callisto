# SPEC: AGC Audio Normalization for VAD

## Task Description
在 `silero_vad_service.py` 中整合 AGC（自動增益控制）功能，解決麥克風音量過小導致 KWS 無法正確偵測的問題。

**目標行為**：
- 接收小音量的音頻輸入（如 RMS -40dB）
- 動態放大至目標音量（RMS -18dB）
- 防止爆音（Limiter 限制在 -3dBFS）
- 不放大純雜音（僅對 VAD 判定為語音的片段應用 AGC）
- 平滑增益變化，避免突然跳變造成爆音

**使用場景**：
- 用戶麥克風靈敏度低或距離遠
- 環境音量小，導致 KWS 模型偵測失敗
- 實時語音流處理（32ms/512 samples, 16kHz mono 16bit）

## Tech Stack
- **numpy**：音頻數值處理（已有依賴，無需額外安裝）
- **演算法**：RMS 計算 + 動態增益調整 + Limiter

## Acceptance Criteria
- [x] 在 `SileroVADService` 類中新增 AGC 功能
- [x] AGC 可透過初始化參數啟用/停用（`enable_agc=True`）
- [x] 支援可調參數：目標 RMS（-18dB）、Limiter 閾值（-3dBFS）、最大增益（+20dB）、平滑係數（0.1）
- [x] 實現 RMS 計算函數
- [x] 實現動態增益調整（平滑變化）
- [x] 實現 Limiter 防爆音
- [x] AGC 應用於所有音頻（先 AGC → 後 VAD），噪音門限防止放大純雜音
- [x] 保持向後兼容（預設不啟用 AGC）
- [x] 單元測試覆蓋正常流程、邊界情況、錯誤處理

## Target Files
- 主文件：`backend/services/silero_vad_service.py`
- 測試文件：`backend/tests/test_silero_vad_service.py`（更新）

---

## Implementation

### [x] Step 1. 在 `__init__` 中新增 AGC 參數
**Goal**: 擴展初始化函數，接收 AGC 相關參數並初始化狀態變數
**Reason**: 讓用戶可以控制 AGC 功能的開啟與參數調整
**Implementation Details**:
- 修改 `SileroVADService.__init__` 函數簽名
- 新增參數：`enable_agc: bool = False`, `target_rms_db: float = -18.0`, `limiter_threshold_db: float = -3.0`, `max_gain_db: float = 20.0`, `smoothing_factor: float = 0.1`, `noise_gate_db: float = -50.0`
- 儲存參數為實例變數：`self.enable_agc`, `self.target_rms_db` 等
- 初始化平滑增益狀態：`self.current_gain_db = 0.0`
- 額外新增 `noise_gate_db` 參數用於噪音門限，低於此值不應用 AGC

### [x] Step 2. 實現 RMS 計算函數
**Goal**: 計算音頻片段的均方根音量（RMS），轉換為 dBFS 單位
**Reason**: RMS 反映人耳感知的平均響度，用於判斷當前音量水平
**Implementation Details**:
- 新增私有方法：`_calculate_rms_db(self, audio_float32: np.ndarray) -> float`
- 計算步驟：
  1. `rms = np.sqrt(np.mean(audio_float32 ** 2))`
  2. 處理 RMS 為 0 的情況（返回 -60.0dB，判斷條件 `rms < 1e-10`）
  3. 轉換為 dBFS：`rms_db = 20 * np.log10(rms)`
- 返回 float 型態，範圍通常在 -60dB 到 0dB 之間

### [x] Step 3. 實現動態增益計算函數
**Goal**: 根據當前 RMS 和目標 RMS 計算需要的增益，並平滑處理
**Reason**: 動態增益確保音量達到目標水平，平滑處理避免突然變化
**Implementation Details**:
- 新增私有方法：`_calculate_gain_db(self, current_rms_db: float) -> float`
- 計算目標增益：`target_gain = self.target_rms_db - current_rms_db`
- 限制最大增益：`target_gain = min(target_gain, self.max_gain_db)`
- 限制最小增益：`target_gain = max(target_gain, -10.0)`（避免過度壓縮）
- 平滑處理：`self.current_gain_db = (1 - smoothing_factor) * self.current_gain_db + smoothing_factor * target_gain`
- 返回平滑後的增益值
- 使用 exponential moving average 避免增益突變

### [x] Step 4. 實現 Limiter 函數
**Goal**: 限制音頻峰值不超過指定閾值，防止削波失真（爆音）
**Reason**: 放大後的音頻可能超過最大值，需要硬限制保護
**Implementation Details**:
- 新增私有方法：`_apply_limiter(self, audio_float32: np.ndarray) -> np.ndarray`
- 計算閾值：`threshold = 10 ** (self.limiter_threshold_db / 20)`（dB 轉線性）
- 使用 numpy clip：`np.clip(audio_float32, -threshold, threshold)`
- 返回限制後的音頻數據
- 預設閾值 -3dBFS 約等於 0.707 的線性值

### [x] Step 5. 實現完整 AGC 處理函數
**Goal**: 整合 RMS 計算、增益調整、Limiter，提供完整的 AGC 處理流程
**Reason**: 封裝完整邏輯，方便在 detect 函數中調用
**Implementation Details**:
- 新增私有方法：`_apply_agc(self, audio_float32: np.ndarray) -> np.ndarray`
- 處理流程：
  1. 計算當前 RMS dB
  2. 噪音門限檢查：如果 RMS < noise_gate_db，直接返回原音頻（不放大純雜音）
  3. 計算需要的增益 dB
  4. 轉換為線性增益：`linear_gain = 10 ** (gain_db / 20)`
  5. 應用增益：`amplified = audio_float32 * linear_gain`
  6. 應用 Limiter：`limited = self._apply_limiter(amplified)`
  7. 返回處理後的音頻
- 加入 debug logging 記錄 RMS 和增益變化

### [x] Step 6. 整合 AGC 到 `detect` 函數
**Goal**: 在 VAD 檢測流程中適當位置插入 AGC 處理
**Reason**: 確保音頻在進入 VAD 模型前已被正規化，提高偵測準確率
**Implementation Details**:
- 修改 `detect` 方法，在正規化為 float32 後、VAD 推理前插入 AGC
- 處理流程：
  1. 將 bytes 轉為 int16 array
  2. 正規化為 float32（-1 到 1）
  3. **如果 `enable_agc=True`，調用 `_apply_agc(audio_float32)`**
  4. 繼續執行 VAD 推理
- 確保 AGC 處理後的音頻仍在 [-1, 1] 範圍內（由 Limiter 保證）
- 保持錯誤處理邏輯不變

### [x] Step 7. 更新 `reset` 和 `get_stats` 方法
**Goal**: 重置時清空 AGC 狀態，狀態查詢時包含 AGC 資訊
**Reason**: 確保 AGC 狀態正確管理，方便除錯
**Implementation Details**:
- 在 `reset` 方法中添加：當 `enable_agc=True` 時重置 `self.current_gain_db = 0.0`
- 在 `get_stats` 方法返回值中添加 AGC 資訊：
  ```python
  stats["agc"] = {
      "enabled": True/False,
      "target_rms_db": self.target_rms_db,
      "limiter_threshold_db": self.limiter_threshold_db,
      "max_gain_db": self.max_gain_db,
      "current_gain_db": round(self.current_gain_db, 2),
      "noise_gate_db": self.noise_gate_db
  }
  ```

---

## Test Generate

### Test Plan
1. **正常功能測試**：
   - `test_agc_amplify_quiet_audio`：測試小音量音頻被正確放大
   - `test_agc_compress_loud_audio`：測試大音量音頻被適度壓縮
   - `test_agc_limiter_prevents_clipping`：測試 Limiter 防止爆音

2. **邊界情況測試**：
   - `test_agc_with_silence`：測試純靜音（RMS 極低）不造成異常
   - `test_agc_with_max_gain`：測試達到最大增益限制
   - `test_agc_disabled`：測試關閉 AGC 時音頻不變

3. **整合測試**：
   - `test_agc_with_vad_detection`：測試 AGC 與 VAD 配合運作
   - `test_agc_gain_smoothing`：測試增益平滑變化

4. **錯誤處理測試**：
   - `test_agc_with_invalid_parameters`：測試非法參數被正確拒絕

### Mock Strategy
- **不需要 Mock**：AGC 功能純數學運算，使用真實數據測試
- **測試音頻生成**：使用 numpy 生成不同音量的正弦波作為測試數據
- **VAD 模型**：使用真實 ONNX 模型（已在 test setup 中載入）

---

## Unit Test

### 測試套件
- **測試類別**：`TestAGCFeature`
- **測試文件**：`backend/tests/test_silero_vad_service.py`
- **總測試數**：11 個 AGC 測試 + 12 個原有 VAD 測試 = 23 個

### 第 1 次執行（2026-01-24）

**測試結果**：✅ **23 passed in 3.59s**

**測試涵蓋範圍**：
1. ✅ `test_agc_initialization` - AGC 初始化參數測試
2. ✅ `test_agc_amplify_quiet_audio` - 小音量放大測試
3. ✅ `test_agc_compress_loud_audio` - 大音量壓縮測試
4. ✅ `test_agc_limiter_prevents_clipping` - Limiter 防爆音測試
5. ✅ `test_agc_with_silence` - 靜音處理測試（噪音門限）
6. ✅ `test_agc_disabled` - AGC 關閉測試（向後兼容）
7. ✅ `test_agc_with_vad_detection` - AGC 與 VAD 整合測試
8. ✅ `test_agc_gain_smoothing` - 增益平滑變化測試
9. ✅ `test_agc_reset` - AGC 狀態重置測試
10. ✅ `test_agc_get_stats` - AGC 狀態查詢測試
11. ✅ `test_agc_with_max_gain_limit` - 最大增益限制測試

**測試覆蓋率**：
- 正常功能：放大、壓縮、Limiter、平滑
- 邊界情況：靜音、極大/極小音量、最大增益限制
- 整合測試：與 VAD 配合運作
- 狀態管理：初始化、重置、查詢
- 向後兼容：AGC 關閉時不影響原有功能

**關鍵驗證點**：
- ✅ 小音量音頻被正確放大（增益 > 0）
- ✅ Limiter 正確限制峰值（無爆音）
- ✅ 噪音門限防止放大純靜音
- ✅ 增益平滑變化（相鄰值差異 < 5dB）
- ✅ AGC 關閉時增益保持為 0
- ✅ 原有 12 個 VAD 測試全部通過（向後兼容）

---

## 使用說明

### 基本使用

**啟用 AGC（推薦用於麥克風音量小的場景）**：
```python
from services.silero_vad_service import SileroVADService

# 創建啟用 AGC 的 VAD 服務
vad = SileroVADService(
    threshold=0.5,           # VAD 閾值
    enable_agc=True,         # 啟用 AGC
    target_rms_db=-18.0,     # 目標音量（RMS）
    limiter_threshold_db=-3.0,  # 防爆音閾值
    max_gain_db=20.0,        # 最大增益限制
    smoothing_factor=0.1,    # 增益平滑係數（0-1，越小越平滑）
    noise_gate_db=-50.0      # 噪音門限（低於此值不放大）
)

# 使用
audio_chunk = ...  # 512 samples, 16-bit PCM
is_speech = vad.detect(audio_chunk)
```

**關閉 AGC（向後兼容，預設行為）**：
```python
vad = SileroVADService(threshold=0.5)  # enable_agc=False（預設）
```

### 在現有服務中整合

**更新 `voice_chat_service.py`（範例）**：
```python
# 修改前
self.vad_service = SileroVADService(threshold=0.5)

# 修改後（啟用 AGC）
self.vad_service = SileroVADService(
    threshold=0.5,
    enable_agc=True,
    target_rms_db=-18.0
)
```

### 調整參數建議

**場景 1：麥克風音量非常小**
```python
vad = SileroVADService(
    enable_agc=True,
    target_rms_db=-15.0,     # 提高目標音量
    max_gain_db=25.0         # 增加最大增益
)
```

**場景 2：環境噪音較多**
```python
vad = SileroVADService(
    enable_agc=True,
    threshold=0.6,           # 提高 VAD 閾值過濾噪音
    noise_gate_db=-45.0,     # 提高噪音門限
    target_rms_db=-20.0      # 降低目標音量避免放大噪音
)
```

**場景 3：需要快速響應（增益變化快）**
```python
vad = SileroVADService(
    enable_agc=True,
    smoothing_factor=0.3     # 提高平滑係數（0.1 → 0.3）
)
```

### 監控 AGC 狀態

```python
# 查看當前 AGC 狀態
stats = vad.get_stats()
print(stats["agc"])
# 輸出：
# {
#   "enabled": True,
#   "target_rms_db": -18.0,
#   "limiter_threshold_db": -3.0,
#   "max_gain_db": 20.0,
#   "current_gain_db": 12.5,  # 當前應用的增益
#   "noise_gate_db": -50.0
# }
```

---

## Spec Amendments

（實作過程中無需變更）

---
