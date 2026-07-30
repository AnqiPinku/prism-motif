"""手写 MCP stdio 客户端：启动一个 MCP server 子进程，做握手并调用其工具。
与我们写的 reaper-mcp 服务端对称，只用标准库 subprocess + json。
故障恢复：写有专职线程（stdin 阻塞不再拖死调用方）、_rpc 轮询探活（子进程退了立刻报）、
超时后按规范发 notifications/cancelled 并丢弃迟到响应；initialize 超时只失败不取消。"""
import os
import sys
import json
import time
import queue
import threading
import subprocess

from .contracts import ToolSpec, ToolResult
from . import paths
from . import secrets_store

PROTOCOL_VERSION = "2024-11-05"


class MCPTransportError(RuntimeError):
    """传输层故障（超时/进程退出/写通道死亡）——区别于工具自身报错，上层可据此重启 server。"""


class MCPClient:
    def __init__(self, command, args, env=None, timeout=60, init_timeout=None,
                 write_timeout=10):
        self.command = command
        self.args = args or []
        self.env = env
        self.timeout = float(timeout) if timeout else 60.0   # 单次调用默认超时（防 MCP 进程挂死）
        # initialize 用更短的专用超时（握手不该慢）；未显式给则不超过调用超时
        self.init_timeout = float(init_timeout) if init_timeout else min(15.0, self.timeout)
        self.write_timeout = float(write_timeout)            # 子进程多久不读 stdin 判定写死
        self.proc = None
        self._id = 0
        self._q = None        # 读线程把 stdout 行塞进这个队列
        self._reader = None
        self._wq = None       # 写队列：_send 只入队，专职写线程负责真正写 stdin
        self._writer = None
        self._dead = False            # 写通道死亡标记：置位后一切 _send 立刻失败
        self._write_started = None    # 写线程当前这笔写的起始时刻（None = 空闲）；_rpc 据此测卡死
        self._stale_ids = set()       # 已超时取消的请求 id：迟到响应按规范静默丢弃

    def start(self):
        """起子进程 + initialize 握手 + initialized 通知。"""
        full_env = dict(os.environ)
        if self.env:
            full_env.update(self.env)
        # 声明了 GEMINI_* 中转设置的 server（= 感知 sidecar）：
        #  ① 从钥匙链补 GEMINI API key（env 已设则不覆盖 → 环境变量优先；密钥只进这一个子进程、绝不落文件）
        #  ② 钉 numba 磁盘缓存到稳定 per-user 目录，让首次 ~16s JIT 编译只发生一次、跨 app 更新保留
        if self.env and any(k.startswith("GEMINI_") for k in self.env):
            if not full_env.get("GEMINI_API_KEY"):
                k = secrets_store.get_secret("GEMINI_API_KEY")
                if k:
                    full_env["GEMINI_API_KEY"] = k
            cache = paths.numba_cache_dir()
            try:
                os.makedirs(cache, exist_ok=True)
            except OSError:
                pass
            full_env.setdefault("NUMBA_CACHE_DIR", cache)
        command = paths.expand(self.command)          # 展开 ${PRISM_HOME} 令牌 → 绝对路径
        # command="python" → 用 gateway 自己的解释器 (打包版是 bundled CPython, dev 版是系统 python)
        if command in ("python", "python.exe"):
            command = sys.executable
        args = [paths.expand(a) for a in self.args]
        for a in args:   # 缺脚本会因 stderr=DEVNULL 静默失败 → 提前报清楚（安装不完整/兄弟仓缺失）
            if a.endswith(".py") and not os.path.isfile(a):
                raise RuntimeError(
                    "MCP server 脚本不存在：%s（检查 ${PRISM_HOME} 或安装完整性）" % a)
        self.proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            bufsize=1, env=full_env,
            # 无窗壳（release Tauri）下父进程没有控制台，console 子进程会各弹一个黑窗 → 显式禁掉
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
        # 后台读线程：把 stdout 逐行塞进队列，让 _rpc 能带超时地等响应（Windows 管道无法 select）。
        self._q = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop,
                                        args=(self.proc.stdout,), daemon=True)
        self._reader.start()
        # 专职写线程：stdin 满管道时 write 会无限阻塞，挪到独立线程里让调用方永不被写卡住。
        self._wq = queue.Queue(maxsize=64)
        self._writer = threading.Thread(target=self._write_loop,
                                        args=(self.proc.stdin,), daemon=True)
        self._writer.start()
        try:
            # 规范：initialize 请求不得取消——超时就整体失败（close），不发 cancelled
            self._rpc("initialize", {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "prism-core", "version": "0.1"},
            }, timeout=self.init_timeout)
            self._notify("notifications/initialized", {})
        except Exception:
            self.close()
            raise

    def list_tools(self):
        """tools/list → list[ToolSpec]。"""
        result = self._rpc("tools/list", {})
        specs = []
        for t in result.get("tools", []):
            specs.append(ToolSpec(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t.get("inputSchema") or {"type": "object", "properties": {}},
            ))
        return specs

    def call_tool(self, name, arguments, timeout=None):
        """tools/call → ToolResult。timeout 覆盖单次调用超时（如 transcribe_melody 要更久）。
        传输层故障（超时/进程死）在结果上打 transport_error 标记，供 ToolHub 决定重启。"""
        try:
            result = self._rpc("tools/call", {"name": name, "arguments": arguments or {}},
                               timeout=timeout)
        except Exception as e:  # noqa: BLE001
            res = ToolResult(id=name, content="工具调用失败: %s" % (e,), is_error=True)
            res.transport_error = isinstance(e, MCPTransportError)
            return res
        blocks = result.get("content", [])
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        return ToolResult(id=name, content=text, is_error=bool(result.get("isError")))

    def close(self):
        """幂等收口，绝不抛异常：卡住的写线程靠杀进程解卡，不在此阻塞。"""
        self._dead = True
        proc, self.proc = self.proc, None
        if proc is None:
            return
        if self._wq is not None:
            try:
                self._wq.put_nowait(None)          # 写线程退出哨兵
            except queue.Full:
                pass                               # 队列满说明写线程卡死，下面杀进程解卡
        try:
            # 写线程正卡在 write/flush 时 stdin.close 会同样阻塞在冲刷 → 跳过，杀进程收尾
            if proc.stdin and self._write_started is None:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        for t in (self._reader, self._writer):
            if t is not None and t is not threading.current_thread():
                t.join(timeout=1)
        try:
            # 进程已死、写线程已停：此时补关 stdin 不会阻塞（冲刷立刻得 broken pipe）
            if proc.stdin and not proc.stdin.closed:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass

    # ---------- internal ----------
    def _next_id(self):
        self._id += 1
        return self._id

    def _send(self, obj):
        """非阻塞入队；写通道已死或队列满（server 长时间不读）立刻失败，绝不卡调用方。"""
        if self._dead:
            raise MCPTransportError("MCP 写通道已死（server 停止读取或已退出）")
        if self.proc is None:
            raise MCPTransportError("MCP client 已关闭")
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        try:
            self._wq.put_nowait(line)
        except queue.Full:
            raise MCPTransportError("MCP 写队列已满（server 长时间不读取 stdin）")

    def _notify(self, method, params):
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _read_loop(self, stdout):
        """后台把子进程 stdout 逐行塞进队列；流关闭（进程退出）后塞一个 "" 哨兵。"""
        try:
            for line in stdout:
                self._q.put(line)
        except Exception:  # noqa: BLE001
            pass
        self._q.put("")

    def _write_loop(self, stdin):
        """专职写线程：消费写队列、真正写 stdin。写卡死由 _rpc 的看门狗检测并杀进程解卡。"""
        while True:
            try:
                item = self._wq.get(timeout=0.5)
            except queue.Empty:
                if self._dead or self.proc is None:
                    break
                continue
            if item is None:                       # close() 哨兵
                break
            try:
                self._write_started = time.monotonic()
                stdin.write(item)
                stdin.flush()
            except Exception:  # noqa: BLE001 管道断/进程被杀 → 写通道死亡
                self._dead = True
                break
            finally:
                self._write_started = None

    def _match(self, line, rid):
        """解析一行，命中 rid 返回 msg；陈旧响应（已取消请求的迟到应答）按规范静默丢弃。"""
        line = line.strip()
        if not line:
            return None
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return None
        mid = msg.get("id")
        if mid in self._stale_ids:
            self._stale_ids.discard(mid)
            return None
        return msg if mid == rid else None         # 其它 id / 通知 → 忽略

    def _drain(self, rid, budget=0.5):
        """子进程退出后短暂清空读队列——尾部响应可能已在途。命中返回 msg，否则 None。"""
        end = time.monotonic() + budget
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return None
            try:
                line = self._q.get(timeout=left)
            except queue.Empty:
                return None
            if line == "":
                return None
            msg = self._match(line, rid)
            if msg is not None:
                return msg

    def _rpc(self, method, params, timeout=None):
        timeout = self.timeout if timeout is None else float(timeout)
        rid = self._next_id()
        self._send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            if self._dead:
                raise MCPTransportError("MCP 写通道已死（method=%s）" % method)
            proc = self.proc
            if proc is None:
                raise MCPTransportError("MCP client 已关闭（method=%s）" % method)
            started = self._write_started          # 写看门狗：server 不读 stdin → 判死并杀进程解卡
            if started is not None and time.monotonic() - started > self.write_timeout:
                self._dead = True
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                raise MCPTransportError(
                    "MCP 写超时（server 停止读取 stdin，method=%s，%.0fs）"
                    % (method, self.write_timeout))
            code = proc.poll()                     # 探活：子进程退了不必傻等到超时
            if code is not None:
                msg = self._drain(rid)
                if msg is None:
                    raise MCPTransportError(
                        "MCP server 已退出（method=%s，exit=%s）" % (method, code))
            else:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    if method != "initialize":     # 规范：initialize 不得取消，其余尽力通知
                        self._stale_ids.add(rid)
                        try:
                            self._notify("notifications/cancelled", {
                                "requestId": rid,
                                "reason": "timed out after %.0fs" % timeout})
                        except Exception:  # noqa: BLE001
                            pass
                    raise MCPTransportError("MCP 调用超时（method=%s，%.0fs）" % (method, timeout))
                try:
                    line = self._q.get(timeout=min(remaining, 0.25))
                except queue.Empty:
                    continue
                if line == "":                     # 哨兵：子进程已退出
                    raise MCPTransportError("MCP server 已退出（method=%s）" % method)
                msg = self._match(line, rid)
                if msg is None:
                    continue
            if "error" in msg:
                raise RuntimeError(str(msg["error"]))
            return msg.get("result", {})
