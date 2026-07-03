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

type ThreadInfo = { id: string; title?: string; archived?: boolean; workspace?: string; mtime?: number }

// 侧栏相对时间（epoch 秒 → 4 小时 / 2 天 / 3 周…）
function relTime(sec?: number) {
  if (!sec) return ''
  const d = Date.now() / 1000 - sec
  if (d < 60) return '刚刚'
  if (d < 3600) return Math.floor(d / 60) + ' 分钟'
  if (d < 86400) return Math.floor(d / 3600) + ' 小时'
  if (d < 7 * 86400) return Math.floor(d / 86400) + ' 天'
  if (d < 30 * 86400) return Math.floor(d / 86400 / 7) + ' 周'
  return Math.floor(d / 86400 / 30) + ' 个月'
}

function elapsedLabel(ms: number) {
  const total = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return m ? `${m}m ${s}s` : `${s}s`
}

function msLabel(ms?: number) {
  if (ms == null) return ''
  if (ms < 1000) return `${ms}ms`
  return elapsedLabel(ms)
}
import Settings, { type SettingsData } from './Settings'
import Onboarding from './Onboarding'

// data-tauri-drag-region marks the title-bar area draggable (only in the Tauri shell).
const drag = inTauri ? { 'data-tauri-drag-region': '' } : {}

// Resizable sidebar bounds (px); width persists in localStorage.
const NAV_KEY = 'prism.navWidth', NAV_COLLAPSED_KEY = 'prism.navCollapsed'
const NAV_DEFAULT = 300, NAV_MIN = 240, NAV_MAX = 440

const I = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

type Chip = { kind: 'chip'; tone: 'ok' | 'err' | 'run'; label: string; detail?: string }
type ProcessingPhase = 'connecting' | 'thinking' | 'generating' | 'tool' | 'retry'
type RunTone = 'run' | 'ok' | 'err' | 'info'
type RunTool = { id: string; name: string; tone: RunTone; durationMs?: number; contentChars?: number; detail?: string; truncated?: boolean; originalChars?: number }
type RunSummary = { kind: 'run'; durationMs: number; status: 'ok' | 'err'; tools: RunTool[]; reason?: string }
type RunMeta = {
  provider?: string; model?: string; workspace?: string; step?: number; maxSteps?: number;
  toolCount?: number; promptPct?: number; promptTokens?: number; contextWindow?: number;
  ttftMs?: number; outputChars?: number; heartbeatIdleMs?: number; lastEvent?: string;
}
type RunActiveState =
  | { status: 'connecting'; requestedAt: number; phase: 'connecting'; work: string; tools: RunTool[]; meta: RunMeta }
  | { status: 'running'; startedAt: number; phase: ProcessingPhase; work: string; tools: RunTool[]; meta: RunMeta }
type RunState =
  | { status: 'idle' }
  | RunActiveState
  | { status: 'done'; startedAt: number; endedAt: number; tools: RunTool[]; reason?: string }
  | { status: 'error'; startedAt: number; endedAt: number; tools: RunTool[]; reason?: string }
type Tile = { label: string; value: string; unit?: string }
type Item =
  | Chip
  | RunSummary
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
type Msg = { role: 'user' | 'assistant'; text: string; items: Item[]; streaming?: boolean }

export default function App() {
  const [state, setState] = useState<State | null>(null)
  const [reaper, setReaper] = useState<ReaperStatus | null>(null)
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [threadId, setThreadId] = useState<string | null>(null)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [processingNow, setProcessingNow] = useState(Date.now())
  const [run, setRun] = useState<RunState>({ status: 'idle' })
  const [bypass, setBypassState] = useState(() => localStorage.getItem('pm_trust') === '1')
  const setBypass = (v: boolean) => { setBypassState(v); localStorage.setItem('pm_trust', v ? '1' : '0') }
  const [statusOpen, setStatusOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [onboarding, setOnboarding] = useState(false)
  const abort = useRef<AbortController | null>(null)
  const runRef = useRef<RunState>({ status: 'idle' })
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
  const [navCollapsed, setNavCollapsed] = useState(() => localStorage.getItem(NAV_COLLAPSED_KEY) === '1')
  useEffect(() => { localStorage.setItem(NAV_KEY, String(navW)) }, [navW])
  const toggleNavCollapsed = () => setNavCollapsed((v) => {
    const next = !v
    localStorage.setItem(NAV_COLLAPSED_KEY, next ? '1' : '0')
    return next
  })
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

  const runActive = run.status === 'connecting' || run.status === 'running'
  useEffect(() => {
    if (!runActive) return
    setProcessingNow(Date.now())
    const id = window.setInterval(() => setProcessingNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [runActive])

  const patchLast = (fn: (m: Msg) => Msg) =>
    setMsgs((prev) => prev.map((m, i) => (i === prev.length - 1 ? fn(m) : m)))

  const setRunState = useCallback((updater: RunState | ((prev: RunState) => RunState)) => {
    const next = typeof updater === 'function' ? (updater as (p: RunState) => RunState)(runRef.current) : updater
    runRef.current = next
    setRun(next)
  }, [])

  const isActiveRun = (r: RunState): r is RunActiveState =>
    r.status === 'connecting' || r.status === 'running'

  const acceptRun = (phase: ProcessingPhase, work: string, meta?: Partial<RunMeta>) => {
    const now = Date.now()
    setProcessingNow(now)
    setRunState((prev) => {
      if (prev.status === 'running') {
        return { ...prev, phase, work, meta: { ...prev.meta, ...(meta || {}) } }
      }
      if (prev.status === 'connecting') {
        return {
          status: 'running',
          startedAt: now,
          phase,
          work,
          tools: prev.tools,
          meta: { ...prev.meta, ...(meta || {}) },
        }
      }
      return {
        status: 'running',
        startedAt: now,
        phase,
        work,
        tools: [],
        meta: { ...(meta || {}) },
      }
    })
  }

  const updateRunMeta = (meta: Partial<RunMeta>) => setRunState((prev) =>
    isActiveRun(prev) ? { ...prev, meta: { ...prev.meta, ...meta } } : prev)

  const upsertRunTool = (tool: RunTool) => setRunState((prev) => {
    if (!isActiveRun(prev)) return prev
    const idx = prev.tools.findIndex((t) => t.id === tool.id)
    const tools = idx < 0 ? [...prev.tools, tool].slice(-6) : prev.tools.map((t, i) => (i === idx ? { ...t, ...tool } : t))
    return { ...prev, tools }
  })

  const turnStartRef = useRef<number>(0)   // 回合真正的开始时刻（send 那一瞬），finishRun 用它算 duration
  const finishRun = (status: 'ok' | 'err' = 'ok', reason?: string) => {
    const current = runRef.current
    if (!isActiveRun(current)) return
    const end = Date.now()
    const start = turnStartRef.current
      || (current.status === 'running' ? current.startedAt : current.requestedAt)
    const summary: RunSummary = {
      kind: 'run',
      durationMs: Math.max(0, end - start),
      status,
      reason,
      tools: current.tools,
    }
    setProcessingNow(end)
    setRunState(status === 'ok'
      ? { status: 'done', startedAt: start, endedAt: end, tools: current.tools, reason }
      : { status: 'error', startedAt: start, endedAt: end, tools: current.tools, reason })
    setSending(false)
    turnStartRef.current = 0                    // 清起点，别污染下一轮
    patchLast((m) => ({
      ...m,
      items: [summary, ...m.items.filter((it) => it.kind !== 'run')],
    }))
  }

  const onEvent = (e: ChatEvent) => {
    if (e.type === 'sse_open') {
      setRunState((prev) => prev.status === 'connecting'
        ? { ...prev, work: e.message || 'SSE 已连接，等待服务端接受请求' }
        : prev)
    }
    else if (e.type === 'heartbeat') {
      updateRunMeta({ heartbeatIdleMs: e.idle_ms, lastEvent: e.last_event })
    }
    else if (e.type === 'thread') {
      acceptRun('thinking', '线程已建立，等待模型响应')
      setThreadId(e.id)
    }
    else if (e.type === 'turn_start') {
      acceptRun('thinking', e.content || '正在初始化会话', {
        provider: e.provider,
        model: e.model,
        workspace: e.workspace,
      })
    }
    else if (e.type === 'mcp_start') {
      acceptRun('thinking', e.content || '正在连接 MCP 服务')
    }
    else if (e.type === 'mcp_ready') {
      acceptRun('thinking', e.content || 'MCP 工具已就绪', { toolCount: e.tool_count })
    }
    else if (e.type === 'prompt_ready') {
      acceptRun('thinking', e.content || '上下文已准备')
    }
    else if (e.type === 'loop_start') {
      acceptRun('thinking', 'Agent 循环已开始', { maxSteps: e.max_steps, toolCount: e.tool_count })
    }
    else if (e.type === 'model_start') {
      acceptRun('thinking', `第 ${e.step || 1} 步请求模型`, { step: e.step, toolCount: e.tool_count })
    }
    else if (e.type === 'model_first_delta') {
      acceptRun('generating', '正在生成回复', { step: e.step, ttftMs: e.ttft_ms })
    }
    else if (e.type === 'model_done') {
      updateRunMeta({ step: e.step, outputChars: e.delta_chars })
    }
    else if (e.type === 'tool_batch') {
      acceptRun('tool', `模型请求 ${e.count || 0} 个工具`, { step: e.step })
    }
    else if (e.type === 'content_start') {                             // 三段式：开头
      patchLast((m) => ({ ...m, streaming: true }))
    }
    else if (e.type === 'delta') {
      acceptRun('generating', '正在生成回复')
      patchLast((m) => ({ ...m, streaming: true, text: m.text + (e.text || '') }))
    }
    else if (e.type === 'content_end' || e.type === 'message_complete') { // 三段式：收尾 → 切 Markdown
      patchLast((m) => ({ ...m, streaming: false }))
    }
    else if (e.type === 'tool_call') {
      acceptRun('tool', `正在执行 ${e.name}`)
      upsertRunTool({ id: e.id || e.name, name: e.name, tone: 'run' })
    }
    else if (e.type === 'tool_start') {
      acceptRun('tool', `正在执行 ${e.name}`)
      upsertRunTool({ id: e.id || e.name, name: e.name, tone: 'run' })
    }
    else if (e.type === 'tool_result') {
      acceptRun('thinking', '等待模型继续')
      if (e.name) {
        upsertRunTool({
          id: e.id || e.name,
          name: e.name,
          tone: e.is_error ? 'err' : 'ok',
          durationMs: e.duration_ms,
          contentChars: e.content_chars,
          detail: (e.content || '').trim(),                   // 详情随 RunSummary 一起归纳
          truncated: e.truncated,                              // 服务端截过 2KB？UI 提供"看完整"
          originalChars: e.original_chars,
        })
      }
      // 结构化的音频分析结果升级成指标卡（RunSummary 展开也能看原始 JSON）
      const metrics = e.is_error ? null : buildMetrics(e.name, e.content)
      if (metrics) patchLast((m) => ({ ...m, items: [...m.items, { kind: 'metrics', ...metrics }] }))
    }
    else if (e.type === 'permission_request') {
      acceptRun('tool', `等待确认 ${e.name}`)
      patchLast((m) => ({ ...m, items: [...m.items, { kind: 'perm', id: e.id, label: e.name }] }))
    }
    else if (e.type === 'permission_result') {          // 服务端最终结局 → 卡片锁死状态
      const label = { allow: '已允许', deny: '已拒绝', timeout: '已超时', disconnected: '已中断' }[e.outcome] || e.outcome
      patchLast((m) => ({
        ...m,
        items: m.items.map((it) =>
          it.kind === 'perm' && it.id === e.id && !it.decided ? { ...it, decided: label } : it),
      }))
    }
    else if (e.type === 'context') {
      const contextMeta = {
        promptPct: e.pct,
        promptTokens: e.prompt_tokens,
        contextWindow: e.window,
      }
      if (isActiveRun(runRef.current)) updateRunMeta(contextMeta)
      else acceptRun('thinking', '上下文已准备', contextMeta)
    }
    else if (e.type === 'retry') {
      acceptRun('retry', e.content || '模型调用重试中')
      patchLast((m) => ({ ...m, items: [...m.items, { kind: 'trace', text: e.content }] }))
    }
    else if (e.type === 'compaction') {
      acceptRun('thinking', '正在整理上下文')
      patchLast((m) => ({ ...m, items: [...m.items, { kind: 'trace', text: e.content }] }))
    }
    else if (e.type === 'loop_done') {
      updateRunMeta({ step: e.steps })
    }
    // 三条终止分支都必须清 streaming —— 流式态用 plain-text 绕过 ReactMarkdown(index.css:247
    // 那条降级),只有 content_end/message_complete 会 patch streaming:false,如果 backend 提前
    // 走 final/done/error 没发过 content_end,消息就永远卡在 streaming=true,markdown 语法全部裸露
    else if (e.type === 'final')
      patchLast((m) => ({ ...m, streaming: false, text: m.text || e.text || '' }))
    else if (e.type === 'done') {
      patchLast((m) => ({ ...m, streaming: false }))
      finishRun('ok')
    }
    else if (e.type === 'error') {
      patchLast((m) => ({ ...m, streaming: false, text: '出错：' + (e.message || '') }))
      finishRun('err', e.message)
    }
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
    const requestedAt = Date.now()
    turnStartRef.current = requestedAt          // 回合起点（finishRun 用它算完整耗时）
    setProcessingNow(requestedAt)
    setRunState({
      status: 'connecting',
      requestedAt,
      phase: 'connecting',
      work: '正在连接模型服务',
      tools: [],
      meta: {},
    })
    abort.current = new AbortController()
    try {
      await streamChat({ goal, provider: state?.providers.default || settings?.default, thread_id: threadId, bypass }, onEvent, abort.current.signal)
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        finishRun('err', '已停止')                                  // 收敛为终态、停计时器
      } else {
        finishRun('err', String(err))
        patchLast((m) => ({ ...m, text: '请求失败：' + err }))
      }
    } finally {
      // 走到 finally 时如果 run 还是 active（干净退出但没收到 done——修 SSE 前的旧问题
      // 已由 sawTerminal 抛错拦住，这里作最后兜底）
      if (isActiveRun(runRef.current)) finishRun('ok')
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
    // 静默切到该对话所属项目（记忆按工作区隔离，续聊要用对的域）
    const t = (state?.threads || []).find((x) => x.id === id)
    if (t) switchWsSilent(t.workspace && wsNames.includes(t.workspace) ? t.workspace : 'default')
    // 从存档重建：同一回合的 assistant/tool 消息合并成一个气泡，
    // 一整轮的工具聚成一个 RunSummary（跟新流实时体验一致），
    // 存档里没记时长/is_error → 用文本特征近似
    const out: Msg[] = []
    let cur: Msg | null = null
    const byCallId = new Map<string, RunTool>()
    let curTools: RunTool[] = []
    const flushRun = (m: Msg | null) => {
      if (!m || curTools.length === 0) return
      const failed = curTools.some((t) => t.tone === 'err')
      const runItem: RunSummary = { kind: 'run', durationMs: 0, status: failed ? 'err' : 'ok', tools: curTools }
      m.items.unshift(runItem)
      curTools = []
      byCallId.clear()
    }
    for (const m of data.messages || []) {
      if (m.role === 'user') {
        flushRun(cur)
        out.push({ role: 'user', text: m.content || '', items: [] })
        cur = null
      } else if (m.role === 'assistant' && (m.content || m.tool_calls?.length)) {
        if (!cur) { cur = { role: 'assistant', text: '', items: [] }; out.push(cur) }
        for (const tc of m.tool_calls || []) {
          const id = tc.id || tc.name
          const tool: RunTool = { id, name: tc.name, tone: 'ok' }
          byCallId.set(id, tool)
          curTools.push(tool)
        }
        if (m.content) cur.text = m.content            // 回合内最后一条带文本的 = 最终回复
      } else if (m.role === 'tool' && cur) {
        const tool = m.tool_call_id ? byCallId.get(m.tool_call_id) : undefined
        if (!tool) continue
        const content = (m.content || '').trim()
        tool.detail = content
        tool.contentChars = content.length
        // 存档没记 is_error，按常见错误开头近似判断
        if (/^(analysis error|error|traceback|用户拒绝)/i.test(content)) tool.tone = 'err'
        const metrics = tool.tone === 'ok' ? buildMetrics(tool.name, content) : null
        if (metrics) cur.items.push({ kind: 'metrics', ...metrics })
      }
    }
    flushRun(cur)
    setMsgs(out)
  }

  const newChat = () => { setThreadId(null); setMsgs([]) }

  // 线程行 ⋯ 菜单：两段式删除确认（WebView2 的原生 confirm 不可靠，不用）
  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [confirmDel, setConfirmDel] = useState(false)
  const [renamingThread, setRenamingThread] = useState<string | null>(null)
  const [threadRenameVal, setThreadRenameVal] = useState('')
  const openMenu = (id: string | null) => { setMenuFor(id); setConfirmDel(false) }
  // 菜单：点外部才关闭（mouseleave 会在移向菜单项的路上误关，导致点击落空）
  useEffect(() => {
    if (!menuFor && !wsMenuFor) return
    const onDown = (e: MouseEvent) => {
      if (!(e.target as Element | null)?.closest?.('.threadmenu,.tmenu')) {
        setMenuFor(null); setWsMenuFor(null); setConfirmDel(false); setWsConfirmDel(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  })
  const delThread = async (id: string) => {
    await postJSON('/api/threads/delete', { id })
    openMenu(null)
    if (threadId === id) newChat()
    loadState()
  }
  const archThread = async (id: string, archived: boolean) => {
    await postJSON('/api/threads/archive', { id, archived })
    openMenu(null)
    loadState()
  }
  const renameThread = async (id: string) => {
    const title = threadRenameVal.trim()
    setRenamingThread(null)
    if (!title) return
    await postJSON('/api/threads/rename', { id, title })
    loadState()
  }

  // 展开/折叠是纯视图状态、与"当前项目"解耦（CC 行为：多个项目可同时展开）；持久化
  const [expandedWs, setExpandedWs] = useState<Set<string>>(() => {
    try { return new Set<string>(JSON.parse(localStorage.getItem('pm_wsExpanded') || '[]')) } catch { return new Set() }
  })
  const toggleWs = (ws: string) => setExpandedWs((prev) => {
    const next = new Set(prev)
    if (next.has(ws)) next.delete(ws); else next.add(ws)
    localStorage.setItem('pm_wsExpanded', JSON.stringify([...next]))
    return next
  })
  useEffect(() => {   // 首次进来至少展开当前工作区
    const cur = state?.workspace.current
    if (cur) setExpandedWs((prev) => (prev.size ? prev : new Set([cur])))
  }, [state?.workspace.current])
  // 每个分区独立的「展开显示」（超过 6 条）
  const [showAllWs, setShowAllWs] = useState<Set<string>>(new Set())
  const toggleShowAll = (ws: string) => setShowAllWs((prev) => {
    const next = new Set(prev)
    if (next.has(ws)) next.delete(ws); else next.add(ws)
    return next
  })
  // 「项目」标签：整组折叠
  const [projGroupCollapsed, setProjGroupCollapsed] = useState(() => localStorage.getItem('pm_projGroup') === '1')
  const toggleProjGroup = () => setProjGroupCollapsed((v) => { localStorage.setItem('pm_projGroup', v ? '0' : '1'); return !v })
  // 工作区切换只在实际行动时静默发生：✎ 在项目里新建 / 打开该项目的对话
  // 切换工作模式:再点一次已选的胶囊 = 切回默认(""),下一回合 runner 会拾起来
  const switchMode = async (id: string) => {
    const target = id === state?.mode?.current ? '' : id
    await postJSON('/api/mode/switch', { mode: target })
    loadState()
  }
  const switchWsSilent = async (name: string) => {
    if (name === state?.workspace.current) return
    await postJSON('/api/workspace/switch', { name })
    loadState()
  }
  const newChatIn = async (ws: string) => {
    await switchWsSilent(ws)
    newChat()
    setExpandedWs((prev) => (prev.has(ws) ? prev : new Set(prev).add(ws)))
  }

  // 项目管理：新建（label 行 + 号，内联输入）/ 重命名（内联）/ 删除（两段式）
  const [creatingWs, setCreatingWs] = useState(false)
  const [wsName, setWsName] = useState('')
  const skipCreateWsBlur = useRef(false)
  const [wsMenuFor, setWsMenuFor] = useState<string | null>(null)
  const [wsConfirmDel, setWsConfirmDel] = useState(false)
  const [renamingWs, setRenamingWs] = useState<string | null>(null)
  const [renameVal, setRenameVal] = useState('')
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [archiveConfirmFor, setArchiveConfirmFor] = useState<string | null>(null)
  const [archiveExpandedWs, setArchiveExpandedWs] = useState<Set<string>>(new Set())
  const openWsMenu = (ws: string | null) => { setWsMenuFor(ws); setWsConfirmDel(false); openMenu(null) }
  const openThreadMenu = (id: string | null) => { openMenu(id); setWsMenuFor(null); setWsConfirmDel(false) }
  const cancelCreateWs = () => { setCreatingWs(false); setWsName('') }
  const toggleCreateWs = () => {
    setCreatingWs((open) => {
      const next = !open
      setWsName('')
      if (next) {
        setProjGroupCollapsed(false)
        openWsMenu(null)
      }
      return next
    })
  }
  const createWs = async () => {
    if (skipCreateWsBlur.current) {
      skipCreateWsBlur.current = false
      return
    }
    const name = wsName.trim()
    setCreatingWs(false); setWsName('')
    if (!name) return
    await postJSON('/api/workspace/create', { name })   // 创建即切换
    setExpandedWs((prev) => {
      const next = new Set(prev).add(name)
      localStorage.setItem('pm_wsExpanded', JSON.stringify([...next]))
      return next
    })
    newChat(); loadState()
  }
  const renameWs = async (old: string) => {
    const name = renameVal.trim()
    setRenamingWs(null)
    if (!name || name === old) return
    await postJSON('/api/workspace/rename', { old, new: name })
    loadState()
  }
  const delWs = async (ws: string) => {
    if (state?.workspace.current === ws)               // 后端拒删当前：先切回「对话」
      await postJSON('/api/workspace/switch', { name: 'default' })
    await postJSON('/api/workspace/delete', { name: ws })
    openWsMenu(null); newChat(); loadState()
  }
  const archWs = async (ws: string, archived: boolean) => {
    await postJSON('/api/workspace/archive', { name: ws, archived })
    if (archived && state?.workspace.current === ws) {
      await postJSON('/api/workspace/switch', { name: 'default' })
      newChat()
    }
    openWsMenu(null)
    loadState()
  }

  const threadsNewest: ThreadInfo[] = (state?.threads || []).slice().reverse()
  const wsNames = state?.workspace.names || ['default']
  const archivedWs = new Set(state?.workspace.archived || [])
  const activeWsNames = wsNames.filter((w) => w !== 'default' && !archivedWs.has(w))
  const archivedWsNames = wsNames.filter((w) => w !== 'default' && archivedWs.has(w))
  const archivedThreads = threadsNewest.filter((t) => t.archived)
  const archiveCount = archivedWsNames.length + archivedThreads.length
  // 线程归组：所属工作区已不存在的归入「对话」
  const wsOf = (t: ThreadInfo) => (t.workspace && wsNames.includes(t.workspace) ? t.workspace : 'default')
  const archiveThreadsOfWs = (ws: string) => threadsNewest.filter((t) => wsOf(t) === ws)
  const toggleArchiveWs = (ws: string) => setArchiveExpandedWs((prev) => {
    const next = new Set(prev)
    if (next.has(ws)) next.delete(ws); else next.add(ws)
    return next
  })
  const activeThreadsIn = (ws: string) => threadsNewest.filter((t) => !t.archived && wsOf(t) === ws)
  const archiveThreadsIn = async (ws: string) => {
    const ids = activeThreadsIn(ws).map((t) => t.id)
    for (const id of ids) await postJSON('/api/threads/archive', { id, archived: true })
    openWsMenu(null)
    loadState()
  }
  const deleteThreadsIn = async (ws: string) => {
    const ids = activeThreadsIn(ws).map((t) => t.id)
    for (const id of ids) await postJSON('/api/threads/delete', { id })
    if (threadId && ids.includes(threadId)) newChat()
    openWsMenu(null)
    loadState()
  }
  const archiveAllProjects = async () => {
    const names = [...activeWsNames]
    if (names.includes(state?.workspace.current || 'default')) {
      await postJSON('/api/workspace/switch', { name: 'default' })
      newChat()
    }
    for (const name of names) await postJSON('/api/workspace/archive', { name, archived: true })
    openWsMenu(null)
    loadState()
  }
  const deleteAllProjects = async () => {
    const names = [...activeWsNames]
    if (names.includes(state?.workspace.current || 'default')) {
      await postJSON('/api/workspace/switch', { name: 'default' })
      newChat()
    }
    for (const name of names) await postJSON('/api/workspace/delete', { name })
    openWsMenu(null)
    loadState()
  }
  useEffect(() => {
    if (!archiveOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setArchiveOpen(false)
        setArchiveConfirmFor(null)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [archiveOpen])

  // 分区的线程列表（展开时显示；6 条 + 每分区独立的展开显示）
  const sectionThreads = (list: ThreadInfo[], ws: string) =>
    list.length ? (
      <>
        {(showAllWs.has(ws) ? list : list.slice(0, 6)).map(renderThread)}
        {list.length > 6 && (
          <button className="showmore" onClick={() => toggleShowAll(ws)}>
            {showAllWs.has(ws) ? '收起' : '展开显示'}
          </button>
        )}
      </>
    ) : <div className="wsempty">还没有对话</div>

  // 一个项目分区：头行 = 纯展开/折叠（多个项目可同时开）+ 悬停 ✎ 新建对话 + ⋯ 菜单
  const wsSection = (ws: string, archived = false) => {
    const cur = ws === (state?.workspace.current || 'default')
    const open = expandedWs.has(ws)
    const list = threadsNewest.filter((t) => !t.archived && wsOf(t) === ws)
    return (
      <div key={ws} className={'wsec' + (archived ? ' archived-ws' : '')}>
        {renamingWs === ws ? (
          <div className="wsinput">
            <input autoFocus value={renameVal} maxLength={24}
              onChange={(e) => setRenameVal(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') renameWs(ws); if (e.key === 'Escape') setRenamingWs(null) }}
              onBlur={() => renameWs(ws)} />
          </div>
        ) : (
          <div className="wsrow">
            <button className={'wshead' + (cur ? ' cur' : '')} onClick={() => toggleWs(ws)}>
              <I n={open ? 'folder_open' : 'folder'} s={18} /><span className="wn">{ws}</span>
              {!open && <span className="wschev"><I n="chevron_right" s={17} /></span>}
            </button>
            <button className="tmenu wsnew" aria-label="在此项目新建对话" title="在此项目新建对话"
              onClick={(e) => { e.stopPropagation(); newChatIn(ws) }}>
              <I n="edit_square" s={16} />
            </button>
            <button className="tmenu wsmenu" aria-label="项目选项"
              onClick={(e) => { e.stopPropagation(); openWsMenu(wsMenuFor === ws ? null : ws) }}>
              <I n="more_horiz" s={18} />
            </button>
            {wsMenuFor === ws && (
              <div className="threadmenu">
                <button onClick={() => archWs(ws, !archived)}>
                  <I n={archived ? 'unarchive' : 'archive'} s={17} />{archived ? '取消归档' : '归档项目'}
                </button>
                <button onClick={() => { setRenamingWs(ws); setRenameVal(ws); openWsMenu(null) }}>
                  <I n="edit" s={17} />重命名
                </button>
                <button className="danger"
                  onClick={() => (wsConfirmDel ? delWs(ws) : setWsConfirmDel(true))}>
                  <I n="delete" s={17} />{wsConfirmDel ? '确认删除？' : '删除项目'}
                </button>
              </div>
            )}
          </div>
        )}
        {open && sectionThreads(list, ws)}
      </div>
    )
  }

  const renderThread = (t: ThreadInfo) => (
    renamingThread === t.id ? (
      <div key={t.id} className="thread editing">
        <input autoFocus className="tedit" value={threadRenameVal} maxLength={48}
          onChange={(e) => setThreadRenameVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') renameThread(t.id); if (e.key === 'Escape') setRenamingThread(null) }}
          onBlur={() => renameThread(t.id)} />
      </div>
    ) : (
      <div key={t.id} className={'thread' + (t.id === threadId ? ' active' : '')}>
        <button className="topen" onClick={() => openThread(t.id)}>
          <span className="t">{cleanTitle(t.title || '') || t.id}</span>
        </button>
        <span className="ttime">{relTime(t.mtime)}</span>
        <button className="tmenu" aria-label="对话选项"
          onClick={(e) => { e.stopPropagation(); openThreadMenu(menuFor === t.id ? null : t.id) }}>
          <I n="more_horiz" s={18} />
        </button>
        {menuFor === t.id && (
          <div className="threadmenu">
            <button onClick={() => { setRenamingThread(t.id); setThreadRenameVal(cleanTitle(t.title || '') || t.id); openMenu(null) }}>
              <I n="edit" s={17} />重命名
            </button>
            <button onClick={() => archThread(t.id, !t.archived)}>
              <I n={t.archived ? 'unarchive' : 'archive'} s={17} />{t.archived ? '取消归档' : '归档'}
            </button>
            <button className="danger"
              onClick={() => (confirmDel ? delThread(t.id) : setConfirmDel(true))}>
              <I n="delete" s={17} />{confirmDel ? '确认删除？' : '删除'}
            </button>
          </div>
        )}
      </div>
    )
  )

  const geminiOk = !!settings?.gemini?.has_key
  const perceptionOn = !!state?.mcp.find((m) => m.name === 'music-perception')?.enabled
  const reaperOk = reaper?.state === 'connected'
  // 默认 provider 是否既存在于 providers.json 又已设 key。缺一项就不算就绪 —— 否则会出现
  // 胶囊显示"已就绪"、发消息却报"未找到 provider" / "缺 API key" 的自相矛盾状态
  const defaultProvider = state?.providers.default
  const llmOk = !!(defaultProvider && settings?.providers?.[defaultProvider]?.has_key)
  const allReady = llmOk && geminiOk && perceptionOn && reaperOk
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
        name="audio-upload" aria-label="添加音频"
        accept="audio/*,.wav,.mp3,.flac,.ogg,.aif,.aiff,.m4a"
        onChange={(e) => onPickAudio(e.target.files?.[0])} />
      <button className="iconbtn" aria-label="添加音频" title="添加音频文件（分析 / 转 MIDI）"
        onClick={() => fileRef.current?.click()}>
        {uploading ? <span className="spinning"><I n="progress_activity" /></span> : <I n="add" />}
      </button>
      <textarea
        name="message"
        aria-label="消息内容"
        rows={1} value={input} placeholder="描述你的音乐想法，交给 Prism…"
        onChange={(e) => setInput(e.target.value)}
        onInput={(e) => { const t = e.currentTarget; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 140) + 'px'; t.style.overflowY = t.scrollHeight > 140 ? 'auto' : 'hidden' }}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
      />
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
        <div className="brandgroup">
          <button className="iconbtn navtoggle" aria-label={navCollapsed ? '展开侧边栏' : '收起侧边栏'}
            title={navCollapsed ? '展开侧边栏' : '收起侧边栏'}
            aria-pressed={!navCollapsed}
            onClick={toggleNavCollapsed}>
            <span className="sidebar-icon" aria-hidden />
          </button>
          <span className="brand" {...drag}>Prism Motif</span>
        </div>
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
        {state?.mode?.list?.length ? (
          <div className="mode-selector" role="tablist" aria-label="工作模式">
            {state.mode.list.map((m) => {
              const active = m.id === state.mode?.current
              return (
                <button key={m.id} role="tab" aria-selected={active}
                  className={'mode-chip' + (active ? ' active' : '')}
                  style={active && m.accent ? { '--mode-accent': m.accent } as CSSProperties : undefined}
                  onClick={() => switchMode(m.id)} title={m.label}>
                  <I n={m.icon || 'auto_awesome'} s={16} />
                  <span>{m.label}</span>
                </button>
              )
            })}
          </div>
        ) : null}
        <button className="iconbtn" aria-label="设置" onClick={() => setSettingsOpen(true)}><I n="settings" /></button>
        {inTauri && <WinControls />}
      </header>

      <div className={'body' + (navCollapsed ? ' nav-collapsed' : '')}>
        {!navCollapsed && (
          <>
        <aside className="nav" style={{ '--nav-w': `${navW}px` } as CSSProperties}>
          <button className="newchat" onClick={newChat}><I n="add" />新对话</button>
          <div className="wsrow navgroup">
            <button className="convhead" onClick={toggleProjGroup}>
              项目<I n={projGroupCollapsed ? 'chevron_right' : 'expand_more'} s={16} />
            </button>
            <button className="tmenu wsnew" aria-label={creatingWs ? '取消新建项目' : '新建项目'} title={creatingWs ? '取消新建项目' : '新建项目'}
              onPointerDown={(e) => { if (creatingWs) { skipCreateWsBlur.current = true; e.preventDefault() } }}
              onClick={(e) => { e.stopPropagation(); toggleCreateWs() }}>
              <I n={creatingWs ? 'close' : 'create_new_folder'} s={17} />
            </button>
            <button className="tmenu wsmenu" aria-label="项目分组选项"
              onClick={(e) => { e.stopPropagation(); openWsMenu(wsMenuFor === '__projects__' ? null : '__projects__') }}>
              <I n="more_horiz" s={18} />
            </button>
            {wsMenuFor === '__projects__' && (
              <div className="threadmenu">
                <button onClick={archiveAllProjects}>
                  <I n="archive" s={17} />归档全部项目
                </button>
                <button className="danger"
                  onClick={() => (wsConfirmDel ? deleteAllProjects() : setWsConfirmDel(true))}>
                  <I n="delete" s={17} />{wsConfirmDel ? '确认删除全部？' : '删除全部项目'}
                </button>
              </div>
            )}
          </div>
          {creatingWs && (
            <div className="wsinput create">
              <I n="create_new_folder" s={18} />
              <input id="new-project-name" name="new-project-name" autoFocus value={wsName} placeholder="项目名称" maxLength={24}
                onChange={(e) => setWsName(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') createWs(); if (e.key === 'Escape') cancelCreateWs() }}
                onBlur={createWs} />
              <button className="mini" aria-label="确认新建项目" title="确认"
                onMouseDown={(e) => e.preventDefault()}
                onClick={createWs}>
                <I n="check" s={17} />
              </button>
              <button className="mini" aria-label="取消新建项目" title="取消"
                onMouseDown={(e) => e.preventDefault()}
                onClick={cancelCreateWs}>
                <I n="close" s={17} />
              </button>
            </div>
          )}
          {!projGroupCollapsed && activeWsNames.map((ws) => wsSection(ws))}

          <div className="wsrow conv">
            <button className="convhead" onClick={() => toggleWs('default')}>
              对话<I n={expandedWs.has('default') ? 'expand_more' : 'chevron_right'} s={16} />
            </button>
            <button className="tmenu wsnew" aria-label="新建对话" title="新建对话"
              onClick={(e) => { e.stopPropagation(); newChatIn('default') }}>
              <I n="edit_square" s={16} />
            </button>
            <button className="tmenu wsmenu" aria-label="对话分组选项"
              onClick={(e) => { e.stopPropagation(); openWsMenu(wsMenuFor === 'default' ? null : 'default') }}>
              <I n="more_horiz" s={18} />
            </button>
            {wsMenuFor === 'default' && (
              <div className="threadmenu">
                <button onClick={() => archiveThreadsIn('default')}>
                  <I n="archive" s={17} />归档所有对话
                </button>
                <button className="danger"
                  onClick={() => (wsConfirmDel ? deleteThreadsIn('default') : setWsConfirmDel(true))}>
                  <I n="delete" s={17} />{wsConfirmDel ? '确认删除所有？' : '删除所有对话'}
                </button>
              </div>
            )}
          </div>
          {expandedWs.has('default') &&
            sectionThreads(threadsNewest.filter((t) => !t.archived && wsOf(t) === 'default'), 'default')}

          <button className="archbtn" onClick={() => setArchiveOpen(true)}>
            <I n="archive" s={16} />
            <span>已归档</span>
          </button>
        </aside>

        <div className="nav-handle" style={{ left: navW - 4 }} onPointerDown={startNavDrag}
          role="separator" aria-orientation="vertical" aria-label="调整侧边栏宽度" />
          </>
        )}

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
                {msgs.map((m, i) => {
                  if (m.role === 'user') return <UserBubble key={i} text={m.text} />
                  const chips = m.items.filter((it): it is Chip => it.kind === 'chip')
                  const runs = m.items.filter((it): it is RunSummary => it.kind === 'run')
                  const others = m.items.filter((it) => it.kind !== 'chip' && it.kind !== 'run')
                  const currentRun = isActiveRun(run) ? run : null
                  const isCurrent = !!currentRun && i === msgs.length - 1
                  const liveStartedAt = currentRun?.status === 'running' ? currentRun.startedAt : currentRun?.requestedAt
                  const liveElapsed = liveStartedAt ? elapsedLabel(processingNow - liveStartedAt) : '0s'
                  return (
                    <div key={i} className="a">
                      <div className="abody">
                        {!isCurrent && runs.map((run, j) => <RunSummaryLine key={j} run={run} threadId={threadId} />)}
                        {isCurrent && currentRun && (
                          <RunPanel
                            phase={currentRun.phase}
                            elapsed={liveElapsed}
                            currentWork={currentRun.work}
                            tools={currentRun.tools}
                            meta={currentRun.meta}
                          />
                        )}
                        {chips.length > 0 && <ToolBar chips={chips} />}
                        {m.text && (m.streaming ? (
                          <div className="atext streaming">{m.text}<span className="cursor" /></div>
                        ) : (
                          <div className="atext md">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                          </div>
                        ))}
                        {others.map((it, j) => <Rendered key={j} it={it} onDecide={decide} />)}
                      </div>
                    </div>
                  )
                })}
              </div>
              <div className="composer">{composer}</div>
            </>
          )}
        </main>
      </div>

      {archiveOpen && (
        <div className="archive-bg" onMouseDown={(e) => {
          if (e.target === e.currentTarget) {
            setArchiveOpen(false)
            setArchiveConfirmFor(null)
          }
        }}>
          <section className="archive-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-title">
            <div className="archive-head">
              <div>
                <h2 id="archive-title">已归档</h2>
                <p>{archiveCount} 个项目或对话</p>
              </div>
              <button className="iconbtn" aria-label="关闭已归档"
                onClick={() => { setArchiveOpen(false); setArchiveConfirmFor(null) }}>
                <I n="close" />
              </button>
            </div>
            <div className="archive-body">
              {archivedWsNames.length > 0 && (
                <section className="archive-sec">
                  <h3>项目</h3>
                  <div className="archive-list">
                    {archivedWsNames.map((ws) => (
                      <div className="archive-project" key={ws}>
                        <div className="archive-row">
                          <button className="archive-expand" aria-label={archiveExpandedWs.has(ws) ? '收起项目对话' : '展开项目对话'}
                            onClick={() => toggleArchiveWs(ws)}>
                            <I n={archiveExpandedWs.has(ws) ? 'expand_more' : 'chevron_right'} s={18} />
                          </button>
                          <span className="archive-ico"><I n="folder" s={20} /></span>
                          <button className="archive-main link" onClick={() => toggleArchiveWs(ws)}>
                            <div className="archive-name">{ws}</div>
                            <div className="archive-meta">{archiveThreadsOfWs(ws).length} 个对话</div>
                          </button>
                          <button className="archive-act" onClick={() => archWs(ws, false)}>
                            <I n="unarchive" s={17} />恢复
                          </button>
                          <button className="archive-act danger"
                            onClick={async () => {
                              const key = `ws:${ws}`
                              if (archiveConfirmFor === key) {
                                await delWs(ws)
                                setArchiveConfirmFor(null)
                              } else setArchiveConfirmFor(key)
                            }}>
                            <I n="delete" s={17} />{archiveConfirmFor === `ws:${ws}` ? '确认删除' : '删除'}
                          </button>
                        </div>
                        {archiveExpandedWs.has(ws) && (
                          <div className="archive-sublist">
                            {archiveThreadsOfWs(ws).length ? archiveThreadsOfWs(ws).map((t) => (
                              <div className="archive-subrow" key={t.id}>
                                <span className="archive-subico"><I n="chat_bubble" s={17} /></span>
                                <button className="archive-main link" onClick={() => { setArchiveOpen(false); openThread(t.id) }}>
                                  <div className="archive-name">{cleanTitle(t.title || '') || t.id}</div>
                                  <div className="archive-meta">{relTime(t.mtime)}{t.archived ? ' · 已归档' : ''}</div>
                                </button>
                                {t.archived && (
                                  <button className="archive-act" onClick={() => archThread(t.id, false)}>
                                    <I n="unarchive" s={17} />恢复
                                  </button>
                                )}
                              </div>
                            )) : <div className="archive-subempty">还没有对话</div>}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {archivedThreads.length > 0 && (
                <section className="archive-sec">
                  <h3>对话</h3>
                  <div className="archive-list">
                    {archivedThreads.map((t) => (
                      <div className="archive-row" key={t.id}>
                        <span className="archive-ico"><I n="chat_bubble" s={20} /></span>
                        <button className="archive-main link" onClick={() => { setArchiveOpen(false); openThread(t.id) }}>
                          <div className="archive-name">{cleanTitle(t.title || '') || t.id}</div>
                          <div className="archive-meta">{relTime(t.mtime)} · {wsOf(t) === 'default' ? '对话' : wsOf(t)}</div>
                        </button>
                        <button className="archive-act" onClick={() => archThread(t.id, false)}>
                          <I n="unarchive" s={17} />恢复
                        </button>
                        <button className="archive-act danger"
                          onClick={async () => {
                            const key = `thread:${t.id}`
                            if (archiveConfirmFor === key) {
                              await delThread(t.id)
                              setArchiveConfirmFor(null)
                            } else setArchiveConfirmFor(key)
                          }}>
                          <I n="delete" s={17} />{archiveConfirmFor === `thread:${t.id}` ? '确认删除' : '删除'}
                        </button>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {archiveCount === 0 && (
                <div className="archive-empty">
                  <I n="archive" s={28} />
                  <span>还没有归档项目或对话</span>
                </div>
              )}
            </div>
          </section>
        </div>
      )}

      {settingsOpen && state && (
        <Settings state={state} trust={bypass} setTrust={setBypass}
          onClose={() => setSettingsOpen(false)}
          onSaved={() => { loadState(); loadSettings() }}
          onOpenOnboarding={() => { setSettingsOpen(false); setOnboarding(true) }} />
      )}
      {onboarding && (
        <Onboarding reaper={reaper} onReaperRefresh={loadReaper}
          onDone={() => { localStorage.setItem('pm_onboarded', '1'); setOnboarding(false); loadSettings() }} />
      )}
    </div>
  )
}

function runToneIcon(tone: RunTone) {
  if (tone === 'ok') return 'check_circle'
  if (tone === 'err') return 'error'
  if (tone === 'info') return 'info'
  return 'progress_activity'
}

function phaseLabel(phase: ProcessingPhase) {
  if (phase === 'connecting') return '连接中'
  if (phase === 'retry') return '重试中'
  return '已处理'
}

function RunPanel({
  phase, elapsed, currentWork, tools, meta,
}: {
  phase: ProcessingPhase; elapsed: string; currentWork: string;
  tools: RunTool[]; meta: RunMeta;
}) {
  const [open, setOpen] = useState(false)
  const activeTools = tools.filter((t) => t.tone === 'run')
  const failedTools = tools.filter((t) => t.tone === 'err').length
  const metricChips: { key: string; icon: string; label: string; title?: string }[] = []
  if (meta.provider || meta.model)
    metricChips.push({ key: 'model', icon: 'memory', label: [meta.provider, meta.model].filter(Boolean).join(' · ') })
  if (meta.workspace)
    metricChips.push({ key: 'workspace', icon: meta.workspace === 'default' ? 'chat_bubble' : 'folder', label: meta.workspace === 'default' ? '对话' : meta.workspace })
  if (meta.step)
    metricChips.push({ key: 'step', icon: 'account_tree', label: `第 ${meta.step}${meta.maxSteps ? `/${meta.maxSteps}` : ''} 步` })
  if (meta.toolCount != null)
    metricChips.push({ key: 'tools', icon: 'construction', label: `${meta.toolCount} 个工具` })
  if (meta.promptPct != null)
    metricChips.push({
      key: 'context',
      icon: 'data_usage',
      label: `上下文 ${Math.round(meta.promptPct * 100)}%`,
      title: meta.promptTokens && meta.contextWindow ? `${meta.promptTokens} / ${meta.contextWindow} tokens` : undefined,
    })

  const headline = activeTools.length ? `${currentWork} · ${activeTools[0].name}` : currentWork
  return (
    <details className={`run-panel active ${phase}`} open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary className="run-head" role="status" aria-live="polite">
        <span className="run-bars" aria-hidden>
          <span />
          <span />
          <span />
        </span>
        <span className="run-copy">
          <span className="run-title">
            <span>{phaseLabel(phase)}</span>
            <span className="run-time">{elapsed}</span>
          </span>
          <span className="run-sub">{headline}</span>
        </span>
        <I n="expand_more" s={19} />
      </summary>

      <div className="run-body">
        {metricChips.length > 0 && (
          <div className="run-meta">
            {metricChips.map((m) => (
              <span className="run-pill" key={m.key} title={m.title}>
                <I n={m.icon} s={15} />{m.label}
              </span>
            ))}
          </div>
        )}

        {tools.length > 0 && (
          <div className="run-section">
            <div className="run-section-title">
              <span>工具</span>
              {activeTools.length > 0 && <span>{activeTools.length} 个运行中</span>}
              {failedTools > 0 && <span className="bad">{failedTools} 个失败</span>}
            </div>
            {tools.slice(-4).map((tool) => (
              <div className={`run-row ${tool.tone}`} key={tool.id}>
                <span className="run-dot"><I n={runToneIcon(tool.tone)} s={15} /></span>
                <span className="run-row-main">
                  <span className="run-row-label">{tool.name}</span>
                  {(tool.contentChars != null || tool.durationMs != null) && (
                    <span className="run-row-detail">
                      {tool.durationMs != null ? msLabel(tool.durationMs) : ''}
                      {tool.contentChars != null ? `${tool.durationMs != null ? ' · ' : ''}${tool.contentChars} 字符` : ''}
                    </span>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </details>
  )
}

function RunSummaryLine({ run, threadId }: { run: RunSummary; threadId?: string | null }) {
  const toolCount = run.tools.length
  // "看完整"能力：截断的 tool 展开后点一下从 /api/threads/:id 拉全量替换 detail
  const [fullDetails, setFullDetails] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState<string | null>(null)
  const loadFull = async (toolId: string) => {
    if (!threadId || fullDetails[toolId] || loading) return
    setLoading(toolId)
    try {
      const data = await getJSON<{ messages: { role: string; tool_call_id?: string; content?: string }[] }>('/api/threads/' + encodeURIComponent(threadId))
      const msg = (data.messages || []).find((m) => m.role === 'tool' && m.tool_call_id === toolId)
      if (msg) setFullDetails((p) => ({ ...p, [toolId]: (msg.content || '').trim() }))
    } finally { setLoading(null) }
  }
  const failedTools = run.tools.filter((t) => t.tone === 'err').length
  const ok = run.status === 'ok'
  const hasDetails = toolCount > 0 || !!run.reason
  return (
    <details className={`run-summary ${run.status}`}>
      <summary>
        <I n={ok ? 'check_circle' : 'error'} s={16} />
        <span>{ok ? '已完成' : '处理失败'}{run.durationMs > 0 ? ' · ' + elapsedLabel(run.durationMs) : ''}</span>
        {toolCount > 0 && (
          <span className="run-summary-note">
            已运行 {toolCount} 个工具{failedTools ? ` · ${failedTools} 个失败` : ''}
          </span>
        )}
        {hasDetails && <I n="expand_more" s={17} />}
      </summary>
      {hasDetails && (
        <div className="run-summary-body">
          {run.reason && <div className="run-summary-reason">{run.reason}</div>}
          {run.tools.map((tool) => (
            tool.detail ? (
              <details className={`run-row hasdetail ${tool.tone}`} key={tool.id}>
                <summary>
                  <span className="run-dot"><I n={runToneIcon(tool.tone)} s={15} /></span>
                  <span className="run-row-main">
                    <span className="run-row-label">{tool.name}</span>
                    {(tool.durationMs != null || tool.contentChars != null) && (
                      <span className="run-row-detail">
                        {tool.durationMs != null ? msLabel(tool.durationMs) : ''}
                        {tool.contentChars != null ? `${tool.durationMs != null ? ' · ' : ''}${tool.contentChars} 字符` : ''}
                      </span>
                    )}
                  </span>
                  <I n="expand_more" s={15} />
                </summary>
                {fullDetails[tool.id] ? (
                  <pre className="tooldetail">{fullDetails[tool.id]}</pre>
                ) : (
                  <>
                    <pre className="tooldetail">{tool.detail.length > 700 ? tool.detail.slice(0, 700) + ' …' : tool.detail}</pre>
                    {tool.truncated && threadId && (
                      <button className="tool-loadfull" onClick={() => loadFull(tool.id)} disabled={loading === tool.id}>
                        {loading === tool.id ? '加载中…' : `查看完整（还有 ${(tool.originalChars || 0) - (tool.detail?.length || 0)} 字符）`}
                      </button>
                    )}
                  </>
                )}
              </details>
            ) : (
              <div className={`run-row ${tool.tone}`} key={tool.id}>
                <span className="run-dot"><I n={runToneIcon(tool.tone)} s={15} /></span>
                <span className="run-row-main">
                  <span className="run-row-label">{tool.name}</span>
                  {(tool.durationMs != null || tool.contentChars != null) && (
                    <span className="run-row-detail">
                      {tool.durationMs != null ? msLabel(tool.durationMs) : ''}
                      {tool.contentChars != null ? `${tool.durationMs != null ? ' · ' : ''}${tool.contentChars} 字符` : ''}
                    </span>
                  )}
                </span>
              </div>
            )
          ))}
        </div>
      )}
    </details>
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
  if (it.kind === 'run') return <RunSummaryLine run={it} />
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
