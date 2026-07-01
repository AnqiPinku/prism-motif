import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getJSON, streamChat, respondPermission,
  type State, type ReaperStatus, type ChatEvent,
} from './api'
import Settings, { type SettingsData } from './Settings'
import Onboarding from './Onboarding'

const I = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

type Chip = { kind: 'chip'; tone: 'ok' | 'err' | 'run'; label: string; detail?: string }
type Item =
  | Chip
  | { kind: 'trace'; text: string }
  | { kind: 'perm'; id: string; label: string; decided?: string }
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
    const goal = input.trim()
    if (!goal || sending) return
    setInput('')
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
    const data = await getJSON<{ messages: { role: string; content: string }[] }>('/api/threads/' + encodeURIComponent(id))
    setThreadId(id)
    setMsgs((data.messages || [])
      .filter((m) => m.role === 'user' || (m.role === 'assistant' && m.content))
      .map((m) => ({ role: m.role as 'user' | 'assistant', text: m.content, items: [] })))
  }

  const newChat = () => { setThreadId(null); setMsgs([]) }

  const geminiOk = !!settings?.gemini?.has_key
  const perceptionOn = !!state?.mcp.find((m) => m.name === 'music-perception')?.enabled
  const reaperOk = reaper?.state === 'connected'
  const allReady = geminiOk && perceptionOn && reaperOk
  const ready = (ok: boolean) => (ok ? 'var(--green)' : 'var(--amber)')

  const composer = (
    <div className="cbox">
      <button className="iconbtn" aria-label="添加"><I n="add" /></button>
      <textarea
        rows={1} value={input} placeholder="想写点什么？让 Prism 帮你作曲、编曲、混音…"
        onChange={(e) => setInput(e.target.value)}
        onInput={(e) => { const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 140) + 'px' }}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
      />
      <span className="modelchip">
        <I n="bolt" s={16} />
        <select value={provider} onChange={(e) => setProvider(e.target.value)}>
          {(state?.providers.names || []).map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </span>
      <button className="fab" aria-label={sending ? '停止' : '发送'} disabled={!sending && !input.trim()}
        onClick={() => (sending ? abort.current?.abort() : send())}>
        <I n={sending ? 'stop' : 'arrow_upward'} />
      </button>
    </div>
  )

  return (
    <div className="app">
      <header className="bar">
        <button className="iconbtn" aria-label="菜单"><I n="menu" /></button>
        <span className="logo"><I n="graphic_eq" /></span>
        <span className="brand">Prism Motif</span>
        <span className="spacer" />
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
        <span className="avatar">科</span>
      </header>

      <div className="body">
        <aside className="nav">
          <button className="ws"><I n="folder_open" s={20} />{state?.workspace.current || 'default'}<span className="spacer" /><I n="expand_more" s={20} /></button>
          <button className="newchat" onClick={newChat}><I n="add" />新对话</button>
          <div className="navlabel">最近</div>
          {(state?.threads || []).slice().reverse().map((t) => (
            <button key={t.id} className={'thread' + (t.id === threadId ? ' active' : '')} onClick={() => openThread(t.id)}>
              <I n="chat_bubble" s={20} /><span className="t">{t.title || t.id}</span>
            </button>
          ))}
        </aside>

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
                    <div key={i} className="u">{m.text}</div>
                  ) : (
                    <div key={i} className="a">
                      <div className="ava"><I n="graphic_eq" s={18} /></div>
                      <div className="abody">
                        {m.text && <div className="atext">{m.text}</div>}
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

// Collapsed-by-default bar of tool calls; expand to see each tool's result/error.
function ToolBar({ chips }: { chips: Chip[] }) {
  if (chips.length === 0) return null
  const fails = chips.filter((c) => c.tone === 'err').length
  const running = chips.some((c) => c.tone === 'run')
  const icon = (t: Chip['tone']) => (t === 'ok' ? 'check_circle' : t === 'err' ? 'cancel' : 'progress_activity')
  return (
    <details className="toolbar">
      <summary>
        <I n="build" s={16} />
        <span>工具 · {chips.length}</span>
        {fails > 0 && <span className="tf">{fails} 失败</span>}
        {running && <span className="tr">运行中…</span>}
        <I n="expand_more" s={18} />
      </summary>
      <div className="toollist">
        {chips.map((c, i) => (
          <div className="toolrow" key={i}>
            <span className={'chip ' + c.tone}><I n={icon(c.tone)} s={16} />{c.label}</span>
            {c.detail && <pre className="tooldetail">{c.detail.length > 700 ? c.detail.slice(0, 700) + ' …' : c.detail}</pre>}
          </div>
        ))}
      </div>
    </details>
  )
}

function Rendered({ it, onDecide }: { it: Item; onDecide: (id: string, allow: boolean) => void }) {
  if (it.kind === 'trace') return <div className="trace">{it.text}</div>
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
