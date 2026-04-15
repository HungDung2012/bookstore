def _format_block(block):
    kind = block.get("kind", "context")
    title = block.get("title") or block.get("id") or "Context"
    text = block.get("text", "")
    if kind == "graph_fact":
        return f"- Graph fact: {title}: {text}"
    if kind == "graph_path":
        relations = " / ".join(block.get("relations", []))
        reason = block.get("reason", "")
        extra = f" ({relations})" if relations else ""
        if reason:
            extra = f"{extra} - {reason}".strip()
        return f"- Graph path: {title}: {text}{extra}"
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
):
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
                "title": "Graph path",
                "text": " -> ".join(path.get("nodes", [])),
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
