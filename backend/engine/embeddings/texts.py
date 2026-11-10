from backend.engine import errors


def document_text(movie):
    english = movie['translations']['en']
    return (f"passage: Title: {english['title']}\n"
            f"Genres: {', '.join(english['genres'])}\n"
            f"Description: {english['description']}")


def query_text(query):
    if not isinstance(query, str) or not query.strip():
        raise errors.InputValidationError('semantic_empty')
    return 'query: ' + query.strip()

