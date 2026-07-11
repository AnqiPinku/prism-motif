import assert from 'node:assert/strict'
import test from 'node:test'

import { streamChat, type ChatEvent } from '../src/api.ts'


const originalFetch = globalThis.fetch

function sseResponse(body: string): Response {
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

test.afterEach(() => {
  globalThis.fetch = originalFetch
})

test('streamChat parses SSE fields and accepts an explicit done event', async () => {
  globalThis.fetch = async () => sseResponse(
    'id: 1\nevent: delta\ndata: {"text":"hello"}\n\n' +
    'id: 2\nevent: done\ndata: {"cancelled":false}\n\n',
  )
  const events: ChatEvent[] = []
  await streamChat(
    { goal: 'test', bypass: false },
    (event) => events.push(event),
    new AbortController().signal,
  )
  assert.deepEqual(events.map((event) => [event.type, event.seq]), [['delta', 1], ['done', 2]])
})

test('streamChat rejects EOF without done or error', async () => {
  globalThis.fetch = async () => sseResponse('event: delta\ndata: {"text":"partial"}\n\n')
  await assert.rejects(
    streamChat(
      { goal: 'test', bypass: false },
      () => undefined,
      new AbortController().signal,
    ),
    /连接中断/,
  )
})

test('streamChat treats an error event as a valid terminal frame', async () => {
  globalThis.fetch = async () => sseResponse('event: error\ndata: {"message":"failed"}\n\n')
  const events: ChatEvent[] = []
  await streamChat(
    { goal: 'test', bypass: false },
    (event) => events.push(event),
    new AbortController().signal,
  )
  assert.equal(events[0]?.type, 'error')
})
