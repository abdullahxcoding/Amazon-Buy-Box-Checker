# Amazon Buy Box Checker (desktop app, scraper-based, SP-API-ready)

Desktop app that monitors a list of ASINs and alerts you whenever a
listing's Buy Box is no longer won by Amazon itself (i.e. some other
vendor's offer has gone live instead of "Sold/Shipped by Amazon"). Keeps
re-alerting every check while the issue persists, then sends a one-time
"resolved" notice once Amazon wins the Buy Box back.

Enter your ASIN list in the app, flip the **Analyzer** switch on: it
checks the whole list immediately, then keeps checking every hour for as
long as the switch stays on. Turn it off to stop.

Currently checks via **web scraping** (Playwright, headless Chromium). The
system is built so that switching to the official **SP-API** later (once
your project manager grants Pricing-role access) is a one-line config
change — see "Switching to SP-API later" below.

## 1. Setup

```powershell
cd amazon_list_checker
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
copy .env.example .env
```

Edit `.env`:
- `AMAZON_SELLER_NAME` — the exact seller name Amazon shows for its own
  listings on your marketplace (confirmed as `Amazon` for amazon.co.uk).
- `HOME_IP` — optional. Set this to your normal (non-VPN) public IP, and the
  app will skip a check (rather than scrape from your raw IP) if it detects
  you're still on that IP, i.e. VPN not connected.
- `MIN_DELAY_SECONDS` / `MAX_DELAY_SECONDS` — random delay between checking
  each ASIN, to look less like a bot. Defaults (3-8s) are trimmed for large
  lists (hundreds to 1000+ ASINs); raise these back up (e.g. 8/20) for a
  small list that can afford to be more cautious about request pacing.

**Performance at scale (large ASIN lists):** one browser process is kept
open for the whole check cycle instead of launching a fresh one per ASIN
(previously real overhead at 1000+ ASINs) — each ASIN still gets its own
clean browser context, so isolation is unchanged. Even so, per-ASIN time is
dominated by real page-load time over the VPN (often 5-20s) plus the
delay above, not launch overhead — so a list of 1000 will still take
multiple hours end-to-end, it just no longer also pays a redundant
browser-launch tax on top. The Analyzer's "hourly" cadence still applies
between full cycles, not between individual ASINs — with a list this
large, expect each ASIN to effectively be re-checked every few hours
rather than every hour, since one full pass takes longer than an hour.

**IP rotation via Privado VPN:** connect Privado VPN before flipping the
Analyzer on, and leave it connected the whole time the app is running
checks. The app does not control the VPN itself; it only checks (via
`ip_guard.py`) that your public IP isn't your raw home IP before scraping,
and skips that hour's check if it looks disconnected (retrying again next
hour). A single VPN connection covers the whole run — simpler than
per-request proxy rotation but coarser: if Amazon starts blocking that VPN
IP, the fix is to reconnect Privado to a different server.

## 2. Run the app

Either run it from source:

```powershell
.venv\Scripts\python desktop_app.py
```

...or build it once into a standalone `.exe` (see "Package as a standalone
.exe" below) and just double-click `AmazonBuyBoxChecker.exe` from then on —
no terminal, no venv activation needed.

- **ASIN list box** (left panel): one per line — `ASIN`, `ASIN,Label`, or
  `ASIN,Label,ExpectedPrice`. Only include ASINs currently Sold/Shipped by
  Amazon, that's the required starting state this tool watches for drift
  away from. Prices are plain numbers (`9.99`, not `£9.99` or `1,234.56` —
  the currency symbol is stripped automatically but a comma thousands
  separator will be misread as a column break in this box; leave the price
  off if you need one). Loads automatically from `data/asins.csv` if you've
  used this before; "Save list" writes your edits back to that file without
  starting a check.
- **Load CSV...** — import a CSV (`asin` column required, `label` and
  `expected_price`/`price` columns optional, header casing doesn't matter,
  column order doesn't matter for this path) instead of typing the list by
  hand.
- **Price checking** — give an ASIN an expected price and every check also
  compares the live price against it (only while Amazon holds the Buy Box —
  a vendor takeover is reported as that issue, not a price mismatch, since
  it's the more serious problem). Leave the price blank for an ASIN to skip
  price checking for it and only watch the seller.
- **Analyzer switch** — flip it on to start: checks the whole list right
  away, then every hour on the hour from that point, until you flip it off.
  Turning it off stops immediately (including mid-check, between ASINs —
  it won't force you to wait through the rest of a running check).
- **Listings tab** — live status per ASIN: green "ok" / red "alert" (vendor
  took the Buy Box — shows who) / amber "price_mismatch" (still sold by
  Amazon, but the live price doesn't match the expected price you set) /
  gray "check_failed" (page navigation kept timing out after 3 retries, or
  the page layout didn't match — not a real issue with the listing itself).
  Each ASIN's navigation is retried up to 3 times with a short delay
  between attempts before being marked failed — a VPN connection can
  intermittently stall an individual request even while others succeed
  fine, so isolated timeouts usually resolve on retry. A "Clear" button at
  the top of this tab resets all statuses back to pending.
- **History tab** — full log of lost / price_mismatch / recovered /
  check-failed events over time, newest first. Its own "Clear" button
  permanently wipes the history file (asks for confirmation first).
- Closing the app window stops the analyzer — it only runs while the app is
  open and the switch is on.

## 3. Alerts

- Every check logs to `logs/checker.log`.
- **Windows desktop notification** (toast popup) fires automatically on this
  PC when an alert fires or resolves — no setup needed. It's a "reminder"
  toast, meaning it does **not** auto-dismiss after a few seconds like a
  normal notification — it stays on screen and sits in the Action Center
  until you act on it, with two buttons: **Open** (brings up the app so
  you can look at the issue) and **Dismiss** (closes it). Only appears
  while you're logged into an active desktop session. A repeat alert for
  the same ASIN replaces the previous toast for it rather than piling up
  duplicates.
- If SMTP settings are filled in in `.env`, email alerts are also sent:
  - `[Buy Box ALERT]` when a listing drifts away from Amazon as seller —
    repeats every check while the issue persists.
  - `[Price ALERT]` when Amazon is still the seller but the live price
    doesn't match the expected price you set — repeats every check while
    it persists.
  - `[RESOLVED]` once, when either issue clears (Amazon wins the Buy Box
    back and/or the price matches again).
- A failed/blocked scrape does NOT fire a false "lost Buy Box" alert — it's
  logged as a check failure instead, so you can tell scraper problems apart
  from real Buy Box losses.

State (open/resolved per ASIN) is tracked in `data/state.json`; full event
history in `data/alerts_history.jsonl`.

## Optional: headless/manual fallback (no app window)

`check_buybox.py` can still be run directly from a terminal for a single
one-off check, independent of the desktop app — useful for quick manual
testing, or if you ever want an external scheduler (e.g. Windows Task
Scheduler via `run_hourly.ps1`) instead of leaving the app open:

```powershell
.venv\Scripts\python check_buybox.py
```

This is not the primary way to run the project day-to-day — the desktop
app's Analyzer switch is — but it shares all the same underlying logic
(`check_one()` in `check_buybox.py`), so results are identical either way.

## Package as a standalone .exe

Build it once, then just double-click the `.exe` from then on:

```powershell
.\build_exe.ps1
```

This installs PyInstaller into the venv if needed, builds
`AmazonBuyBoxChecker.exe` with Playwright's Chromium browser bundled
directly inside it, and copies it into the project folder. Pin it to your
taskbar or desktop for one-click launching — no terminal or venv
activation required to run it day-to-day.

The exe is fully self-contained — around **170MB**, since it embeds a real
Chromium browser (not just the automation code). **Moving to a new device
is just copying this one file** — no `.env`, no separate browser install
step, no setup script. Its defaults already target amazon.co.uk correctly.
Trade-off: launches take a few extra seconds compared to a small exe,
since PyInstaller's onefile mode extracts the whole bundle (including the
browser) to a temp folder on every startup.

Building requires Chromium to already be installed in your own dev
environment first (`.venv\Scripts\playwright install chromium` — a
one-time step on the machine you build from, not on machines you run the
built exe on). The build script finds it automatically under
`%LOCALAPPDATA%\ms-playwright\` and bundles it in.

Other notes:
- `data/asins.csv` is still read from the project folder next to the
  `.exe` (not bundled inside it), so your ASIN list persists across
  rebuilds and updates if you keep the `.exe` in the same folder.
- `data/` and `logs/` folders are created automatically on first run if
  they don't already exist (e.g. on a freshly-copied device).
- Rebuild (`.\build_exe.ps1` again) any time you or I change the Python
  source files — the `.exe` is a snapshot, it doesn't auto-update.
- The `.exe` isn't committed to git (it's 170MB+ and just a build
  artifact) — `dist/`, `build/`, `*.spec`, and the root-level `.exe` are
  all gitignored. Anyone else working from this repo runs `build_exe.ps1`
  themselves to get their own copy.

## Switching to SP-API later

Once you have SP-API credentials with the Pricing role:

1. `pip install python-amazon-sp-api`
2. Fill in the SP-API fields in `.env` (`LWA_APP_ID`, `LWA_CLIENT_SECRET`,
   `SP_API_REFRESH_TOKEN`, `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `ROLE_ARN`,
   `MARKETPLACE`) and set `AMAZON_SELLER_ID` to Amazon's real retail Seller
   ID for your marketplace.
3. Implement `get_buybox_offer()` in `offer_sources/sp_api_source.py` (the
   file has the exact steps in its docstring) using
   `Products.get_item_offers()`.
4. Set `OFFER_SOURCE=sp_api` in `.env`.

Nothing else changes — `check_buybox.py`, `analyzer.py`, `alerts.py`,
`state_store.py`, the CSV format, and the desktop app all stay exactly the
same, because they only talk to the generic `OfferSource` interface in
`offer_sources/base.py`, never to the scraper or SP-API directly.
