import http.server
import socketserver
import sys
import threading

PORT = 9199
LOG = r"C:\workspace\pea\verify\.echo_path.log"

# 记录 BFF 实际打过来的路径, 用于断言 /v1 不重复
with open(LOG, "w", encoding="utf-8") as f:
    f.write("")

paths = []


class Handler(http.server.BaseHTTPRequestHandler):
    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        chunks = [
            'data: {"choices":[{"delta":{"content":"hi "}}]}\n\n',
            'data: {"choices":[{"delta":{"content":"from echo"}}],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\n\n',
            "data: [DONE]\n\n",
        ]
        for c in chunks:
            try:
                self.wfile.write(c.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                break

    def do_POST(self):
        # 记录路径
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(self.path + "\n")
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length:
            self.rfile.read(length)
        self._stream()

    def log_message(self, *args):
        pass


class TCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"echo LLM server on :{PORT}", flush=True)
        httpd.serve_forever()
