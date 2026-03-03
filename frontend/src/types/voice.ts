// 語音監聽狀態類型
export enum MonitorStatus {
  IDLE = 'idle',
  CONNECTING = 'connecting',
  LISTENING = 'listening',
  SPEECH = 'speech',
  KEYWORD = 'keyword',
  PROCESSING = 'processing',
  SPEAKING = 'speaking',
  ERROR = 'error'
}

// 後端事件類型
export interface BackendEvent {
  type: 'connected' | 'keyword' | 'speech' | 'error' | 'transcribing' | 'transcript' | 'generating' | 'response' | 'speaking' | 'done'
  timestamp?: number
  keyword?: string
  confidence?: number
  duration?: number
  message?: string
  text?: string
}

// WebSocket 配置
export interface VoiceMonitorConfig {
  wsUrl?: string
  reconnectAttempts?: number
  reconnectDelay?: number
  timeslice?: number
}
