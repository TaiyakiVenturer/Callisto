<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useVoiceChatStore } from '@/stores/voiceChat'
import { useVoiceRecorder } from '@/composables/useVoiceRecorder'
import { useStatusPolling } from '@/composables/useStatusPolling'
import { useVoiceMonitor } from '@/composables/useVoiceMonitor'
import { MonitorStatus } from '@/types/voice'

const store = useVoiceChatStore()
const { startPolling } = useStatusPolling()

// 語音監聽 Composable（包含自動錄音邏輯）
const {
    isMonitoring,
    isRecording: monitorIsRecording,  // 監聽模式的錄音狀態
    status: monitorStatus,
    error: monitorError,
    lastKeyword,
    transcript: monitorTranscript,
    aiResponse: monitorAiResponse,
    websocket,
    startMonitoring,
    stopMonitoring
} = useVoiceMonitor()

// 手動錄音 Composable（僅用於按鈕錄音）
const { isRecording: buttonIsRecording, startRecording, stopRecording, cancelRecording } = useVoiceRecorder()

// 統一的錄音狀態（監聽自動錄音 or 按鈕手動錄音）
const isRecording = computed(() => monitorIsRecording.value || buttonIsRecording.value)

// 按鈕錄音模式專用標記（輪詢 API 方式）
const hasAddedMessages = ref(false)
const hasAddedTranscript = ref(false)
const hasAddedResponse = ref(false)

// 監聽模式專用標記（watch WebSocket 事件方式）
const hasAddedMonitorTranscript = ref(false)
const hasAddedMonitorResponse = ref(false)

// 開始錄音（點擊模式 - 純手動控制）
const handleStartRecording = async () => {
    if (store.isProcessing || isMonitoring.value) {
        console.warn('⚠️ 正在處理中或監聽中，請稍候')
        return
    }

    store.setError(null)
    store.setState('thinking')
    hasAddedMessages.value = false
    hasAddedTranscript.value = false
    hasAddedResponse.value = false

    try {
        // ✅ 傳入 onRecordingComplete 回調，處理超時自動上傳後的輪詢
        await startRecording({
            onRecordingComplete: () => {
                console.log('📤 錄音已完成並上傳（超時觸發），開始輪詢狀態...')
                handlePolling()
            }
        })
    } catch (error) {
        console.error('❌ 錄音失敗:', error)
        store.setError(error instanceof Error ? error.message : '錄音失敗')
        store.setState('idle')
    }
}

// 開始輪詢狀態（提取為獨立函數，供手動傳送和超時自動上傳使用）
const handlePolling = () => {
    console.log('📤 音訊已上傳，開始輪詢狀態...')

    startPolling(
        // 處理完成
        (data) => {
            if (!hasAddedMessages.value) {
                hasAddedMessages.value = true
                
                if (data.transcript && !hasAddedTranscript.value) {
                    store.addMessage({
                        type: 'user',
                        text: data.transcript
                    })
                    hasAddedTranscript.value = true
                }

                if (data.response && !hasAddedResponse.value) {
                    store.addMessage({
                        type: 'ai',
                        text: data.response
                    })
                    hasAddedResponse.value = true
                }
                
                if (store.state !== 'speaking') {
                    store.setState('speaking')
                }
                
                setTimeout(() => {
                    store.setState('idle')
                }, 500)
            }
        },
        // 錯誤處理
        (error) => {
            store.setError(error)
            store.setState('idle')
        },
        // TTS 開始播放
        () => {
            console.log('🎵 切換到 speaking 狀態')
            store.setState('speaking')
        },
        // 實時更新
        (data) => {
            if (data.transcript && !hasAddedTranscript.value) {
                store.addMessage({
                    type: 'user',
                    text: data.transcript
                })
                hasAddedTranscript.value = true
            }
            
            if (data.response) {
                if (!hasAddedResponse.value) {
                    store.addMessage({
                        type: 'ai',
                        text: data.response
                    })
                    hasAddedResponse.value = true
                } else {
                    store.updateLastMessage(data.response)
                }
            }
        }
    )
}

// 手動傳送（提前結束）
const handleSendRecording = async () => {
    try {
        // 停止錄音並上傳
        await stopRecording()
        
        // 開始輪詢狀態
        handlePolling()
    } catch (error) {
        console.error('❌ 上傳失敗:', error)
        store.setError(error instanceof Error ? error.message : '上傳失敗')
        store.setState('idle')
    }
}

// 手動取消
const handleCancelRecording = () => {
    cancelRecording()
    store.setState('idle')
    console.log('❌ 已取消錄音')
}

// 語音監聽功能
const toggleMonitoring = async () => {
    if (isMonitoring.value) {
        stopMonitoring()
    } else {
        try {
            await startMonitoring()
        } catch (error) {
            console.error('❌ 啟動監聽失敗:', error)
        }
    }
}

// 計算狀態文字
const statusText = computed(() => {
    if (monitorError.value) return monitorError.value
    
    switch (monitorStatus.value) {
        case MonitorStatus.IDLE:
            return '待命中'
        case MonitorStatus.CONNECTING:
            return '等我一下喔...'
        case MonitorStatus.LISTENING:
            return '我在聽'
        case MonitorStatus.SPEECH:
            return '有人叫我嗎？'
        case MonitorStatus.KEYWORD:
            return `${lastKeyword.value}, 我聽到囉`
        case MonitorStatus.PROCESSING:
            return '思考中...'
        case MonitorStatus.SPEAKING:
            return '說話中'
        case MonitorStatus.ERROR:
            return '錯誤'
        default:
            return '未知狀態'
    }
})

// 計算狀態顏色
const statusColor = computed(() => {
    switch (monitorStatus.value) {
        case MonitorStatus.LISTENING:
            return '#4ade80'
        case MonitorStatus.SPEECH:
            return '#facc15'
        case MonitorStatus.KEYWORD:
            return '#a78bfa'
        case MonitorStatus.PROCESSING:
        case MonitorStatus.SPEAKING:
            return '#60a5fa'
        case MonitorStatus.ERROR:
            return '#f87171'
        default:
            return '#9ca3af'
    }
})

const isListeningActive = computed(() => 
    monitorStatus.value === MonitorStatus.LISTENING || 
    monitorStatus.value === MonitorStatus.SPEECH
)

const isKeywordActive = computed(() => 
    monitorStatus.value === MonitorStatus.KEYWORD
)

// ===== 監聽模式 WebSocket 事件處理 =====

// 監聽 keyword 事件，重置標記
watch(lastKeyword, (newKeyword) => {
    if (newKeyword) {
        console.log('🎯 檢測到喚醒詞，重置標記')
        hasAddedMonitorTranscript.value = false
        hasAddedMonitorResponse.value = false
    }
})

// 監聽 transcript 變化，添加到聊天列表
watch(monitorTranscript, (newTranscript) => {
    if (newTranscript && !hasAddedMonitorTranscript.value) {
        console.log('📝 監聽模式收到 transcript，添加到聊天列表:', newTranscript)
        store.addMessage({
            type: 'user',
            text: newTranscript
        })
        hasAddedMonitorTranscript.value = true
    }
})

// 監聽 aiResponse 變化，實時更新聊天列表
watch(monitorAiResponse, (newResponse) => {
    if (newResponse) {
        if (!hasAddedMonitorResponse.value) {
            console.log('🤖 監聽模式收到 AI 回應，添加到聊天列表')
            store.addMessage({
                type: 'ai',
                text: newResponse
            })
            hasAddedMonitorResponse.value = true
        } else {
            console.log('🤖 監聽模式更新 AI 回應')
            store.updateLastMessage(newResponse)
        }
    }
})

// 監聽 status 變化，更新 store 狀態
watch(monitorStatus, (newStatus, oldStatus) => {
    // SPEAKING 狀態
    if (newStatus === MonitorStatus.SPEAKING) {
        console.log('🎵 切換到 speaking 狀態')
        store.setState('speaking')
    }
    
    // 從 SPEAKING 回到 LISTENING（完成）
    if (oldStatus === MonitorStatus.SPEAKING && newStatus === MonitorStatus.LISTENING) {
        console.log('✅ 對話完成，恢復 idle 狀態')
        store.setState('idle')
    }
    
    // 從 PROCESSING 回到 LISTENING（無語音/靜音）
    if (oldStatus === MonitorStatus.PROCESSING && newStatus === MonitorStatus.LISTENING) {
        console.log('⚠️ 無有效語音，恢復 idle 狀態')
        store.setState('idle')
    }
    
    // PROCESSING 狀態
    if (newStatus === MonitorStatus.PROCESSING) {
        store.setState('thinking')
    }
})
</script>

<template>
    <div class="voice-recorder">
        <!-- 語音監聽按鈕 -->
        <div class="monitor-section">
            <button
                class="monitor-button"
                :class="{ 
                    active: isMonitoring,
                    disabled: isRecording || monitorStatus === MonitorStatus.PROCESSING || monitorStatus === MonitorStatus.SPEAKING
                }"
                :disabled="isRecording || monitorStatus === MonitorStatus.PROCESSING || monitorStatus === MonitorStatus.SPEAKING"
                @click="toggleMonitoring"
            >
                <span class="icon">{{ isMonitoring ? '🛑' : '👂' }}</span>
                <span class="text">
                    {{ isRecording ? '錄音中...' : (isMonitoring ? '停止監聽' : '持續監聽') }}
                </span>
            </button>
            
            <!-- 狀態指示器 -->
            <div 
                v-if="isMonitoring" 
                class="status-indicator"
                :class="{
                    'pulse': isListeningActive,
                    'flash': isKeywordActive
                }"
            >
                <div 
                    class="status-dot" 
                    :style="{ backgroundColor: statusColor }"
                ></div>
                <span class="status-text">{{ statusText }}</span>
            </div>
        </div>

        <!-- 錄音按鈕區域 -->
        <div class="recording-section">
            <!-- 錄音前：顯示「開始錄音」按鈕 -->
            <button
                v-if="!isRecording"
                class="record-button"
                :class="{ disabled: isMonitoring || store.isProcessing }"
                :disabled="isMonitoring || store.isProcessing"
                @click="handleStartRecording"
            >
                <span class="icon">🎤</span>
                <span class="text">
                    {{ isMonitoring ? '監聽中...' : '開始錄音' }}
                </span>
            </button>

            <!-- 錄音中：顯示「傳送」和「取消」按鈕 -->
            <div v-else class="recording-controls">
                <div class="recording-indicator">
                    <span class="recording-dot"></span>
                    <span class="recording-text">
                        {{ monitorIsRecording ? '錄音中（VAD 自動檢測）' : '錄音中（按下傳送完成）' }}
                    </span>
                </div>
                <div v-if="!monitorIsRecording" class="button-group">
                    <button @click="handleSendRecording" class="send-btn">
                        ✅ 傳送
                    </button>
                    <button @click="handleCancelRecording" class="cancel-btn">
                        ❌ 取消
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
.voice-recorder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 30px;
    padding: 20px;
}

/* 監聽功能區塊 */
.monitor-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
    width: 100%;
    max-width: 400px;
}

.monitor-button {
    display: flex;
    flex-direction: row;
    align-items: center;
    justify-content: center;
    gap: 12px;
    
    width: 180px;
    height: 60px;
    border-radius: 30px;
    border: 2px solid var(--color-accent-blue);
    background: var(--color-bg-secondary);
    
    color: var(--color-text);
    font-size: 16px;
    font-weight: 500;
    
    cursor: pointer;
    user-select: none;
    transition: all 0.2s ease;
}

.monitor-button:hover:not(.disabled) {
    transform: scale(1.05);
    border-color: var(--color-accent-pink);
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.3);
}

.monitor-button.active {
    background: var(--color-accent-blue);
    border-color: var(--color-accent-blue);
    color: white;
}

.monitor-button.disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.monitor-button .icon {
    font-size: 24px;
}

/* 狀態指示器 */
.status-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 20px;
    background: var(--color-bg-secondary);
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.status-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    transition: background-color 0.3s ease;
}

.status-text {
    font-size: 14px;
    color: var(--color-text);
}

/* 脈動動畫 */
@keyframes pulse {
    0%, 100% {
        opacity: 1;
        transform: scale(1);
    }
    50% {
        opacity: 0.6;
        transform: scale(1.2);
    }
}

.status-indicator.pulse .status-dot {
    animation: pulse 2s ease-in-out infinite;
}

/* 閃爍動畫 */
@keyframes flash {
    0%, 50%, 100% {
        opacity: 1;
    }
    25%, 75% {
        opacity: 0.3;
    }
}

.status-indicator.flash .status-dot {
    animation: flash 0.8s ease-in-out infinite;
}

/* 錄音區域 */
.recording-section {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 20px;
}

.record-button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    
    width: 160px;
    height: 160px;
    border-radius: 50%;
    border: 3px solid var(--color-accent-pink);
    background: var(--color-bg-secondary);
    
    color: var(--color-text);
    font-size: 16px;
    font-weight: 500;
    
    cursor: pointer;
    user-select: none;
    transition: all 0.2s ease;
}

.record-button:hover:not(.disabled) {
    transform: scale(1.05);
    border-color: var(--color-accent-blue);
    box-shadow: 0 8px 20px rgba(238, 187, 195, 0.3);
}

.record-button.disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

.record-button .icon {
    font-size: 48px;
}

.record-button .text {
    font-size: 14px;
}

/* 錄音控制區 */
.recording-controls {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 16px;
}

.recording-indicator {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 20px;
    background: var(--color-bg-secondary);
    border-radius: 20px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.recording-dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: #ef4444;
    animation: pulse 1.5s ease-in-out infinite;
}

.recording-text {
    font-size: 14px;
    color: var(--color-text);
}

.button-group {
    display: flex;
    gap: 16px;
}

.send-btn,
.cancel-btn {
    padding: 12px 24px;
    border-radius: 20px;
    border: none;
    font-size: 16px;
    font-weight: 500;
    cursor: pointer;
    user-select: none;
    transition: all 0.2s ease;
}

.send-btn {
    background: var(--color-accent-blue);
    color: white;
}

.send-btn:hover {
    transform: scale(1.05);
    box-shadow: 0 4px 12px rgba(96, 165, 250, 0.4);
}

.cancel-btn {
    background: var(--color-bg-secondary);
    color: var(--color-text);
    border: 2px solid rgba(255, 255, 255, 0.2);
}

.cancel-btn:hover {
    transform: scale(1.05);
    border-color: #ef4444;
    color: #ef4444;
}
</style>
