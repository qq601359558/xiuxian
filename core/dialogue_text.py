"""AI 对话正文呈现清洗（chat-structure spec §C）。

仅呈现层：剥离 AI 叙事里残留的 markdown 记号、统一换行；
不改叙事内容生成、不动任何数值与结算。纯函数、幂等
（内部迭代至不动点，输出再清洗必不变）。
只处理明确的 markdown 记号，不动中文叙事符号（「」『』【】·：等）。
"""

import re

_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BOLD3_STAR = re.compile(r"\*{3,}(.+?)\*{3,}", re.S)
_BOLD_STAR = re.compile(r"\*\*(.+?)\*\*", re.S)
# 单星斜体仅当内容含中文时才剥（防误伤 3*5 一类数字表达式）
_ITALIC_STAR = re.compile(r"\*([^*\n]*[一-鿿][^*\n]*)\*")
_BOLD_UNDER = re.compile(r"__(.+?)__", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_HEADING = re.compile(r"^#{1,6}[ \t]+", re.M)
_QUOTE = re.compile(r"^>[ \t]?", re.M)
# 悬挂星号：贴在词首/词尾的落单强调符（词中或数字间的 * 不动）
_LEAD_STAR = re.compile(r"(^|[\s，。；：、！？·])\*(?=\S)", re.M)
_TAIL_STAR = re.compile(r"(?<=\S)\*(?=$|[\s，。；：、！？·])", re.M)
_BLANK_RUN = re.compile(r"\n{3,}")


def _strip_once(t: str) -> str:
    t = _LINK.sub(r"\1", t)
    t = _BOLD3_STAR.sub(r"\1", t)
    t = _BOLD_STAR.sub(r"\1", t)
    t = _ITALIC_STAR.sub(r"\1", t)
    t = _BOLD_UNDER.sub(r"\1", t)
    t = _INLINE_CODE.sub(r"\1", t)
    t = _HEADING.sub("", t)
    t = _QUOTE.sub("", t)
    t = _LEAD_STAR.sub(r"\1", t)
    t = _TAIL_STAR.sub("", t)
    return t


def clean_dialogue_text(s) -> str:
    """清洗一段 AI 对话正文用于呈现；非字符串入参按空串处理。"""
    if not isinstance(s, str):
        return ""
    out = s.replace("\r\n", "\n").replace("\r", "\n")
    for _ in range(6):
        nxt = _strip_once(out)
        if nxt == out:
            break
        out = nxt
    out = "\n".join(line.rstrip() for line in out.split("\n"))
    out = _BLANK_RUN.sub("\n\n", out)
    return out.strip()
