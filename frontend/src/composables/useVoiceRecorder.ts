import { ref } from 'vue'
import type { ApiUploadResponse } from '@/types/chat'

export interface VoiceRecorderOptions {
    enableVAD?: boolean          // 是否啟用 VAD 自動停止
    websocket?: WebSocket | null // 外部傳入的 WebSocket
    onVADStop?: () => void       // VAD 檢測到靜音的回調（監聽模式專用）
    onRecordingComplete?: () => void  // 錄音完成並上傳後的回調（錄音模式專用）
}

export function useVoiceRecorder() {
    const isRecording = ref(false)
    const mediaRecorder = ref<MediaRecorder | null>(null)
    const audioChunks = ref<Blob[]>([])
    const stream = ref<MediaStream | null>(null)

    // VAD 檢測相關
    let wsConnection: WebSocket | null = null
    let audioContext: AudioContext | null = null
    let workletNode: AudioWorkletNode | null = null
    let vadMessageHandler: ((event: MessageEvent) => void) | null = null
    let recordingTimeout: number | null = null
    let currentRecordingOptions: VoiceRecorderOptions | null = null

    // 開始錄音
    const startRecording = async (options?: VoiceRecorderOptions): Promise<boolean> => {
        // 保存當前錄音選項（用於超時處理）
        currentRecordingOptions = options || null
        
        try {
            // 1. 請求麥克風
            stream.value = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,  // 單聲道
                    sampleRate: 16000 // 16kHz
                }
            })

            // 2. MediaRecorder（用於保存音訊）
            mediaRecorder.value = new MediaRecorder(stream.value, {
                mimeType: 'audio/webm;codecs=opus'
            })
            audioChunks.value = []
            mediaRecorder.value.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.value.push(event.data)
                }
            }
            mediaRecorder.value.start()

            // 3. AudioWorklet（用於實時 VAD 檢測）
            if (options?.enableVAD && options?.websocket) {
                wsConnection = options.websocket

                // 檢查 WebSocket 狀態
                if (!wsConnection || wsConnection.readyState !== WebSocket.OPEN) {
                    console.warn('⚠️ WebSocket 未連接，無法啟用 VAD 自動檢測')
                    console.log('💡 提示：請先啟動「持續監聽」或手動使用「傳送」按鈕')
                    // 不啟用 VAD，但繼續錄音
                } else {
                    // 建立 AudioContext 與 Worklet
                    audioContext = new AudioContext({ sampleRate: 16000 })
                    const source = audioContext.createMediaStreamSource(stream.value)

                    await audioContext.audioWorklet.addModule('/audio-processor.js')
                    workletNode = new AudioWorkletNode(audioContext, 'pcm-audio-processor')

                    // Worklet 輸出 PCM → WebSocket
                    workletNode.port.onmessage = (event) => {
                        const pcmData = event.data // ArrayBuffer (int16)
                        if (wsConnection?.readyState === WebSocket.OPEN) {
                            wsConnection.send(pcmData)
                        }
                    }

                    source.connect(workletNode)
                    workletNode.connect(audioContext.destination)

                    // 監聽 VAD stop_recording 事件
                    vadMessageHandler = (event: MessageEvent) => {
                        try {
                            const data = JSON.parse(event.data)
                            if (data.type === 'stop_recording') {
                                console.log(
                                    `🛑 VAD 檢測到 ${data.silence_duration} 秒靜音，自動停止錄音`
                                )
                                stopRecording()
                                options.onVADStop?.()
                            }
                        } catch (e) {
                            // 忽略非 JSON 消息
                        }
                    }
                    wsConnection.addEventListener('message', vadMessageHandler)

                    // 發送命令：啟動 VAD 檢測模式
                    if (wsConnection.readyState === WebSocket.OPEN) {
                        wsConnection.send(JSON.stringify({ type: 'start_vad_only' }))
                        console.log('📡 已發送 VAD 檢測模式命令')
                    }
                }
            }

            // 4. 超時保護（30 秒）
            recordingTimeout = window.setTimeout(async () => {
                console.warn('⏰ 錄音超時 30 秒，自動停止')
                try {
                    await stopRecording()  // stopRecording 內部會調用 onRecordingComplete
                } catch (err) {
                    console.error('超時停止錄音失敗:', err)
                }
            }, 30000)

            isRecording.value = true
            console.log('🎤 開始錄音', options?.enableVAD ? '(啟用 VAD 自動檢測)' : '')
            return true
        } catch (error) {
            console.error('❌ 無法存取麥克風:', error)
            throw new Error('麥克風權限被拒絕或不可用')
        }
    }

    // 停止錄音並上傳
    const stopRecording = (): Promise<ApiUploadResponse> => {
        return new Promise((resolve, reject) => {
            if (!isRecording.value) {
                reject(new Error('未在錄音中'))
                return
            }

            // 清理超時
            if (recordingTimeout) {
                clearTimeout(recordingTimeout)
                recordingTimeout = null
            }

            if (!mediaRecorder.value) {
                reject(new Error('MediaRecorder 未初始化'))
                return
            }

            mediaRecorder.value.onstop = async () => {
                isRecording.value = false
                console.log('🛑 停止錄音')

                // 停止 AudioWorklet
                if (workletNode) {
                    workletNode.disconnect()
                    workletNode = null
                }
                if (audioContext) {
                    await audioContext.close()
                    audioContext = null
                }

                // 停止麥克風
                if (stream.value) {
                    stream.value.getTracks().forEach((track) => track.stop())
                    stream.value = null
                }

                // 清理 WebSocket 監聽器
                if (vadMessageHandler && wsConnection) {
                    wsConnection.removeEventListener('message', vadMessageHandler)
                    vadMessageHandler = null
                }

                // 建立 Blob 並上傳
                const audioBlob = new Blob(audioChunks.value, { type: 'audio/webm' })
                console.log(`📦 音訊大小: ${(audioBlob.size / 1024).toFixed(2)} KB`)

                try {
                    const response = await uploadAudio(audioBlob)
                    
                    // ✅ 上傳成功後觸發完成回調
                    if (currentRecordingOptions?.onRecordingComplete) {
                        currentRecordingOptions.onRecordingComplete()
                    }
                    
                    resolve(response)
                } catch (error) {
                    reject(error)
                }
            }

            mediaRecorder.value.stop()
        })
    }

    // 取消錄音（不上傳）
    const cancelRecording = () => {
        if (!isRecording.value) {
            return
        }

        console.log('❌ 取消錄音')

        // 清理超時
        if (recordingTimeout) {
            clearTimeout(recordingTimeout)
            recordingTimeout = null
        }

        // 停止 MediaRecorder
        if (mediaRecorder.value) {
            mediaRecorder.value.stop()
            mediaRecorder.value = null
        }

        // 停止 AudioWorklet
        if (workletNode) {
            workletNode.disconnect()
            workletNode = null
        }
        if (audioContext) {
            audioContext.close()
            audioContext = null
        }

        // 停止麥克風
        if (stream.value) {
            stream.value.getTracks().forEach((track) => track.stop())
            stream.value = null
        }

        // 清理 WebSocket 監聽器
        if (vadMessageHandler && wsConnection) {
            wsConnection.removeEventListener('message', vadMessageHandler)
            vadMessageHandler = null
        }

        // 清空音訊數據
        audioChunks.value = []
        isRecording.value = false
        
        // 清理選項
        currentRecordingOptions = null
    }

    // 上傳音訊到後端
    const uploadAudio = async (audioBlob: Blob): Promise<ApiUploadResponse> => {
        const formData = new FormData()
        formData.append('audio', audioBlob, 'recording.webm')

        try {
            const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/chat/voice`, {
                method: 'POST',
                body: formData
            })

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`)
            }

            const data: ApiUploadResponse = await response.json()
            console.log('✅ 音訊上傳成功:', data)
            return data
        } catch (error) {
            console.error('❌ 音訊上傳失敗:', error)
            throw new Error('無法連接到後端服務，請確認後端已啟動')
        }
    }

    return {
        isRecording,
        startRecording,
        stopRecording,
        cancelRecording
    }
}
