import { createRouter, createWebHistory } from 'vue-router'
import VoiceChatView from '@/views/VoiceChatView.vue'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        {
            path: '/',
            name: 'home',
            component: VoiceChatView
        }
    ],
})

export default router
