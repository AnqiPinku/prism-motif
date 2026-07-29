import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAX_RECORD_SECONDS,
  chunkRms,
  encodeWav,
  encodeWavBytes,
  formatClock,
  recordingName,
} from '../src/recorder.ts'


function ascii(bytes: Uint8Array, off: number, len: number): string {
  return String.fromCharCode(...bytes.subarray(off, off + len))
}

function dv(bytes: Uint8Array): DataView {
  return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
}

test('encodeWavBytes writes an exact RIFF/fmt/data header', () => {
  const bytes = encodeWavBytes([new Float32Array([0.5]), new Float32Array([-0.5, 0.25])], 48000)
  const v = dv(bytes)
  assert.equal(bytes.length, 44 + 6)
  assert.equal(ascii(bytes, 0, 4), 'RIFF')
  assert.equal(v.getUint32(4, true), 36 + 6)      // RIFF 大小 = 36 + data
  assert.equal(ascii(bytes, 8, 4), 'WAVE')
  assert.equal(ascii(bytes, 12, 4), 'fmt ')
  assert.equal(v.getUint32(16, true), 16)         // fmt 块长度
  assert.equal(v.getUint16(20, true), 1)          // PCM
  assert.equal(v.getUint16(22, true), 1)          // 单声道
  assert.equal(v.getUint32(24, true), 48000)
  assert.equal(v.getUint32(28, true), 96000)      // 字节率
  assert.equal(v.getUint16(32, true), 2)          // 块对齐
  assert.equal(v.getUint16(34, true), 16)         // 位深
  assert.equal(ascii(bytes, 36, 4), 'data')
  assert.equal(v.getUint32(40, true), 6)
})

test('encodeWavBytes converts to 16-bit and clips beyond full scale', () => {
  const bytes = encodeWavBytes([new Float32Array([0, 0.5, 1, -1, 2, -2])], 44100)
  const v = dv(bytes)
  const samples = [0, 1, 2, 3, 4, 5].map((i) => v.getInt16(44 + i * 2, true))
  assert.deepEqual(samples, [0, 16384, 32767, -32768, 32767, -32768])
})

test('encodeWavBytes concatenates odd-sized chunks in order', () => {
  const chunks = [new Float32Array([1]), new Float32Array([]), new Float32Array([-1, 1, -1])]
  const bytes = encodeWavBytes(chunks, 8000)
  const v = dv(bytes)
  assert.equal(v.getUint32(40, true), 8)
  const samples = [0, 1, 2, 3].map((i) => v.getInt16(44 + i * 2, true))
  assert.deepEqual(samples, [32767, -32768, 32767, -32768])
})

test('encodeWav wraps the same bytes in an audio/wav Blob', async () => {
  const chunks = [new Float32Array([0.25, -0.25])]
  const blob = encodeWav(chunks, 16000)
  assert.equal(blob.type, 'audio/wav')
  assert.deepEqual(new Uint8Array(await blob.arrayBuffer()), encodeWavBytes(chunks, 16000))
})

test('formatClock renders m:ss including the 5 minute cap', () => {
  assert.equal(formatClock(0), '0:00')
  assert.equal(formatClock(59.9), '0:59')
  assert.equal(formatClock(299), '4:59')
  assert.equal(formatClock(MAX_RECORD_SECONDS), '5:00')
})

test('recordingName formats local date and time', () => {
  assert.equal(recordingName(new Date(2026, 6, 29, 21, 43, 5)), 'recording-20260729-2143.wav')
  assert.equal(recordingName(new Date(2026, 0, 3, 4, 7)), 'recording-20260103-0407.wav')
})

test('chunkRms of known signals', () => {
  assert.equal(chunkRms(new Float32Array(128)), 0)
  assert.equal(chunkRms(new Float32Array([1, -1, 1, -1])), 1)
  assert.equal(chunkRms(new Float32Array(0)), 0)
  assert.ok(Math.abs(chunkRms(new Float32Array([0.5, -0.5])) - 0.5) < 1e-9)
})
