"""局域网联机对战：基于 TCP socket 的简单主机/加入模型。

一台电脑作为主机（执黑先行）监听端口，另一台作为客户端（执白）连接。
连上后主机先发一条 setup（玩法、棋盘大小、吃几子），之后双方以“一行一条 JSON”
交换落子、停一手、认输、数子时的死子标记等消息。
网络在后台线程收发，UI 每帧调用 poll() 取消息，不会卡住画面。
"""
from __future__ import annotations

import json
import queue
import socket
import threading
from typing import Any, Dict, List, Optional

DEFAULT_PORT = 5920


def local_ip() -> str:
    """尽量获取本机在局域网中的 IP（供对方连接）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # 不会真的发包，只为拿到出口网卡地址
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class NetGame:
    def __init__(self, role: str):
        self.role = role            # 'host' / 'client'
        self.status = "init"        # init / listening / connecting / connected / error / closed
        self.error = ""
        self.color = "b" if role == "host" else "w"   # 主机执黑
        self._sock: Optional[socket.socket] = None
        self._srv: Optional[socket.socket] = None
        self._in: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self._alive = True
        self._lock = threading.Lock()

    # ---------- 建立连接 ----------
    def host(self, port: int = DEFAULT_PORT) -> None:
        self.status = "listening"
        threading.Thread(target=self._host_thread, args=(port,), daemon=True).start()

    def _host_thread(self, port: int) -> None:
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("0.0.0.0", port))
            srv.listen(1)
            srv.settimeout(1.0)
            self._srv = srv
            while self._alive:
                try:
                    conn, _addr = srv.accept()
                except socket.timeout:
                    continue
                self._sock = conn
                self.status = "connected"
                self._recv_loop()
                return
        except OSError as e:
            self.status = "error"
            self.error = str(e)

    def join(self, ip: str, port: int = DEFAULT_PORT) -> None:
        self.status = "connecting"
        threading.Thread(target=self._join_thread, args=(ip, port), daemon=True).start()

    def _join_thread(self, ip: str, port: int) -> None:
        try:
            sock = socket.create_connection((ip, port), timeout=8.0)
            self._sock = sock
            self.status = "connected"
            self._recv_loop()
        except OSError as e:
            self.status = "error"
            self.error = str(e)

    # ---------- 收发 ----------
    def _recv_loop(self) -> None:
        buf = b""
        self._sock.settimeout(1.0)
        while self._alive:
            try:
                data = self._sock.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    self._in.put(json.loads(line.decode("utf-8")))
                except ValueError:
                    pass
        if self._alive and self.status == "connected":
            self.status = "closed"

    def send(self, msg: Dict[str, Any]) -> None:
        with self._lock:
            if self._sock is None:
                return
            try:
                self._sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
            except OSError:
                self.status = "closed"

    def poll(self) -> List[Dict[str, Any]]:
        out = []
        while True:
            try:
                out.append(self._in.get_nowait())
            except queue.Empty:
                break
        return out

    def send_move(self, move) -> None:
        """move 为 (r,c)；None 表示停一手。"""
        self.send({"type": "move", "move": None if move is None else list(move)})

    def send_setup(self, rule: str, size: int, capture_target: int) -> None:
        self.send({"type": "setup", "rule": rule, "size": size, "capture_target": capture_target})

    def send_resign(self) -> None:
        self.send({"type": "resign"})

    def close(self) -> None:
        self._alive = False
        for s in (self._sock, self._srv):
            try:
                if s is not None:
                    s.close()
            except OSError:
                pass
        self.status = "closed"
