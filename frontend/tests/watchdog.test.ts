import assert from 'node:assert/strict'
import test from 'node:test'

import {
  createChatState,
  failChat,
  isActiveRun,
  reduceChatEvent,
  startChat,
  watchdogState,
} from '../src/chatReducer.ts'


function started(now = 1_000) {
  return startChat(createChatState(), '做一段 loop', now)
}

test('lastEventAt updates on message and heartbeat events', () => {
  const s0 = started(1_000)
  assert.equal(s0.lastEventAt, 1_000)                    // 回合开始即计时
  const s1 = reduceChatEvent(s0, { type: 'delta', seq: 1, text: 'A' }, 2_000)
  assert.equal(s1.lastEventAt, 2_000)
  const s2 = reduceChatEvent(s1, { type: 'heartbeat', seq: 2, idle_ms: 5_000 }, 7_000)
  assert.equal(s2.lastEventAt, 7_000)                    // 心跳同样续命
  // 重复 seq 被丢弃时不得刷新计时
  const dup = reduceChatEvent(s2, { type: 'delta', seq: 2, text: 'B' }, 9_000)
  assert.equal(dup.lastEventAt, 7_000)
})

test('lastGoal is stashed when a turn starts', () => {
  assert.equal(started().lastGoal, '做一段 loop')
  assert.equal(started().retryable, false)
})

test('watchdogState thresholds and boundaries', () => {
  const base = 10_000
  assert.equal(watchdogState(base, base, true), 'ok')
  assert.equal(watchdogState(base + 14_999, base, true), 'ok')
  assert.equal(watchdogState(base + 15_000, base, true), 'degraded')   // 15s 整点降级
  assert.equal(watchdogState(base + 44_999, base, true), 'degraded')
  assert.equal(watchdogState(base + 45_000, base, true), 'lost')       // 45s 整点丢失
  assert.equal(watchdogState(base + 999_999, base, false), 'ok')       // 非活跃回合永远 ok
  assert.equal(watchdogState(base + 999_999, null, true), 'ok')        // 没有事件时间戳也不误报
})

test('watchdog lost path rolls back to a retryable terminal error', () => {
  const failed = failChat(started(), '连接丢失', 46_000, '请求失败：', true)
  assert.equal(failed.terminal, 'error')
  assert.equal(failed.run.status, 'error')
  assert.equal(failed.retryable, true)
  assert.match(failed.messages.at(-1)?.text || '', /连接丢失/)
})

test('done reason=cancelled keeps the stopped presentation', () => {
  const s = reduceChatEvent(started(), { type: 'done', seq: 1, cancelled: true, reason: 'cancelled' }, 2_000)
  assert.equal(s.terminal, 'cancelled')
  assert.equal(s.run.status, 'error')
  assert.equal(s.retryable, false)
  const run = s.messages.at(-1)?.items.find((item) => item.kind === 'run')
  assert.equal(run?.kind === 'run' ? run.reason : '', '已停止')
})

test('done reason=deadline is an error-toned, retryable ending', () => {
  const s = reduceChatEvent(started(), { type: 'done', seq: 1, cancelled: false, reason: 'deadline' }, 2_000)
  assert.equal(s.terminal, 'error')
  assert.equal(s.run.status, 'error')
  assert.equal(s.retryable, true)
  const run = s.messages.at(-1)?.items.find((item) => item.kind === 'run')
  assert.equal(run?.kind === 'run' ? run.reason : '', '本轮超时被终止')
})

test('done reason=ok stays the success path', () => {
  const s = reduceChatEvent(started(), { type: 'done', seq: 1, cancelled: false, reason: 'ok' }, 2_000)
  assert.equal(s.terminal, 'done')
  assert.equal(s.run.status, 'done')
  assert.equal(s.retryable, false)
})

test('done with degraded/circuit_open appends warning lines to the run summary', () => {
  const s = reduceChatEvent(started(), {
    type: 'done', seq: 1, reason: 'ok',
    degraded: ['music-perception'], circuit_open: ['reaper'],
  }, 2_000)
  const run = s.messages.at(-1)?.items.find((item) => item.kind === 'run')
  const warnings = run?.kind === 'run' ? run.warnings || [] : []
  assert.deepEqual(warnings, ['⚠ 服务降级: music-perception', '⚠ 熔断: reaper'])
})

test('done with empty degraded lists produces no warnings', () => {
  const s = reduceChatEvent(started(), { type: 'done', seq: 1, reason: 'ok', degraded: [], circuit_open: [] }, 2_000)
  const run = s.messages.at(-1)?.items.find((item) => item.kind === 'run')
  assert.equal(run?.kind === 'run' ? run.warnings : null, undefined)
})

test('mcp_degraded mid-turn produces a run-panel notice line', () => {
  const s = reduceChatEvent(started(), {
    type: 'mcp_degraded', seq: 1, failed: ['music-perception', 'reaper'], content: '【工具降级】…',
  }, 2_000)
  assert.ok(isActiveRun(s.run))
  const notices = isActiveRun(s.run) ? s.run.meta.notices : []
  assert.deepEqual(notices, ['⚠ 部分工具不可用: music-perception, reaper'])
})
