import { useEffect, useRef, useState } from 'react'
import { uploadAudio } from './api'
import { encodeWav, formatClock, recordingName, MAX_RECORD_SECONDS, chunkRms } from './recorder'

const I = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

type Phase = 'idle' | 'recording' | 'preview' | 'uploading'

// 电平条的相对高度系数：中间高两侧低，像一个小频谱
const BAR_K = [0.55, 0.8, 1, 0.8, 0.55]

// 哼唱录音：mic 按钮 + 锚定在 composer 上方的小面板
// idle → recording（worklet 采 PCM）→ preview（WAV 试听）→ uploading → onDone
export default function RecordPanel({ disabled, onDone }: {
  disabled?: boolean
  onDone: (name: string, path: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [phase, setPhase] = useState<Phase>('idle')
  const [elapsed, setElapsed] = useState(0)
  const [level, setLevel] = useState(0)
  const [duration, setDuration] = useState(0)
  const [previewUrl, setPreviewUrl] = useState('')
  const [playing, setPlaying] = useState(false)
  const [error, setError] = useState('')

  const streamRef = useRef<MediaStream | null>(null)
  const ctxRef = useRef<AudioContext | null>(null)
  const chunksRef = useRef<Float32Array[]>([])
  const sampleRateRef = useRef(48000)
  const startAtRef = useRef(0)
  const levelRef = useRef(0)
  const blobRef = useRef<Blob | null>(null)
  const urlRef = useRef('')
  const audioRef = useRef<HTMLAudioElement>(null)

  const stopAudio = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    const ctx = ctxRef.current
    ctxRef.current = null
    if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => {})
  }
  const dropPreview = () => {
    audioRef.current?.pause()
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
    urlRef.current = ''
    blobRef.current = null
    setPreviewUrl('')
    setPlaying(false)
  }
  const closePanel = () => {
    stopAudio()
    dropPreview()
    setPhase('idle')
    setError('')
    setOpen(false)
  }

  const startRecording = async () => {
    setError('')
    dropPreview()
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false },
      })
      const ctx = new AudioContext()
      await ctx.audioWorklet.addModule('/pcm-worklet.js')
      const node = new AudioWorkletNode(ctx, 'pcm-capture')
      node.port.onmessage = (e: MessageEvent<{ pcm: Float32Array; rms?: number }>) => {
        chunksRef.current.push(e.data.pcm)
        levelRef.current = e.data.rms ?? chunkRms(e.data.pcm)
      }
      ctx.createMediaStreamSource(stream).connect(node)
      // 静音接入 destination 保证图被驱动，又绝不外放
      const mute = ctx.createGain()
      mute.gain.value = 0
      node.connect(mute).connect(ctx.destination)
      streamRef.current = stream
      ctxRef.current = ctx
      sampleRateRef.current = ctx.sampleRate
      chunksRef.current = []
      levelRef.current = 0
      startAtRef.current = Date.now()
      setElapsed(0)
      setLevel(0)
      setPhase('recording')
    } catch (e) {
      stopAudio()
      setPhase('idle')
      setError('无法访问麦克风：' + ((e as Error)?.message || e))
    }
  }

  const stopRecording = () => {
    stopAudio()
    const chunks = chunksRef.current
    const total = chunks.reduce((n, c) => n + c.length, 0)
    if (!total) {
      setPhase('idle')
      setError('没有录到声音，请重试')
      return
    }
    const blob = encodeWav(chunks, sampleRateRef.current)
    blobRef.current = blob
    urlRef.current = URL.createObjectURL(blob)
    setPreviewUrl(urlRef.current)
    setDuration(total / sampleRateRef.current)
    setPhase('preview')
  }

  const togglePlay = () => {
    const a = audioRef.current
    if (!a) return
    if (a.paused) void a.play()
    else a.pause()
  }

  const useRecording = async () => {
    const blob = blobRef.current
    if (!blob) return
    audioRef.current?.pause()
    setError('')
    setPhase('uploading')
    try {
      const file = new File([blob], recordingName(new Date()), { type: 'audio/wav' })
      const r = await uploadAudio(file)
      if (r.path) {
        onDone(file.name, r.path)
        closePanel()
      } else {
        setError('上传失败：' + (r.error || '未知错误'))
        setPhase('preview')
      }
    } catch (e) {
      setError('上传失败：' + e)
      setPhase('preview')
    }
  }

  // 计时 + 电平驱动（rms 落在 ref 里，100ms 刷一次避免高频重渲染）；到上限自动停
  useEffect(() => {
    if (phase !== 'recording') return
    const id = window.setInterval(() => {
      const secs = Math.floor((Date.now() - startAtRef.current) / 1000)
      setElapsed(secs)
      setLevel(levelRef.current)
      if (secs >= MAX_RECORD_SECONDS) stopRecording()
    }, 100)
    return () => window.clearInterval(id)
  })

  // 点外部 / Escape 关闭（同 App 的 threadmenu 模式）
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      if (!(e.target as Element | null)?.closest?.('.recwrap')) closePanel()
    }
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closePanel() }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  })

  // 卸载兜底：停轨、关上下文、回收 blob URL
  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    const ctx = ctxRef.current
    if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => {})
    if (urlRef.current) URL.revokeObjectURL(urlRef.current)
  }, [])

  const recording = phase === 'recording'
  return (
    <div className="recwrap">
      <button className={'iconbtn recmic' + (recording ? ' on' : '')} aria-label="录音"
        title="录音哼唱旋律" disabled={disabled}
        onClick={() => {
          if (open) closePanel()
          else { setOpen(true); void startRecording() }
        }}>
        <I n="mic" />
      </button>
      {open && (
        <div className="recmenu" role="dialog" aria-label="录音">
          {recording && (
            <>
              <div className="recrow">
                <span className="recdot" aria-hidden />
                <span className="reclevel" aria-hidden>
                  {BAR_K.map((k, i) => (
                    <span key={i} style={{ transform: `scaleY(${Math.max(0.15, Math.min(1, level * 6 * k))})` }} />
                  ))}
                </span>
                <span className="rectime">{formatClock(elapsed)}</span>
                <button className="fab" aria-label="停止" onClick={stopRecording}>
                  <I n="stop" />
                </button>
              </div>
              <div className="rechint">用「哒哒哒」哼唱，慢一点更准</div>
            </>
          )}
          {(phase === 'preview' || phase === 'uploading') && (
            <>
              <div className="recrow">
                <button className="iconbtn" aria-label="试听" onClick={togglePlay} disabled={phase === 'uploading'}>
                  <I n={playing ? 'pause' : 'play_arrow'} />
                </button>
                <span className="rectime">{formatClock(duration)}</span>
              </div>
              <div className="recbtns">
                <button className="redo" aria-label="重录" disabled={phase === 'uploading'}
                  onClick={() => { dropPreview(); void startRecording() }}>
                  <I n="replay" s={16} />重录
                </button>
                <button className="use" aria-label="使用录音" disabled={phase === 'uploading'} onClick={useRecording}>
                  {phase === 'uploading'
                    ? <><span className="spinning"><I n="progress_activity" s={16} /></span>上传中…</>
                    : '使用录音'}
                </button>
              </div>
              <audio ref={audioRef} src={previewUrl}
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                onEnded={() => setPlaying(false)} />
            </>
          )}
          {error && <div className="recerr">{error}</div>}
        </div>
      )}
    </div>
  )
}
