"""
udp_gui.py  -  Reliable UDP Group Notifier (GUI)
=================================================
Run with:  python udp_gui.py

MODE TOGGLE
-----------
  SIM  (Simulation) : 3 virtual peers all on localhost. Use the loss
                      slider to simulate dropped packets and watch
                      retransmissions happen in the log.

  LAN  (Real)       : Teammates run this on their own machines.
                      Enter their actual LAN IPs in the peer list.
                      No artificial drops - real network only.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading

from udp_core import ReliableUDPNode, get_local_ip

# ─── Palette ──────────────────────────────────────────────────────────────────
BG      = "#0d1117"
PANEL   = "#161b22"
CARD    = "#1f2430"
ACCENT  = "#58a6ff"
SUCCESS = "#3fb950"
WARNING = "#d29922"
DANGER  = "#f85149"
TEXT    = "#e6edf3"
SUBTEXT = "#8b949e"
BORDER  = "#30363d"
SIM_CLR = "#bf91f3"   # purple tint for simulation mode
LAN_CLR = "#56d364"   # green tint for real LAN mode

FONT_MONO = ("Consolas", 10)
FONT_UI   = ("Segoe UI", 10)
FONT_H    = ("Segoe UI", 12, "bold")
FONT_SML  = ("Segoe UI", 9)


# ─── App ──────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UDP Reliable Group Notifier")
        self.configure(bg=BG)
        self.geometry("950x700")
        self.resizable(True, True)

        self._node: ReliableUDPNode | None = None
        self._running = False
        self._mode_var = tk.StringVar(value="LAN")   # "LAN" | "SIM"

        self._build_ui()
        self._on_mode_change()   # initialise panel visibility

    # ══════════════════════════════════════════════════════════════════════════
    #  UI CONSTRUCTION
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Top bar ────────────────────────────────────────────────────────────
        topbar = tk.Frame(self, bg=PANEL, pady=0)
        topbar.pack(fill="x")

        title_f = tk.Frame(topbar, bg=PANEL, padx=16, pady=10)
        title_f.pack(side="left")
        tk.Label(title_f, text="📡", font=("Segoe UI", 18), bg=PANEL, fg=TEXT).pack(side="left")
        tk.Label(title_f, text="  UDP Reliable Group Notifier",
                 font=("Segoe UI", 14, "bold"), bg=PANEL, fg=TEXT).pack(side="left")

        # Mode toggle (top-right)
        mode_f = tk.Frame(topbar, bg=PANEL, padx=16, pady=10)
        mode_f.pack(side="right")
        tk.Label(mode_f, text="Mode:", font=FONT_UI, bg=PANEL, fg=SUBTEXT).pack(side="left", padx=(0, 6))
        for val, label, colour in [("SIM", "⚗  Simulation", SIM_CLR),
                                    ("LAN", "🌐  Real LAN",   LAN_CLR)]:
            rb = tk.Radiobutton(
                mode_f, text=label, variable=self._mode_var, value=val,
                command=self._on_mode_change,
                font=FONT_UI, bg=PANEL, fg=colour, selectcolor=BG,
                activebackground=PANEL, activeforeground=colour,
                indicatoron=False, padx=10, pady=4, relief="flat",
                bd=1, highlightthickness=1, highlightbackground=BORDER,
                cursor="hand2",
            )
            rb.pack(side="left", padx=3)
        self._mode_btns = mode_f.winfo_children()[1:]  # the two radiobuttons

        sep = tk.Frame(self, bg=BORDER, height=1)
        sep.pack(fill="x")

        # ── Body (left config | right log) ────────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=10)

        left  = tk.Frame(body, bg=BG, width=300)
        right = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)
        right.pack(side="left", fill="both", expand=True)

        # ── Mode info banner ───────────────────────────────────────────────────
        self._banner_var = tk.StringVar()
        self._banner = tk.Label(left, textvariable=self._banner_var,
                                font=FONT_SML, bg=BG, fg=SIM_CLR,
                                justify="left", anchor="w", wraplength=280)
        self._banner.pack(fill="x", pady=(0, 6))

        # ── My LAN IP display ──────────────────────────────────────────────────
        ip_f = tk.Frame(left, bg=CARD, padx=10, pady=8,
                        highlightthickness=1, highlightbackground=BORDER)
        ip_f.pack(fill="x", pady=(0, 8))
        tk.Label(ip_f, text="Your LAN IP  (share with teammates)",
                 font=FONT_SML, bg=CARD, fg=SUBTEXT).pack(anchor="w")
        self._lan_ip = get_local_ip()
        ip_row = tk.Frame(ip_f, bg=CARD)
        ip_row.pack(fill="x", pady=(4, 0))
        tk.Label(ip_row, text=self._lan_ip, font=("Consolas", 13, "bold"),
                 bg=CARD, fg=LAN_CLR).pack(side="left")
        tk.Button(ip_row, text="Copy", font=FONT_SML, bg=BORDER, fg=TEXT,
                  relief="flat", padx=6, pady=2, cursor="hand2",
                  command=self._copy_ip).pack(side="right")

        # ── Config card ────────────────────────────────────────────────────────
        cfg = self._card(left, "⚙  Configuration")

        # Role
        self._role_var = tk.StringVar(value="server")
        rf = tk.Frame(cfg, bg=CARD)
        rf.pack(fill="x", pady=4)
        tk.Label(rf, text="Role:", font=FONT_UI, bg=CARD,
                 fg=SUBTEXT, width=8, anchor="w").pack(side="left")
        for r, t in [("server", "Server (Host)"), ("client", "Client (Join)")]:
            tk.Radiobutton(rf, text=t, variable=self._role_var, value=r,
                           font=FONT_UI, bg=CARD, fg=TEXT, selectcolor=BG,
                           activebackground=CARD, activeforeground=ACCENT,
                           command=self._on_role_change).pack(side="left", padx=6)

        self._name_var = tk.StringVar(value="User")
        self._row(cfg, "My Display Name:", self._name_var)

        self._port_var = tk.StringVar(value="9000")
        self._row(cfg, "My Port:", self._port_var)

        # ── Simulation-only settings (hidden in LAN mode) ──────────────────────
        self._sim_frame = tk.Frame(cfg, bg=CARD)
        self._sim_frame.pack(fill="x")

        sep1 = tk.Frame(self._sim_frame, bg=BORDER, height=1)
        sep1.pack(fill="x", pady=6)
        tk.Label(self._sim_frame, text="Simulated Peers  (host:port, one per line)",
                 font=FONT_SML, bg=CARD, fg=SUBTEXT).pack(anchor="w")
        self._sim_peers_txt = tk.Text(self._sim_frame, height=4, width=28,
                                      bg=BG, fg=SIM_CLR, insertbackground=TEXT,
                                      font=FONT_MONO, bd=0, relief="flat",
                                      highlightthickness=1, highlightbackground=BORDER)
        self._sim_peers_txt.pack(fill="x", pady=4)
        self._sim_peers_txt.insert("1.0", "127.0.0.1:9001\n127.0.0.1:9002")

        # loss slider
        tk.Label(self._sim_frame, text="Packet Loss Simulation",
                 font=FONT_SML, bg=CARD, fg=SUBTEXT).pack(anchor="w", pady=(6, 0))
        lf = tk.Frame(self._sim_frame, bg=CARD)
        lf.pack(fill="x")
        self._loss_var = tk.DoubleVar(value=0.0)
        self._loss_lbl = tk.Label(lf, text="0%", font=FONT_UI,
                                  bg=CARD, fg=WARNING, width=5, anchor="e")
        self._loss_lbl.pack(side="right")
        sl = tk.Scale(self._sim_frame, from_=0, to=100, orient="horizontal",
                      variable=self._loss_var, command=self._update_loss,
                      bg=CARD, fg=TEXT, highlightthickness=0, troughcolor=BG,
                      activebackground=SIM_CLR, sliderrelief="flat", bd=0)
        sl.pack(fill="x")

        # ── LAN-only settings (hidden in SIM mode) ─────────────────────────────
        self._lan_frame = tk.Frame(cfg, bg=CARD)

        sep2 = tk.Frame(self._lan_frame, bg=BORDER, height=1)
        sep2.pack(fill="x", pady=6)
        
        self._peer_lbl_var = tk.StringVar(value="Connect To (Server IP:port)")
        tk.Label(self._lan_frame, textvariable=self._peer_lbl_var,
                 font=FONT_SML, bg=CARD, fg=SUBTEXT).pack(anchor="w")
        
        self._lan_peers_txt = tk.Text(self._lan_frame, height=3, width=28,
                                      bg=BG, fg=LAN_CLR, insertbackground=TEXT,
                                      font=FONT_MONO, bd=0, relief="flat",
                                      highlightthickness=1, highlightbackground=BORDER)
        self._lan_peers_txt.pack(fill="x", pady=4)

        self._lan_info_lbl = tk.Label(self._lan_frame,
                 text="ℹ  As Server, you can leave this empty.\n   Clients will auto-register on first message.",
                 font=FONT_SML, bg=CARD, fg=SUBTEXT, justify="left")
        self._lan_info_lbl.pack(anchor="w", pady=(4, 0))

        # ── Start / Stop ───────────────────────────────────────────────────────
        sep3 = tk.Frame(cfg, bg=BORDER, height=1)
        sep3.pack(fill="x", pady=8)
        btn_f = tk.Frame(cfg, bg=CARD)
        btn_f.pack(fill="x")
        self._start_btn = self._btn(btn_f, "▶  Start", self._start, ACCENT)
        self._stop_btn  = self._btn(btn_f, "■  Stop",  self._stop,  DANGER)
        self._start_btn.pack(side="left", padx=(0, 6))
        self._stop_btn.pack(side="left")
        self._stop_btn.config(state="disabled")

        # ── Peer status ────────────────────────────────────────────────────────
        ps = self._card(left, "📊  Delivery Status")
        self._status_frame = tk.Frame(ps, bg=CARD)
        self._status_frame.pack(fill="x")
        self._status_labels: dict[str, tk.Label] = {}

        # ── Right: send + log ──────────────────────────────────────────────────
        send_card = self._card(right, "✉  Send Notification")
        ef = tk.Frame(send_card, bg=CARD)
        ef.pack(fill="x")
        self._msg_var = tk.StringVar()
        ent = tk.Entry(ef, textvariable=self._msg_var, font=FONT_UI,
                       bg=BG, fg=TEXT, insertbackground=TEXT,
                       relief="flat", bd=4)
        ent.pack(side="left", fill="x", expand=True)
        ent.bind("<Return>", lambda _: self._send())
        self._send_btn = self._btn(ef, "Send →", self._send, SUCCESS)
        self._send_btn.pack(side="left", padx=(8, 0))
        self._send_btn.config(state="disabled")

        log_card = self._card(right, "📜  Live Event Log")
        self._log = scrolledtext.ScrolledText(
            log_card, height=26, state="disabled",
            bg=BG, fg=TEXT, insertbackground=TEXT, font=FONT_MONO,
            bd=0, relief="flat", wrap="word",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._log.pack(fill="both", expand=True)
        for tag, colour in [
            ("ok",   SUCCESS), ("warn", WARNING), ("err",  DANGER),
            ("info", ACCENT),  ("recv", TEXT),    ("sim",  SIM_CLR),
            ("lan",  LAN_CLR),
        ]:
            self._log.tag_config(tag, foreground=colour)

        clr = self._btn(log_card, "Clear", self._clear_log, SUBTEXT)
        clr.pack(anchor="e", pady=(4, 0))

    # ══════════════════════════════════════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════════════════════════════════════

    def _card(self, parent, title: str) -> tk.Frame:
        outer = tk.Frame(parent, bg=BORDER, pady=1, padx=1)
        outer.pack(fill="x", pady=5)
        inner = tk.Frame(outer, bg=CARD, padx=12, pady=10)
        inner.pack(fill="both", expand=True)
        tk.Label(inner, text=title, font=FONT_H, bg=CARD, fg=TEXT).pack(anchor="w", pady=(0, 8))
        return inner

    def _row(self, parent, label: str, var: tk.StringVar):
        f = tk.Frame(parent, bg=CARD)
        f.pack(fill="x", pady=2)
        tk.Label(f, text=label, font=FONT_UI, bg=CARD,
                 fg=SUBTEXT, width=9, anchor="w").pack(side="left")
        tk.Entry(f, textvariable=var, font=FONT_UI, bg=BG, fg=TEXT,
                 insertbackground=TEXT, relief="flat", bd=2,
                 width=16).pack(side="left")

    def _btn(self, parent, text, cmd, colour) -> tk.Button:
        return tk.Button(parent, text=text, command=cmd, font=FONT_UI,
                         bg=colour, fg="white", activebackground=colour,
                         activeforeground="white", relief="flat", bd=0,
                         padx=10, pady=4, cursor="hand2")

    def _log_msg(self, text: str, tag: str = "info"):
        def _do():
            self._log.config(state="normal")
            self._log.insert("end", text + "\n", tag)
            self._log.see("end")
            self._log.config(state="disabled")
        self.after(0, _do)

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _copy_ip(self):
        self.clipboard_clear()
        self.clipboard_append(self._lan_ip)
        self._log_msg(f"[COPY] LAN IP {self._lan_ip} copied to clipboard.", "info")

    def _update_loss(self, _=None):
        v = int(self._loss_var.get())
        self._loss_lbl.config(text=f"{v}%")
        if self._node:
            self._node.loss_probability = v / 100

    def _parse_peers(self, text_widget: tk.Text) -> list[tuple[str, int]]:
        peers = []
        for line in text_widget.get("1.0", "end").strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            h, _, p = line.rpartition(":")
            try:
                peers.append((h.strip(), int(p.strip())))
            except ValueError:
                pass
        return peers

    def _update_status(self, addr: str, seq: int, ok: bool):
        colour = SUCCESS if ok else DANGER
        symbol = "✔" if ok else "✘"
        txt    = f"  {symbol}  {addr}  (seq {seq})"

        def _do():
            if addr not in self._status_labels:
                lbl = tk.Label(self._status_frame, text=txt, font=FONT_UI,
                               bg=CARD, fg=colour, anchor="w")
                lbl.pack(fill="x", pady=1)
                self._status_labels[addr] = lbl
            else:
                self._status_labels[addr].config(text=txt, fg=colour)
        self.after(0, _do)

    # ══════════════════════════════════════════════════════════════════════════
    #  MODE / ROLE CHANGE
    # ══════════════════════════════════════════════════════════════════════════

    def _on_mode_change(self):
        mode = self._mode_var.get()
        if mode == "SIM":
            self._sim_frame.pack(fill="x")
            self._lan_frame.pack_forget()
            self._banner_var.set(
                "⚗  SIMULATION MODE\n"
                "All peers are on localhost. Use the loss slider\n"
                "to see retransmissions. Great for testing alone."
            )
            self._banner.config(fg=SIM_CLR)
        else:
            self._lan_frame.pack(fill="x")
            self._sim_frame.pack_forget()
            self._banner_var.set(
                f"🌐  REAL LAN MODE\n"
                f"Your IP: {self._lan_ip}\n"
                "Enter teammates' IPs in the peer list below."
            )
            self._banner.config(fg=LAN_CLR)

    def _on_role_change(self):
        role = self._role_var.get()
        if role == "server":
            self._peer_lbl_var.set("Additional Targets (Optional)")
            self._lan_info_lbl.config(
                text="ℹ  As Server, you can leave this empty.\n   Clients will auto-register on first message."
            )
        else:
            self._peer_lbl_var.set("Server IP:Port (Required)")
            self._lan_info_lbl.config(
                text="ℹ  Enter the Host's IP (displayed on their screen)\n   to join the chat session."
            )

    # ══════════════════════════════════════════════════════════════════════════
    #  NODE CALLBACKS
    # ══════════════════════════════════════════════════════════════════════════

    def _on_message(self, sender: str, msg: str, addr: str):
        self._log_msg(f"[RECV ←] {sender}: {msg}  ({addr})", "recv")

    def _on_ack(self, addr: str, seq: int, ok: bool):
        if ok:
            self._log_msg(f"[ACK ✔] seq={seq}  peer={addr}", "ok")
        else:
            mode = self._mode_var.get()
            tag  = "sim" if mode == "SIM" else "warn"
            self._log_msg(f"[DROP/NO-ACK] seq={seq}  peer={addr}", tag)
        self._update_status(addr, seq, ok)

    # ══════════════════════════════════════════════════════════════════════════
    #  CONTROL
    # ══════════════════════════════════════════════════════════════════════════

    def _start(self):
        if self._running:
            return

        mode = self._mode_var.get()
        try:
            port  = int(self._port_var.get().strip())
            name  = self._name_var.get().strip() or "Member"
            role  = self._role_var.get()
            loss  = self._loss_var.get() / 100

            if mode == "SIM":
                peers = self._parse_peers(self._sim_peers_txt)
                sim   = True
            else:
                peers = self._parse_peers(self._lan_peers_txt)
                sim   = False

        except Exception as e:
            messagebox.showerror("Config Error", str(e))
            return

        self._node = ReliableUDPNode(
            name=name,
            on_message=self._on_message,
            on_ack=self._on_ack,
            simulation_mode=sim,
            loss_probability=loss,
        )

        tag = "sim" if sim else "lan"
        if role == "server":
            self._node.start_server(port, peers)
            self._log_msg(
                f"[START] Server '{name}'  port={port}  mode={mode}  clients={peers}", tag)
        else:
            server_addr = peers[0] if peers else ("127.0.0.1", 9000)
            self._node.start_client(port, server_addr)
            self._log_msg(
                f"[START] Client '{name}'  port={port}  mode={mode}  server={server_addr}", tag)

        if mode == "LAN":
            self._log_msg(
                f"[INFO] Listening on 0.0.0.0:{port}  — teammates connect to {self._lan_ip}:{port}", "lan")

        self._running = True
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._send_btn.config(state="normal")

    def _stop(self):
        if self._node:
            self._node.stop()
            self._node = None
        self._running = False
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._send_btn.config(state="disabled")
        self._log_msg("[STOP] Node stopped.", "warn")

    def _send(self):
        msg = self._msg_var.get().strip()
        if not msg or not self._node:
            return
        self._msg_var.set("")
        self._log_msg(f"[SEND →] {msg}", "info")
        threading.Thread(target=self._do_send, args=(msg,), daemon=True).start()

    def _do_send(self, msg: str):
        results = self._node.send_notification(msg)
        for addr, ok in results.items():
            tag    = "ok" if ok else "err"
            status = "delivered ✔" if ok else "FAILED after retries ✘"
            self._log_msg(f"[RESULT] {addr} → {status}", tag)


# ─── Entry ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.mainloop()
