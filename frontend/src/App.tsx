import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getCurrentWindow } from '@tauri-apps/api/window'
import {
  getJSON, postJSON, streamChat, respondPermission, uploadAudio, inTauri,
  type State, type ReaperStatus, type ChatEvent,
} from './api'

// 历史标题里可能截进附件行（旧存档），显示前清掉
const cleanTitle = (s: string) => s.replace(/\[音频文件:[^\]]*\]?/g, '').trim()
import Settings, { type SettingsData } from './Settings'
import Onboarding from './Onboarding'

// data-tauri-drag-region marks the title-bar area draggable (only in the Tauri shell).
const drag = inTauri ? { 'data-tauri-drag-region': '' } : {}

// Resizable sidebar bounds (px); width persists in localStorage.
const NAV_KEY = 'prism.navWidth', NAV_DEFAULT = 300, NAV_MIN = 240, NAV_MAX = 440

const I = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

type Chip = { kind: 'chip'; tone: 'ok' | 'err' | 'run'; label: string; detail?: string }
type Tile = { label: string; value: string; unit?: string }
type Item =
  | Chip
  | { kind: 'trace'; text: string }
  | { kind: 'perm'; id: string; label: string; decided?: string }
  | { kind: 'metrics'; title: string; tiles: Tile[] }

// 音频分析类工具的 JSON 结果 → 指标磁贴（设计稿的"工程分析"卡）；解析不了就返回 null 走普通 chip。
function buildMetrics(name?: string, content?: string): { title: string; tiles: Tile[] } | null {
  if (!name || !content) return null
  let d: Record<string, any>
  try { d = JSON.parse(content) } catch { return null }
  if (typeof d !== 'object' || d === null) return null
  const tiles: Tile[] = []
  if (/analyze_audio|measure_loudness/.test(name)) {
    if (typeof d.key?.key === 'string') tiles.push({ label: '调性', value: `${d.key.key} ${d.key.mode || ''}`.trim() })
    if (typeof d.tempo?.bpm === 'number') tiles.push({ label: '速度', value: String(d.tempo.bpm), unit: 'BPM' })
    if (typeof d.loudness?.integrated_lufs === 'number') tiles.push({ label: '响度', value: String(d.loudness.integrated_lufs), unit: 'LUFS' })
    if (typeof d.loudness?.loudness_range_lu === 'number') tiles.push({ label: '动态范围', value: String(d.loudness.loudness_range_lu), unit: 'LU' })
    if (typeof d.loudness?.true_peak_dbtp === 'number') tiles.push({ label: '真峰值', value: String(d.loudness.true_peak_dbtp), unit: 'dBTP' })
    if (typeof d.duration_seconds === 'number') tiles.push({ label: '长度', value: String(d.duration_seconds), unit: '秒' })
    return tiles.length >= 2 ? { title: '音频分析', tiles: tiles.slice(0, 6) } : null
  }
  if (/listen_subjective/.test(name)) {
    // Gemini 听感：0-100 越低越好的四项 + 情绪
    if (typeof d.mood === 'string') tiles.push({ label: '情绪', value: d.mood })
    for (const [k, label] of [['muddy', '浑浊'], ['harsh', '刺耳'], ['sibilant', '齿音'], ['bright', '明亮']] as const)
      if (typeof d[k] === 'number') tiles.push({ label, value: String(d[k]), unit: '/100' })
    return tiles.length >= 2 ? { title: 'Gemini 听感', tiles: tiles.slice(0, 6) } : null
  }
  return null
}
type Msg = { role: 'user' | 'assistant'; text: string; items: Item[] }

export default function App() {
  const [state, setState] = useState<State | null>(null)
  const [reaper, setReaper] = useState<ReaperStatus | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [provider, setProvider] = useState('')
  const [threadId, setThreadId] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [bypass, setBypassState] = useState(() => localStorage.getItem('pm_trust') === '1')
  const setBypass = (v: boolean) => { setBypassState(v); localStorage.setItem('pm_trust', v ? '1' : '0') }
  const [statusOpen, setStatusOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [onboarding, setOnboarding] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const msgsRef = useRef<HTMLDivElement>(null)

  // 聊天附音频：+ 号选文件 → 传给 gateway 落盘 → 显示为附件胶囊，路径发送时才拼进消息
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [atts, setAtts] = useState<{ name: string; path: string }[]>([])
  const onPickAudio = async (f?: File) => {
    if (!f || uploading) return
    setUploading(true)
    try {
      const r = await uploadAudio(f)
      const p = r.path
      if (p) setAtts((a) => [...a, { name: f.name, path: p }])
      else alert('上传失败：' + (r.error || '未知错误'))
    } catch (e) {
      alert('上传失败：' + e)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  // Resizable sidebar — width persisted; delta-based pointer drag (handle sits outside the drag region).
  const [navW, setNavW] = useState<number>(() => {
    const v = parseInt(localStorage.getItem(NAV_KEY) || '', 10)
    return Number.isFinite(v) ? Math.min(NAV_MAX, Math.max(NAV_MIN, v)) : NAV_DEFAULT
  })
  useEffect(() => { localStorage.setItem(NAV_KEY, String(navW)) }, [navW])
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)
  const onNavDrag = useCallback((e: PointerEvent) => {
    const d = dragRef.current; if (!d) return
    setNavW(Math.min(NAV_MAX, Math.max(NAV_MIN, d.startW + (e.clientX - d.startX))))
  }, [])
  const endNavDrag = useCallback(() => {
    dragRef.current = null
    document.body.classList.remove('nav-resizing')
    document.querySelector('.nav-handle')?.classList.remove('dragging')
    window.removeEventListener('pointermove', onNavDrag)
  }, [onNavDrag])
  const startNavDrag = (e: ReactPointerEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: navW }
    document.body.classList.add('nav-resizing')
    ;(e.currentTarget as HTMLElement).classList.add('dragging')
    window.addEventListener('pointermove', onNavDrag)
    window.addEventListener('pointerup', endNavDrag, { once: true })
  }
  useEffect(() => () => window.removeEventListener('pointermove', onNavDrag), [onNavDrag])

  const loadState = useCallback(async () => {
    const s = await getJSON<State>('/api/state')
    setState(s)
    setProvider((p) => p || s.providers.default)
  }, [])
  const loadReaper = useCallback(async () => {
    try { setReaper(await getJSON<ReaperStatus>('/api/reaper/status')) } catch { /* ignore */ }
  }, [])
  const loadSettings = useCallback(async () => {
    const s = await getJSON<SettingsData>('/api/settings')
    setSettings(s)
    return s
  }, [])

  useEffect(() => {
    loadState()
    loadReaper()
    loadSettings().then((s) => {
      const configured = Object.values(s.providers || {}).some((p) => p.has_key) || s.gemini?.has_key
      if (!configured && !localStorage.getItem('pm_onboarded')) setOnboarding(true)
    })
    const t = setInterval(loadReaper, 5000)
    return () => clearInterval(t)
  }, [loadState, loadReaper, loadSettings])

  useEffect(() => {
    const el = msgsRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [msgs])

  const patchLast = (fn: (m: Msg) => Msg) =>
    setMsgs((prev) => prev.map((m, i) => (i === prev.length - 1 ? fn(m) : m)))

  const onEvent = (e: ChatEvent) => {
    if (e.type === 'thread') setThreadId(e.id)
    else if (e.type === 'delta') patchLast((m) => ({ ...m, text: m.text + (e.text || '') }))
    else if (e.type === 'tool_call')
      patchLast((m) => ({ ...m, items: [...m.items, { kind: 'chip', tone: 'run', label: e.name }] }))
    else if (e.type === 'tool_result')
      patchLast((m) => {
        const items = [...m.items]
        for (let i = items.length - 1; i >= 0; i--) {
          const it = items[i]
          if (it.kind === 'chip' && it.tone === 'run') {
            items[i] = { ...it, tone: e.is_error ? 'err' : 'ok', detail: (e.content || '').trim() }
            break
          }
        }
        // 结构化的音频分析结果额外升级成指标卡（原始 JSON 仍收在工具栏里）
        const metrics = e.is_error ? null : buildMetrics(e.name, e.content)
        if (metrics) items.push({ kind: 'metrics', ...metrics })
        return { ...m, items }
      })
    else if (e.type === 'permission_request')
      patchLast((m) => ({ ...m, items: [...m.items, { kind: 'perm', id: e.id, label: e.name }] }))
    else if (e.type === 'retry' || e.type === 'compaction')
      patchLast((m) => ({ ...m, items: [...m.items, { kind: 'trace', text: e.content }] }))
    else if (e.type === 'final')
      patchLast((m) => (m.text ? m : { ...m, text: e.text || '' }))
    else if (e.type === 'error')
      patchLast((m) => ({ ...m, text: '出错：' + (e.message || '') }))
  }

  const send = async () => {
    const text = input.trim()
    if ((!text && atts.length === 0) || sending) return
    // 附件路径拼在指令后面（agent 的分析/转 MIDI 工具吃本机路径）
    const goal = [text, ...atts.map((a) => `[音频文件: ${a.path}]`)].filter(Boolean).join('\n')
    setInput('')
    setAtts([])
    setMsgs((m) => [...m, { role: 'user', text: goal, items: [] }, { role: 'assistant', text: '', items: [] }])
    setSending(true)
    abort.current = new AbortController()
    try {
      await streamChat({ goal, provider, thread_id: threadId, bypass }, onEvent, abort.current.signal)
    } catch (err) {
      if ((err as Error).name !== 'AbortError')
        patchLast((m) => ({ ...m, text: '请求失败：' + err }))
    } finally {
      setSending(false)
      abort.current = null
      loadState()
    }
  }

  const decide = (id: string, allow: boolean) => {
    respondPermission(id, allow)
    patchLast((m) => ({
      ...m,
      items: m.items.map((it) =>
        it.kind === 'perm' && it.id === id ? { ...it, decided: allow ? '已允许' : '已拒绝' } : it),
    }))
  }

  const openThread = async (id: string) => {
    type Raw = { role: string; content?: string | null; tool_call_id?: string; tool_calls?: { id?: string; name: string }[] }
    const data = await getJSON<{ messages: Raw[] }>('/api/threads/' + encodeURIComponent(id))
    setThreadId(id)
    // 从存档重建：同一回合的 assistant/tool 消息合并成一个气泡，工具链恢复成 chips + 指标卡
    const out: Msg[] = []
    const byCallId = new Map<string, Chip>()
    let cur: Msg | null = null
    for (const m of data.messages || []) {
      if (m.role === 'user') {
        out.push({ role: 'user', text: m.content || '', items: [] })
        cur = null
      } else if (m.role === 'assistant' && (m.content || m.tool_calls?.length)) {
        if (!cur) { cur = { role: 'assistant', text: '', items: [] }; out.push(cur) }
        for (const tc of m.tool_calls || []) {
          const chip: Chip = { kind: 'chip', tone: 'ok', label: tc.name }
          if (tc.id) byCallId.set(tc.id, chip)
          cur.items.push(chip)
        }
        if (m.content) cur.text = m.content            // 回合内最后一条带文本的 = 最终回复
      } else if (m.role === 'tool' && cur) {
        const chip = m.tool_call_id ? byCallId.get(m.tool_call_id) : undefined
        if (!chip) continue
        const content = (m.content || '').trim()
        chip.detail = content
        // 存档没记 is_error，按常见错误开头近似判断
        if (/^(analysis error|error|traceback|用户拒绝)/i.test(content)) chip.tone = 'err'
        const metrics = chip.tone === 'ok' ? buildMetrics(chip.label, content) : null
        if (metrics) cur.items.push({ kind: 'metrics', ...metrics })
      }
    }
    setMsgs(out)
  }

  const newChat = () => { setThreadId(null); setMsgs([]) }

  // 线程行 ⋯ 菜单：两段式删除确认（WebView2 的原生 confirm 不可靠，不用）
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState(false)
  const openMenu = (id: string | null) => { setMenuFor(id); setConfirmDel(false) }
  const delThread = async (id: string) => {
    await postJSON('/api/threads/delete', { id })
    openMenu(null)
    if (threadId === id) newChat()
    loadState()
  }

  const geminiOk = !!settings?.gemini?.has_key
  const perceptionOn = !!state?.mcp.find((m) => m.name === 'music-perception')?.enabled
  const reaperOk = reaper?.state === 'connected'
  const allReady = geminiOk && perceptionOn && reaperOk
  const ready = (ok: boolean) => (ok ? 'var(--green)' : 'var(--amber)')

  const composer = (
    <div>
      {atts.length > 0 && (
        <div className="attrow">
          {atts.map((a, i) => (
            <span className="attchip" key={i}>
              <I n="music_note" s={16} />
              <span className="an">{a.name}</span>
              <button aria-label="移除附件" onClick={() => setAtts((x) => x.filter((_, j) => j !== i))}>
                <I n="close" s={15} />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className="cbox">
      <input ref={fileRef} type="file" style={{ display: 'none' }}
        accept="audio/*,.wav,.mp3,.flac,.ogg,.aif,.aiff,.m4a"
        onChange={(e) => onPickAudio(e.target.files?.[0])} />
      <button className="iconbtn" aria-label="添加音频" title="添加音频文件（分析 / 转 MIDI）"
        onClick={() => fileRef.current?.click()}>
        {uploading ? <span className="spinning"><I n="progress_activity" /></span> : <I n="add" />}
      </button>
      <textarea
        rows={1} value={input} placeholder="描述你的音乐想法，交给 Prism…"
        onChange={(e) => setInput(e.target.value)}
        onInput={(e) => { const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 140) + 'px'; t.style.overflowY = t.scrollHeight > 140 ? 'auto' : 'hidden' }}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
      />
      <span className="modelchip">
        <I n="bolt" s={16} />
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {(state?.providers.names || []).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </span>
      <button className="fab" aria-label={sending ? '停止' : '发送'}
        disabled={!sending && !input.trim() && atts.length === 0}
        onClick={() => (sending ? abort.current?.abort() : send())}>
        <I n={sending ? 'stop' : 'arrow_upward'} />
      </button>
      </div>
    </div>
  )

  return (
    <div className="app">
      <header className="bar" {...drag}>
        <button className="iconbtn" aria-label="菜单"><I n="menu" /></button>
        <span className="logo" {...drag}><I n="graphic_eq" /></span>
        <span className="brand" {...drag}>Prism Motif</span>
        <span className="spacer" {...drag} />
        <div className="statuswrap">
          <button className="statuschip" onClick={() => setStatusOpen((v) => !v)}>
            <span className="dot" style={{ background: ready(allReady) }} />
            {allReady ? '已就绪' : '待连接'}
            <I n="expand_more" s={18} />
          </button>
          {statusOpen && (
            <div className="statusmenu" onMouseLeave={() => setStatusOpen(false)}>
              <div className="mh">连接状态</div>
              <div className="status"><span className="dot" style={{ background: 'var(--green)' }} /><span className="lbl">语言模型</span><span className="val">{state?.providers.default}</span></div>
              <div className="status"><span className="dot" style={{ background: ready(geminiOk) }} /><span className="lbl">音频分析 API</span><span className="val">{geminiOk ? 'Gemini' : '未设置'}</span></div>
              <div className="status"><span className="dot" style={{ background: ready(perceptionOn) }} /><span className="lbl">感知引擎</span><span className="val">{perceptionOn ? '运行中' : '已停用'}</span></div>
              <div className="status"><span className="dot" style={{ background: ready(reaperOk) }} /><span className="lbl">REAPER</span><span className="val">{reaperLabel(reaper)}</span></div>
            </div>
          )}
        </div>
        <button className="iconbtn" aria-label="设置" onClick={() => setSettingsOpen(true)}><I n="settings" /></button>
        {inTauri && <WinControls />}
      </header>

      <div className="body">
        <aside className="nav" style={{ '--nav-w': `${navW}px` } as CSSProperties}>
          <button className="ws"><I n="folder_open" s={20} />{state?.workspace.current || 'default'}<span className="spacer" /><I n="expand_more" s={20} /></button>
          <button className="newchat" onClick={newChat}><I n="add" />新对话</button>
          <div className="navlabel">最近</div>
          {(state?.threads || []).slice().reverse().map((t) => (
            <div key={t.id} className={'thread' + (t.id === threadId ? ' active' : '')}>
              <button className="topen" onClick={() => openThread(t.id)}>
                <I n="chat_bubble" s={20} /><span className="t">{cleanTitle(t.title || '') || t.id}</span>
              </button>
              <button className="tmenu" aria-label="对话选项"
                onClick={(e) => { e.stopPropagation(); openMenu(menuFor === t.id ? null : t.id) }}>
                <I n="more_horiz" s={18} />
              </button>
              {menuFor === t.id && (
                <div className="threadmenu" onMouseLeave={() => openMenu(null)}>
                  <button className="danger"
                    onClick={() => (confirmDel ? delThread(t.id) : setConfirmDel(true))}>
                    <I n="delete" s={17} />{confirmDel ? '确认删除？' : '删除'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </aside>

        <div className="nav-handle" style={{ left: navW - 4 }} onPointerDown={startNavDrag}
          role="separator" aria-orientation="vertical" aria-label="调整侧边栏宽度" />

        <main className="chat">
          {msgs.length === 0 ? (
            <div className="hero">
              <div className="greet">今天想创作点什么？</div>
              <div className="sub">作曲、编曲、混音，说一句就行。</div>
              <div className="cwrap">{composer}</div>
            </div>
          ) : (
            <>
              <div className="msgs" ref={msgsRef}>
                {msgs.map((m, i) =>
                  m.role === 'user' ? (
                    <UserBubble key={i} text={m.text} />
                  ) : (
                    <div key={i} className="a">
                      <div className="ava"><I n="graphic_eq" s={18} /></div>
                      <div className="abody">
                        {m.text && (
                          <div className="atext md">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                          </div>
                        )}
                        <ToolBar chips={m.items.filter((it): it is Chip => it.kind === 'chip')} />
                        {m.items.filter((it) => it.kind !== 'chip').map((it, j) => <Rendered key={j} it={it} onDecide={decide} />)}
                      </div>
                    </div>
                  ),
                )}
              </div>
              <div className="composer">{composer}</div>
            </>
          )}
        </main>
      </div>

      {settingsOpen && state && (
        <Settings state={state} trust={bypass} setTrust={setBypass}
          onClose={() => setSettingsOpen(false)}
          onSaved={() => { loadState(); loadSettings() }} />
      )}
      {onboarding && (
        <Onboarding reaper={reaper} onReaperRefresh={loadReaper}
          onDone={() => { localStorage.setItem('pm_onboarded', '1'); setOnboarding(false); loadSettings() }} />
      )}
    </div>
  )
}

// 用户气泡：把消息里的 [音频文件: path] 行渲染成附件胶囊（只显示文件名），正文照常。
const AUD_LINE = /^\[音频文件: (.+)\]$/
function UserBubble({ text }: { text: string }) {
  const lines = text.split('\n')
  const files = lines.map((l) => l.match(AUD_LINE)?.[1]).filter((p): p is string => !!p)
  const rest = lines.filter((l) => !AUD_LINE.test(l)).join('\n')
  return (
    <div className="u">
      {rest}
      {files.length > 0 && (
        <div className="uatts">
          {files.map((p, i) => (
            <span key={i} className="attchip small"><I n="music_note" s={14} />{p.split(/[\\/]/).pop()}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// Custom window buttons (frameless Tauri window). Only rendered inside the shell.
function WinControls() {
  const w = getCurrentWindow()
  return (
    <div className="wctl">
      <button aria-label="最小化" onClick={() => w.minimize()}><I n="remove" s={18} /></button>
      <button aria-label="最大化" onClick={() => w.toggleMaximize()}><I n="crop_square" s={15} /></button>
      <button className="close" aria-label="关闭" onClick={() => w.close()}><I n="close" s={18} /></button>
    </div>
  )
}

// Collapsed-by-default bar of tool calls; expand to see each tool's result/error.
function ToolBar({ chips }: { chips: Chip[] }) {
  if (chips.length === 0) return null
  const fails = chips.filter((c) => c.tone === 'err').length
  const active = chips.filter((c) => c.tone === 'run')
  const running = active.length > 0
  // show the current tool (running one, else the most recent) instead of a bare count
  const cur = running ? active[active.length - 1] : chips[chips.length - 1]
  const icon = (t: Chip['tone']) => (t === 'ok' ? 'check_circle' : t === 'err' ? 'cancel' : 'progress_activity')
  return (
    <details className="toolbar">
      <summary>
        {running ? <span className="spinning"><I n="progress_activity" s={16} /></span> : <I n="build" s={16} />}
        <span className="tname">{cur.label}</span>
        {chips.length > 1 && <span className="tcount">{chips.length}</span>}
        {fails > 0 && <span className="tf">{fails} 失败</span>}
        {running && <span className="tr">运行中…</span>}
        <I n="expand_more" s={18} />
      </summary>
      <div className="toollist">
        {chips.map((c, i) =>
          c.detail ? (
            // 有输出的工具：默认收起，点 chip 再展开详情
            <details className="toolrow" key={i}>
              <summary>
                <span className={'chip ' + c.tone}>
                  <I n={icon(c.tone)} s={16} />{c.label}<I n="expand_more" s={14} />
                </span>
              </summary>
              <pre className="tooldetail">{c.detail.length > 700 ? c.detail.slice(0, 700) + ' …' : c.detail}</pre>
            </details>
          ) : (
            <div className="toolrow" key={i}>
              <span className={'chip ' + c.tone}><I n={icon(c.tone)} s={16} />{c.label}</span>
            </div>
          ),
        )}
      </div>
    </details>
  )
}

function Rendered({ it, onDecide }: { it: Item; onDecide: (id: string, allow: boolean) => void }) {
  if (it.kind === 'trace') return <div className="trace">{it.text}</div>
  if (it.kind === 'metrics')
    return (
      <div className="mcard">
        <div className="mtitle">{it.title}</div>
        <div className="mtiles">
          {it.tiles.map((t, i) => (
            <div className="mtile" key={i}>
              <div className="ml">{t.label}</div>
              <div className="mv">{t.value}{t.unit && <span className="mu">{t.unit}</span>}</div>
            </div>
          ))}
        </div>
      </div>
    )
  if (it.kind === 'chip')
    return (
      <div className="chips"><span className={'chip ' + it.tone}>
        <I n={it.tone === 'ok' ? 'check_circle' : it.tone === 'err' ? 'cancel' : 'progress_activity'} s={16} />{it.label}
      </span></div>
    )
  return (
    <div className="perm">
      {it.decided ? <div className="q">{it.decided} · {it.label}</div> : <>
        <div className="q">⚠ AI 想执行 {it.label}</div>
        <div className="acts">
          <button className="allow" onClick={() => onDecide(it.id, true)}>允许</button>
          <button className="deny" onClick={() => onDecide(it.id, false)}>拒绝</button>
        </div>
      </>}
    </div>
  )
}

function reaperLabel(r: ReaperStatus | null) {
  if (!r) return '…'
  return { connected: '已连接', running_not_loaded: '桥未加载', not_running: '未运行', not_loaded: '未连接' }[r.state] || '未知'
}
