def build_chat_prompt(question, behavior_segment, feature_summary, documents, recommended_books):
    kb_text = "\n".join(
        f"- {doc.get('title', doc.get('id', 'Document'))}: {doc.get('text', '')}"
        for doc in documents
    )
    books_text = "\n".join(
        f"- {book.get('title', 'Untitled')} (${book.get('price', '0.00')})"
        for book in recommended_books
    )
    return f"""
You are an AI bookstore advisor.
User question: {question}
Behavior segment: {behavior_segment}
Behavior explanation: {feature_summary}
Knowledge base:
{kb_text}
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
