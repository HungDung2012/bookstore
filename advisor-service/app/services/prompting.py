from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalContext:
    documents: list | None = None
    recommended_books: list | None = None
    graph_facts: list | None = None
    graph_paths: list | None = None
    text_sources: list | None = None
    context_blocks: list | None = None


def _humanize_identifier(value):
    if not value:
        return ""
    return str(value).split(":", 1)[-1].replace("_", " ")


def _format_path_text(block):
    nodes = block.get("nodes", [])
    if nodes:
        return " -> ".join(_humanize_identifier(node) for node in nodes if node)
    return block.get("text", "") or block.get("title", "Graph path")


def _pick_context_value(current, override):
    if override is None:
        return current
    return override


def _format_block(block):
    kind = block.get("kind", "context")
    title = block.get("title") or block.get("id") or "Context"
    text = block.get("text", "")
    if kind == "graph_fact":
        return f"- Graph fact: {title}: {text}"
    if kind == "graph_path":
        relations = " / ".join(block.get("relations", []))
        reason = block.get("reason", "")
        path_text = _format_path_text(block)
        extra = ""
        if relations:
            extra += f" ({relations})"
        if reason:
            extra += f" - {reason}"
        return f"- Graph path: {path_text}{extra}"
    if kind == "text_source":
        return f"- Text source: {title}: {text}"
    return f"- {title}: {text}"


def build_chat_prompt(
    question,
    behavior_segment,
    feature_summary,
    documents=None,
    recommended_books=None,
    graph_facts=None,
    graph_paths=None,
    text_sources=None,
    context_blocks=None,
    retrieval_context=None,
):
    if retrieval_context is not None:
        if hasattr(retrieval_context, "get"):
            documents = _pick_context_value(documents, retrieval_context.get("documents"))
            recommended_books = _pick_context_value(recommended_books, retrieval_context.get("recommended_books"))
            graph_facts = _pick_context_value(graph_facts, retrieval_context.get("graph_facts"))
            graph_paths = _pick_context_value(graph_paths, retrieval_context.get("graph_paths"))
            text_sources = _pick_context_value(text_sources, retrieval_context.get("text_sources"))
            context_blocks = _pick_context_value(context_blocks, retrieval_context.get("context_blocks"))
        else:
            documents = _pick_context_value(documents, getattr(retrieval_context, "documents", None))
            recommended_books = _pick_context_value(
                recommended_books,
                getattr(retrieval_context, "recommended_books", None),
            )
            graph_facts = _pick_context_value(graph_facts, getattr(retrieval_context, "graph_facts", None))
            graph_paths = _pick_context_value(graph_paths, getattr(retrieval_context, "graph_paths", None))
            text_sources = _pick_context_value(text_sources, getattr(retrieval_context, "text_sources", None))
            context_blocks = _pick_context_value(context_blocks, getattr(retrieval_context, "context_blocks", None))

    documents = documents or []
    recommended_books = recommended_books or []
    if text_sources is None:
        text_sources = documents

    if context_blocks is None:
        context_blocks = []
        context_blocks.extend(
            {
                "kind": "graph_fact",
                "id": fact.get("id"),
                "title": fact.get("relation", fact.get("id", "Graph fact")),
                "text": fact.get("statement", ""),
            }
            for fact in (graph_facts or [])
        )
        context_blocks.extend(
            {
                "kind": "graph_path",
                "nodes": list(path.get("nodes", [])),
                "relations": list(path.get("relations", [])),
                "title": _format_path_text(path),
                "text": _format_path_text(path),
                "reason": path.get("reason", ""),
            }
            for path in (graph_paths or [])
        )
        context_blocks.extend(
            {
                "kind": "text_source",
                "id": doc.get("id"),
                "title": doc.get("title", doc.get("id", "Document")),
                "text": doc.get("text", ""),
            }
            for doc in text_sources
        )

    context_text = "\n".join(_format_block(block) for block in context_blocks)
    books_text = "\n".join(
        f"- {book.get('title', 'Untitled')} (${book.get('price', '0.00')})"
        for book in recommended_books
    )
    return f"""
You are an AI bookstore advisor.
User question: {question}
Behavior segment: {behavior_segment}
Behavior explanation: {feature_summary}
Relevant context:
{context_text}
Suggested books:
{books_text}
Answer in a concise and grounded way. Explain why the recommendations match the user's behavior.
""".strip()


def build_fallback_answer(question, behavior_segment, recommended_books):
    book_names = ", ".join(
        title
        for title in (
            book.get("title")
            for book in recommended_books[:3]
            if isinstance(book, dict)
        )
        if title
    ) or "our featured catalog"
    return (
        f"Based on your behavior segment `{behavior_segment}`, I recommend starting with {book_names}. "
        f"This matches your recent shopping pattern. For service questions, I will answer using the bookstore knowledge base."
    )
