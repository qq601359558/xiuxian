"""AI 对话正文呈现清洗（chat-structure spec §C）。

仅呈现层：剥离 AI 叙事里残留的 markdown 记号、统一换行；
不改叙事内容生成、不动任何数值与结算。纯函数、幂等。
只处理明确的 markdown 记号，不动中文叙事符号（「」『』·：等）。
"""

import re

_BOLD_STAR = re.compile(r"\*\*(.+?)\*\*", re.S)
_BOLD_UNDER = re.compile(r"__(.+?)__", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_HEADING = re.compile(r"^#{1,6}[ \t]+", re.M)
_QUOTE = re.compile(r"^>[ \t]?", re.M)
_BLANK_RUN = re.compile(r"\n{3,}")


def clean_dialogue_text(s) -> str:
    """清洗一段 AI 对话正文用于呈现；非字符串入参按空串处理。"""
    if not isinstance(s, str):
        return ""
    out = s.replace("\r\n", "\n").replace("\r", "\n")
    out = _LINK.sub(r"\1", out)
    out = _BOLD_STAR.sub(r"\1", out)
    out = _BOLD_UNDER.sub(r"\1", out)
    out = _INLINE_CODE.sub(r"\1", out)
    out = _HEADING.sub("", out)
    out = _QUOTE.sub("", out)
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    out = _BLANK_RUN.sub("\n\n", out)
    return out.strip()
