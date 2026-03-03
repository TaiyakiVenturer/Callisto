<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import { useVoiceChatStore } from '@/stores/voiceChat'

const store = useVoiceChatStore()
const speakingFrame = ref(1)
let speakingInterval: number | null = null

// 根據狀態顯示對應的 PNG 圖片
const currentImage = computed(() => {
    switch (store.state) {
        case 'idle':
            return '/character-idle.png'
        case 'thinking':
            return '/character-thinking.png'
        case 'speaking':
            // 250ms 切換
            return speakingFrame.value === 1 
                ? '/character-speaking-1.png'
                : '/character-speaking-2.png'
        default:
            return '/character-idle.png'
    }
})

// 是否顯示漂浮動畫和聚光燈
const isFloating = computed(() => store.state === 'speaking')

// 監聽狀態變化，控制說話動畫
watch(() => store.state, (newState) => {
    if (newState === 'speaking') {
        // 開始說話動畫：250ms 切換圖片
        speakingInterval = window.setInterval(() => {
            speakingFrame.value = speakingFrame.value === 1 ? 2 : 1
        }, 250)
    }
    else {
        // 停止動畫
        if (speakingInterval !== null) {
            clearInterval(speakingInterval)
            speakingInterval = null
        }
        speakingFrame.value = 1
    }
})

// 清理計時器
onUnmounted(() => {
    if (speakingInterval !== null) {
        clearInterval(speakingInterval)
    }
})
</script>

<template>
    <div class="character-display">
        <!-- 聚光燈背景（只在說話時顯示） -->
        <div v-if="isFloating" class="spotlight"></div>
        
        <!-- PNG 角色圖片 -->
        <img 
            :src="currentImage" 
            :alt="`Character ${store.state}`"
            class="character-image" 
            :class="{ floating: isFloating }"
        />
    </div>
</template>

<style scoped>
.character-display {
    position: relative;
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: 100%;
    min-height: 400px;
}

.character-image {
    width: 100%;
    max-width: 600px;
    height: auto;
    user-select: none;
    position: relative;
    z-index: 2;
    transition: opacity 0.3s ease;
    filter: drop-shadow(0 10px 30px rgba(0, 0, 0, 0.5));
}

/* 上下漂浮動畫 */
.character-image.floating {
    animation: float 2s ease-in-out infinite;
}

@keyframes float {
    0%, 100% {
        transform: translateY(0);
    }
    50% {
        transform: translateY(-20px);
    }
}

/* 聚光燈效果 */
.spotlight {
    position: absolute;
    width: 1000px;
    height: 1000px;
    border-radius: 50%;
    background: radial-gradient(
        circle,
        rgba(238, 187, 195, 0.4) 0%,
        rgba(168, 216, 234, 0.3) 40%,
        transparent 70%
    );
    animation: spotlight 2s ease-in-out infinite;
    z-index: 1;
}

@keyframes spotlight {
    0%, 100% {
        opacity: 0.3;
        transform: scale(1);
    }
    50% {
        opacity: 0.6;
        transform: scale(1.1);
    }
}
</style>
