from __future__ import annotations

import socket
import socketserver
import threading
import time

from waveos.utils.metrics import counters
from waveos.utils.proxy import ProxyConfig, start_proxy
import pytest
import http.client


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
    except PermissionError:
        pytest.skip("Socket bind not permitted in this environment")
    port = sock.getsockname()[1]
    sock.close()
    return port


class EchoHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = self.request.recv(4096)
        if data:
            self.request.sendall(data)


def test_tcp_forwarder_proxy() -> None:
    target_port = _free_port()
    listen_port = _free_port()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", target_port), EchoHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    start_value = counters()["proxy_connections"].labels(direction="inbound")._value.get()
    start_bytes_ct = counters()["proxy_bytes"].labels(direction="client_to_target")._value.get()
    start_bytes_tc = counters()["proxy_bytes"].labels(direction="target_to_client")._value.get()

    start_proxy(
        ProxyConfig(
            mode="tcp_forward",
            listen_host="127.0.0.1",
            listen_port=listen_port,
            target_host="127.0.0.1",
            target_port=target_port,
        )
    )

    time.sleep(0.05)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("127.0.0.1", listen_port))
    payload = b"ping"
    client.sendall(payload)
    response = client.recv(4096)
    client.close()
    server.shutdown()
    server.server_close()

    assert response == payload
    assert counters()["proxy_connections"].labels(direction="inbound")._value.get() >= start_value + 1
    assert counters()["proxy_bytes"].labels(direction="client_to_target")._value.get() >= start_bytes_ct + len(payload)
    assert counters()["proxy_bytes"].labels(direction="target_to_client")._value.get() >= start_bytes_tc + len(payload)


class HttpHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = self.request.recv(4096)
        if not data:
            return
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 5\r\n"
            b"\r\n"
            b"hello"
        )
        self.request.sendall(response)


def test_http_forwarder_proxy() -> None:
    target_port = _free_port()
    listen_port = _free_port()
    server = socketserver.ThreadingTCPServer(("127.0.0.1", target_port), HttpHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    start_value = counters()["proxy_connections"].labels(direction="inbound")._value.get()
    start_proxy(
        ProxyConfig(
            mode="http_forward",
            listen_host="127.0.0.1",
            listen_port=listen_port,
            target_host="127.0.0.1",
            target_port=target_port,
        )
    )
    time.sleep(0.05)
    conn = http.client.HTTPConnection("127.0.0.1", listen_port, timeout=5)
    conn.request("GET", "/hello")
    response = conn.getresponse()
    body = response.read().decode("utf-8")
    conn.close()
    server.shutdown()
    server.server_close()

    assert response.status == 200
    assert body == "hello"
    assert counters()["proxy_connections"].labels(direction="inbound")._value.get() >= start_value + 1
