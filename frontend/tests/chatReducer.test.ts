import assert from 'node:assert/strict'
import test from 'node:test'

import type { ChatEvent } from '../src/api.ts'
import {
  cancelChat,
  createChatState,
  decidePermission,
  failChat,
  reduceChatEvent,
  replaceConversation,
  startChat,
} from '../src/chatReducer.ts'


function started(now = 1_000) {
  return startChat(createChatState(), '做一段 loop', now)
}

test('reduceChatEvent covers the full successful event lifecycle', () => {
  const events: ChatEvent[] = [
    { type: 'sse_open', seq: 1, message: 'connected' },
    { type: 'heartbeat', seq: 2, idle_ms: 10, last_event: 'sse_open' },
    { type: 'thread', seq: 3, id: 'thread-1' },
    { type: 'turn_start', seq: 4, provider: 'fake', model: 'fake-1', workspace: 'default' },
    { type: 'mcp_start', seq: 5, server_count: 2 },
    { type: 'mcp_ready', seq: 6, server_count: 2, tool_count: 29 },
    { type: 'prompt_ready', seq: 7, prior_messages: 0, sent_messages: 1 },
    { type: 'loop_start', seq: 8, max_steps: 8, tool_count: 29 },
    { type: 'status', seq: 9, state: 'thinking', verb: '思考中' },
    { type: 'model_start', seq: 10, step: 1, message_count: 1, tool_count: 29 },
    { type: 'model_first_delta', seq: 11, step: 1, ttft_ms: 25 },
    { type: 'content_start', seq: 12, step: 1, block_type: 'text' },
    { type: 'delta', seq: 13, step: 1, text: '完成' },
    { type: 'model_done', seq: 14, step: 1, kind: 'tools', delta_chars: 2, delta_chunks: 1 },
    { type: 'content_end', seq: 15, step: 1, block_type: 'text' },
    { type: 'message_complete', seq: 16, step: 1, delta_chars: 2 },
    { type: 'tool_batch', seq: 17, step: 1, count: 1 },
    { type: 'tool_call', seq: 18, id: 'call-1', name: 'analyze_audio', arguments: {} },
    { type: 'tool_start', seq: 19, id: 'call-1', name: 'analyze_audio', arguments: {} },
    {
      type: 'tool_result',
      seq: 20,
      id: 'call-1',
      name: 'analyze_audio',
      content: '{"tempo":{"bpm":90},"loudness":{"integrated_lufs":-14}}',
      duration_ms: 30,
      content_chars: 62,
    },
    { type: 'permission_request', seq: 21, id: 'perm-1', name: 'render_to_wav', arguments: {}, risk: 'write' },
    { type: 'permission_result', seq: 22, id: 'perm-1', outcome: 'allow' },
    { type: 'context', seq: 23, prompt_tokens: 100, window: 1_000, pct: 0.1 },
    { type: 'retry', seq: 24, attempt: 1, max: 3, kind: 'connect', content: '重试中' },
    { type: 'compaction', seq: 25, kind: 'elide', count: 1, content: '已压缩' },
    { type: 'status', seq: 26, state: 'streaming' },
    { type: 'status', seq: 27, state: 'tool_executing' },
    { type: 'status', seq: 28, state: 'permission_pending' },
    { type: 'status', seq: 29, state: 'compacting' },
    { type: 'loop_done', seq: 30, steps: 1, reason: 'final' },
    { type: 'final', seq: 31, text: '完成' },
    { type: 'turn_saved', seq: 32, thread_id: 'thread-1', messages: 3 },
    { type: 'status', seq: 33, state: 'idle' },
    { type: 'done', seq: 34, cancelled: false },
  ]

  const state = events.reduce((current, event, index) =>
    reduceChatEvent(current, event, 1_010 + index), started())

  assert.equal(state.terminal, 'done')
  assert.equal(state.threadId, 'thread-1')
  assert.equal(state.run.status, 'done')
  assert.equal(state.messages.at(-1)?.text, '完成')
  assert.equal(state.messages.at(-1)?.streaming, false)
  assert.ok(state.messages.at(-1)?.items.some((item) => item.kind === 'metrics'))
  assert.ok(state.messages.at(-1)?.items.some((item) => item.kind === 'perm' && item.decided === '已允许'))
  assert.ok(state.messages.at(-1)?.items.some((item) => item.kind === 'trace'))
  assert.ok(state.messages.at(-1)?.items.some((item) => item.kind === 'run'))
})

test('unknown event types are ignored instead of corrupting state', () => {
  const modeActive = { type: 'mode_active', seq: 1, mode: 'compose' } as unknown as ChatEvent
  const state = reduceChatEvent(started(), modeActive, 1_100)
  assert.ok(state, 'reducer must never return undefined for unknown events')
  assert.equal(state.lastSeq, 1)
  const after = reduceChatEvent(state, { type: 'delta', seq: 2, text: 'A' }, 1_101)
  assert.equal(after.messages.at(-1)?.text, 'A')
})

test('duplicate and out-of-order sequence numbers are ignored', () => {
  let state = reduceChatEvent(started(), { type: 'delta', seq: 2, text: 'A' }, 1_100)
  const afterDuplicate = reduceChatEvent(state, { type: 'delta', seq: 2, text: 'B' }, 1_101)
  const afterLate = reduceChatEvent(afterDuplicate, { type: 'delta', seq: 1, text: 'C' }, 1_102)
  assert.strictEqual(afterDuplicate, state)
  assert.strictEqual(afterLate, state)
  assert.equal(state.messages.at(-1)?.text, 'A')
})

test('events arriving after done are ignored', () => {
  let state = reduceChatEvent(started(), { type: 'done', seq: 1 }, 1_100)
  const late = reduceChatEvent(state, { type: 'delta', seq: 2, text: 'late' }, 1_200)
  assert.strictEqual(late, state)
  assert.equal(late.messages.at(-1)?.text, '')
})

test('cancel is terminal and ignores later events', () => {
  const cancelled = cancelChat(started(), 1_100)
  const late = reduceChatEvent(cancelled, { type: 'delta', seq: 1, text: 'late' }, 1_200)
  assert.equal(cancelled.terminal, 'cancelled')
  assert.equal(cancelled.run.status, 'error')
  assert.strictEqual(late, cancelled)
})

test('EOF without done is represented as an error, never success', () => {
  const failed = failChat(started(), '连接中断，回答可能不完整', 1_100)
  assert.equal(failed.terminal, 'error')
  assert.equal(failed.run.status, 'error')
  assert.match(failed.messages.at(-1)?.text || '', /连接中断/)
})

test('explicit server error is terminal', () => {
  const failed = reduceChatEvent(started(), { type: 'error', seq: 1, message: 'provider failed' }, 1_100)
  assert.equal(failed.terminal, 'error')
  assert.equal(failed.run.status, 'error')
  assert.equal(failed.messages.at(-1)?.text, '出错：provider failed')
})

test('conversation replacement and local permission decisions stay pure', () => {
  const base = replaceConversation(createChatState(), 'saved', [
    { role: 'assistant', text: '', items: [{ kind: 'perm', id: 'p', label: 'render' }] },
  ])
  const decided = decidePermission(base, 'p', false)
  assert.notStrictEqual(decided, base)
  assert.equal(decided.messages[0].items[0].kind, 'perm')
  assert.equal(decided.messages[0].items[0].kind === 'perm' ? decided.messages[0].items[0].decided : '', '已拒绝')
  assert.equal(base.messages[0].items[0].kind === 'perm' ? base.messages[0].items[0].decided : '', undefined)
})
