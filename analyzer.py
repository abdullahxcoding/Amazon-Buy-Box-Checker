"""
The toggle-controlled analyzer loop used by the desktop app.

start() runs an immediate check of the whole ASIN list, then keeps
checking every hour until stop() is called. Uses an interruptible wait
(threading.Event) so turning the toggle off stops it right away instead
of waiting for the current hour to elapse, and also breaks out of an
in-progress check between ASINs rather than finishing the whole list.

Talks to the UI only through a thread-safe queue of (event_name, payload)
tuples — desktop_app.py polls this queue on the main thread and updates
widgets there. Nothing in here touches Tkinter directly, so this module
has no UI dependency and could be reused by any interface.
"""

import queue
import random
import threading
import time
import traceback

import config
from alerts import logger
from check_buybox import check_one
from ip_guard import ensure_vpn_connected
from offer_sources import get_offer_source
from state_store import load_state, save_state

CHECK_INTERVAL_SECONDS = 3600


class Analyzer:
    def __init__(self, update_queue: "queue.Queue"):
        self.update_queue = update_queue
        self._stop_event = threading.Event()
        self._thread = None
        self._running = False

    def is_running(self) -> bool:
        return self._running

    def start(self, asin_rows: list[dict]) -> None:
        if self._running:
            return
        self._stop_event.clear()
        self._running = True
        self._asin_rows = asin_rows
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.update_queue.put(("analyzer_started", None))

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_event.set()
        self._running = False
        self.update_queue.put(("analyzer_stopped", None))

    def _loop(self) -> None:
        # This runs in a background daemon thread — an uncaught exception
        # here would otherwise kill the thread silently (no console when
        # packaged with --windowed), leaving the toggle showing "on" with
        # no further activity and no clue why. Always catch, log, and
        # surface it to the UI instead.
        while not self._stop_event.is_set():
            try:
                self._run_check_cycle()
            except Exception:
                logger.exception("Analyzer check cycle crashed")
                self.update_queue.put(("analyzer_crashed", traceback.format_exc()))
                self._running = False
                return
            if self._stop_event.is_set():
                break
            next_run_at = time.time() + CHECK_INTERVAL_SECONDS
            self.update_queue.put(("next_check_at", next_run_at))
            self._stop_event.wait(timeout=CHECK_INTERVAL_SECONDS)

    def _run_check_cycle(self) -> None:
        self.update_queue.put(("check_started", None))

        if config.OFFER_SOURCE == "scraper" and not ensure_vpn_connected():
            logger.error("Aborting this check: VPN preflight failed.")
            self.update_queue.put(("check_aborted_vpn", None))
            return

        state = load_state()
        source = get_offer_source()

        for i, row in enumerate(self._asin_rows):
            if self._stop_event.is_set():
                break

            result = check_one(source, row["asin"], row["label"], state)
            save_state(state)
            self.update_queue.put(("row_update", result))

            is_last = i == len(self._asin_rows) - 1
            if not is_last and not self._stop_event.is_set():
                delay = random.uniform(config.MIN_DELAY_SECONDS, config.MAX_DELAY_SECONDS)
                self._stop_event.wait(timeout=delay)

        self.update_queue.put(("check_finished", None))
