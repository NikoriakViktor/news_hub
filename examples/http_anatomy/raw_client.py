"""«Сирий» HTTP через сокет: що насправді йде по мережі. Спершу запусти inspect_app на порту 8014."""
import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8014


def send(request: bytes) -> str:
    with socket.create_connection(("127.0.0.1", PORT)) as s:
        s.sendall(request)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    return data.decode()


def request(start_line: str, headers: dict[str, str], body: bytes = b"") -> bytes:
    if body:
        headers = {**headers, "Content-Type": "application/json", "Content-Length": str(len(body))}
    head = start_line + "\r\n" + "".join(f"{k}: {v}\r\n" for k, v in {"Host": f"127.0.0.1:{PORT}", **headers,
                                                                        "Connection": "close"}.items())
    return head.encode() + b"\r\n" + body


def short(response: str) -> str:
    """Статус-рядок, заголовки без date і тіло."""
    return "\n".join(line for line in response.split("\r\n") if line and not line.startswith("date:"))


full = request("POST /inspect?debug=1 HTTP/1.1",
               {"User-Agent": "MyClient/1.0", "X-Request-ID": "abc-1", "Cookie": "session_id=tok-123"},
               '{"message": "Привіт"}'.encode())
print("=== ЗАПИТ\n" + full.decode() + "\n\n=== ВІДПОВІДЬ\n" + send(full))

for start, headers, body in [
    ("GET /items HTTP/1.1", {}, b""),                                  # без косої риски в кінці
    ("DELETE /items/ HTTP/1.1", {}, b""),                              # шлях є, методу немає
    ("POST /inspect HTTP/1.1", {}, b"{}"),                             # тіло без message
    ("POST /inspect HTTP/1.1", {"X_Request_ID": "under"}, b'{"message":"m"}'),   # підкреслення в імені
]:
    print(f"\n=== {start} {headers or ''} {body.decode()}\n" + short(send(request(start, headers, body))))
