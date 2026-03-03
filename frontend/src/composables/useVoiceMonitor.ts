import { ref, type Ref } from 'vue'
import { MonitorStatus, type BackendEvent, type VoiceMonitorConfig } from '@/types/voice'
import { useVoiceRecorder } from './useVoiceRecorder'

export function useVoiceMonitor(config: VoiceMonitorConfig = {}) {
  // ===== 配置 =====
  const wsUrl = config.wsUrl || `${import.meta.env.VITE_API_BASE_URL.replace('http', 'ws')}/ws/voice-monitor`
  const maxReconnectAttempts = config.reconnectAttempts || 3
  const reconnectDelay = config.reconnectDelay || 1000
  const timeslice = config.timeslice || 80

  // ===== 響應式狀態 =====
  const isMonitoring: Ref<boolean> = ref(false)
  const status: Ref<MonitorStatus> = ref(MonitorStatus.IDLE)
  const error: Ref<string | null> = ref(null)
  const lastKeyword: Ref<string | null> = ref(null)
  const transcript: Ref<string> = ref('')
  const aiResponse: Ref<string> = ref('')

  // ===== 錄音整合 =====
  const { isRecording, startRecording, stopRecording } = useVoiceRecorder()

  // ===== 內部狀態 =====
  let websocket: WebSocket | null = null
  const websocketRef: Ref<WebSocket | null> = ref(null)  // 對外暴露的 ref
  let mediaRecorder: MediaRecorder | null = null
  let mediaStream: MediaStream | null = null
  let reconnectCount = 0
  let reconnectTimer: number | null = null
  let keywordLockTimer: number | null = null  // Keyword 狀態鎖定計時器

  // ===== WebSocket 處理 =====
  const connectWebSocket = (): Promise<void> => {
    return new Promise((resolve, reject) => {
      status.value = MonitorStatus.CONNECTING
      error.value = null

      try {
        websocket = new WebSocket(wsUrl)
        websocket.binaryType = 'arraybuffer'

        websocket.onopen = () => {
          console.log('[VoiceMonitor] WebSocket connected')
          reconnectCount = 0
          websocketRef.value = websocket  // 更新 ref
          resolve()
        }

        websocket.onmessage = (event) => {
          try {
            const backendEvent: BackendEvent = JSON.parse(event.data)
            handleBackendEvent(backendEvent)
          } catch (err) {
            console.error('[VoiceMonitor] Failed to parse event:', err)
          }
        }

        websocket.onerror = (err) => {
          console.error('[VoiceMonitor] WebSocket error:', err)
          error.value = 'WebSocket 連接錯誤'
          reject(new Error('WebSocket connection failed'))
        }

        websocket.onclose = () => {
          console.log('[VoiceMonitor] WebSocket closed')
          if (isMonitoring.value) {
            attemptReconnect()
          }
        }
      } catch (err) {
        console.error('[VoiceMonitor] Failed to create WebSocket:', err)
        error.value = 'WebSocket 創建失敗'
        reject(err)
      }
    })
  }

  const attemptReconnect = () => {
    if (reconnectCount >= maxReconnectAttempts) {
      console.error('[VoiceMonitor] Max reconnect attempts reached')
      error.value = '連接失敗，已達最大重試次數'
      stopMonitoring()
      return
    }

    reconnectCount++
    console.log(`[VoiceMonitor] Attempting reconnect (${reconnectCount}/${maxReconnectAttempts})...`)
    
    reconnectTimer = window.setTimeout(async () => {
      try {
        await connectWebSocket()
        if (mediaRecorder && mediaStream) {
          startMediaRecorder()
        }
      } catch (err) {
        console.error('[VoiceMonitor] Reconnect failed:', err)
      }
    }, reconnectDelay)
  }

  // ===== 麥克風處理 =====
  const getMicrophone = async (): Promise<MediaStream> => {
    try {
      // 請求麥克風（讓瀏覽器自動處理採樣率）
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      })
      return stream
    } catch (err: any) {
      console.error('[VoiceMonitor] Microphone access denied:', err)
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        throw new Error('麥克風權限被拒絕，請在瀏覽器設定中允許麥克風存取')
      } else if (err.name === 'NotFoundError') {
        throw new Error('找不到麥克風設備')
      } else {
        throw new Error('無法存取麥克風：' + err.message)
      }
    }
  }

  const startMediaRecorder = async () => {
    if (!mediaStream || !websocket) return

    try {
      // 創建 AudioContext（16kHz 採樣率）
      const audioContext = new AudioContext({ sampleRate: 16000 })
      const source = audioContext.createMediaStreamSource(mediaStream)
      
      // 使用 AudioWorklet（現代替代方案，取代已淘汰的 ScriptProcessorNode）
      // 加載 worklet 模組
      await audioContext.audioWorklet.addModule('/audio-processor.js')
      
      // 創建 AudioWorkletNode
      const workletNode = new AudioWorkletNode(audioContext, 'pcm-audio-processor')
      
      // 監聽來自 worklet 的訊息
      workletNode.port.onmessage = (event) => {
        if (websocket?.readyState === WebSocket.OPEN) {
          // 發送原始 PCM binary data
          websocket.send(event.data)
        }
      }

      // 連接音訊節點
      source.connect(workletNode)
      workletNode.connect(audioContext.destination)

      // 儲存引用以便清理
      ;(mediaStream as any).__audioContext = audioContext
      ;(mediaStream as any).__source = source
      ;(mediaStream as any).__workletNode = workletNode

      console.log('[VoiceMonitor] AudioContext started:', {
        sampleRate: audioContext.sampleRate,
        processor: 'AudioWorklet (modern)',
        chunkSize: '512 samples (32ms @ 16kHz)',
        bufferStrategy: 'Accumulate 4x128 samples before sending',
        state: audioContext.state
      })
    } catch (err: any) {
      console.error('[VoiceMonitor] Failed to start AudioContext:', err)
      error.value = '無法啟動音訊處理：' + err.message
      throw err
    }
  }

  // ===== 後端事件處理 =====
  const handleBackendEvent = (event: BackendEvent) => {
    switch (event.type) {
      case 'connected':
        status.value = MonitorStatus.LISTENING
        console.log('[VoiceMonitor] 已連接，開始監聽')
        break

      case 'keyword':
        status.value = MonitorStatus.KEYWORD
        lastKeyword.value = event.keyword || null
        transcript.value = ''
        aiResponse.value = ''
        console.log(`[VoiceMonitor] 檢測到喚醒詞: ${event.keyword}，自動開始錄音`)
        
        // 🎤 自動觸發錄音（啟用 VAD）
        handleAutoRecording()
        
        // 鎖定 KEYWORD 狀態 3 秒（防止被 speech 事件覆蓋）
        if (keywordLockTimer) {
          clearTimeout(keywordLockTimer)
        }
        keywordLockTimer = window.setTimeout(() => {
          if (status.value === MonitorStatus.KEYWORD) {
            status.value = MonitorStatus.LISTENING
          }
          keywordLockTimer = null
        }, 3000)
        break

      case 'speech':
        // 如果在 KEYWORD 鎖定期間，忽略 speech 事件
        if (keywordLockTimer) {
          break
        }
        status.value = MonitorStatus.SPEECH
        break

      case 'transcribing':
        status.value = MonitorStatus.PROCESSING
        break

      case 'transcript':
        transcript.value = event.text || ''
        break

      case 'generating':
        status.value = MonitorStatus.PROCESSING
        break

      case 'response':
        aiResponse.value = event.text || ''
        break

      case 'speaking':
        status.value = MonitorStatus.SPEAKING
        break

      case 'done':
        status.value = MonitorStatus.LISTENING
        break

      case 'error':
        status.value = MonitorStatus.ERROR
        error.value = event.message || '未知錯誤'
        console.warn('[VoiceMonitor] ⚠️ 收到錯誤事件:', event.message)
        // 注：後端會立即發送 done 事件，狀態會被覆蓋為 LISTENING
        break

      default:
        console.warn('[VoiceMonitor] Unknown event type:', event.type)
    }
    console.log('[VoiceMonitor] Event received:', event)
  }

  // ===== 自動錄音處理（喚醒詞觸發）=====
  const handleAutoRecording = async () => {
    if (isRecording.value) {
      console.warn('[VoiceMonitor] 已在錄音中，忽略喚醒詞')
      return
    }

    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      console.error('[VoiceMonitor] WebSocket 未連接，無法啟動自動錄音')
      return
    }

    try {
      console.log('[VoiceMonitor] 🎤 開始自動錄音（啟用 VAD）')
      
      // 啟動錄音（啟用 VAD）
      await startRecording({
        enableVAD: true,
        websocket: websocket,
        onVADStop: async () => {
          console.log('[VoiceMonitor] ✅ VAD 檢測到靜音，錄音完成')
          
          try {
            // 停止錄音並上傳
            await stopRecording()
            console.log('[VoiceMonitor] 📤 音訊已上傳，等待處理完成...')
            
            // 切換到處理中狀態
            status.value = MonitorStatus.PROCESSING
            console.log('[VoiceMonitor] 🤔 切換到處理中狀態')
            
            // 發送命令：啟動狀態追蹤
            if (websocket && websocket.readyState === WebSocket.OPEN) {
              websocket.send(JSON.stringify({ type: 'start_tracking' }))
              console.log('[VoiceMonitor] 🚀 已發送啟動追蹤命令')
            }
            
            // ✅ 不立即恢復監聽，等待後端發送 done 後自動恢復
            console.log('[VoiceMonitor] ⏳ 等待後端處理完成後自動恢復監聽')
          } catch (err) {
            console.error('[VoiceMonitor] ❌ 錄音上傳失敗:', err)
            error.value = '錄音上傳失敗'
          }
        }
      })
    } catch (err) {
      console.error('[VoiceMonitor] ❌ 自動錄音啟動失敗:', err)
      error.value = '自動錄音啟動失敗'
    }
  }

  // ===== 公開 API =====
  const startMonitoring = async () => {
    if (isMonitoring.value) {
      console.warn('[VoiceMonitor] Already monitoring')
      return
    }

    try {
      console.log('[VoiceMonitor] 開始監聽')
      
      error.value = null
      isMonitoring.value = true

      // 1. 獲取麥克風
      mediaStream = await getMicrophone()

      // 2. 連接 WebSocket
      await connectWebSocket()

      // 3. 開始錄音
      startMediaRecorder()
      
      console.log('[VoiceMonitor] 監聽已啟動')
    } catch (err: any) {
      console.error('[VoiceMonitor] Failed to start monitoring:', err)
      error.value = err.message || '啟動監聽失敗'
      isMonitoring.value = false
      status.value = MonitorStatus.ERROR
      
      // 清理資源
      cleanup()
      throw err
    }
  }

  const stopMonitoring = () => {
    if (!isMonitoring.value) {
      console.warn('[VoiceMonitor] Not monitoring')
      return
    }

    console.log('[VoiceMonitor] 停止監聽')
    isMonitoring.value = false
    
    // 主動關閉 WebSocket（避免等待超時）
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.close(1000, 'User stopped monitoring')  // 正常關閉
    }
    
    cleanup()
    status.value = MonitorStatus.IDLE
    
    console.log('[VoiceMonitor] 監聽已停止')
  }

  const cleanup = () => {
    console.log('[VoiceMonitor] Cleanup started')
    
    // 清理重連計時器
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    
    // 清理 keyword 鎖定計時器
    if (keywordLockTimer !== null) {
      clearTimeout(keywordLockTimer)
      keywordLockTimer = null
    }

    // 優先關閉 WebSocket（最重要）
    if (websocket) {
      if (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING) {
        try {
          websocket.close(1000, 'Cleanup')
          console.log('[VoiceMonitor] WebSocket closed')
        } catch (e) {
          console.warn('[VoiceMonitor] Failed to close WebSocket:', e)
        }
      }
      websocket = null
    }

    // 停止 AudioContext 處理
    if (mediaStream) {
      const audioContext = (mediaStream as any).__audioContext
      const source = (mediaStream as any).__source
      const workletNode = (mediaStream as any).__workletNode
      
      if (source) {
        try {
          source.disconnect()
        } catch (e) {
          console.warn('[VoiceMonitor] Failed to disconnect source:', e)
        }
      }
      if (workletNode) {
        try {
          workletNode.disconnect()
        } catch (e) {
          console.warn('[VoiceMonitor] Failed to disconnect workletNode:', e)
        }
      }
      if (audioContext && audioContext.state !== 'closed') {
        audioContext.close().catch((e: any) => {
          console.warn('[VoiceMonitor] Failed to close AudioContext:', e)
        })
      }
    }

    // 停止錄音（如果使用 MediaRecorder）
    if (mediaRecorder) {
      if (mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop()
      }
      mediaRecorder = null
    }

    // 關閉麥克風
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => {
        track.stop()
        console.log('[VoiceMonitor] Microphone track stopped')
      })
      mediaStream = null
    }

    reconnectCount = 0
    console.log('[VoiceMonitor] Cleanup completed')
  }

  // ===== 返回 API =====
  return {
    // 狀態
    isMonitoring,
    isRecording,  // 暴露錄音狀態
    status,
    error,
    lastKeyword,
    transcript,
    aiResponse,
    websocket: websocketRef,  // 暴露 websocket ref

    // 方法
    startMonitoring,
    stopMonitoring
  }
}
