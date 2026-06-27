"use strict";

const $ = (id) => document.getElementById(id);
const el = (tag, cls, txt) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (txt != null) e.textContent = txt;
  return e;
};

let sending = false;
let currentThreadId = null;
let currentAbort = null;
let providerWindows = {};   // 各模型的上下文预算（来自 /api/state）

function ctxBudget() { return providerWindows[$("provider").value] || 128000; }

function setSending(on) {
  sending = on;
  $("send").innerHTML = on ? "■" : "➤";
  $("send").title = on ? "停止" : "发送";
}

function postJSON(url, obj) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(obj),
  });
}

async function loadState() {
  const s = await fetch("/api/state").then((r) => r.json());
  providerWindows = (s.providers && s.providers.windows) || {};
  renderProviders(s.providers);
  renderWorkspaces(s.workspace);
  renderMcp(s.mcp);
  renderSkills(s.skills);
  renderThreads(s.threads);
  if (!currentThreadId) renderContextRing(0, ctxBudget(), 0);   // 无活动线程→圆环归零
}

function renderWorkspaces(ws) {
  if (!ws) return;
  const sel = $("ws-select");
  sel.innerHTML = "";
  (ws.names || ["default"]).forEach((name) => {
    const o = el("option", null, name);
    o.value = name;
    if (name === ws.current) o.selected = true;
    sel.appendChild(o);
  });
}

function renderProviders(p) {
  const sel = $("provider");
  sel.innerHTML = "";
  (p.names || []).forEach((name) => {
    const o = el("option", null, name);
    o.value = name;
    if (name === p.default) o.selected = true;
    sel.appendChild(o);
  });
}

function renderMcp(servers) {
  const box = $("mcp-list");
  box.innerHTML = "";
  (servers || []).forEach((s) => {
    const row = el("label", "row");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = !!s.enabled;
    cb.onchange = () => {
      postJSON("/api/mcp/toggle", { name: s.name, enabled: cb.checked }).then(() => loadState());
    };
    row.appendChild(cb);
    row.appendChild(el("span", null, s.name));
    const cnt = el("span", "tag", s.enabled ? "…" : "");
    row.appendChild(cnt);
    const del = el("button", "mini-btn", "×");
    del.style.marginLeft = "6px";
    del.title = "删除";
    del.onclick = async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      if (confirm("删除 MCP “" + s.name + "”？")) {
        await postJSON("/api/mcp/delete", { name: s.name });
        loadState();
      }
    };
    row.appendChild(del);
    if (!s.enabled) row.style.color = "var(--faint)";
    box.appendChild(row);

    if (s.enabled) {
      fetch("/api/mcp/tools?name=" + encodeURIComponent(s.name))
        .then((r) => r.json())
        .then((d) => {
          if (d.error) {
            cnt.textContent = "✗";
            cnt.style.color = "#c0392b";
            cnt.title = d.error;
          } else {
            cnt.textContent = d.count + " 工具";
            cnt.title = (d.tools || []).map((t) => t.name).join(", ");
          }
        })
        .catch(() => { cnt.textContent = ""; });
    }
  });
}

function renderSkills(skills) {
  const box = $("skills-list");
  box.innerHTML = "";
  if (!skills || !skills.length) {
    box.appendChild(el("div", "muted", "（还没有技能，点“新建”添加）")).style.fontSize = "12px";
    return;
  }
  const groups = {};
  skills.forEach((sk) => {
    const cat = (sk.tags && sk.tags[0]) || "未分类";
    (groups[cat] = groups[cat] || []).push(sk);
  });
  Object.keys(groups).forEach((cat) => {
    box.appendChild(el("div", "cat", cat));
    groups[cat].forEach((sk) => {
      const row = el("label", "row");
      row.appendChild(el("span", null, sk.name));
      const tag = el("span", "tag" + (sk.disclosure === "full" ? " full" : ""),
        sk.disclosure === "full" ? "常驻" : "按需");
      row.appendChild(tag);
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = sk.enabled !== false;
      cb.style.marginLeft = "8px";
      cb.onchange = () => postJSON("/api/skills/toggle", { name: sk.name, enabled: cb.checked });
      row.appendChild(cb);
      box.appendChild(row);
    });
  });
}

function renderThreads(threads) {
  const box = $("threads");
  box.innerHTML = "";
  (threads || []).slice().reverse().forEach((t) => {
    const row = el("div", "thread" + (t.id === currentThreadId ? " active" : ""));
    const main = el("div", "thread-main");
    main.appendChild(el("div", null, t.title || t.id));
    main.appendChild(el("div", "meta", t.id));
    main.onclick = () => openThread(t.id);
    row.appendChild(main);

    const ren = el("button", "thread-act", "✎");
    ren.title = "重命名";
    ren.onclick = async (ev) => {
      ev.stopPropagation();
      const nt = prompt("重命名线程：", t.title || "");
      if (nt != null) { await postJSON("/api/threads/rename", { id: t.id, title: nt }); loadState(); }
    };
    const del = el("button", "thread-act", "×");
    del.title = "删除";
    del.onclick = async (ev) => {
      ev.stopPropagation();
      if (confirm("删除这条线程？")) {
        await postJSON("/api/threads/delete", { id: t.id });
        if (currentThreadId === t.id) { currentThreadId = null; $("messages").innerHTML = ""; }
        loadState();
      }
    };
    row.appendChild(ren);
    row.appendChild(del);
    box.appendChild(row);
  });
}

async function openThread(id) {
  const data = await fetch("/api/threads/" + encodeURIComponent(id)).then((r) => r.json());
  currentThreadId = id;
  $("messages").innerHTML = "";
  (data.messages || []).forEach((m) => {
    if (m.role === "user") addUser(m.content);
    else if (m.role === "assistant" && m.content) addAssistant().textEl.textContent = m.content;
  });
  if (data.context) renderContextRing(data.context.prompt_tokens, data.context.window, data.context.pct);
}

function addUser(text) {
  const d = el("div", "msg-user", text);
  $("messages").appendChild(d);
  scroll();
  return d;
}

function addAssistant() {
  const wrap = el("div", "msg-asst");
  wrap.appendChild(el("div", "avatar", "◣"));
  const body = el("div", "asst-body");
  const textEl = el("div", "asst-text", "");
  body.appendChild(textEl);
  wrap.appendChild(body);
  $("messages").appendChild(wrap);
  scroll();
  return { wrap, body, textEl };
}

function scroll() {
  const m = $("messages");
  m.scrollTop = m.scrollHeight;
}

async function send() {
  if (sending) return;
  const input = $("input");
  const goal = input.value.trim();
  if (!goal) return;
  input.value = "";
  input.style.height = "auto";
  setSending(true);
  currentAbort = new AbortController();

  addUser(goal);
  const asst = addAssistant();
  asst.streamed = false;
  const provider = $("provider").value;

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, provider, thread_id: currentThreadId, bypass: $("bypass").checked }),
      signal: currentAbort.signal,
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        const line = block.split("\n").find((l) => l.startsWith("data: "));
        if (line) handleEvent(JSON.parse(line.slice(6)), asst);
      }
    }
  } catch (e) {
    if (e && e.name === "AbortError") {
      asst.textEl.textContent += "（已停止）";
    } else {
      asst.textEl.textContent = "请求失败：" + e;
    }
  } finally {
    setSending(false);
    currentAbort = null;
    loadState();
  }
}

function handleEvent(e, asst) {
  if (e.type === "thread") {
    currentThreadId = e.id;
  } else if (e.type === "delta") {
    asst.streamed = true;
    asst.textEl.textContent += e.text || "";
  } else if (e.type === "permission_request") {
    const card = el("div", "perm");
    const q = el("div", "perm-q", "⚠ AI 想执行 " + e.name + "(" + fmt(e.arguments) + ")");
    card.appendChild(q);
    const acts = el("div", "perm-acts");
    const allow = el("button", "perm-allow", "允许");
    const deny = el("button", "perm-deny", "拒绝");
    const decide = (ok) => {
      allow.disabled = deny.disabled = true;
      q.textContent = (ok ? "✓ 已允许 " : "✗ 已拒绝 ") + e.name;
      postJSON("/api/permission", { id: e.id, allow: ok });
    };
    allow.onclick = () => decide(true);
    deny.onclick = () => decide(false);
    acts.appendChild(allow); acts.appendChild(deny);
    card.appendChild(acts);
    asst.body.appendChild(card);
  } else if (e.type === "context") {
    renderContextRing(e.prompt_tokens, e.window, e.pct);
  } else if (e.type === "compaction") {
    asst.body.appendChild(el("div", "trace compact", trim(e.content)));
  } else if (e.type === "retry") {
    asst.body.appendChild(el("div", "trace retry", trim(e.content)));
  } else if (e.type === "tool_call") {
    asst.body.appendChild(el("div", "trace call", e.name + "(" + fmt(e.arguments) + ")"));
  } else if (e.type === "tool_result") {
    asst.body.appendChild(el("div", "trace " + (e.is_error ? "err" : "ok"), trim(e.content)));
  } else if (e.type === "final") {
    if (!asst.streamed) asst.textEl.textContent = e.text || "";
  } else if (e.type === "error") {
    asst.textEl.textContent = "出错：" + (e.message || "");
  }
  scroll();
}

const CTX_C = 87.96; // 2π·14
function renderContextRing(pt, win, pct) {
  const box = $("ctx");
  if (!box) return;
  box.hidden = false;
  const p = Math.max(0, Math.min(1, pct || 0));
  const dash = p * CTX_C;
  const arc = $("ctx-arc");
  arc.setAttribute("stroke-dasharray", dash.toFixed(1) + " " + (CTX_C - dash).toFixed(1));
  arc.setAttribute("stroke", p >= 0.8 ? "#c0392b" : p >= 0.6 ? "#e0a400" : "#1f9d57");
  $("ctx-tip").textContent = "已用 " + fmtTokens(pt) + " / 预算 " + fmtTokens(win) + "（" + Math.round(p * 100) + "%）";
}

function fmt(o) {
  let s;
  try { s = JSON.stringify(o); } catch (_) { s = String(o); }
  return s.length > 80 ? s.slice(0, 80) + "…" : s;
}
function trim(t) {
  t = (t || "").replace(/\s+/g, " ").trim();
  return t.length > 120 ? t.slice(0, 120) + "…" : t;
}

// composer behaviors
$("send").onclick = () => {
  if (sending) { if (currentAbort) currentAbort.abort(); }
  else { send(); }
};
$("input").addEventListener("keydown", (ev) => {
  if (ev.key === "Enter" && !ev.shiftKey) {
    ev.preventDefault();
    send();
  }
});
$("input").addEventListener("input", function () {
  this.style.height = "auto";
  this.style.height = Math.min(this.scrollHeight, 140) + "px";
});
$("new-chat").onclick = () => {
  $("messages").innerHTML = "";
  currentThreadId = null;
  renderContextRing(0, ctxBudget(), 0);   // 新对话：上下文从零开始
};
$("provider").onchange = () => { if (!currentThreadId) renderContextRing(0, ctxBudget(), 0); };

// skill modal
$("new-skill").onclick = () => $("skill-modal").classList.remove("hidden");
$("sk-cancel").onclick = () => $("skill-modal").classList.add("hidden");
$("sk-save").onclick = async () => {
  const name = $("sk-name").value.trim();
  if (!name) return;
  const tags = $("sk-tags").value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
  await fetch("/api/skills", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      body: $("sk-body").value,
      disclosure: $("sk-disclosure").value,
      tags,
    }),
  });
  $("skill-modal").classList.add("hidden");
  $("sk-name").value = ""; $("sk-body").value = ""; $("sk-tags").value = "";
  loadState();
};

// add MCP server
$("add-mcp").onclick = () => $("mcp-modal").classList.remove("hidden");
$("mcp-cancel").onclick = () => $("mcp-modal").classList.add("hidden");
$("mcp-save").onclick = async () => {
  const name = $("mcp-name").value.trim();
  if (!name) return;
  const r = await postJSON("/api/mcp/add", {
    name,
    command: $("mcp-cmd").value.trim() || "python",
    args: $("mcp-args").value,
  }).then((x) => x.json());
  if (r.error) { alert(r.error); return; }
  $("mcp-modal").classList.add("hidden");
  $("mcp-name").value = ""; $("mcp-args").value = "";
  loadState();
};

// settings (configure brains / API keys)
let settingsData = null;

async function openSettings() {
  settingsData = await fetch("/api/settings").then((r) => r.json());
  const def = $("set-default");
  const pick = $("set-provider");
  def.innerHTML = "";
  pick.innerHTML = "";
  Object.keys(settingsData.providers).forEach((name) => {
    const o1 = el("option", null, name); o1.value = name;
    if (name === settingsData.default) o1.selected = true;
    def.appendChild(o1);
    const o2 = el("option", null, name); o2.value = name;
    pick.appendChild(o2);
  });
  pick.value = settingsData.default;
  fillProviderFields(settingsData.default);
  $("settings-modal").classList.remove("hidden");
}

// 上下文预算档位（跨数量级，滑轨吸附到这些标准值；含各模型默认值）
const WINDOW_STOPS = [8000, 16000, 32768, 64000, 128000, 192000, 256000, 384000, 512000, 768000, 1000000];
function fmtTokens(n) {
  n = Math.round(n || 0);
  if (n >= 1000000) return +(n / 1000000).toFixed(1) + "M";
  if (n >= 1000) return +(n / 1000).toFixed(n >= 10000 ? 0 : 1) + "K";
  return "" + n;
}
function windowIndexFor(v) {
  v = +v || 128000;
  let best = 0, bd = Infinity;
  WINDOW_STOPS.forEach((s, i) => { const d = Math.abs(s - v); if (d < bd) { bd = d; best = i; } });
  return best;
}

function fillProviderFields(name) {
  const p = settingsData.providers[name] || {};
  $("set-baseurl").value = p.base_url || "";
  $("set-model").value = p.model || "";
  const idx = windowIndexFor(p.window_tokens);
  $("set-window").value = idx;
  $("set-window-val").textContent = fmtTokens(WINDOW_STOPS[idx]);
  $("set-key").value = "";
  $("set-keystatus").textContent = p.has_key ? "（已设置，留空则保留）" : "（未设置）";
}

$("open-settings").onclick = openSettings;
$("set-provider").onchange = function () { fillProviderFields(this.value); };
$("set-window").oninput = function () { $("set-window-val").textContent = fmtTokens(WINDOW_STOPS[+this.value]); };
$("set-cancel").onclick = () => $("settings-modal").classList.add("hidden");
$("set-save").onclick = async () => {
  const name = $("set-provider").value;
  const payload = {
    default: $("set-default").value,
    provider: name,
    base_url: $("set-baseurl").value.trim(),
    model: $("set-model").value.trim(),
  };
  payload.window_tokens = WINDOW_STOPS[+$("set-window").value];
  const key = $("set-key").value.trim();
  if (key) payload.api_key = key;
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  $("settings-modal").classList.add("hidden");
  loadState();
};

// workspace（= 长期记忆命名空间；只管记忆，不打包技能/MCP/模型）
$("ws-select").onchange = async function () {
  await postJSON("/api/workspace/switch", { name: this.value });
  loadState();
};
$("ws-new").onclick = async () => {
  const name = prompt("新建工作区名称（如：绘画）：", "");
  if (!name || !name.trim()) return;
  const r = await postJSON("/api/workspace/create", { name: name.trim() }).then((x) => x.json());
  if (r.error) { alert(r.error); return; }
  loadState();
};
$("ws-rename").onclick = async () => {
  const cur = $("ws-select").value;
  const nn = prompt("重命名工作区：", cur);
  if (!nn || !nn.trim() || nn.trim() === cur) return;
  const r = await postJSON("/api/workspace/rename", { old: cur, new: nn.trim() }).then((x) => x.json());
  if (r.error) { alert(r.error); return; }
  loadState();
};
$("ws-del").onclick = async () => {
  const cur = $("ws-select").value;
  if (!confirm("删除工作区 “" + cur + "” 及其全部长期记忆？此操作不可撤销。")) return;
  const r = await postJSON("/api/workspace/delete", { name: cur }).then((x) => x.json());
  if (r.error) { alert(r.error); return; }
  loadState();
};

loadState();
