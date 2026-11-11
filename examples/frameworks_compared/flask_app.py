"""Ті самі нотатки на Flask: дані з request і перевірка — вручну."""
from flask import Flask, jsonify, request

app = Flask(__name__)
NOTES: list[dict] = []


@app.get("/api/notes")
def list_notes():
    limit = request.args.get("limit", 10, type=int)   # «abc» → тихо стане 10
    if not 1 <= limit <= 100:
        return jsonify(error="limit: від 1 до 100"), 400
    return jsonify(NOTES[:limit])


@app.post("/api/notes")
def create_note():
    data = request.get_json(silent=True) or {}
    errors = {}
    title = data.get("title")
    if not isinstance(title, str) or not 1 <= len(title) <= 200:
        errors["title"] = "рядок від 1 до 200 символів"
    priority = data.get("priority", 1)
    if not isinstance(priority, int) or not 1 <= priority <= 4:
        errors["priority"] = "ціле від 1 до 4"
    if errors:
        return jsonify(errors=errors), 400
    NOTES.append({"id": len(NOTES) + 1, "title": title, "priority": priority})
    return jsonify(NOTES[-1]), 201
