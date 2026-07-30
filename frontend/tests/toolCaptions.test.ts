import assert from 'node:assert/strict'
import test from 'node:test'

import { captionForTool, coerceArgs, formatToolArgs, resultBadge } from '../src/toolCaptions.ts'


test('captionForTool 把已知工具翻成中文动作 + 关键参数', () => {
  assert.equal(captionForTool('transcribe_melody', { path: 'C:\\tmp\\vocal take.wav' }), '转录 vocal take.wav')
  assert.equal(captionForTool('transcribe_melody', { file_path: '/tmp/melody.mp3' }), '转录 melody.mp3')
  assert.equal(
    captionForTool('replace_midi_notes', { track_index: 2, item_index: 0, notes: [{}, {}, {}] }),
    '替换音符 ×3（轨 2）',
  )
  assert.equal(captionForTool('add_midi_notes', { track_index: 1, notes: [{}, {}] }), '写入音符 ×2')
  assert.equal(captionForTool('add_track', { name: '鼓' }), '新建轨「鼓」')
  assert.equal(captionForTool('add_track_fx', { track_index: 0, fx_name: 'ReaEQ' }), '挂载 ReaEQ')
  assert.equal(captionForTool('render_to_wav', {}), '渲染试听')
  assert.equal(captionForTool('analyze_audio', { path: '/tmp/mix.wav' }), '分析音频')
  assert.equal(captionForTool('measure_loudness'), '测量响度')
  assert.equal(captionForTool('get_midi_notes', { track_index: 1 }), '读回音符')
  assert.equal(captionForTool('reaper_status'), '检查工程状态')
  assert.equal(captionForTool('set_tempo', { bpm: 96 }), '设速度 96')
  assert.equal(captionForTool('run_lua', { code: 'reaper.UpdateArrange()' }), '执行 Lua 片段')
  assert.equal(captionForTool('listen_subjective', { path: '/tmp/mix.wav' }), '主观听感')
  assert.equal(captionForTool('batch', { calls: [{}, {}, {}, {}] }), '批量操作 ×4')
})

test('captionForTool 覆盖其余 REAPER / 文件工具', () => {
  assert.equal(captionForTool('list_tracks'), '列出轨道')
  assert.equal(captionForTool('list_track_fx', { track_index: 0 }), '查看效果器链')
  assert.equal(captionForTool('list_fx_presets'), '列出效果器预设')
  assert.equal(captionForTool('list_installed_fx'), '列出已安装效果器')
  assert.equal(captionForTool('get_fx_params'), '读取效果器参数')
  assert.equal(captionForTool('create_midi_item', { track_index: 3, start_beats: 0 }), '新建 MIDI 段（轨 3）')
  assert.equal(captionForTool('delete_midi_notes', { note_indices: [1, 2] }), '删除音符 ×2')
  assert.equal(captionForTool('update_midi_note', { note_index: 5 }), '修改音符')
  assert.equal(captionForTool('update_track', { name: 'Bass' }), '调整轨「Bass」')
  assert.equal(captionForTool('update_track', { index: 2 }), '调整轨道 2')
  assert.equal(captionForTool('delete_track', { index: 4 }), '删除轨道 4')
  assert.equal(captionForTool('set_time_signature', { numerator: 6, denominator: 8 }), '设拍号 6/8')
  assert.equal(captionForTool('set_time_selection'), '设置时间选区')
  assert.equal(captionForTool('add_marker', { name: 'Chorus' }), '添加标记「Chorus」')
  assert.equal(captionForTool('set_fx_preset', { preset: 'Vocal' }), '切换预设「Vocal」')
  assert.equal(captionForTool('set_fx_param', { param: 'Threshold' }), '调整参数 Threshold')
  assert.equal(captionForTool('transport', { action: 'play' }), '播放')
  assert.equal(captionForTool('transport', { action: 'warp' }), '走带控制')
  assert.equal(captionForTool('reaper_call', { function: 'GetPlayState' }), '调用 GetPlayState')
  assert.equal(captionForTool('render_project'), '渲染工程')
  assert.equal(captionForTool('run_command', { command: 'dir' }), '执行命令')
  assert.equal(captionForTool('write_file', { path: '/tmp/out/notes.md' }), '写文件 notes.md')
  assert.equal(captionForTool('edit_file', { path: 'C:\\proj\\track.rpp' }), '编辑 track.rpp')
  assert.equal(captionForTool('move_path'), '移动文件')
  assert.equal(captionForTool('delete_path', { path: '/tmp/old.wav' }), '删除 old.wav')
})

test('captionForTool 缺参数时退回纯动词，不留空洞', () => {
  assert.equal(captionForTool('transcribe_melody'), '转录音频')
  assert.equal(captionForTool('replace_midi_notes'), '替换音符')
  assert.equal(captionForTool('add_midi_notes', {}), '写入音符')
  assert.equal(captionForTool('add_track'), '新建轨')
  assert.equal(captionForTool('add_track_fx'), '挂载效果器')
  assert.equal(captionForTool('set_tempo'), '设速度')
  assert.equal(captionForTool('batch'), '批量操作')
  assert.equal(captionForTool('reaper_call'), '调用 REAPER API')
})

test('captionForTool 未知工具原样返回工具名', () => {
  assert.equal(captionForTool('totally_new_tool'), 'totally_new_tool')
  assert.equal(captionForTool('mcp__x__do_thing', { foo: 1 }), 'mcp__x__do_thing')
})

test('resultBadge 从结果里提取一条完成事实（JSON 字符串或对象都收）', () => {
  assert.equal(resultBadge('add_midi_notes', '{"inserted":8,"item_extended":true}'), '已写入 ×8')
  assert.equal(resultBadge('replace_midi_notes', { removed: 3, inserted: 5 }), '3 → 5 音符')
  assert.equal(resultBadge('delete_midi_notes', '{"removed":2}'), '已删除 ×2')
  assert.equal(resultBadge('get_midi_notes', '{"note_count":16,"notes":[]}'), '16 个音符')
  assert.equal(resultBadge('add_midi_notes', '{"item_extended":true}'), '已延长 item')
  assert.equal(resultBadge('transcribe_melody', { bpm_used: 92 }), '92 BPM')
})

test('resultBadge 提不出事实时返回 null，绝不猜', () => {
  assert.equal(resultBadge('reaper_status', '{"tracks":[]}'), null)
  assert.equal(resultBadge('run_lua', 'not json at all'), null)
  assert.equal(resultBadge('analyze_audio'), null)
  assert.equal(resultBadge('add_midi_notes', '"just a string"'), null)
  assert.equal(resultBadge('add_midi_notes', '{"inserted":"eight"}'), null)
  assert.equal(resultBadge('add_midi_notes', '[1,2,3]'), null)
})

test('coerceArgs 接受对象或 JSON 字符串，其余给 undefined', () => {
  assert.deepEqual(coerceArgs({ a: 1 }), { a: 1 })
  assert.deepEqual(coerceArgs('{"a":1}'), { a: 1 })
  assert.equal(coerceArgs('[1,2]'), undefined)
  assert.equal(coerceArgs('oops'), undefined)
  assert.equal(coerceArgs(null), undefined)
  assert.equal(coerceArgs(undefined), undefined)
})

test('formatToolArgs 空参数不产出文本，有参数给缩进 JSON', () => {
  assert.equal(formatToolArgs({}), undefined)
  assert.equal(formatToolArgs(undefined), undefined)
  assert.equal(formatToolArgs('not json'), undefined)
  assert.equal(formatToolArgs({ bpm: 90 }), '{\n  "bpm": 90\n}')
})
