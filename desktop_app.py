"""
Desktop app for the Amazon Buy Box Checker.

Enter your ASIN list, flip the Analyzer switch on: it checks the whole
list immediately, then keeps checking every hour until you flip it off.
Everything else (scraper, VPN preflight, alerts, desktop notifications,
alert history) is unchanged from the rest of the project — this is just
the interface.
"""

import csv
import io
import os
import queue
import sys
import time
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from tkinter import ttk

if sys.platform == "win32":
    # Without this, Windows DPI-virtualizes the window on scaled displays,
    # which double-scales on top of customtkinter's own DPI scaling and
    # pushes right-aligned widgets (the Analyzer switch) off the visible
    # window. Must run before importing customtkinter.
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass

import customtkinter as ctk

import config
from analyzer import Analyzer, CHECK_INTERVAL_SECONDS
from csv_utils import read_asin_rows

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

STATUS_COLORS = {
    "ok": "#1a9c5f",
    "alert": "#d0392b",
    "price_mismatch": "#b3760a",
    "check_failed": "#9aa1ab",
    "pending": "#6b7280",
}


def _fmt_ts(ts):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "-"


def _parse_price(raw: str):
    raw = (raw or "").strip().replace("£", "").replace(",", "")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_asin_textbox(text: str) -> list[dict]:
    """Accepts lines like 'ASIN', 'ASIN,Label', or 'ASIN,Label,ExpectedPrice'
    (an optional header row is skipped) — same lenient parsing as
    csv_utils, but from raw text."""
    reader = csv.reader(io.StringIO(text))
    rows = []
    for parts in reader:
        if not parts or not parts[0].strip():
            continue
        first = parts[0].strip()
        if first.lower() == "asin":
            continue
        label = parts[1].strip() if len(parts) > 1 else ""
        expected_price = _parse_price(parts[2]) if len(parts) > 2 else None
        rows.append({"asin": first, "label": label, "expected_price": expected_price})
    return rows


def _rows_to_textbox(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        price = r.get("expected_price")
        if price is not None:
            lines.append(f"{r['asin']},{r['label']},{price}")
        elif r["label"]:
            lines.append(f"{r['asin']},{r['label']}")
        else:
            lines.append(r["asin"])
    return "\n".join(lines)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Amazon Buy Box Checker")
        self.geometry("980x680")
        self.minsize(760, 520)

        self.update_queue: "queue.Queue" = queue.Queue()
        self.analyzer = Analyzer(self.update_queue)
        self._row_index = {}  # asin -> treeview item id
        self._next_check_at = None

        self._build_layout()
        self._load_existing_asins()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._poll_queue)
        self.after(1000, self._tick_countdown)

    # ---------- layout ----------

    def _build_layout(self):
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(top, text="Amazon Buy Box Checker", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        self.switch_var = ctk.StringVar(value="off")
        self.analyzer_switch = ctk.CTkSwitch(
            top, text="Analyzer: OFF", command=self._on_toggle,
            variable=self.switch_var, onvalue="on", offvalue="off",
        )
        self.analyzer_switch.pack(side="right")

        self.status_label = ctk.CTkLabel(top, text="Idle", text_color=("gray30", "gray70"))
        self.status_label.pack(side="right", padx=(0, 16))

        # stats row
        stats = ctk.CTkFrame(self, fg_color="transparent")
        stats.pack(fill="x", padx=16, pady=(0, 8))
        self.total_stat = self._make_stat(stats, "Total ASINs")
        self.total_alerts_stat = self._make_stat(stats, "Active alerts")
        self.alert_stat = self._make_stat(stats, "Seller/Shipper mismatch")
        self.price_stat = self._make_stat(stats, "Price mismatches")
        self.ok_stat = self._make_stat(stats, "OK")

        # main split: left = ASIN input, right = tabs (listings/history)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=8)
        body.grid_columnconfigure(0, weight=1, minsize=280)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(left, text="ASIN list: one per line — ASIN, ASIN,Label, or ASIN,Label,ExpectedPrice",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=12, pady=(12, 4))
        self.asin_box = ctk.CTkTextbox(left, wrap="none")
        self.asin_box.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkButton(btn_row, text="Load CSV...", command=self._load_csv, width=100).pack(side="left")
        ctk.CTkButton(btn_row, text="Save list", command=self._save_asins_from_box, width=100).pack(side="left", padx=8)

        right = ctk.CTkFrame(body)
        right.grid(row=0, column=1, sticky="nsew")

        self.tabs = ctk.CTkTabview(right)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=8)
        self.tabs.add("Listings")
        self.tabs.add("History")

        listings_toolbar = ctk.CTkFrame(self.tabs.tab("Listings"), fg_color="transparent")
        listings_toolbar.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(listings_toolbar, text="Clear", width=70, command=self._clear_listings).pack(side="right")

        self.listings_tree = self._make_tree(
            self.tabs.tab("Listings"),
            columns=("asin", "label", "expected_price", "status", "detail", "last_checked"),
            headings=("ASIN", "Label", "Expected Price", "Status", "Detail", "Last checked"),
            widths=(110, 100, 100, 90, 240, 140),
        )

        history_toolbar = ctk.CTkFrame(self.tabs.tab("History"), fg_color="transparent")
        history_toolbar.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(history_toolbar, text="Clear", width=70, command=self._clear_history).pack(side="right")

        self.history_tree = self._make_tree(
            self.tabs.tab("History"),
            columns=("time", "asin", "label", "event", "detail"),
            headings=("Time", "ASIN", "Label", "Event", "Detail"),
            widths=(140, 110, 100, 90, 260),
        )

        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 12))
        self.countdown_label = ctk.CTkLabel(bottom, text="", text_color=("gray30", "gray70"))
        self.countdown_label.pack(side="left")

    def _make_stat(self, parent, label):
        frame = ctk.CTkFrame(parent)
        frame.pack(side="left", expand=True, fill="x", padx=(0, 8))
        ctk.CTkLabel(frame, text=label, font=ctk.CTkFont(size=11), text_color=("gray40", "gray60")).pack(
            anchor="w", padx=12, pady=(10, 0))
        value = ctk.CTkLabel(frame, text="0", font=ctk.CTkFont(size=22, weight="bold"))
        value.pack(anchor="w", padx=12, pady=(0, 10))
        return value

    def _make_tree(self, parent, columns, headings, widths):
        style = ttk.Style()
        style.theme_use("default")
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="none")
        for col, head, w in zip(columns, headings, widths):
            tree.heading(col, text=head)
            tree.column(col, width=w, anchor="w")
        tree.pack(fill="both", expand=True, padx=4, pady=4)
        for status, color in STATUS_COLORS.items():
            tree.tag_configure(status, foreground=color)
        return tree

    # ---------- ASIN list handling ----------

    def _load_existing_asins(self):
        if os.path.exists(config.ASIN_CSV_PATH):
            rows = read_asin_rows(config.ASIN_CSV_PATH)
            self.asin_box.insert("1.0", _rows_to_textbox(rows))
            self._refresh_listings_placeholder(rows)

    def _refresh_listings_placeholder(self, rows):
        for r in rows:
            self._upsert_row(r["asin"], r["label"], r.get("expected_price"), "pending", "Not checked yet", None)
        self._update_stats()

    def _load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        with open(path, encoding="utf-8") as f:
            content = f.read()
        rows = _parse_asin_textbox(content)
        self.asin_box.delete("1.0", "end")
        self.asin_box.insert("1.0", _rows_to_textbox(rows))
        self._save_asins_from_box()

    def _save_asins_from_box(self):
        rows = _parse_asin_textbox(self.asin_box.get("1.0", "end"))
        os.makedirs(os.path.dirname(config.ASIN_CSV_PATH), exist_ok=True)
        with open(config.ASIN_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["asin", "label", "expected_price"])
            writer.writeheader()
            for r in rows:
                writer.writerow({
                    "asin": r["asin"],
                    "label": r["label"],
                    "expected_price": "" if r.get("expected_price") is None else r["expected_price"],
                })
        return rows

    # ---------- analyzer toggle ----------

    def _on_toggle(self):
        if self.switch_var.get() == "on":
            rows = self._save_asins_from_box()
            if not rows:
                messagebox.showwarning("No ASINs", "Add at least one ASIN before starting the analyzer.")
                self.switch_var.set("off")
                self.analyzer_switch.configure(text="Analyzer: OFF")
                return
            self._refresh_listings_placeholder(rows)
            self.analyzer_switch.configure(text="Analyzer: ON")
            self.status_label.configure(text="Starting...")
            self.analyzer.start(rows)
        else:
            self.analyzer_switch.configure(text="Analyzer: OFF")
            self.status_label.configure(text="Stopping...")
            self.analyzer.stop()

    # ---------- queue-driven UI updates (runs on main thread) ----------

    def _poll_queue(self):
        try:
            while True:
                event, payload = self.update_queue.get_nowait()
                self._handle_event(event, payload)
        except queue.Empty:
            pass
        self.after(200, self._poll_queue)

    def _handle_event(self, event, payload):
        if event == "analyzer_started":
            self.status_label.configure(text="Running")
        elif event == "analyzer_stopped":
            self.status_label.configure(text="Idle")
            self.countdown_label.configure(text="")
            self._next_check_at = None
        elif event == "check_started":
            self.status_label.configure(text="Checking now...")
        elif event == "check_aborted_vpn":
            self.status_label.configure(text="Check skipped: VPN not connected")
        elif event == "analyzer_crashed":
            self.status_label.configure(text="Stopped: error (see logs/checker.log)")
            self.switch_var.set("off")
            self.analyzer_switch.configure(text="Analyzer: OFF")
            self.countdown_label.configure(text="")
            self._next_check_at = None
            messagebox.showerror(
                "Analyzer stopped unexpectedly",
                "The analyzer hit an error and stopped:\n\n" + str(payload)[-1200:] +
                "\n\nFull details are in logs/checker.log.")
        elif event == "check_finished":
            if self.analyzer.is_running():
                self.status_label.configure(text="Running (waiting for next check)")
        elif event == "next_check_at":
            self._next_check_at = payload
        elif event == "row_update":
            self._upsert_row(payload["asin"], payload["label"], payload.get("expected_price"),
                              payload["status"], payload["detail"], time.time())
            self._append_history_if_notable(payload)
            self._update_stats()

    def _upsert_row(self, asin, label, expected_price, status, detail, checked_ts):
        price_display = f"£{expected_price:.2f}" if expected_price is not None else "-"
        values = (asin, label, price_display, status, detail, _fmt_ts(checked_ts))
        if asin in self._row_index:
            self.listings_tree.item(self._row_index[asin], values=values, tags=(status,))
        else:
            item = self.listings_tree.insert("", "end", values=values, tags=(status,))
            self._row_index[asin] = item

    def _append_history_if_notable(self, payload):
        # alerts.py already writes the authoritative event history (lost /
        # recovered / check_failed) to data/alerts_history.jsonl on every
        # row that fires an alert — just reload that for the History tab.
        self._reload_history_tab()

    def _reload_history_tab(self):
        path = config.ALERTS_HISTORY_PATH
        if not os.path.exists(path):
            return
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        import json
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()[-200:]
        for line in reversed(lines):
            e = json.loads(line)
            tag = {"lost": "alert", "price_mismatch": "price_mismatch", "recovered": "ok",
                   "check_failed": "check_failed"}.get(e["event"], "")
            self.history_tree.insert("", "end", values=(
                _fmt_ts(e["ts"]), e["asin"], e.get("label", ""), e["event"], e["detail"]
            ), tags=(tag,))

    def _clear_listings(self):
        if not messagebox.askyesno(
                "Clear listings",
                "Clear all listing statuses? They'll show as 'pending' again until the next check."):
            return
        for item in self.listings_tree.get_children():
            self.listings_tree.delete(item)
        self._row_index.clear()
        if os.path.exists(config.STATE_JSON_PATH):
            os.remove(config.STATE_JSON_PATH)
        rows = read_asin_rows(config.ASIN_CSV_PATH) if os.path.exists(config.ASIN_CSV_PATH) else []
        self._refresh_listings_placeholder(rows)

    def _clear_history(self):
        if not messagebox.askyesno("Clear history", "Clear all alert history? This cannot be undone."):
            return
        if os.path.exists(config.ALERTS_HISTORY_PATH):
            os.remove(config.ALERTS_HISTORY_PATH)
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

    def _update_stats(self):
        total = len(self._row_index)
        statuses = [self.listings_tree.set(item, "status") for item in self.listings_tree.get_children()]
        alerts = statuses.count("alert")
        price_mismatches = statuses.count("price_mismatch")
        ok = statuses.count("ok")
        self.total_stat.configure(text=str(total))
        self.total_alerts_stat.configure(text=str(alerts + price_mismatches))
        self.alert_stat.configure(text=str(alerts))
        self.price_stat.configure(text=str(price_mismatches))
        self.ok_stat.configure(text=str(ok))

    def _tick_countdown(self):
        if self._next_check_at:
            remaining = int(self._next_check_at - time.time())
            if remaining > 0:
                mins, secs = divmod(remaining, 60)
                self.countdown_label.configure(text=f"Next check in {mins:02d}:{secs:02d}")
            else:
                self.countdown_label.configure(text="Next check starting...")
        self.after(1000, self._tick_countdown)

    def _on_close(self):
        if self.analyzer.is_running():
            self.analyzer.stop()
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
