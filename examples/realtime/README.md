# Потоки у FastAPI: SSE, WebSocket, webhooks

```bash
pip install -r requirements.txt
python realtime_demo.py
```

- `GET /events/news` — Server-Sent Events через вбудований `fastapi.sse` (FastAPI ≥ 0.135), `Last-Event-ID`;
- `WS /ws/chat?token=secret-token` — WebSocket з автентифікацією через `Depends` і `WebSocketException`, розсилка без падіння на зниклих клієнтах;
- `app.webhooks` — опис webhook, який надсилає сервер, у розділі `webhooks` OpenAPI.

Ті самі стилі на метеоданих, разом із GraphQL і gRPC, — `../meteo_api/api_styles_demo.py`. Розбір — сторінка книги «Які бувають API» (Частина I).
