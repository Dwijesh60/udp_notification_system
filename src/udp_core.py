"""
udp_core.py  –  Reliable UDP Group Notification Engine
=======================================================
Handles:
  • UDP socket send / receive  (binds to 0.0.0.0 for LAN reachability)
  • ACK-based reliability (stop-and-wait per peer)
  • TWO modes:
      - REAL  : actual teammates on the same LAN  (no artificial loss)
      - SIM   : all peers on localhost, artificial packet-loss injection
  • Server (broadcaster) and Client (receiver) roles
"""

import socket
import threading
import random
import json
import struct
import logging
from dataclasses import dataclass, asdict
from typing import Callable, Optional

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("udp_core")

# ─── Constants ────────────────────────────────────────────────────────────────
MAGIC       = b"\xAB\xCD"
VERSION     = 1
MAX_RETRIES = 5
ACK_TIMEOUT = 2.0
BUFFER_SIZE = 4096

TYPE_DATA = "DATA"
TYPE_ACK  = "ACK"


# ─── Packet ───────────────────────────────────────────────────────────────────
@dataclass
class Packet:
    ptype:   str
    seq:     int
    sender:  str
    payload: str = ""

    def encode(self) -> bytes:
        body   = json.dumps(asdict(self)).encode("utf-8")
        header = MAGIC + struct.pack("!HH", VERSION, len(body))
        return header + body

    @staticmethod
    def decode(raw: bytes) -> "Packet":
        if raw[:2] != MAGIC:
            raise ValueError("Bad magic bytes")
        _ver, blen = struct.unpack("!HH", raw[2:6])
        d = json.loads(raw[6:6 + blen].decode("utf-8"))
        return Packet(**d)


# ─── Node ─────────────────────────────────────────────────────────────────────
class ReliableUDPNode:
    """
    Parameters
    ----------
    name            : display name shown in packets
    on_message      : callback(sender, message, from_addr_str)
    on_ack          : callback(peer_addr_str, seq, success: bool)
    simulation_mode : True  -> artificial loss on localhost
                      False -> real LAN, no artificial drops
    loss_probability: only used when simulation_mode=True  (0.0-1.0)
    """

    def __init__(
        self,
        name:             str,
        on_message:       Callable[[str, str, str], None],
        on_ack:           Callable[[str, int, bool], None],
        simulation_mode:  bool  = False,
        loss_probability: float = 0.0,
    ):
        self.name             = name
        self.on_message       = on_message
        self.on_ack           = on_ack
        self.simulation_mode  = simulation_mode
        self.loss_probability = loss_probability

        self._sock: Optional[socket.socket] = None
        self._running  = False
        self._seq      = 0
        self._seq_lock = threading.Lock()
        self._mode: Optional[str] = None

        self._clients          = []
        self._clients_lock     = threading.Lock()
        self._server_addr      = None

        self._ack_events: dict[int, threading.Event] = {}
        self._ack_lock   = threading.Lock()

    # ── public API ─────────────────────────────────────────────────────────────

    def start_server(self, port: int, client_addrs: list[tuple[str, int]] = None):
        self._mode = "server"
        with self._clients_lock:
            self._clients = list(client_addrs or [])
        self._bind_and_listen(port)

    def start_client(self, port: int, server_addr: tuple[str, int]):
        self._mode        = "client"
        self._server_addr = server_addr
        self._bind_and_listen(port)

    def stop(self):
        self._running = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None

    def send_notification(self, message: str) -> dict[str, bool]:
        if self._mode == "server":
            with self._clients_lock:
                targets = list(self._clients)
        elif self._mode == "client" and self._server_addr:
            targets = [self._server_addr]
        else:
            return {}

        results = {}
        lock    = threading.Lock()
        threads = []

        def _worker(addr):
            ok = self._send_reliable(message, addr)
            with lock:
                results[f"{addr[0]}:{addr[1]}"] = ok

        for addr in targets:
            t = threading.Thread(target=_worker, args=(addr,), daemon=True)
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        return results

    # ── internals ──────────────────────────────────────────────────────────────

    def _bind_and_listen(self, port: int):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", port))   # listen on ALL interfaces
        self._sock.settimeout(0.5)
        self._running = True
        threading.Thread(target=self._recv_loop, daemon=True).start()
        tag = "[SIM]" if self.simulation_mode else "[LAN]"
        log.info(f"{tag} {self.name} bound 0.0.0.0:{port} as {self._mode}")

    def _next_seq(self) -> int:
        with self._seq_lock:
            self._seq += 1
            return self._seq

    def _should_drop(self) -> bool:
        return self.simulation_mode and (random.random() < self.loss_probability)

    def _send_reliable(self, message: str, addr: tuple[str, int]) -> bool:
        seq     = self._next_seq()
        pkt     = Packet(TYPE_DATA, seq, self.name, message)
        raw     = pkt.encode()
        addr_s  = f"{addr[0]}:{addr[1]}"

        evt = threading.Event()
        with self._ack_lock:
            self._ack_events[seq] = evt

        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            if self._should_drop():
                log.warning(f"[SIM-DROP-OUT] seq={seq} attempt={attempt} -> {addr_s}")
                self.on_ack(addr_s, seq, False)
            else:
                try:
                    self._sock.sendto(raw, addr)
                    log.debug(f"[SENT] seq={seq} attempt={attempt} -> {addr_s}")
                except Exception as e:
                    log.error(f"sendto: {e}")

            if evt.wait(timeout=ACK_TIMEOUT):
                success = True
                log.info(f"[ACK-OK] seq={seq} peer={addr_s}")
                self.on_ack(addr_s, seq, True)
                break

            log.warning(f"[NO-ACK] seq={seq} attempt={attempt}/{MAX_RETRIES} peer={addr_s}")

        with self._ack_lock:
            self._ack_events.pop(seq, None)

        if not success:
            log.error(f"[FAILED] seq={seq} peer={addr_s}")
            self.on_ack(addr_s, seq, False)

        return success

    def _recv_loop(self):
        while self._running:
            try:
                raw, addr = self._sock.recvfrom(BUFFER_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break

            if self._should_drop():
                log.warning(f"[SIM-DROP-IN] from {addr[0]}:{addr[1]}")
                continue

            try:
                pkt = Packet.decode(raw)
            except Exception as e:
                log.error(f"Decode error from {addr}: {e}")
                continue

            if pkt.ptype == TYPE_ACK:
                with self._ack_lock:
                    evt = self._ack_events.get(pkt.seq)
                if evt:
                    evt.set()

            elif pkt.ptype == TYPE_DATA:
                # 1. ACK immediately
                ack = Packet(TYPE_ACK, pkt.seq, self.name)
                try:
                    self._sock.sendto(ack.encode(), addr)
                except Exception:
                    pass

                # 2. Add to clients list if server (dynamic discovery)
                if self._mode == "server":
                    with self._clients_lock:
                        if addr not in self._clients:
                            self._clients.append(addr)
                            log.info(f"[NEW-CLIENT] Registered {addr[0]}:{addr[1]}")

                # 3. Notify app
                self.on_message(pkt.sender, pkt.payload, f"{addr[0]}:{addr[1]}")

                # 4. Relay only if server
                if self._mode == "server":
                    with self._clients_lock:
                        others = [c for c in self._clients if c != addr]
                    for c in others:
                        threading.Thread(
                            target=self._send_reliable,
                            args=(f"[relay from {pkt.sender}] {pkt.payload}", c),
                            daemon=True,
                        ).start()


# ─── Helper ───────────────────────────────────────────────────────────────────
def get_local_ip() -> str:
    """Detect this machine's LAN IP (not 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
