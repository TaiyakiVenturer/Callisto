import { ref } from 'vue'
import type { ApiStatusResponse, ApiHealthResponse } from '@/types/chat'

export function useStatusPolling() {
    const isPolling = ref(false)
    const pollingInterval = ref<number | null>(null)
    const retryCount = ref(0)
    const maxRetries = 3
    const hasSpeaking = ref(false)  // 記錄是否已經進入 speaking 狀態

    // 開始輪詢狀態
    const startPolling = (
        onComplete: (data: ApiStatusResponse) => void,
        onError: (error: string) => void,
        onSpeaking?: () => void,  // 新增：當開始說話時的回調
        onDataUpdate?: (data: ApiStatusResponse) => void  // 新增：每次輪詢到資料時的回調（實時更新）
    ) => {
        if (isPolling.value) {
            console.warn('⚠️ 已在輪詢中，跳過')
            return
        }

        isPolling.value = true
        retryCount.value = 0
        hasSpeaking.value = false
        console.log('🔄 開始輪詢狀態...')

        pollingInterval.value = window.setInterval(async () => {
            try {
                // 查詢處理狀態（已整合 player 狀態）
                const response = await fetch(`${import.meta.env.VITE_API_BASE_URL}/api/status`)
                
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`)
                }

                const data: ApiStatusResponse = await response.json()
                
                // 重置重試計數
                retryCount.value = 0
                
                // 🔥 實時更新資料（不等 is_done）
                if (onDataUpdate) {
                    onDataUpdate(data)
                }
                
                // tts_done=False 表示 TTS 正在播放，切換到 speaking 狀態
                if (!hasSpeaking.value && onSpeaking && !data.tts_done) {
                    console.log('🎤 TTS 開始播放，切換到 speaking 狀態')
                    hasSpeaking.value = true
                    onSpeaking()
                }

                // 檢查是否完成
                if (data.is_done) {
                    console.log('✅ 處理完成:', data)
                    stopPolling()  // 先停止輪詢
                    onComplete(data)  // 再執行回調
                    return  // 確保不再繼續執行
                }
                else {
                    const status_message = !hasSpeaking.value ? '⏳ 處理中...' : '🎤 語音播放中...'
                    console.log(status_message)
                }
            }
            catch (error) {
                retryCount.value++
                console.error(`❌ 輪詢失敗 (${retryCount.value}/${maxRetries}):`, error)

                // 超過重試次數則停止
                if (retryCount.value >= maxRetries) {
                    stopPolling()
                    onError('無法獲取處理狀態，請檢查後端連線')
                }
            }
        }, 500)  // 每 500ms 輪詢一次
    }

    // 停止輪詢
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

    return {
        isPolling,
        startPolling,
        stopPolling
    }
}
