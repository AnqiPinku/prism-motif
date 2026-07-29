import { useEffect, useRef, useState, type ReactNode } from 'react'
import { apiFetch } from './gatewaySession'

// Material Symbols 图标助手（与 App.tsx 同款）
const I = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

// 模块级 blob URL 缓存：path → objectURL，最多 10 条，按插入序淘汰并回收
const MAX_CACHE = 10
const urlCache = new Map<string, string>()
const cachePut = (path: string, url: string) => {
  urlCache.set(path, url)
  while (urlCache.size > MAX_CACHE) {
    const [oldPath, oldUrl] = urlCache.entries().next().value as [string, string]
    urlCache.delete(oldPath)
    URL.revokeObjectURL(oldUrl)
  }
}

// 全局同一时刻只放一段：新的开播先暂停旧的（旧 chip 经 onpause 自己回到待播态）
let playingNow: HTMLAudioElement | null = null

type Play = 'idle' | 'loading' | 'playing' | 'gone' | 'error'

// 音频附件胶囊：点播放按需拉字节转 blob URL 播放。
// 404 = 上传目录只留最新 20 个、文件已被清理 → 置灰「已过期」不再重试；
// 网络错误 → 短暂错误态，点按可重试。children 用于外挂按钮（composer 的移除 ×）。
export default function AudioChip({ name, path, small, children }: {
  name: string
  path: string
  small?: boolean
  children?: ReactNode
}) {
  const [st, setSt] = useState<Play>('idle')
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const alive = useRef(true)
  const errTimer = useRef(0)

  // 卸载清理：停播、解除全局占用、取消错误态回退计时
  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
      window.clearTimeout(errTimer.current)
      const a = audioRef.current
      audioRef.current = null
      if (a) {
        a.pause()
        if (playingNow === a) playingNow = null
      }
    }
  }, [])

  // 错误态是暂时的：几秒后回到待播，允许重试
  const fail = () => {
    if (!alive.current) return
    setSt('error')
    window.clearTimeout(errTimer.current)
    errTimer.current = window.setTimeout(() => { if (alive.current) setSt('idle') }, 2500)
  }

  const play = async () => {
    window.clearTimeout(errTimer.current)
    let url = urlCache.get(path)
    if (!url) {
      setSt('loading')
      try {
        const r = await apiFetch('/api/upload/file?path=' + encodeURIComponent(path))
        if (r.status === 404) {                    // 文件没了：终态，不给重试
          if (alive.current) setSt('gone')
          return
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        url = URL.createObjectURL(await r.blob())
        cachePut(path, url)
      } catch {
        fail()
        return
      }
      if (!alive.current) return
    }
    let a = audioRef.current
    if (!a || a.src !== url) {                     // URL 被淘汰后重取过 → 换新元素
      a = new Audio(url)
      a.onplay = () => { if (alive.current) setSt('playing') }
      a.onpause = () => { if (alive.current) setSt('idle') }
      a.onended = () => { if (alive.current) setSt('idle') }
      a.onerror = fail
      audioRef.current = a
    }
    if (playingNow && playingNow !== a) playingNow.pause()
    playingNow = a
    try { await a.play() } catch { fail() }
  }

  const sz = small ? 15 : 16
  if (st === 'gone') {
    return (
      <span className={'attchip gone' + (small ? ' small' : '')}>
        <I n="music_off" s={sz} />
        <span className="an">{name}</span>
        <span className="agone">已过期</span>
        {children}
      </span>
    )
  }
  return (
    <span className={'attchip' + (small ? ' small' : '')}>
      <button className="aplay" disabled={st === 'loading'}
        aria-label={st === 'playing' ? '暂停' : '播放'}
        title={st === 'error' ? '加载失败，点击重试' : st === 'playing' ? '暂停' : '播放'}
        onClick={() => { if (st === 'playing') audioRef.current?.pause(); else void play() }}>
        <I n={st === 'loading' ? 'hourglass' : st === 'playing' ? 'pause' : st === 'error' ? 'error' : 'play_arrow'} s={sz} />
      </button>
      <span className="an">{name}</span>
      {children}
    </span>
  )
}
