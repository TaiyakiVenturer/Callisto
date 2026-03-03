import { defineStore } from 'pinia'
import type { 
    VoiceChatState, 
    ChatMessage, 
    AppState 
} from '@/types/chat'

export const useVoiceChatStore = defineStore('voiceChat', {
    state: (): VoiceChatState => ({
        state: 'idle',
        messages: [],
        isProcessing: false,
        error: null
    }),

    getters: {
        currentState: (state): AppState => state.state,
        
        lastMessage: (state): ChatMessage | null => {
            const lastMsg = state.messages[state.messages.length - 1]
            return lastMsg ?? null
        },
        
        messageCount: (state): number => state.messages.length,
        
        hasError: (state): boolean => state.error !== null
    },

    actions: {
        setState(newState: AppState) {
            this.state = newState
            this.isProcessing = newState !== 'idle'
        },

        addMessage(message: Omit<ChatMessage, 'id' | 'timestamp'>) {
            const newMessage: ChatMessage = {
                ...message,
                id: Date.now().toString() + Math.random().toString(36),
                timestamp: new Date()
            }
            this.messages.push(newMessage)
        },

        updateLastMessage(text: string) {
            if (this.messages.length > 0) {
                const lastIndex = this.messages.length - 1
                const currentMessage = this.messages[lastIndex]
                this.messages[lastIndex] = {
                    id: currentMessage.id,
                    type: currentMessage.type,
                    timestamp: currentMessage.timestamp,
                    text: text
                }
            }
        },

        setError(error: string | null) {
            this.error = error
        },

        reset() {
            this.state = 'idle'
            this.messages = []
            this.isProcessing = false
            this.error = null
        }
    }
})
