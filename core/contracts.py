"""Prism Core 的通用数据模型 —— 全员依赖，签名冻结，勿改。"""
from dataclasses import dataclass


@dataclass
class Message:
    """一条对话消息。role: system | user | assistant | tool。"""
    role: str
    content: object = None          # str（M1 只用 str）；以后可放多模态块
    tool_call_id: str = None        # role == "tool" 时填，对应 ToolCall.id
    tool_calls: list = None         # role == "assistant" 且要调工具时，list[ToolCall]


@dataclass
class ToolSpec:
    """一个可被模型调用的工具的描述。"""
    name: str
    description: str
    parameters: dict                # JSON Schema（object）


@dataclass
class ToolCall:
    """模型决定调用某工具。"""
    id: str
    name: str
    arguments: dict


@dataclass
class ToolResult:
    """工具执行结果（文字或多模态块）。"""
    id: str
    content: object
    is_error: bool = False


@dataclass
class Decision:
    """reasoner 的输出：要么最终回答，要么要调一批工具。"""
    kind: str                       # "final" | "tools"
    text: str = None                # kind == "final"
    tool_calls: list = None         # kind == "tools"，list[ToolCall]
