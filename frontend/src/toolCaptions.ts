// 工具状态卡文案：把原始工具名 / 参数 / 结果翻成一句短中文，
// 前端各渲染点（实时 RunPanel、回合 RunSummary、存档重建）共用。
// 纯函数、无 DOM 依赖，node:test 直接可测。

/** 事件里的 arguments 可能是对象（正常）或 JSON 字符串（个别 provider），统一收敛成 Record */
export function coerceArgs(value: unknown): Record<string, unknown> | undefined {
  let v = value
  if (typeof v === 'string') {
    try { v = JSON.parse(v) } catch { return undefined }
  }
  return typeof v === 'object' && v !== null && !Array.isArray(v) ? v as Record<string, unknown> : undefined
}

/** 原始参数 → 折叠区展示用的 JSON 文本；无参数 / 空对象返回 undefined（不渲染空块） */
export function formatToolArgs(value: unknown): string | undefined {
  const rec = coerceArgs(value)
  if (!rec || Object.keys(rec).length === 0) return undefined
  try { return JSON.stringify(rec, null, 2) } catch { return undefined }
}

const asStr = (v: unknown): string | undefined => (typeof v === 'string' && v.trim() ? v : undefined)
const asNum = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)
const arrLen = (v: unknown): number | undefined => (Array.isArray(v) ? v.length : undefined)

// 文件路径 → 基名（Windows / POSIX 分隔符都可能出现）
const baseName = (p: string): string => p.split(/[\\/]/).pop() || p

// 音频类工具的文件参数在不同版本里叫法不一，按常见程度依次取
function fileArg(args?: Record<string, unknown>): string | undefined {
  for (const key of ['path', 'file_path', 'audio_path', 'file', 'input_path']) {
    const v = asStr(args?.[key])
    if (v) return baseName(v)
  }
  return undefined
}

// 「（轨 N）」定位后缀；缺 track_index 就整个省略
function trackSuffix(args?: Record<string, unknown>): string {
  const idx = asNum(args?.track_index)
  return idx != null ? `（轨 ${idx}）` : ''
}

// 「 ×N」数量后缀；键不存在或不是数组就省略
function countSuffix(args: Record<string, unknown> | undefined, key: string): string {
  const n = arrLen(args?.[key])
  return n != null ? ` ×${n}` : ''
}

// transport 的 action → 中文动词
const TRANSPORT_ACTIONS: Record<string, string> = {
  play: '播放',
  stop: '停止',
  pause: '暂停',
  record: '录音',
  goto_start: '回到开头',
  toggle_repeat: '切换循环',
}

/** 已知工具 → 「动词 + 关键参数」的短中文标题；未知工具原样返回工具名 */
export function captionForTool(name: string, args?: Record<string, unknown>): string {
  switch (name) {
    // —— 感知（读） ——
    case 'transcribe_melody': {
      const file = fileArg(args)
      return file ? `转录 ${file}` : '转录音频'
    }
    case 'analyze_audio': return '分析音频'
    case 'measure_loudness': return '测量响度'
    case 'listen_subjective': return '主观听感'
    // —— 工程状态（读） ——
    case 'reaper_status': return '检查工程状态'
    case 'list_tracks': return '列出轨道'
    case 'get_midi_notes': return '读回音符'
    case 'list_track_fx': return '查看效果器链'
    case 'list_fx_presets': return '列出效果器预设'
    case 'list_installed_fx': return '列出已安装效果器'
    case 'get_fx_params': return '读取效果器参数'
    // —— 工程设置 ——
    case 'set_tempo': {
      const bpm = asNum(args?.bpm)
      return bpm != null ? `设速度 ${bpm}` : '设速度'
    }
    case 'set_time_signature': {
      const num = asNum(args?.numerator)
      const den = asNum(args?.denominator)
      return num != null && den != null ? `设拍号 ${num}/${den}` : '设拍号'
    }
    case 'set_time_selection': return '设置时间选区'
    case 'add_marker': {
      const label = asStr(args?.name)
      return label ? `添加标记「${label}」` : '添加标记'
    }
    // —— 轨道 ——
    case 'add_track': {
      const trackName = asStr(args?.name)
      return trackName ? `新建轨「${trackName}」` : '新建轨'
    }
    case 'update_track': {
      const trackName = asStr(args?.name)
      if (trackName) return `调整轨「${trackName}」`
      const idx = asNum(args?.index ?? args?.track_index)
      return idx != null ? `调整轨道 ${idx}` : '调整轨道'
    }
    case 'delete_track': {
      const idx = asNum(args?.index ?? args?.track_index)
      return idx != null ? `删除轨道 ${idx}` : '删除轨道'
    }
    // —— MIDI ——
    case 'create_midi_item': return `新建 MIDI 段${trackSuffix(args)}`
    case 'add_midi_notes': return `写入音符${countSuffix(args, 'notes')}`
    case 'replace_midi_notes': return `替换音符${countSuffix(args, 'notes')}${trackSuffix(args)}`
    case 'delete_midi_notes': return `删除音符${countSuffix(args, 'note_indices')}`
    case 'update_midi_note': return '修改音符'
    // —— FX ——
    case 'add_track_fx': {
      const fx = asStr(args?.fx_name)
      return fx ? `挂载 ${fx}` : '挂载效果器'
    }
    case 'set_fx_preset': {
      const preset = asStr(args?.preset)
      return preset ? `切换预设「${preset}」` : '切换效果器预设'
    }
    case 'set_fx_param': {
      const param = asStr(args?.param)
      return param ? `调整参数 ${param}` : '调整效果器参数'
    }
    // —— 走带 / 渲染 ——
    case 'transport': {
      const action = asStr(args?.action)
      return (action && TRANSPORT_ACTIONS[action]) || '走带控制'
    }
    case 'render_to_wav': return '渲染试听'
    case 'render_project': return '渲染工程'
    // —— 逃生舱 ——
    case 'reaper_call': {
      const fn = asStr(args?.function)
      return fn ? `调用 ${fn}` : '调用 REAPER API'
    }
    case 'run_lua': return '执行 Lua 片段'
    case 'batch': return `批量操作${countSuffix(args, 'calls')}`
    // —— 文件 / 命令 ——
    case 'run_command': return '执行命令'
    case 'write_file': {
      const file = fileArg(args)
      return file ? `写文件 ${file}` : '写文件'
    }
    case 'edit_file': {
      const file = fileArg(args)
      return file ? `编辑 ${file}` : '编辑文件'
    }
    case 'move_path': return '移动文件'
    case 'delete_path': {
      const file = fileArg(args)
      return file ? `删除 ${file}` : '删除文件'
    }
    default:
      return name
  }
}

/**
 * 从工具结果里挑一条最有信息量的完成事实做徽标（结果可以是 JSON 字符串或已解析对象）。
 * 提不出来就返回 null——调用方不渲染徽标即可，绝不猜。
 */
export function resultBadge(name: string, result?: unknown): string | null {
  const data = coerceArgs(result)
  if (!data) return null
  const inserted = asNum(data.inserted)
  const removed = asNum(data.removed)
  // replace 的「删了几个、写了几个」合成一条替换事实
  if (name === 'replace_midi_notes' && inserted != null && removed != null) return `${removed} → ${inserted} 音符`
  if (inserted != null) return `已写入 ×${inserted}`
  if (removed != null) return `已删除 ×${removed}`
  const noteCount = asNum(data.note_count)
  if (noteCount != null) return `${noteCount} 个音符`
  if (data.item_extended === true) return '已延长 item'
  const bpm = asNum(data.bpm_used)
  if (bpm != null) return `${bpm} BPM`
  return null
}
