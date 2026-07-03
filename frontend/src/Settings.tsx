import { useEffect, useState } from 'react'
import { getJSON, postJSON, type State } from './api'

export interface SettingsData {
  default: string
  providers: Record<string, { base_url: string; model: string; type: string; window_tokens: number | string; has_key: boolean }>
  gemini: { base_url: string; model: string; has_key: boolean; env_only: boolean }
}

const Icon = ({ n, s }: { n: string; s?: number }) => (
  <span className="material-symbols-outlined" style={s ? { fontSize: s } : undefined} aria-hidden>{n}</span>
)

export default function Settings({ state, trust, setTrust, onClose, onSaved, onOpenOnboarding }:
  { state: State; trust: boolean; setTrust: (v: boolean) => void;
    onClose: () => void; onSaved: () => void; onOpenOnboarding?: () => void }) {
  const [data, setData] = useState<SettingsData | null>(null)
  const [def, setDef] = useState('')
  const [pick, setPick] = useState('')
  const [baseUrl, setBaseUrl] = useState('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [gKey, setGKey] = useState('')
  const [gBase, setGBase] = useState('')
  const [gModel, setGModel] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => { getJSON<SettingsData>('/api/settings').then((d) => {
    setData(d); setDef(d.default); fill(d, d.default)
    setGBase(d.gemini?.base_url || ''); setGModel(d.gemini?.model || '')
  }) }, [])

  const fill = (d: SettingsData, name: string) => {
    setPick(name)
    const p = d.providers[name] || { base_url: '', model: '' }
    setBaseUrl(p.base_url || ''); setModel(p.model || ''); setApiKey('')
  }

  const save = async () => {
    setSaving(true)
    const gemini: Record<string, string> = { base_url: gBase.trim(), model: gModel.trim() }
    if (gKey.trim()) gemini.api_key = gKey.trim()
    const body: Record<string, unknown> = { default: def, provider: pick, base_url: baseUrl.trim(), model: model.trim(), gemini }
    if (apiKey.trim()) body.api_key = apiKey.trim()
    const r = await postJSON<{ ok?: boolean; error?: string }>('/api/settings', body)
    setSaving(false)
    if (r && r.ok === false) { alert(r.error || '保存失败'); return }
    onSaved(); onClose()
  }

  const importEnv = async () => {
    await postJSON('/api/settings', { gemini: { import_env: true } })
    const d = await getJSON<SettingsData>('/api/settings'); setData(d)
    alert('已从环境变量导入到钥匙链。建议清除旧的 GEMINI_API_KEY 环境变量并轮换该 key。')
  }

  const toggleMcp = async (name: string, enabled: boolean) => { await postJSON('/api/mcp/toggle', { name, enabled }); onSaved() }
  const toggleSkill = async (name: string, enabled: boolean) => { await postJSON('/api/skills/toggle', { name, enabled }); onSaved() }

  const providerNames = Object.keys(data?.providers || {})
  const provKeySet = !!data?.providers[pick]?.has_key
  const gKeySet = !!data?.gemini?.has_key

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal settings-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>设置</h2>
          <button className="iconbtn" aria-label="关闭" onClick={onClose}><Icon n="close" /></button>
        </div>
        <div className="modal-body settings-body">
          <div className="sec settings-sec">
            <div className="sec-title">
              <h3>语言模型</h3>
              <span className="softtag">默认：{def || '-'}</span>
            </div>
            <div className="field wide"><div className="field-title">默认模型</div>
              <div className="choice-row" role="radiogroup" aria-label="默认模型">
                {providerNames.map((n) => (
                  <button key={n} className={'choice' + (def === n ? ' active' : '')}
                    onClick={() => setDef(n)} type="button" role="radio" aria-checked={def === n}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
            <div className="field wide"><div className="field-title">编辑配置</div>
              <div className="choice-row" role="radiogroup" aria-label="编辑配置">
                {providerNames.map((n) => (
                  <button key={n} className={'choice' + (pick === n ? ' active' : '')}
                    onClick={() => data && fill(data, n)} type="button" role="radio" aria-checked={pick === n}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
            <div className="row2">
              <div className="field"><label htmlFor="provider-base-url">Base URL</label><input id="provider-base-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.deepseek.com" /></div>
              <div className="field"><label htmlFor="provider-model">模型名称</label><input id="provider-model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="deepseek-chat" /></div>
            </div>
            <div className="field"><label htmlFor="provider-api-key">API Key<span className={'keypill' + (provKeySet ? ' ok' : '')}>{provKeySet ? '已设置' : '未设置'}</span></label>
              <input id="provider-api-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="留空保留当前 key" /></div>
          </div>

          <div className="sec settings-sec">
            <div className="sec-title">
              <h3>音频分析</h3>
              <span className={'keypill' + (gKeySet ? ' ok' : '')}>{gKeySet ? 'Gemini 已配置' : '未配置'}</span>
            </div>
            <div className="field"><label htmlFor="gemini-api-key">API Key</label>
              <input id="gemini-api-key" type="password" value={gKey} onChange={(e) => setGKey(e.target.value)} placeholder="留空保留当前 key" /></div>
            {data?.gemini?.env_only && <button className="btn small" onClick={importEnv}>从环境变量导入到钥匙链</button>}
            <div className="row2">
              <div className="field"><label htmlFor="gemini-base-url">Base URL</label><input id="gemini-base-url" value={gBase} onChange={(e) => setGBase(e.target.value)} placeholder="Google 原生可留空" /></div>
              <div className="field"><label htmlFor="gemini-model">模型名称</label><input id="gemini-model" value={gModel} onChange={(e) => setGModel(e.target.value)} placeholder="gemini-2.5-flash" /></div>
            </div>
          </div>

          <div className="sec settings-sec">
            <h3>MCP 服务</h3>
            {state.mcp.map((m) => (
              <div className="togglerow" key={m.name}>{m.name}<span className="tag" />
                <button className={'switch' + (m.enabled ? '' : ' off')} aria-label={m.name} onClick={() => toggleMcp(m.name, !m.enabled)} /></div>
            ))}
          </div>

          <div className="sec settings-sec">
            <h3>技能</h3>
            {state.skills.length === 0 && <div className="keystate">暂无技能</div>}
            {state.skills.map((s) => (
              <div className="togglerow" key={s.name}>{s.name}<span className="tag">{s.disclosure === 'full' ? '常驻' : '按需'}</span>
                <button className={'switch' + (s.enabled ? '' : ' off')} aria-label={s.name} onClick={() => toggleSkill(s.name, !s.enabled)} /></div>
            ))}
          </div>

          <div className="sec settings-sec">
            <h3>行为</h3>
            <div className="togglerow">信任模式
              <span className="tag">跳过危险操作确认</span>
              <button className={'switch' + (trust ? '' : ' off')} aria-label="信任模式" onClick={() => setTrust(!trust)} /></div>
            {onOpenOnboarding && (
              <div className="togglerow">重新查看引导
                <span className="tag">再走一遍 3 步向导</span>
                <button className="btn small" onClick={onOpenOnboarding}>打开</button></div>
            )}
          </div>

          <div className="btnrow">
            <button className="btn" onClick={onClose}>取消</button>
            <button className="btn filled" onClick={save} disabled={saving}>{saving ? '保存中…' : '保存'}</button>
          </div>
        </div>
      </div>
    </div>
  )
}
