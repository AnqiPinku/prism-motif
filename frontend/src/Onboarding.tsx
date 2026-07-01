import { useEffect, useState } from 'react'
import { getJSON, postJSON, type ReaperStatus } from './api'
import { type SettingsData } from './Settings'

const Icon = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

export default function Onboarding({ reaper, onReaperRefresh, onDone }:
  { reaper: ReaperStatus | null; onReaperRefresh: () => void; onDone: () => void }) {
  const [sd, setSd] = useState<SettingsData | null>(null)
  const [llmKey, setLlmKey] = useState('')
  const [gKey, setGKey] = useState('')
  const [busy, setBusy] = useState('')

  const refresh = () => getJSON<SettingsData>('/api/settings').then(setSd)
  useEffect(() => { refresh() }, [])

  const llmDone = !!sd && Object.values(sd.providers).some((p) => p.has_key)
  const gDone = !!sd?.gemini?.has_key
  const reaperDone = reaper?.state === 'connected'

  const saveLlm = async () => {
    if (!sd || !llmKey.trim()) return
    setBusy('llm')
    await postJSON('/api/settings', { provider: sd.default, api_key: llmKey.trim() })
    setLlmKey(''); await refresh(); setBusy('')
  }
  const saveGemini = async () => {
    if (!gKey.trim()) return
    setBusy('g')
    await postJSON('/api/settings', { gemini: { api_key: gKey.trim() } })
    setGKey(''); await refresh(); setBusy('')
  }
  const installBridge = async () => {
    setBusy('reaper')
    const r = await postJSON<{ ok?: boolean; error?: string; actions?: string[] }>('/api/reaper/install-bridge', {})
    setBusy('')
    if (r && r.ok === false) { alert(r.error || '安装失败'); return }
    alert('已安装：\n- ' + (r.actions || []).join('\n- ') + '\n\n请重启 REAPER 让自动加载生效。')
    onReaperRefresh()
  }

  const mark = (done: boolean, n: number) =>
    done ? <div className="mark done"><Icon n="check" s={18} /></div> : <div className="mark active">{n}</div>

  return (
    <div className="modal-bg">
      <div className="wiz">
        <div className="logo"><Icon n="graphic_eq" s={30} /></div>
        <h2>欢迎使用 <span className="g">Prism Motif</span></h2>
        <p className="wsub">作曲、编曲到混音，一个 agent 全程陪你。三步开始：填一个语言模型 key、一个音频分析 key，再连上 REAPER。后台的音频引擎已自带，无需另装。</p>

        <div className="step">
          {mark(llmDone, 1)}
          <div className="sbody">
            <div className="stitle">语言模型 API{llmDone && <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--green)' }}>已连接 · {sd?.default}</span>}</div>
            <p className="sdesc">agent 的“大脑”。key 只存系统钥匙链。</p>
            {!llmDone && (
              <div className="inline">
                <input type="password" value={llmKey} placeholder={'粘贴 ' + (sd?.default || '') + ' key'} onChange={(e) => setLlmKey(e.target.value)} />
                <button className="btn filled" onClick={saveLlm} disabled={busy === 'llm'}>保存</button>
              </div>
            )}
          </div>
        </div>

        <div className="step">
          {mark(gDone, 2)}
          <div className="sbody">
            <div className="stitle">音频分析 API{gDone && <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--green)' }}>已连接 · Gemini</span>}</div>
            <p className="sdesc">用来“听”你的作品——听感、情绪、混音问题。key 只存本机钥匙链。</p>
            {!gDone && (
              <div className="inline">
                <input type="password" value={gKey} placeholder="粘贴 Gemini / 中转 key" onChange={(e) => setGKey(e.target.value)} />
                <button className="btn filled" onClick={saveGemini} disabled={busy === 'g'}>保存</button>
              </div>
            )}
          </div>
        </div>

        <div className="step">
          {mark(reaperDone, 3)}
          <div className="sbody">
            <div className="stitle">REAPER{reaperDone && <span style={{ marginLeft: 'auto', fontSize: 13, color: 'var(--green)' }}>已连接</span>}</div>
            <p className="sdesc">连接你的 DAW。点一下装好桥，之后打开 REAPER 会自动连上，不用碰 Actions 菜单。</p>
            {!reaperDone && (
              <div className="inline" style={{ alignItems: 'center' }}>
                <span className="sdesc" style={{ flex: 1, margin: 0 }}>{reaperLabel(reaper)}</span>
                <button className="btn" onClick={installBridge} disabled={busy === 'reaper'}>一键装桥</button>
              </div>
            )}
          </div>
        </div>

        <div className="wfoot">
          <button className="start" onClick={onDone}>开始创作</button>
          <button className="later" onClick={onDone}>稍后设置</button>
        </div>
      </div>
    </div>
  )
}

function reaperLabel(r: ReaperStatus | null) {
  if (!r) return '检测中…'
  return { connected: '已连接', running_not_loaded: 'REAPER 已开，桥未加载', not_running: 'REAPER 未运行', not_loaded: '未连接' }[r.state] || '未知'
}
