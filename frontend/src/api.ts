export interface State {
  providers: { default: string; names: string[]; windows: Record<string, number> }
  mcp: { name: string; enabled: boolean }[]
  skills: { name: string; disclosure: string; tags: string[]; enabled: boolean }[]
  threads: { id: string; title?: string }[]
  workspace: { current: string; names: string[] }
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

export type ChatEvent =
  | { type: 'thread'; id: string }
  | { type: 'delta'; text: string }
  | { type: 'tool_call'; name: string; arguments: unknown }
  | { type: 'tool_result'; name?: string; is_error?: boolean; content?: string }
  | { type: 'permission_request'; id: string; name: string; arguments: unknown }
  | { type: 'context'; prompt_tokens: number; window: number; pct: number }
  | { type: 'compaction'; content: string }
  | { type: 'retry'; content: string }
  | { type: 'final'; text: string }
  | { type: 'error'; message: string }
  | { type: 'done' }

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

// POST /api/chat streams newline-delimited SSE ("data: {json}\n\n"). Parse and dispatch.
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
  if (!res.body) return
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i)
      buf = buf.slice(i + 2)
      const line = block.split('\n').find((l) => l.startsWith('data: '))
      if (line) {
        try { onEvent(JSON.parse(line.slice(6))) } catch { /* skip partial */ }
      }
    }
  }
}

export const respondPermission = (id: string, allow: boolean) =>
  postJSON('/api/permission', { id, allow })
