"""Conversation-history normalisation and compression for QA."""

from __future__ import annotations

from typing import Any

from aika.qa.constants import HISTORY_COMPRESSION_SYSTEM_PROMPT
from aika.question_planner import extract_companies


def normalize_conversation_history(
    messages: list[dict[str, str]] | None,
    *,
    max_turns: int,
    max_chars: int,
) -> list[dict[str, str]]:
    """归一化对话历史，控制大小和内容。

    裁剪规则：
    1. 只保留 role 为 "user" 或 "assistant" 的消息
    2. 每条消息内容截断到 3000 字符
    3. 按 max_turns 限制轮数（最近 N 轮）
    4. 按 max_chars 限制总字符数（从最近开始累加）

    Args:
        messages: 原始对话历史
        max_turns: 最大保留轮数（≤0 时不保留历史）
        max_chars: 最大保留字符数（≤0 时不限制）

    Returns:
        归一化后的对话历史
    """
    normalized = normalize_conversation_messages(messages)

    if max_turns <= 0:
        return []
    normalized = normalized[-max_turns * 2 :]
    return trim_history_to_chars(normalized, max_chars)


def normalize_conversation_messages(
    messages: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    """Normalize supported conversation messages without discarding old turns."""
    normalized: list[dict[str, str]] = []
    for message in messages or []:
        role = str(message.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        normalized.append({"role": role, "content": content[:3000]})
    return normalized


def trim_history_to_chars(
    messages: list[dict[str, str]],
    max_chars: int,
) -> list[dict[str, str]]:
    """Keep the newest messages within a character budget."""
    if max_chars <= 0:
        return list(messages)

    selected: list[dict[str, str]] = []
    used = 0
    for message in reversed(messages):
        content = message["content"]
        size = len(content)
        if selected and used + size > max_chars:
            break
        if size > max_chars:
            content = content[-max_chars:]
            size = len(content)
        selected.append({"role": message["role"], "content": content})
        used += size
    return list(reversed(selected))


def fit_summary_and_recent_to_budget(
    messages: list[dict[str, str]],
    max_chars: int,
) -> list[dict[str, str]]:
    """Keep a synthetic summary and as much recent verbatim history as possible."""
    if max_chars <= 0 or not messages:
        return messages
    summary = dict(messages[0])
    recent_budget = max(0, max_chars - len(summary["content"]))
    recent = [] if recent_budget <= 0 else trim_history_to_chars(messages[1:], recent_budget)
    remaining = max_chars - sum(len(message["content"]) for message in recent)
    if remaining <= 0:
        return recent
    summary["content"] = summary["content"][:remaining]
    return [summary, *recent]


def compress_history_with_llm(
    messages: list[dict[str, str]],
    *,
    llm_client: Any,
    llm_options: dict[str, Any],
    max_summary_chars: int,
    chunk_chars: int,
) -> str:
    """Compress older messages, using hierarchical summaries for long histories."""
    chunks = history_chunks(messages, max_chars=chunk_chars)
    summaries = [
        request_history_summary(
            chunk,
            llm_client=llm_client,
            llm_options=llm_options,
            max_summary_chars=max_summary_chars,
        )
        for chunk in chunks
    ]
    summaries = [summary for summary in summaries if summary]
    while len(summaries) > 1:
        summary_messages = [
            {"role": "assistant", "content": f"分段摘要 {index}：{summary}"}
            for index, summary in enumerate(summaries, start=1)
        ]
        merge_chunk_chars = max(chunk_chars, max_summary_chars * 2 + 100)
        chunks = history_chunks(summary_messages, max_chars=merge_chunk_chars)
        summaries = [
            request_history_summary(
                chunk,
                llm_client=llm_client,
                llm_options=llm_options,
                max_summary_chars=max_summary_chars,
            )
            for chunk in chunks
        ]
        summaries = [summary for summary in summaries if summary]
    return sanitize_history_summary(summaries[0] if summaries else "", max_chars=max_summary_chars)


def history_chunks(
    messages: list[dict[str, str]],
    *,
    max_chars: int,
) -> list[list[dict[str, str]]]:
    """Split history on message boundaries before LLM compression."""
    chunks: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    used = 0
    for message in messages:
        size = len(message["content"])
        if current and used + size > max_chars:
            chunks.append(current)
            current = []
            used = 0
        current.append(message)
        used += size
    if current:
        chunks.append(current)
    return chunks


def request_history_summary(
    messages: list[dict[str, str]],
    *,
    llm_client: Any,
    llm_options: dict[str, Any],
    max_summary_chars: int,
) -> str:
    prompt = (
        format_history_for_prompt(messages)
        + f"\n\n请压缩为不超过 {max_summary_chars} 个中文字符的连续摘要。"
    )
    options = dict(llm_options)
    options["thinking_enabled"] = False
    options.pop("reasoning_effort", None)
    if hasattr(llm_client, "chat_messages"):
        response = llm_client.chat_messages(
            messages=[
                {"role": "system", "content": HISTORY_COMPRESSION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            **options,
        )
        return sanitize_history_summary(response.content, max_chars=max_summary_chars)
    if hasattr(llm_client, "chat_text"):
        content = llm_client.chat_text(
            system_prompt=HISTORY_COMPRESSION_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=0.0,
            **options,
        )
        return sanitize_history_summary(content, max_chars=max_summary_chars)
    raise TypeError("LLM client does not support conversation history compression")


def sanitize_history_summary(content: str, *, max_chars: int) -> str:
    text = str(content or "").replace("```", "").strip()
    for prefix in ("摘要：", "对话摘要：", "历史摘要："):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text[:max_chars]


def build_contextualizer_prompt(question: str) -> str:
    """构建追问改写器的 user prompt。

    Args:
        question: 用户当前问题

    Returns:
        prompt 字符串
    """
    return f"""请把下面当前问题改写成一个不依赖上下文也能检索的单轮问题。
如果当前问题已经完整，原样输出。

当前问题：{question}
"""


def heuristic_contextual_question(question: str, history: list[dict[str, str]]) -> str:
    """基于启发式规则的追问上下文补全。

    将上一轮用户问题中的公司名提取出来，拼接到当前问题前。
    如上一轮提到"寒武纪"，当前问"它的风险呢" → "寒武纪 它的风险呢"

    Args:
        question: 用户当前问题
        history: 对话历史

    Returns:
        补全后的问题
    """
    question = question.strip()
    if not history or not question_needs_context(question):
        return question
    last_user = next((message["content"] for message in reversed(history) if message["role"] == "user"), "")
    if not last_user:
        return question
    companies = extract_companies(last_user)
    if companies:
        return f"{'和'.join(companies)} {question}"
    return f"{last_user}；追问：{question}"


def question_needs_context(question: str) -> bool:
    """判断当前问题是否需要上下文补全。

    需要上下文的情况：
    - 包含代词（它、其、他们、这些等）
    - 包含承接词（继续、进一步、再展开等）
    - "主要风险"不带公司名
    - 问题很短（≤18 字符）且无独立关键词

    Args:
        question: 用户当前问题

    Returns:
        是否需要上下文补全
    """
    question = question.strip()
    context_terms = (
        "它",
        "其",
        "他们",
        "这些",
        "这类",
        "上述",
        "上面",
        "前面",
        "刚才",
        "继续",
        "进一步",
        "再展开",
        "风险呢",
        "差异呢",
        "还有呢",
    )
    if any(term in question for term in context_terms):
        return True
    if "主要风险" in question and not extract_companies(question):
        return True
    independent_terms = ("哪些公司", "上市公司", "有哪些", "是什么", "为什么", "如何", "多少")
    if any(term in question for term in independent_terms):
        return False
    return len(question) <= 18


def sanitize_contextual_question(content: str) -> str:
    """清洗 LLM 输出的上下文补全结果。

    移除 Markdown 代码块标记、前缀（"改写后的问题："等）、引号。

    Args:
        content: LLM 输出的原始文本

    Returns:
        清洗后的问题文本（最长 500 字符）
    """
    text = str(content or "").strip()
    if not text:
        return ""
    text = text.replace("```", "").strip()
    if text.startswith(("改写后的问题：", "问题：")):
        text = text.split("：", 1)[-1].strip()
    text = text.strip("\"'“”‘’ \n")
    return text[:500]


def format_history_for_prompt(history: list[dict[str, str]]) -> str:
    """将对话历史格式化为 prompt 可读文本。

    用于旧版 LLM 接口（chat_text），将历史对话拼接到 prompt 中。

    Args:
        history: 对话历史

    Returns:
        格式化后的历史文本
    """
    lines = ["历史对话："]
    for message in history:
        role = "用户" if message["role"] == "user" else "助手"
        lines.append(f"{role}：{message['content']}")
    return "\n".join(lines)
