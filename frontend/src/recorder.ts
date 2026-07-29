// 纯录音数据处理：无 DOM / AudioContext 依赖，node:test 可直接测

// 5 分钟上限：gateway 上传限 200MB，48k 单声道 16bit 约 5.8MB/min，
// 5 分钟 ~29MB 余量充足，同时避免超长录音撑爆内存里的 Float32 块
export const MAX_RECORD_SECONDS = 300

// 拼接单声道 float PCM 块，钳到 [-1,1] 转 16-bit LE，加 RIFF/WAVE 头
export function encodeWavBytes(chunks: Float32Array[], sampleRate: number): Uint8Array<ArrayBuffer> {
  let total = 0
  for (const c of chunks) total += c.length
  const dataSize = total * 2                       // 16-bit 单声道：每样本 2 字节
  const buf = new ArrayBuffer(44 + dataSize)
  const view = new DataView(buf)
  const ascii = (off: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i))
  }
  ascii(0, 'RIFF')
  view.setUint32(4, 36 + dataSize, true)
  ascii(8, 'WAVE')
  ascii(12, 'fmt ')
  view.setUint32(16, 16, true)                     // fmt 块长度
  view.setUint16(20, 1, true)                      // PCM
  view.setUint16(22, 1, true)                      // 单声道
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)         // 字节率 = 采样率 * 块对齐
  view.setUint16(32, 2, true)                      // 块对齐
  view.setUint16(34, 16, true)                     // 位深
  ascii(36, 'data')
  view.setUint32(40, dataSize, true)
  let off = 44
  for (const c of chunks) {
    for (let i = 0; i < c.length; i++) {
      const s = Math.max(-1, Math.min(1, c[i]))
      // 负半轴满幅是 -32768，正半轴 32767，分开缩放避免溢出
      view.setInt16(off, Math.round(s < 0 ? s * 0x8000 : s * 0x7fff), true)
      off += 2
    }
  }
  return new Uint8Array(buf)
}

export function encodeWav(chunks: Float32Array[], sampleRate: number): Blob {
  return new Blob([encodeWavBytes(chunks, sampleRate)], { type: 'audio/wav' })
}

// 计时器显示：'m:ss'
export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// 录音文件名：哼唱-0729-2254.wav（本地时间，调用方传 Date 方便测试）
export function recordingName(now: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `哼唱-${p(now.getMonth() + 1)}${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}.wav`
}

// 电平表用：单块均方根，0 静音 1 满幅
export function chunkRms(chunk: Float32Array): number {
  if (chunk.length === 0) return 0
  let sum = 0
  for (let i = 0; i < chunk.length; i++) sum += chunk[i] * chunk[i]
  return Math.sqrt(sum / chunk.length)
}
