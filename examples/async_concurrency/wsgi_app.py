"""Найменший WSGI-застосунок: звичайна функція, один виклик — один запит від початку до кінця.

    python wsgi_app.py 8771            # wsgiref: один потік, запити по одному
    python wsgi_app.py 8772 threaded   # wsgiref + потік на кожен запит
"""
import os
import sys
import threading
import time
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server


def app(environ, start_response):
    if environ["PATH_INFO"] == "/slow":
        time.sleep(0.5)                          # WSGI не має await: чекати можна лише блокуючи потік
    body = f"pid={os.getpid()} thread={threading.current_thread().name}".encode()
    start_response("200 OK", [("Content-Type", "text/plain"), ("Content-Length", str(len(body)))])
    return [body]


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


class QuietHandler(WSGIRequestHandler):
    def log_message(self, *args) -> None:        # без рядка журналу на кожен запит
        pass


if __name__ == "__main__":
    port, threaded = int(sys.argv[1]), sys.argv[2:] == ["threaded"]
    server_class = ThreadingWSGIServer if threaded else WSGIServer
    make_server("127.0.0.1", port, app, server_class=server_class, handler_class=QuietHandler).serve_forever()
