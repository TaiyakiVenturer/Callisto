// 對話訊息類型
export interface ChatMessage {
    id: string
    type: 'user' | 'ai'
    text: string
    timestamp: Date
}

// 應用狀態類型
export type AppState = 'idle' | 'thinking' | 'speaking'

// API 狀態回應
export interface ApiStatusResponse {
    is_done: boolean
    transcript: string
    response: string
    error: string | null
    tts_done: boolean  // False = TTS 播放中，True = 未在播放
}

// API 健康檢查回應
export interface ApiHealthResponse {
    status: string
    message: string
    services?: {
        groq?: { status: string; using_model?: string }
        tts?: { status: string }
        stt?: { status: string; model?: string }
    }
    processing?: {
        is_done: boolean
        has_error: boolean
        status: string
    }
}

// 語音上傳回應
export interface ApiUploadResponse {
    status: string
    message: string
}

// Store 狀態
export interface VoiceChatState {
    state: AppState
    messages: ChatMessage[]
    isProcessing: boolean
    error: string | null
}
