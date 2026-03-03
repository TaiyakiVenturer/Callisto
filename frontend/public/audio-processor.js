/**
 * AudioWorklet Processor for PCM Audio Processing
 * 替代已淘汰的 ScriptProcessorNode
 * 累積 512 samples 後再發送（Silero VAD 要求）
 * 包含軟體 AGC（自動增益控制）
 */
class PCMAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.buffer = []  // 累積 buffer
    this.targetSize = 512  // 目標大小（512 samples = 32ms @ 16kHz）
    this.gain = 4.0  // 增益倍數（可調整：1.0-4.0）
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0]
    
    // 確保有音訊輸入
    if (input.length > 0) {
      const inputChannel = input[0]  // Float32Array [-1, 1]
      
      // 累積到 buffer（並套用增益）
      for (let i = 0; i < inputChannel.length; i++) {
        // 軟體 AGC：放大音量
        let sample = inputChannel[i] * this.gain
        // Clamp to [-1, 1] 避免削波失真
        sample = Math.max(-1, Math.min(1, sample))
        this.buffer.push(sample)
      }
      
      // 當累積到 512 samples 時，轉換並發送
      if (this.buffer.length >= this.targetSize) {
        // 取出 512 samples
        const chunk = this.buffer.splice(0, this.targetSize)
        
        // 轉換為 int16 PCM
        const int16Data = new Int16Array(chunk.length)
        for (let i = 0; i < chunk.length; i++) {
          const s = chunk[i]  // 已經 clamp 過
          int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF
        }
        
        // 發送到主線程
        this.port.postMessage(int16Data.buffer, [int16Data.buffer])
      }
    }
    
    // 返回 true 保持處理器運行
    return true
  }
}

registerProcessor('pcm-audio-processor', PCMAudioProcessor)
