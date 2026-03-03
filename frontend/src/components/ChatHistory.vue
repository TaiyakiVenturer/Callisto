<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useVoiceChatStore } from '@/stores/voiceChat'

const store = useVoiceChatStore()
const chatContainer = ref<HTMLElement | null>(null)

// 自動滾動到最新訊息
watch(() => store.messages.length, async () => {
    await nextTick()
    if (chatContainer.value) {
        chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
})

// 格式化時間
const formatTime = (date: Date): string => {
    const hours = date.getHours().toString().padStart(2, '0')
    const minutes = date.getMinutes().toString().padStart(2, '0')
    return `${hours}:${minutes}`
}
</script>

<template>
    <div class="chat-history">
        <div class="header">
            <h2>對話記錄</h2>
            <button 
                v-if="store.messages.length > 0" 
                class="clear-button"
                @click="store.reset()"
            >
                清空
            </button>
        </div>
        
        <div class="messages" ref="chatContainer">
            <div 
                v-for="message in store.messages" 
                :key="message.id"
                class="message"
                :class="message.type"
            >
                <div class="bubble">
                    <p class="text">{{ message.text }}</p>
                    <span class="time">{{ formatTime(message.timestamp) }}</span>
                </div>
            </div>

            <div v-if="store.messages.length === 0" class="empty">
                <p>還沒有對話記錄</p>
                <p class="hint">按住按鈕開始說話吧 🎤</p>
            </div>
        </div>

        <!-- 錯誤提示 -->
        <div v-if="store.error" class="error-toast">
            ⚠️ {{ store.error }}
        </div>
    </div>
</template>

<style scoped>
.chat-history {
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100%;
    background: var(--color-bg-secondary);
    border-radius: 16px;
    overflow: hidden;
    position: relative;
}

.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.header h2 {
    font-size: 18px;
    font-weight: 600;
    color: var(--color-text);
    margin: 0;
}

.clear-button {
    padding: 6px 12px;
    border: none;
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.1);
    color: var(--color-text);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.2s;
}

.clear-button:hover {
    background: rgba(255, 255, 255, 0.2);
}

.messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.messages::-webkit-scrollbar {
    width: 6px;
}

.messages::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.2);
    border-radius: 3px;
}

.message {
    display: flex;
    animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(10px);
    }
    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.message.user {
    justify-content: flex-end;
}

.message.ai {
    justify-content: flex-start;
}

.bubble {
    max-width: 80%;
    padding: 12px 16px;
    border-radius: 16px;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.message.user .bubble {
    background: var(--color-accent-pink);
    color: var(--color-bg-primary);
    border-bottom-right-radius: 4px;
}

.message.ai .bubble {
    background: var(--color-accent-blue);
    color: var(--color-bg-primary);
    border-bottom-left-radius: 4px;
}

.text {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
    word-wrap: break-word;
}

.time {
    font-size: 11px;
    opacity: 0.7;
    text-align: right;
}

.empty {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 8px;
    color: var(--color-text);
    opacity: 0.5;
}

.empty p {
    margin: 0;
}

.hint {
    font-size: 12px;
}

.error-toast {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 12px 20px;
    background: rgba(255, 80, 80, 0.9);
    color: white;
    border-radius: 8px;
    font-size: 14px;
    animation: slideUp 0.3s ease;
    z-index: 10;
}

@keyframes slideUp {
    from {
        opacity: 0;
        transform: translate(-50%, 20px);
    }
    to {
        opacity: 1;
        transform: translate(-50%, 0);
    }
}
</style>
