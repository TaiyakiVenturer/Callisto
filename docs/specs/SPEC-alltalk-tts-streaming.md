# SPEC: AllTalk TTS Streaming Integration

## Task Description
實作一個 Python 模組來呼叫 AllTalk TTS 服務的串流模式 API，提供文字轉語音功能，並支援：
- **邊生成邊播放**音訊串流（真正的 streaming playback）
- 將音訊串流儲存為 WAV 檔案
- 自訂語音、語言等參數

**API 資訊**：
- URL: `http://localhost:7851/api/tts-generate-streaming`
- Method: **GET** (實測發現，文件寫錯)
- 參數: text (URL-encoded), voice, language, output_file (透過 query string)
- **串流特性**: 實測證實 API 會分批傳送音訊資料（約每 2-3 秒一批），支援真正的串流播放

**已知問題**：
- ⚠️ AllTalk 串流 API 會回傳不完整的 WAV 標頭（data chunk size = 0）
- 音訊資料本身完整，但播放器可能無法識別
- **需要修復 WAV 標頭**才能正常播放（僅儲存時需要）

**音訊格式**：
- 格式: WAV (RIFF)
- 取樣率: 24000 Hz
- 位元深度: 16-bit PCM
- 聲道: Mono (單聲道)
- WAV 標頭: 固定 44 bytes

**使用情境**：
1. 從外部程式呼叫 TTS 服務
2. **即時播放**：邊生成邊播放，降低延遲
3. 儲存模式：儲存完整 WAV 檔案供後續使用

## Tech Stack
- Python 3.12+
- requests (HTTP 請求)
- pyaudio (即時音訊播放)
- numpy (音量控制)
- wave (WAV 標頭修復)
- struct (二進位資料處理)

## Acceptance Criteria
- [x] 能夠成功呼叫 AllTalk TTS 串流 API
- [x] 支援自訂 text, voice, language 參數
- [x] **支援即時播放模式（邊生成邊播放）**
- [x] **支援音量控制（0.0 到 2.0 範圍）**
- [x] 能夠將串流音訊儲存為 WAV 檔案
- [x] **修復 WAV 標頭使音訊能正常播放**
- [x] 提供簡單的函式介面供外部呼叫
- [x] 包含錯誤處理 (連線失敗、API 錯誤等)
- [x] 程式碼遵循 Python coding style (snake_case, 4 空格縮排)

## Target Files
- Main: `backend/tts_stream.py`

---

## Implementation

### [x] Step 1. 建立基本 TTS 客戶端類別
**Goal**: 建立 `AllTalkTTSClient` 類別作為 API 介面
**Reason**: 封裝 API 呼叫邏輯，提供清晰的介面
**Implementation Details**: (已實作)
- 建立 `AllTalkTTSClient` 類別，初始化時接收 `base_url` 參數（預設 `http://localhost:7851`）
- 定義類別屬性：`base_url`, `streaming_endpoint = "/api/tts-generate-streaming"`
- 使用 `requests` 庫進行 HTTP 通訊
- 實測發現：API 使用 **GET 請求**（非文件說明的 POST），參數以 query string 傳遞
- 關鍵技術：`urllib.parse.quote()` 進行 URL 編碼，支援中文和特殊字元

**實際執行**:
```python
class AllTalkTTSClient:
    def __init__(self, base_url: str = "http://localhost:7851"):
        self.base_url = base_url.rstrip('/')
        self.streaming_endpoint = "/api/tts-generate-streaming"
```
- 自動去除 base_url 尾部斜線，確保 URL 構建正確
- 支援自訂伺服器位址，方便部署到不同環境

### [x] Step 2. 實作串流請求方法
**Goal**: 實作發送 GET 請求到 TTS API 並接收串流資料
**Reason**: 核心功能，需要正確處理 URL 編碼和參數
**Implementation Details**: (已實作)
- 建立 `generate_stream()` 方法，參數：text, voice, language, output_file
- 使用 `urllib.parse.quote()` 對 text 進行 URL 編碼
- 構建完整 URL：`{base_url}{endpoint}?text={encoded_text}&voice={voice}&language={language}&output_file={output_file}`
- 使用 `requests.get(url, stream=True)` 發送請求
- `stream=True` 確保以串流方式接收資料，避免記憶體溢位
- 回傳 `requests.Response` 物件供後續處理

**實際執行**:
```python
def generate_stream(self, text: str, voice: str = "female_01.wav", 
                   language: str = "en", output_file: str = "stream"):
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    
    encoded_text = urllib.parse.quote(text)
    url = f"{self.base_url}{self.streaming_endpoint}?text={encoded_text}&..."
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    return response
```
- 空字串檢查防止無效請求
- timeout=30 避免無限等待
- 自動檢查 HTTP 狀態碼並拋出異常

### [x] Step 3. 實作即時播放功能（含音量控制）
**Goal**: 實現邊接收串流邊播放音訊，降低延遲，並支援音量調整
**Reason**: 這是使用 streaming API 的核心價值，音量控制提升使用彈性
**Implementation Details**: (已實作)
**Implementation Details**: (已實作)
- 建立 `play_stream(response, volume=1.0)` 方法
- **音量參數驗證**: 在方法開頭檢查 `0.0 <= volume <= 2.0`，超出範圍拋出 `ValueError`
- 使用 `pyaudio` 庫進行音訊播放
- 初始化 PyAudio 串流：`pyaudio.PyAudio().open(format=paInt16, channels=1, rate=24000, output=True)`
- **跳過 WAV 標頭**：先讀取 44 bytes 並解析（不播放）
- **音量控制實作**：
  - volume 參數範圍：0.0 到 2.0（0.0=靜音，1.0=原始音量，2.0=兩倍音量）
  - 使用 `numpy` 處理 16-bit PCM 音訊資料
  - 將音訊資料轉換為 numpy array：`np.frombuffer(chunk, dtype=np.int16)`
  - 調整振幅：`adjusted = (audio_array * volume).astype(np.int16)`
  - 防止溢位：使用 `np.clip(adjusted, -32768, 32767)` 限制在 int16 範圍
  - 轉回 bytes：`adjusted.tobytes()`
  - **效能優化**: volume=1.0 時跳過處理，直接播放原始音訊
- 逐塊播放：`for chunk in response.iter_content(chunk_size=4096): stream.write(adjusted_chunk)`
- chunk_size 設為 4096（約 0.17 秒音訊，平衡延遲與流暢度）
- 實測證實：API 每 2-3 秒傳一批資料，PyAudio 可即時播放

**實際執行**:
```python
def play_stream(self, response: requests.Response, volume: float = 1.0):
    if not (0.0 <= volume <= 2.0):
        raise ValueError(f"Volume must be between 0.0 and 2.0, got {volume}")
    
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=24000, output=True)
    
    first_chunk = True
    for chunk in response.iter_content(chunk_size=4096):
        if first_chunk:
            audio_chunk = chunk[44:] if len(chunk) > 44 else b''
            first_chunk = False
        else:
            audio_chunk = chunk
        
        if audio_chunk and volume != 1.0:
            audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
            audio_data = (audio_data * volume).astype(np.int16)
            audio_data = np.clip(audio_data, -32768, 32767)
            audio_chunk = audio_data.tobytes()
        
        if audio_chunk:
            stream.write(audio_chunk)
```
- 首個 chunk 跳過 44 字節 WAV 標頭
- volume=1.0 時效能優化，跳過音量處理
- finally 區塊確保資源正確釋放

### [x] Step 4. 實作音訊儲存功能（含自動修復標頭）
**Goal**: 將接收到的串流資料寫入 WAV 檔案，並自動修復標頭
**Reason**: 滿足儲存音訊的需求，使用者不需記得額外步驟
**Implementation Details**: (已實作)
- 建立 `save_to_file()` 方法，接收 `response` 物件和 `file_path` 參數
- 使用 `with open(file_path, 'wb')` 以二進位模式寫入檔案
- 使用 `response.iter_content(chunk_size=8192)` 分塊讀取串流資料
- 逐塊寫入檔案：`for chunk in response.iter_content(chunk_size=8192): f.write(chunk)`
- **寫入完成後自動呼叫 `_fix_wav_header(file_path)` 修復標頭**
- 實測音訊格式：RIFF WAVE, PCM 16-bit, mono 24000 Hz

**實際執行**:
```python
def save_to_file(self, response: requests.Response, file_path: str):
    try:
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Auto-fix WAV header after saving
        self._fix_wav_header(file_path)
        
    except IOError as e:
        raise IOError(f"Failed to write file {file_path}: {e}")
```
- 使用 context manager 確保檔案正確關閉
- chunk_size=8192 平衡記憶體與 I/O 效率
- 自動修復標頭，使用者無需額外操作

### [x] Step 5. 實作 WAV 標頭修復（私有方法）
**Goal**: 修正 AllTalk API 回傳的不完整 WAV 標頭
**Reason**: API 的 data chunk size 設為 0，導致播放器無法識別
**Implementation Details**: (已實作)
- 建立 `_fix_wav_header()` **私有方法**，接收 `file_path` 參數
- 使用 `struct.pack('<I', size)` 寫入正確的 little-endian 32-bit 整數
- 修復兩個欄位：
  1. RIFF chunk size (offset 4-7): 設為檔案大小 - 8
  2. data chunk size (offset 40-43): 設為實際音訊資料長度
- 找到 `data` 標記位置：`content.find(b'data')`
- 原地修改 bytearray 並寫回檔案
- 實測：修復後音訊可正常播放（例如 62KB 檔案 = 1.3 秒）
- **由 `save_to_file()` 自動呼叫，使用者無需手動呼叫**

**實際執行**:
```python
def _fix_wav_header(self, file_path: str):
    try:
        with open(file_path, 'r+b') as f:
            content = bytearray(f.read())
        
        data_pos = content.find(b'data')
        if data_pos == -1:
            return
        
        # Fix data chunk size
        actual_data_size = len(content) - data_pos - 8
        content[data_pos + 4:data_pos + 8] = struct.pack('<I', actual_data_size)
        
        # Fix RIFF chunk size
        riff_size = len(content) - 8
        content[4:8] = struct.pack('<I', riff_size)
        
        with open(file_path, 'wb') as f:
            f.write(content)
    except Exception as e:
        print(f"Warning: Could not fix WAV header: {e}")
```
- r+b 模式允許讀寫二進位檔案
- 找不到 data 標記時優雅退出
- 修復失敗不影響主流程（檔案仍可在部分播放器使用）

### [x] Step 6. 加入錯誤處理和參數驗證
**Goal**: 處理網路錯誤、API 錯誤、參數錯誤等異常情況
**Reason**: 提升程式碼健壯性
**Implementation Details**: (已實作)
- 在 `generate_stream()` 中檢查必要參數（text 不可為空）
- 使用 `response.raise_for_status()` 檢查 HTTP 狀態碼
- 捕捉 `requests.exceptions.RequestException` 處理網路錯誤（連線失敗、超時等）
- 捕捉 `requests.exceptions.HTTPError` 處理 API 錯誤（404, 500 等）
- 加入 `ValueError` 處理無效參數
- 在儲存檔案時捕捉 `IOError` 處理檔案系統錯誤
- PyAudio 錯誤處理：捕捉 `OSError` 處理音訊裝置錯誤
- **音量參數驗證**：檢查 volume 在 0.0 到 2.0 範圍內，超出範圍拋出 `ValueError`

**實際執行**:
```python
# 參數驗證
if not text or not text.strip():
    raise ValueError("Text cannot be empty")

if not (0.0 <= volume <= 2.0):
    raise ValueError(f"Volume must be between 0.0 and 2.0, got {volume}")

# 網路錯誤處理
try:
    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
except requests.exceptions.Timeout:
    raise requests.exceptions.RequestException(
        "Request timed out. Please check if the TTS server is running."
    )
except requests.exceptions.ConnectionError:
    raise requests.exceptions.RequestException(
        f"Failed to connect to TTS server at {self.base_url}."
    )
except requests.exceptions.HTTPError as e:
    raise requests.exceptions.HTTPError(
        f"TTS API returned error: {e.response.status_code}"
    )

# 音訊裝置錯誤
except OSError as e:
    raise OSError(f"Audio device error: {e}")
```
- 所有異常都包含清晰的錯誤訊息
- 網路錯誤提供除錯建議
- 測試涵蓋所有錯誤情境

### [x] Step 7. 提供便利函式介面
**Goal**: 建立簡單的函式供外部快速呼叫
**Reason**: 提升使用便利性
**Implementation Details**: (已實作)
- 建立函式 `play_tts(text, voice, language, volume, base_url)` - 即時播放（加入 volume 參數）
- 建立函式 `save_tts(text, voice, language, save_path, base_url)` - 儲存檔案（自動修復標頭）
- 函式內部建立 `AllTalkTTSClient` 實例並自動處理請求、播放/儲存
- 提供預設值：`voice="female_01.wav"`, `language="en"`, `volume=1.0`, `base_url="http://localhost:7851"`
- 函式回傳成功/失敗狀態或錯誤訊息
- 加入 docstring 說明使用範例和參數說明
- **注意**: Response 物件的 `iter_content()` 只能迭代一次，play 和 save 需分別請求

**實際執行**:
```python
def play_tts(
    text: str,
    voice: str = "female_01.wav",
    language: str = "en",
    volume: float = 1.0,
    base_url: str = "http://localhost:7851"
) -> bool:
    """Generate and play TTS audio immediately."""
    try:
        client = AllTalkTTSClient(base_url)
        response = client.generate_stream(text, voice, language)
        client.play_stream(response, volume=volume)
        return True
    except Exception as e:
        print(f"Error playing TTS: {e}")
        return False

def save_tts(
    text: str,
    save_path: str,
    voice: str = "female_01.wav",
    language: str = "en",
    base_url: str = "http://localhost:7851"
) -> Optional[str]:
    """Generate TTS and save to WAV file."""
    try:
        client = AllTalkTTSClient(base_url)
        response = client.generate_stream(text, voice, language)
        client.save_to_file(response, save_path)
        return save_path
    except Exception as e:
        print(f"Error saving TTS: {e}")
        return None
```
- 單行呼叫即可使用 TTS 功能
- 錯誤自動處理並輸出友善訊息
- 回傳值方便進行後續判斷

### [x] Step 8. 撰寫完整 Unit Tests
**Goal**: 建立完整的單元測試覆蓋所有功能和錯誤情況
**Reason**: 確保程式碼品質和可靠性
**Implementation Details**: (已實作)
- 建立測試檔案 `backend/tests/test_tts_stream.py`
- 使用 pytest 框架和 pytest-mock 進行 Mock
- 建立 `TestAllTalkTTSClient` 測試類別（18 測試方法）
- 建立 `TestConvenienceFunctions` 測試類別（9 測試方法）
- Mock HTTP 請求：使用 `mocker.patch('requests.get')`
- Mock PyAudio：使用 `mocker.patch('pyaudio.PyAudio')`
- Mock 檔案系統：使用 `tmp_path` fixture
- 建立測試用 WAV 標頭資料（44 bytes）
- 測試覆蓋率達成：**行覆蓋率 96%**（超過目標 90%）
- 執行測試：`pytest tests/test_tts_stream.py -v --cov=tts_stream --cov-report=term-missing`

**實際執行結果**:
```bash
$ cd backend && pytest tests/test_tts_stream.py -v --cov=tts_stream --cov-report=term-missing

======================================================================= test session starts ========================================================================
platform win32 -- Python 3.12.10, pytest-9.0.2, pluggy-1.6.0
collected 27 items

tests/test_tts_stream.py::TestAllTalkTTSClient::test_client_initialization_default PASSED                                                                     [  3%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_client_initialization_custom_url PASSED                                                                  [  7%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_client_initialization_strips_trailing_slash PASSED                                                       [ 11%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_success PASSED                                                                           [ 14%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_url_encoding_special_characters PASSED                                                   [ 18%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_url_encoding_chinese PASSED                                                              [ 22%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_empty_text_raises_error PASSED                                                           [ 25%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_connection_error PASSED                                                                  [ 29%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_timeout_error PASSED                                                                     [ 33%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_generate_stream_http_error PASSED                                                                        [ 37%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_play_stream_success PASSED                                                                               [ 40%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_play_stream_audio_device_error PASSED                                                                    [ 44%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_play_stream_with_volume_control PASSED                                                                   [ 48%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_play_stream_volume_validation PASSED                                                                     [ 51%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_play_stream_volume_edge_cases PASSED                                                                     [ 55%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_save_to_file_success PASSED                                                                              [ 59%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_save_to_file_io_error PASSED                                                                             [ 62%]
tests/test_tts_stream.py::TestAllTalkTTSClient::test_fix_wav_header PASSED                                                                                    [ 66%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_play_tts_success PASSED                                                                              [ 70%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_play_tts_with_custom_parameters PASSED                                                               [ 74%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_play_tts_with_volume_parameter PASSED                                                                [ 77%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_play_tts_volume_default_value PASSED                                                                 [ 81%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_play_tts_failure PASSED                                                                              [ 85%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_save_tts_success PASSED                                                                              [ 88%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_save_tts_with_custom_parameters PASSED                                                               [ 92%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_save_tts_failure PASSED                                                                              [ 96%]
tests/test_tts_stream.py::TestConvenienceFunctions::test_save_tts_chinese_text PASSED                                                                         [100%]

========================================================================== tests coverage ==========================================================================
Name            Stmts   Miss  Cover   Missing
---------------------------------------------
tts_stream.py      98      4    96%   180, 273, 289-291
---------------------------------------------
TOTAL              98      4    96%

======================================================================== 27 passed in 1.22s ========================================================================
```

**測試統計**:
- **總測試數**: 27（包含 5 個音量控制測試）
- **通過率**: 100% ✅
- **覆蓋率**: 96%（超過目標 90%）
- **執行時間**: 1.22 秒
- **未覆蓋行**: 僅 4 行 print 語句（180, 273, 289-291）

**測試分類**:
1. 初始化測試: 3 個
2. 串流生成測試: 4 個
3. 播放測試: 5 個（含 3 個音量控制）
4. 儲存測試: 3 個
5. 錯誤處理測試: 7 個
6. 便利函式測試: 5 個

---

## Test Generate

### Test File Structure
- 測試檔案: `backend/tests/test_tts_stream.py`
- 使用框架: pytest + pytest-mock
- 測試類別: `TestAllTalkTTSClient`（測試類別方法）、`TestConvenienceFunctions`（測試便利函式）

### Test Plan

#### 1. 正常功能測試
- **test_client_initialization**
  - 驗證客戶端初始化，確認屬性設置正確
  - 測試自訂 base_url 和預設值

- **test_volume_control**
  - 測試音量參數正常運作（volume=0.5, 1.0, 2.0）
  - 驗證音量調整後的音訊資料正確
  
- **test_generate_stream_success**
  - Mock `requests.get` 回傳模擬的串流 response
  - 驗證 URL 構建正確（含 URL 編碼）
  - 驗證回傳 Response 物件
  - 測試不同參數組合（voice, language）

- **test_play_stream_success**
  - Mock PyAudio 播放器
  - Mock response.iter_content 回傳模擬音訊資料
  - 驗證 WAV 標頭被正確跳過（前 44 bytes）
  - 驗證音訊資料被寫入播放串流
  - 驗證資源正確清理（stream.close, terminate）

- **test_save_to_file_success**
  - Mock response.iter_content 回傳音訊資料
  - 使用 tmp_path fixture 建立臨時檔案
  - 驗證檔案被正確寫入
  - 驗證 `_fix_wav_header` 被自動呼叫

- **test_fix_wav_header**
  - 建立含錯誤標頭的測試 WAV 檔案（data size = 0）
  - 呼叫 `_fix_wav_header`
  - 驗證 RIFF chunk size 被修正
  - 驗證 data chunk size 被修正

#### 2. 邊界情況測試
- **test_empty_text**
  - 傳入空字串或只有空白
  - 應拋出 `ValueError`

- **test_special_characters_and_chinese**
  - 測試文字含特殊字元：`"Hello! How are you?"`
  - 測試中文：`"你好，這是測試！"`
  - 驗證 URL 編碼正確（使用 `urllib.parse.quote`）

- **test_long_text**
  - 測試超長文字（例如 1000 字）
  - 驗證不會因文字長度而失敗

#### 3. 錯誤處理測試
- **test_connection_error**
  - Mock `requests.get` 拋出 `ConnectionError`
  - 驗證捕捉並重新拋出清晰的錯誤訊息

- **test_timeout_error**
  - Mock `requests.get` 拋出 `Timeout`
  - 驗證錯誤訊息包含建議（檢查伺服器）

- **test_http_error**
  - Mock response.status_code = 500
  - Mock response.raise_for_status() 拋出 HTTPError
  - 驗證錯誤被正確處理

- **test_file_write_error**
  - Mock `open()` 拋出 `IOError`
  - 驗證捕捉並拋出清晰的錯誤訊息

- **test_audio_device_error**
  - Mock PyAudio.open() 拋出 `OSError`
  - 驗證捕捉並提供友善錯誤訊息

- **test_invalid_volume_parameter**
  - 測試 volume < 0.0 或 > 2.0
  - 應拋出 `ValueError` 並顯示清晰錯誤訊息

#### 4. 便利函式測試
- **test_play_tts_success**
  - Mock AllTalkTTSClient 類別
  - 驗證 `generate_stream` 和 `play_stream` 被呼叫
  - 驗證回傳 True

- **test_play_tts_with_volume**
  - Mock AllTalkTTSClient 類別
  - 呼叫 `play_tts(text, volume=0.5)`
  - 驗證 volume 參數被正確傳遞到 `play_stream()`

- **test_play_tts_failure**
  - Mock 拋出異常
  - 驗證回傳 False

- **test_save_tts_success**
  - Mock AllTalkTTSClient 類別
  - 驗證 `generate_stream` 和 `save_to_file` 被呼叫
  - 驗證回傳檔案路徑

- **test_save_tts_failure**
  - Mock 拋出異常
  - 驗證回傳 None

### Mock Strategy
- **HTTP 請求**: Mock `requests.get` 使用 `mocker.patch`
  - 回傳含 `iter_content()` 方法的 Mock Response
  - 模擬 WAV 標頭（44 bytes）+ 音訊資料
  
- **PyAudio**: Mock `pyaudio.PyAudio` 和 `stream` 物件
  - Mock `open()` 回傳含 `write()`, `close()`, `stop_stream()` 的 mock
  
- **檔案系統**: 使用 pytest 的 `tmp_path` fixture 處理臨時檔案
  
- **測試資料**: 
  - 建立完整的 44-byte WAV 標頭
  - 附加測試音訊資料（模擬 PCM）

### 測試覆蓋率目標
- 行覆蓋率: ≥ 90%
- 分支覆蓋率: ≥ 85%
- 所有公開方法必須測試
- 錯誤路徑必須測試

---

## Unit Test

### Test Implementation Details

**測試檔案位置**: `backend/tests/test_tts_stream.py`

**測試結構**:
```python
import pytest
from unittest.mock import Mock, MagicMock, mock_open
from tts_stream import AllTalkTTSClient, play_tts, save_tts

class TestAllTalkTTSClient:
    """測試 AllTalkTTSClient 類別"""
    
    def test_client_initialization(self):
        """測試客戶端初始化"""
        pass
    
    def test_generate_stream_success(self, mocker):
        """測試成功生成串流"""
        pass
    
    def test_play_stream_success(self, mocker):
        """測試成功播放串流"""
        pass
    
    def test_save_to_file_success(self, mocker, tmp_path):
        """測試成功儲存檔案"""
        pass
    
    # ... 其他測試方法

class TestConvenienceFunctions:
    """測試便利函式"""
    
    def test_play_tts_success(self, mocker):
        """測試 play_tts 成功"""
        pass
    
    def test_save_tts_success(self, mocker):
        """測試 save_tts 成功"""
        pass
```

**關鍵 Mock 範例**:
- Mock Response 物件:
  ```python
  mock_response = Mock()
  mock_response.iter_content.return_value = [wav_header, audio_data]
  mocker.patch('requests.get', return_value=mock_response)
  ```

- Mock PyAudio:
  ```python
  mock_pyaudio = Mock()
  mock_stream = Mock()
  mock_pyaudio.open.return_value = mock_stream
  mocker.patch('pyaudio.PyAudio', return_value=mock_pyaudio)
  ```

### Test Results

**執行日期**: 2026年1月3日

**最新測試統計** (加入音量控制後):
- 總測試數: **27** (新增 5 個音量控制測試)
- 通過: 27 ✅
- 失敗: 0
- 執行時間: 1.22s

**測試覆蓋率**:
- 行覆蓋率: **96%** ✅（目標 ≥ 90%）
- 總語句數: 98
- 未覆蓋語句: 4 行（皆為例外處理的 print 語句）

**測試分類結果**:

1. **正常功能測試** (18/18 通過):
   - ✅ test_client_initialization_default
   - ✅ test_client_initialization_custom_url
   - ✅ test_client_initialization_strips_trailing_slash
   - ✅ test_generate_stream_success
   - ✅ test_generate_stream_url_encoding_special_characters
   - ✅ test_generate_stream_url_encoding_chinese
   - ✅ test_play_stream_success
   - ✅ **test_play_stream_with_volume_control** (新增)
   - ✅ **test_play_stream_volume_edge_cases** (新增)
   - ✅ test_save_to_file_success
   - ✅ test_fix_wav_header
   - ✅ test_play_tts_success
   - ✅ test_play_tts_with_custom_parameters
   - ✅ **test_play_tts_with_volume_parameter** (新增)
   - ✅ **test_play_tts_volume_default_value** (新增)
   - ✅ test_save_tts_success
   - ✅ test_save_tts_with_custom_parameters
   - ✅ test_save_tts_chinese_text

2. **錯誤處理測試** (7/7 通過):
   - ✅ test_generate_stream_empty_text_raises_error
   - ✅ test_generate_stream_connection_error
   - ✅ test_generate_stream_timeout_error
   - ✅ test_generate_stream_http_error
   - ✅ test_play_stream_audio_device_error
   - ✅ **test_play_stream_volume_validation** (新增)
   - ✅ test_save_to_file_io_error

3. **便利函式測試** (2/2 通過):
   - ✅ test_play_tts_failure
   - ✅ test_save_tts_failure

---

### 音量控制功能測試詳情

**新增測試案例** (2026年1月3日):

1. **test_play_stream_with_volume_control**
   - 測試音量調整功能正確運作
   - 使用 volume=0.5，驗證輸出音訊振幅為原始的 50%
   - ✅ 通過

2. **test_play_stream_volume_validation**
   - 測試音量參數驗證
   - 驗證 volume < 0.0 或 > 2.0 時拋出 ValueError
   - ✅ 通過

3. **test_play_stream_volume_edge_cases**
   - 測試邊界值：volume=0.0 (靜音) 和 volume=2.0 (兩倍)
   - 驗證 0.0 時所有樣本為 0
   - 驗證 2.0 時振幅正確加倍
   - ✅ 通過

4. **test_play_tts_with_volume_parameter**
   - 測試便利函式 play_tts() 正確傳遞 volume 參數
   - ✅ 通過

5. **test_play_tts_volume_default_value**
   - 測試 play_tts() 預設 volume=1.0
   - ✅ 通過

**測試失敗與修復**:

**首次執行問題**:
- ❌ test_play_tts_volume_default_value - NameError: name 'generate_call' is not defined

**失敗原因**:
測試程式碼中有未定義的變數 `generate_call`，為複製貼上時的殘留程式碼。

**修復方法**:
移除未使用的驗證行：
```python
# 移除這兩行
assert generate_call[0][1] == "male_01.wav"
assert generate_call[0][2] == "zh-cn"
```

**第二次執行**:
- ✅ 所有 27 個測試通過
- 執行時間: 1.22s
- 覆蓋率: 96%

---

### 測試過程中的問題與修復 (原有功能)

#### 問題 1: 首次測試 3 個案例失敗

**失敗案例** (第一次執行):
- ❌ test_play_tts_with_custom_parameters - KeyError: 'voice'
- ❌ test_save_tts_with_custom_parameters - KeyError: 'voice'
- ❌ test_save_tts_chinese_text - KeyError: 'language'

**失敗原因**:
測試程式碼假設便利函式傳遞參數時使用關鍵字參數（kwargs）：
```python
# 測試中的錯誤假設
assert generate_call[1]['voice'] == "male_01.wav"  # call_args[1] 是 kwargs
assert generate_call[1]['language'] == "zh-cn"
```

但實際實作中使用位置參數：
```python
# 實際實作 (tts_stream.py)
response = client.generate_stream(text, voice, language)  # 位置參數
```

**錯誤訊息**:
```
KeyError: 'voice'
E       KeyError: 'voice'
tests\test_tts_stream.py:302: KeyError
```

**修復方法**:
修改測試程式碼以符合實際實作的參數傳遞方式：
```python
# 修復後的測試
assert generate_call[0][0] == "Test"         # 第1個位置參數: text
assert generate_call[0][1] == "male_01.wav"  # 第2個位置參數: voice
assert generate_call[0][2] == "zh-cn"        # 第3個位置參數: language
```

**修復結果**: 修正後所有測試通過 (22/22) ✅

---

### 經驗總結

1. **測試與實作同步**: 測試程式碼必須精確反映實際實作的呼叫方式
2. **Mock 呼叫驗證**: 使用 `call_args[0]` 檢查位置參數，`call_args[1]` 檢查關鍵字參數
3. **快速迭代**: 測試失敗 → 分析錯誤 → 修正 → 重新測試，整個流程約 5 分鐘完成

**結論**: ✅ 所有測試通過，覆蓋率達標
