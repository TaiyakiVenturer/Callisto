<script setup lang="ts">
import CharacterDisplay from '@/components/CharacterDisplay.vue'
import VoiceRecorder from '@/components/VoiceRecorder.vue'
import ChatHistory from '@/components/ChatHistory.vue'
</script>

<template>
    <div class="voice-chat-view">
        <!-- 左側：角色顯示 + 錄音按鈕 -->
        <div class="left-panel">
            <div class="character-container">
                <CharacterDisplay />
            </div>
            <VoiceRecorder />
        </div>

        <!-- 右側：對話記錄 -->
        <div class="right-panel">
            <ChatHistory />
        </div>
    </div>
</template>

<style scoped>
.voice-chat-view {
    display: flex;
    width: 100%;
    min-height: 100vh;
    background: var(--color-bg-primary);
    gap: 20px;
    padding: 20px;
    box-sizing: border-box;
}

.left-panel {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 20px;
}

.character-container {
    flex: 1;
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
}

.right-panel {
    flex: 0 0 400px;
    min-width: 300px;
    max-width: 500px;
    display: flex;
    height: calc(100vh - 40px);
}

/* 響應式設計 */
@media (max-width: 768px) {
    .voice-chat-view {
        flex-direction: column;
        padding: 10px;
    }

    .left-panel {
        flex: 0 0 auto;
        height: 60vh;
    }

    .right-panel {
        flex: 0 0 auto;
        height: 40vh;
    }
}
</style>
