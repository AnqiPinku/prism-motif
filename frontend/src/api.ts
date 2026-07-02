export interface State {
  providers: { default: string; names: string[]; windows: Record<string, number> }
  mcp: { name: string; enabled: boolean }[]
  skills: { name: string; disclosure: string; tags: string[]; enabled: boolean }[]
  threads: { id: string; title?: string; archived?: boolean; workspace?: string; mtime?: number }[]
  workspace: { current: string; names: string[]; archived?: string[] }
}

export interface ReaperStatus {
  state: 'connected' | 'running_not_loaded' | 'not_running' | 'not_loaded'
  reaper_running: boolean | null
  bridge_loaded: boolean
  installed: boolean
  installed_current: boolean
  resource_path?: string
  resource_detected?: boolean
  error?: string
}

type SseEnvelope = { seq?: number; ts?: number; elapsed_ms?: number }
export type ChatEvent = SseEnvelope & (
  | { type: 'sse_open'; phase?: string; message?: string }
  | { type: 'heartbeat'; idle_ms?: number; last_event?: string }
  | { type: 'thread'; id: string }
  | { type: 'turn_start'; provider?: string; model?: string; workspace?: string; phase?: string; content?: string }
  | { type: 'mcp_start'; server_count?: number; content?: string }
  | { type: 'mcp_ready'; server_count?: number; tool_count?: number; content?: string }
  | { type: 'prompt_ready'; prior_messages?: number; sent_messages?: number; summary?: boolean; content?: string }
  | { type: 'loop_start'; max_steps?: number; tool_count?: number }
  | { type: 'model_start'; step?: number; message_count?: number; tool_count?: number }
  | { type: 'model_first_delta'; step?: number; ttft_ms?: number }
  | { type: 'model_done'; step?: number; kind?: string; duration_ms?: number; delta_chars?: number; delta_chunks?: number }
  | { type: 'delta'; text: string; step?: number }
  | { type: 'tool_batch'; step?: number; count?: number }
  | { type: 'tool_call' | 'tool_start'; id?: string; name: string; arguments: unknown; step?: number; index?: number; count?: number }
  | { type: 'tool_result'; id?: string; name?: string; is_error?: boolean; content?: string; duration_ms?: number; content_chars?: number; permission?: string }
  | { type: 'permission_request'; id: string; name: string; arguments: unknown }
  | { type: 'context'; prompt_tokens: number; window: number; pct: number }
  | { type: 'compaction'; kind?: string; count?: number; content: string }
  | { type: 'retry'; attempt?: number; max?: number; content: string }
  | { type: 'final'; text: string }
  | { type: 'loop_done'; steps?: number; duration_ms?: number; reason?: string }
  | { type: 'turn_saved'; thread_id?: string; messages?: number; content?: string }
  | { type: 'error'; message: string }
  | { type: 'done' }
)

// In the Tauri shell the UI is served from tauri:// (bundled), so the gateway is a
// cross-origin absolute URL; in a plain browser it's same-origin (relative).
export const inTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
const API = inTauri ? 'http://127.0.0.1:8770' : ''

export async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(API + url)
  return r.json()
}

export async function postJSON<T = unknown>(url: string, body: unknown): Promise<T> {
  const r = await fetch(API + url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return r.json()
}

// POST /api/chat streams standard SSE frames. The JSON payload still carries
// `type`, but we also honor `event:` and `id:` so the stream can evolve safely.
export async function streamChat(
  body: { goal: string; provider?: string; thread_id?: string | null; bypass: boolean },
  onEvent: (e: ChatEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(API + '/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  if (!res.body) return
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let sawTerminal = false                   // 收到过 done/error 才算干净结束
  const dispatch = (block: string) => {
    const data: string[] = []
    let eventName = ''
    let id = ''
    for (const raw of block.split(/\r?\n/)) {
      if (!raw || raw.startsWith(':')) continue
      const i = raw.indexOf(':')
      const field = i >= 0 ? raw.slice(0, i) : raw
      let value = i >= 0 ? raw.slice(i + 1) : ''
      if (value.startsWith(' ')) value = value.slice(1)
      if (field === 'data') data.push(value)
      else if (field === 'event') eventName = value
      else if (field === 'id') id = value
    }
    if (data.length === 0) return
    try {
      const parsed = JSON.parse(data.join('\n')) as { type?: string; seq?: number; [key: string]: unknown }
      if (!parsed.type && eventName) parsed.type = eventName
      if (id && !parsed.seq) parsed.seq = Number(id) || undefined
      if (parsed.type === 'done' || parsed.type === 'error') sawTerminal = true
      onEvent(parsed as unknown as ChatEvent)
    } catch {
      /* skip malformed event */
    }
  }
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      dispatch(block)
    }
  }
  // close-delimited SSE：EOF 是唯一信号；没收到 done/error 就是服务端崩溃 / 连接断裂，
  // 必须让上层看到失败，否则半截回答会被渲染成 ✓ 完成。
  if (!sawTerminal) throw new Error('连接中断，回答可能不完整')
}

export const respondPermission = (id: string, allow: boolean) =>
  postJSON('/api/permission', { id, allow })

// 聊天附音频：传原始字节给 gateway，拿回本机路径（agent 的分析/转 MIDI 工具吃路径）。
export async function uploadAudio(file: File): Promise<{ path?: string; error?: string }> {
  const r = await fetch(API + '/api/upload', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/octet-stream',
      'X-Filename': encodeURIComponent(file.name),
    },
    body: file,
  })
  return r.json()
}
