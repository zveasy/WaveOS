from __future__ import annotations

from dataclasses import dataclass
from threading import Thread
import socket
import http.client
import http.server
import socketserver
from urllib.parse import urlsplit

from waveos.utils.logging import get_logger
from waveos.utils.metrics import counters


@dataclass
class ProxyConfig:
    mode: str = "sanitize"
    backpressure: bool = True
    listen_host: str = "127.0.0.1"
    listen_port: int | None = None
    target_host: str | None = None
    target_port: int | None = None


def start_proxy(config: ProxyConfig) -> None:
    logger = get_logger("waveos.proxy")
    logger.info("Proxy enabled mode=%s backpressure=%s", config.mode, config.backpressure)
    if config.mode == "tcp_forward":
        if not config.listen_port or not config.target_host or not config.target_port:
            logger.warning("Proxy tcp_forward missing listen/target settings")
            return
        thread = Thread(
            target=_run_tcp_forwarder,
            args=(config.listen_host, config.listen_port, config.target_host, config.target_port),
            daemon=True,
        )
        thread.start()
    if config.mode == "http_forward":
        if not config.listen_port or not config.target_host or not config.target_port:
            logger.warning("Proxy http_forward missing listen/target settings")
            return
        thread = Thread(
            target=_run_http_forwarder,
            args=(config.listen_host, config.listen_port, config.target_host, config.target_port),
            daemon=True,
        )
        thread.start()


def _run_tcp_forwarder(listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    logger = get_logger("waveos.proxy")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((listen_host, listen_port))
        server.listen(50)
        logger.info("Proxy listening on %s:%s -> %s:%s", listen_host, listen_port, target_host, target_port)
        while True:
            client, addr = server.accept()
            counters()["proxy_connections"].labels(direction="inbound").inc()
            logger.info("Proxy accepted connection from %s:%s", addr[0], addr[1])
            thread = Thread(target=_handle_connection, args=(client, target_host, target_port), daemon=True)
            thread.start()


def _handle_connection(client: socket.socket, target_host: str, target_port: int) -> None:
    logger = get_logger("waveos.proxy")
    try:
        counters()["proxy_bytes"].labels(direction="client_to_target").inc(0)
        counters()["proxy_bytes"].labels(direction="target_to_client").inc(0)
        target = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target.connect((target_host, target_port))
        counters()["proxy_connections"].labels(direction="outbound").inc()
    except OSError as exc:
        logger.warning("Proxy connect failed: %s", exc)
        client.close()
        return
    Thread(target=_pipe, args=(client, target, "client_to_target"), daemon=True).start()
    Thread(target=_pipe, args=(target, client, "target_to_client"), daemon=True).start()


def _pipe(src: socket.socket, dst: socket.socket, direction: str) -> None:
    try:
        while True:
            data = src.recv(4096)
            if not data:
                break
            counters()["proxy_bytes"].labels(direction=direction).inc(len(data))
            dst.sendall(data)
    except OSError:
        pass
    finally:
        try:
            src.close()
        except OSError:
            pass
        try:
            dst.close()
        except OSError:
            pass


def _run_http_forwarder(listen_host: str, listen_port: int, target_host: str, target_port: int) -> None:
    logger = get_logger("waveos.proxy")

    class _Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _proxy(self) -> None:
            counters()["proxy_connections"].labels(direction="inbound").inc()
            counters()["proxy_bytes"].labels(direction="client_to_target").inc(0)
            counters()["proxy_bytes"].labels(direction="target_to_client").inc(0)
            path = self.path
            if path.startswith("http://") or path.startswith("https://"):
                parsed = urlsplit(path)
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
            body = b""
            if "Content-Length" in self.headers:
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = 0
                if length:
                    body = self.rfile.read(length)
            counters()["proxy_connections"].labels(direction="outbound").inc()
            conn = http.client.HTTPConnection(target_host, target_port, timeout=10)
            headers = {key: value for key, value in self.headers.items()}
            for hop in ("Connection", "Proxy-Connection", "Keep-Alive", "Transfer-Encoding", "Upgrade"):
                headers.pop(hop, None)
            headers["Host"] = target_host
            conn.request(self.command, path, body=body, headers=headers)
            response = conn.getresponse()
            resp_body = response.read()
            self.send_response(response.status, response.reason)
            for key, value in response.getheaders():
                if key.lower() == "transfer-encoding" and value.lower() == "chunked":
                    continue
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            if body:
                counters()["proxy_bytes"].labels(direction="client_to_target").inc(len(body))
            counters()["proxy_bytes"].labels(direction="target_to_client").inc(len(resp_body))
            if resp_body:
                self.wfile.write(resp_body)
            conn.close()

        def do_GET(self) -> None:
            self._proxy()

        def do_POST(self) -> None:
            self._proxy()

        def do_PUT(self) -> None:
            self._proxy()

        def do_DELETE(self) -> None:
            self._proxy()

    with socketserver.ThreadingTCPServer((listen_host, listen_port), _Handler) as httpd:
        logger.info("HTTP proxy listening on %s:%s -> %s:%s", listen_host, listen_port, target_host, target_port)
        httpd.serve_forever()
