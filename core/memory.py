"""记忆：接口 + 实现 + 工厂。换后端 = 改 config/memory.json，core 不动。"""
import os
import json
from abc import ABC, abstractmethod


class Memory(ABC):
    @abstractmethod
    def remember(self, item):
        """存一条记忆（str 或 dict）。"""

    @abstractmethod
    def recall(self, query, k=5):
        """取回与 query 相关的记忆，返回 list[str]。"""

    def reflect(self):
        """（预留）定期巩固/反思。默认不做。"""
        return None


class JsonMemory(Memory):
    """最简实现：存一个 json 列表，recall 用关键词匹配。空库返回 []。"""

    def __init__(self, directory):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.path = os.path.join(directory, "memories.json")

    def _load(self):
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def remember(self, item):
        items = self._load()
        text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        items.append({"text": text})
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

    def recall(self, query, k=5):
        items = self._load()
        if not items:
            return []
        q = (query or "").lower()
        for sep in ("，", "。", "、", ",", "."):
            q = q.replace(sep, " ")
        toks = [t for t in q.split() if t]
        scored = []
        for it in items:
            text = it.get("text", "")
            score = sum(1 for t in toks if t in text.lower())
            scored.append((score, text))
        # 没命中关键词就返回 []，不再兜底塞“最近 k 条”——避免跨领域/无关记忆污染上下文。
        return [t for s, t in sorted(scored, key=lambda x: x[0], reverse=True) if s > 0][:k]


def build_memory(cfg):
    """按配置造记忆后端。"""
    cfg = cfg or {}
    backend = cfg.get("backend", "json")
    opts = cfg.get("options", {})
    if backend == "json":
        return JsonMemory(opts.get("dir", "data/memory"))
    raise ValueError("未知记忆后端: %s" % backend)
