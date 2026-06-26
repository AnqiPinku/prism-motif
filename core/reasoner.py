"""模型接口：给定历史 + 工具，产出决策。换模型 = 换一个实现。"""
from abc import ABC, abstractmethod

from .contracts import Decision


class Reasoner(ABC):
    @abstractmethod
    def decide(self, messages: list, tools: list, on_delta=None) -> Decision:
        """输入 list[Message] + list[ToolSpec]，返回 Decision。
        若提供 on_delta(回调)，应在生成文本时逐块调用它以实现流式输出。"""
        raise NotImplementedError
