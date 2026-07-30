import type { ChatEvent } from './api'
import { captionForTool, coerceArgs, formatToolArgs, resultBadge } from './toolCaptions.ts'

export type Chip = { kind: 'chip'; tone: 'ok' | 'err' | 'run'; label: string; detail?: string }
export type ProcessingPhase = 'connecting' | 'thinking' | 'generating' | 'tool' | 'retry'
export type RunTone = 'run' | 'ok' | 'err' | 'info'
export type RunTool = {
  id: string
  name: string
  tone: RunTone
  caption?: string          // 中文动作文案（captionForTool 产物），渲染时优先于原始工具名
  badge?: string            // 结果徽标（resultBadge 产物），如「已写入 ×8」
  args?: string             // 原始参数 JSON 文本，折叠区里展示
  durationMs?: number
  contentChars?: number
  detail?: string
  truncated?: boolean
  originalChars?: number
}
export type RunSummary = {
  kind: 'run'
  durationMs: number
  status: 'ok' | 'err'
  tools: RunTool[]
  reason?: string
  warnings?: string[]       // 终帧带回的降级 / 熔断名单，渲染成 ⚠ 警示行
}
export type RunMeta = {
  provider?: string
  model?: string
  workspace?: string
  step?: number
  maxSteps?: number
  toolCount?: number
  promptPct?: number
  promptTokens?: number
  contextWindow?: number
  ttftMs?: number
  outputChars?: number
  heartbeatIdleMs?: number
  lastEvent?: string
  notices?: string[]        // 回合中途的提醒行（如 mcp_degraded 的「部分工具不可用」）
}
export type RunActiveState =
  | { status: 'connecting'; requestedAt: number; phase: 'connecting'; work: string; tools: RunTool[]; meta: RunMeta }
  | { status: 'running'; startedAt: number; phase: ProcessingPhase; work: string; tools: RunTool[]; meta: RunMeta }
export type RunState =
  | { status: 'idle' }
  | RunActiveState
  | { status: 'done'; startedAt: number; endedAt: number; tools: RunTool[]; reason?: string }
  | { status: 'error'; startedAt: number; endedAt: number; tools: RunTool[]; reason?: string }
export type Tile = { label: string; value: string; unit?: string }
export type Item =
  | Chip
  | RunSummary
  | { kind: 'trace'; text: string }
  | { kind: 'perm'; id: string; label: string; risk?: string; decided?: string }
  | { kind: 'metrics'; title: string; tiles: Tile[] }
export type Msg = { role: 'user' | 'assistant'; text: string; items: Item[]; streaming?: boolean }

export type ChatState = {
  messages: Msg[]
  threadId: string | null
  sending: boolean
  run: RunState
  turnStartedAt: number
  lastSeq?: number
  terminal?: 'done' | 'error' | 'cancelled'
  lastEventAt: number | null   // 最近一次归约事件（含心跳）的时刻，看门狗以此判连接健康
  lastGoal: string             // 本回合的原始目标文本，重试时回填输入框
  retryable?: boolean          // 看门狗丢失 / deadline / error 收尾的回合，展示重试入口
}

export const createChatState = (): ChatState => ({
  messages: [],
  threadId: null,
  sending: false,
  run: { status: 'idle' },
  turnStartedAt: 0,
  lastEventAt: null,
  lastGoal: '',
})

// 看门狗：只看「距最近一次事件多久没响应」；15s 内正常，15-45s 视为连接不稳，45s 起判定丢失。
// 回合不活跃（或还没有任何事件时间戳）时永远 ok，避免空闲界面误报。
export function watchdogState(now: number, lastEventAt: number | null, runActive: boolean): 'ok' | 'degraded' | 'lost' {
  if (!runActive || lastEventAt == null) return 'ok'
  const idle = now - lastEventAt
  if (idle >= 45_000) return 'lost'
  if (idle >= 15_000) return 'degraded'
  return 'ok'
}

export const isActiveRun = (run: RunState): run is RunActiveState =>
  run.status === 'connecting' || run.status === 'running'

export function patchLastMessage(state: ChatState, patch: (message: Msg) => Msg): ChatState {
  if (state.messages.length === 0) return state
  const last = state.messages[state.messages.length - 1]
  return { ...state, messages: [...state.messages.slice(0, -1), patch(last)] }
}

function acceptRun(state: ChatState, phase: ProcessingPhase, work: string, now: number, meta?: Partial<RunMeta>): ChatState {
  const current = state.run
  if (current.status === 'running') {
    return { ...state, run: { ...current, phase, work, meta: { ...current.meta, ...meta } } }
  }
  if (current.status === 'connecting') {
    return {
      ...state,
      run: {
        status: 'running',
        startedAt: now,
        phase,
        work,
        tools: current.tools,
        meta: { ...current.meta, ...meta },
      },
    }
  }
  return {
    ...state,
    run: { status: 'running', startedAt: now, phase, work, tools: [], meta: { ...meta } },
  }
}

function updateRunMeta(state: ChatState, meta: Partial<RunMeta>): ChatState {
  if (!isActiveRun(state.run)) return state
  return { ...state, run: { ...state.run, meta: { ...state.run.meta, ...meta } } }
}

function upsertRunTool(state: ChatState, tool: RunTool): ChatState {
  if (!isActiveRun(state.run)) return state
  const index = state.run.tools.findIndex((item) => item.id === tool.id)
  const tools = index < 0
    ? [...state.run.tools, tool].slice(-6)
    : state.run.tools.map((item, itemIndex) => itemIndex === index ? { ...item, ...tool } : item)
  return { ...state, run: { ...state.run, tools } }
}

function finishRun(
  state: ChatState,
  status: 'ok' | 'err',
  now: number,
  reason?: string,
  terminal: ChatState['terminal'] = status === 'ok' ? 'done' : 'error',
  extra: { warnings?: string[]; retryable?: boolean } = {},
): ChatState {
  if (!isActiveRun(state.run)) {
    return { ...state, sending: false, terminal, turnStartedAt: 0, retryable: !!extra.retryable }
  }
  const start = state.turnStartedAt
    || (state.run.status === 'running' ? state.run.startedAt : state.run.requestedAt)
  const summary: RunSummary = {
    kind: 'run',
    durationMs: Math.max(0, now - start),
    status,
    reason,
    warnings: extra.warnings?.length ? extra.warnings : undefined,
    tools: state.run.tools,
  }
  const withSummary = patchLastMessage(state, (message) => ({
    ...message,
    streaming: false,
    items: [summary, ...message.items.filter((item) => item.kind !== 'run')],
  }))
  return {
    ...withSummary,
    run: status === 'ok'
      ? { status: 'done', startedAt: start, endedAt: now, tools: state.run.tools, reason }
      : { status: 'error', startedAt: start, endedAt: now, tools: state.run.tools, reason },
    sending: false,
    turnStartedAt: 0,
    terminal,
    retryable: !!extra.retryable,
  }
}

export function startChat(state: ChatState, goal: string, now: number): ChatState {
  return {
    ...state,
    messages: [
      ...state.messages,
      { role: 'user', text: goal, items: [] },
      { role: 'assistant', text: '', items: [] },
    ],
    sending: true,
    run: {
      status: 'connecting',
      requestedAt: now,
      phase: 'connecting',
      work: '正在连接模型服务',
      tools: [],
      meta: {},
    },
    turnStartedAt: now,
    lastSeq: undefined,
    terminal: undefined,
    lastEventAt: now,
    lastGoal: goal,
    retryable: false,
  }
}

export function failChat(state: ChatState, reason: string, now: number, prefix = '请求失败：', retryable = false): ChatState {
  if (state.terminal) return state
  const failed = patchLastMessage(state, (message) => ({
    ...message,
    streaming: false,
    text: prefix + reason,
  }))
  return finishRun(failed, 'err', now, reason, 'error', { retryable })
}

export function cancelChat(state: ChatState, now: number, reason = '已停止'): ChatState {
  if (state.terminal) return state
  return finishRun(
    patchLastMessage(state, (message) => ({ ...message, streaming: false })),
    'err',
    now,
    reason,
    'cancelled',
  )
}

export function replaceConversation(state: ChatState, threadId: string | null, messages: Msg[]): ChatState {
  return {
    ...state,
    threadId,
    messages,
    sending: false,
    run: { status: 'idle' },
    turnStartedAt: 0,
    lastSeq: undefined,
    terminal: undefined,
    lastEventAt: null,
    retryable: false,
  }
}

export function decidePermission(state: ChatState, id: string, allow: boolean): ChatState {
  return patchLastMessage(state, (message) => ({
    ...message,
    items: message.items.map((item) =>
      item.kind === 'perm' && item.id === id
        ? { ...item, decided: allow ? '已允许' : '已拒绝' }
        : item),
  }))
}

export function buildMetrics(name?: string, content?: string): { title: string; tiles: Tile[] } | null {
  if (!name || !content) return null
  let data: Record<string, unknown>
  try { data = JSON.parse(content) as Record<string, unknown> } catch { return null }
  if (typeof data !== 'object' || data === null) return null
  const tiles: Tile[] = []
  if (/analyze_audio|measure_loudness/.test(name)) {
    const key = data.key as Record<string, unknown> | undefined
    const tempo = data.tempo as Record<string, unknown> | undefined
    const loudness = data.loudness as Record<string, unknown> | undefined
    if (typeof key?.key === 'string') tiles.push({ label: '调性', value: `${key.key} ${key.mode || ''}`.trim() })
    if (typeof tempo?.bpm === 'number') tiles.push({ label: '速度', value: String(tempo.bpm), unit: 'BPM' })
    if (typeof loudness?.integrated_lufs === 'number') tiles.push({ label: '响度', value: String(loudness.integrated_lufs), unit: 'LUFS' })
    if (typeof loudness?.loudness_range_lu === 'number') tiles.push({ label: '动态范围', value: String(loudness.loudness_range_lu), unit: 'LU' })
    if (typeof loudness?.true_peak_dbtp === 'number') tiles.push({ label: '真峰值', value: String(loudness.true_peak_dbtp), unit: 'dBTP' })
    if (typeof data.duration_seconds === 'number') tiles.push({ label: '长度', value: String(data.duration_seconds), unit: '秒' })
    return tiles.length >= 2 ? { title: '音频分析', tiles: tiles.slice(0, 6) } : null
  }
  if (/listen_subjective/.test(name)) {
    if (typeof data.mood === 'string') tiles.push({ label: '情绪', value: data.mood })
    for (const [key, label] of [['muddy', '浑浊'], ['harsh', '刺耳'], ['sibilant', '齿音'], ['bright', '明亮']] as const) {
      if (typeof data[key] === 'number') tiles.push({ label, value: String(data[key]), unit: '/100' })
    }
    return tiles.length >= 2 ? { title: 'Gemini 听感', tiles: tiles.slice(0, 6) } : null
  }
  return null
}

export function reduceChatEvent(state: ChatState, event: ChatEvent, now: number): ChatState {
  if (state.terminal) return state
  if (event.seq != null && state.lastSeq != null && event.seq <= state.lastSeq) return state

  // 每个被归约的事件（含心跳）都刷新 lastEventAt，看门狗据此判断连接是否还活着
  let next: ChatState = event.seq == null
    ? { ...state, lastEventAt: now }
    : { ...state, lastSeq: event.seq, lastEventAt: now }
  switch (event.type) {
    case 'sse_open':
      if (next.run.status === 'connecting') {
        next = { ...next, run: { ...next.run, work: event.message || 'SSE 已连接，等待服务端接受请求' } }
      }
      return next
    case 'heartbeat':
      return updateRunMeta(next, { heartbeatIdleMs: event.idle_ms, lastEvent: event.last_event })
    case 'thread':
      return { ...acceptRun(next, 'thinking', '线程已建立，等待模型响应', now), threadId: event.id }
    case 'turn_start':
      return acceptRun(next, 'thinking', event.content || '正在初始化会话', now, {
        provider: event.provider,
        model: event.model,
        workspace: event.workspace,
      })
    case 'mcp_start':
      return acceptRun(next, 'thinking', event.content || '正在连接 MCP 服务', now)
    case 'mcp_ready':
      return acceptRun(next, 'thinking', event.content || 'MCP 工具已就绪', now, { toolCount: event.tool_count })
    case 'mcp_degraded': {
      // 部分 MCP 启动失败：回合早期就把「哪些工具不可用」亮给用户，不等到终帧
      const running = acceptRun(next, 'thinking', event.content || '部分 MCP 服务不可用', now)
      if (!isActiveRun(running.run)) return running
      const names = (event.failed || []).join(', ')
      const notice = '⚠ 部分工具不可用: ' + (names || event.content || '未知服务')
      const meta = running.run.meta
      return {
        ...running,
        run: { ...running.run, meta: { ...meta, notices: [...(meta.notices || []), notice] } },
      }
    }
    case 'prompt_ready':
      return acceptRun(next, 'thinking', event.content || '上下文已准备', now)
    case 'loop_start':
      return acceptRun(next, 'thinking', 'Agent 循环已开始', now, { maxSteps: event.max_steps, toolCount: event.tool_count })
    case 'model_start':
      return acceptRun(next, 'thinking', `第 ${event.step || 1} 步请求模型`, now, { step: event.step, toolCount: event.tool_count })
    case 'model_first_delta':
      return acceptRun(next, 'generating', '正在生成回复', now, { step: event.step, ttftMs: event.ttft_ms })
    case 'model_done':
      return updateRunMeta(next, { step: event.step, outputChars: event.delta_chars })
    case 'tool_batch':
      return acceptRun(next, 'tool', `模型请求 ${event.count || 0} 个工具`, now, { step: event.step })
    case 'content_start':
      return patchLastMessage(next, (message) => ({ ...message, streaming: true }))
    case 'delta':
      return patchLastMessage(
        acceptRun(next, 'generating', '正在生成回复', now),
        (message) => ({ ...message, streaming: true, text: message.text + (event.text || '') }),
      )
    case 'content_end':
    case 'message_complete':
      return patchLastMessage(next, (message) => ({ ...message, streaming: false }))
    case 'tool_call':
    case 'tool_start': {
      // 状态卡约定：调用一到就把工具名 + 参数翻成中文动作文案，原始参数收进折叠区
      const caption = captionForTool(event.name, coerceArgs(event.arguments))
      const running = acceptRun(next, 'tool', `正在执行 ${caption}`, now)
      return upsertRunTool(running, {
        id: event.id || event.name,
        name: event.name,
        tone: 'run',
        caption,
        args: formatToolArgs(event.arguments),
      })
    }
    case 'tool_result': {
      let result = acceptRun(next, 'thinking', '等待模型继续', now)
      if (event.name) {
        result = upsertRunTool(result, {
          id: event.id || event.name,
          name: event.name,
          tone: event.is_error ? 'err' : 'ok',
          // 成功结果里能便宜提取的完成事实（写入数 / 音符数 / 已延长 item…）做徽标
          badge: (event.is_error ? null : resultBadge(event.name, event.content)) ?? undefined,
          durationMs: event.duration_ms,
          contentChars: event.content_chars,
          detail: (event.content || '').trim(),
          truncated: event.truncated,
          originalChars: event.original_chars,
        })
      }
      const metrics = event.is_error ? null : buildMetrics(event.name, event.content)
      return metrics
        ? patchLastMessage(result, (message) => ({ ...message, items: [...message.items, { kind: 'metrics', ...metrics }] }))
        : result
    }
    case 'permission_request':
      return patchLastMessage(
        acceptRun(next, 'tool', `等待确认 ${event.name}`, now),
        (message) => ({
          ...message,
          items: [...message.items, { kind: 'perm', id: event.id, label: event.name, risk: event.risk }],
        }),
      )
    case 'permission_result': {
      const label = { allow: '已允许', deny: '已拒绝', timeout: '已超时', disconnected: '已中断' }[event.outcome]
      return patchLastMessage(next, (message) => ({
        ...message,
        items: message.items.map((item) =>
          item.kind === 'perm' && item.id === event.id && !item.decided
            ? { ...item, decided: label }
            : item),
      }))
    }
    case 'context': {
      const meta = { promptPct: event.pct, promptTokens: event.prompt_tokens, contextWindow: event.window }
      return isActiveRun(next.run)
        ? updateRunMeta(next, meta)
        : acceptRun(next, 'thinking', '上下文已准备', now, meta)
    }
    case 'retry':
      return patchLastMessage(
        acceptRun(next, 'retry', event.content || '模型调用重试中', now),
        (message) => ({ ...message, items: [...message.items, { kind: 'trace', text: event.content }] }),
      )
    case 'compaction':
      return patchLastMessage(
        acceptRun(next, 'thinking', '正在整理上下文', now),
        (message) => ({ ...message, items: [...message.items, { kind: 'trace', text: event.content }] }),
      )
    case 'loop_done':
      return updateRunMeta(next, { step: event.steps })
    case 'final':
      return patchLastMessage(next, (message) => ({ ...message, streaming: false, text: message.text || event.text || '' }))
    case 'done': {
      const closed = patchLastMessage(next, (message) => ({ ...message, streaming: false }))
      // 终帧「验尸」信息：降级 / 熔断名单变成回合汇总里的 ⚠ 警示行
      const warnings: string[] = []
      if (event.degraded?.length) warnings.push('⚠ 服务降级: ' + event.degraded.join(', '))
      if (event.circuit_open?.length) warnings.push('⚠ 熔断: ' + event.circuit_open.join(', '))
      const reason = event.reason || (event.cancelled ? 'cancelled' : 'ok')
      if (reason === 'cancelled') {
        // 保持与本地停止一致的呈现（err 底色 + 「已停止」+ cancelled 终态）
        return finishRun(closed, 'err', now, '已停止', 'cancelled', { warnings })
      }
      if (reason === 'deadline') {
        return finishRun(closed, 'err', now, '本轮超时被终止', 'error', { warnings, retryable: true })
      }
      if (reason === 'error') {
        // 正常路径 error 事件先到并已收尾；这里兜底孤立的 error 终帧
        return finishRun(closed, 'err', now, '本轮出错结束', 'error', { warnings, retryable: true })
      }
      return finishRun(closed, 'ok', now, undefined, 'done', { warnings })
    }
    case 'error':
      return finishRun(
        patchLastMessage(next, (message) => ({ ...message, streaming: false, text: '出错：' + (event.message || '') })),
        'err',
        now,
        event.message,
        'error',
        { retryable: true },
      )
    case 'status': {
      if (event.state === 'idle') return next
      const phase: ProcessingPhase = event.state === 'streaming'
        ? 'generating'
        : event.state === 'tool_executing' || event.state === 'permission_pending'
          ? 'tool'
          : 'thinking'
      const work = event.verb || (next.run.status === 'running' ? next.run.work : '处理中')
      return acceptRun(next, phase, work, now)
    }
    case 'turn_saved':
      return next
    default:
      // 后端会发 union 之外的事件（如 mode_active）；未知事件必须静默忽略，绝不能落出 switch 返回 undefined
      return next
  }
}
