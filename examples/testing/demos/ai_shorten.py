"""Відповідь AI-асистента на «обріж заголовок до limit символів і додай три крапки». Не використовується в newsapp."""


def shorten(title: str, limit: int) -> str:
    if len(title) > limit:
        return title[:limit] + "…"
    return title
