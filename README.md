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
  each ASIN, to look less like a bot.

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

- **ASIN list box** (left panel): one ASIN per line, or `ASIN,Label` — only
  include ASINs currently Sold/Shipped by Amazon, that's the required
  starting state this tool watches for drift away from. Loads automatically
  from `data/asins.csv` if you've used this before; "Save list" writes your
  edits back to that file without starting a check.
- **Load CSV...** — import a CSV (`asin` column required, `label` optional,
  header casing doesn't matter) instead of typing the list by hand.
- **Analyzer switch** — flip it on to start: checks the whole list right
  away, then every hour on the hour from that point, until you flip it off.
  Turning it off stops immediately (including mid-check, between ASINs —
  it won't force you to wait through the rest of a running check).
- **Listings tab** — live status per ASIN: green "ok" / red "alert" (shows
  which seller currently holds the Buy Box) / gray "check_failed" (page
  navigation kept timing out after 3 retries, or the page layout didn't
  match — not a real Buy Box loss). Each ASIN's navigation is retried up to
  3 times with a short delay between attempts before being marked failed —
  a VPN connection can intermittently stall an individual request even
  while others succeed fine, so isolated timeouts usually resolve on retry.
  A "Clear" button at the top of this tab resets all statuses back to
  pending.
- **History tab** — full log of lost / recovered / check-failed events over
  time, newest first. Its own "Clear" button permanently wipes the history
  file (asks for confirmation first).
- Closing the app window stops the analyzer — it only runs while the app is
  open and the switch is on.

## 3. Alerts

- Every check logs to `logs/checker.log`.
- **Windows desktop notification** (toast popup) fires automatically on this
  PC when an alert fires or resolves — no setup needed, uses `winotify`.
  Only appears while you're logged into an active desktop session.
- If SMTP settings are filled in in `.env`, email alerts are also sent:
  - `[Buy Box ALERT]` when a listing drifts away from Amazon as seller —
    repeats every check while the issue persists.
  - `[Buy Box RESOLVED]` once, when Amazon wins the Buy Box back.
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

This installs PyInstaller into the venv if needed, builds both
`AmazonBuyBoxChecker.exe` (the app) and `InstallBrowser.exe` (a one-time
setup helper, see below), and copies both into the project folder. Pin
`AmazonBuyBoxChecker.exe` to your taskbar or desktop for one-click
launching — no terminal or venv activation required to run it day-to-day.

**Moving to a new device:** copy `AmazonBuyBoxChecker.exe` there — that's
now genuinely all you need (its defaults already target amazon.co.uk
correctly, no `.env` required). But Playwright's Chromium browser
(~100-150MB) is NOT bundled inside the app exe, so on a device that's
never run this before, also copy `InstallBrowser.exe` and **run it once
first**. It downloads just the browser (using the exact Playwright version
bundled in the app, so there's no version-mismatch risk) — after that
one-time step, `AmazonBuyBoxChecker.exe` works normally on that device from
then on. You only need to do this once per device, not per launch.

Other notes:
- `data/asins.csv` is still read from the project folder next to the
  `.exe` (not bundled inside it), so your ASIN list persists across
  rebuilds and updates if you keep the `.exe` in the same folder.
- `data/` and `logs/` folders are created automatically on first run if
  they don't already exist (e.g. on a freshly-copied device).
- Rebuild (`.\build_exe.ps1` again) any time you or I change the Python
  source files — the `.exe` is a snapshot, it doesn't auto-update.
- Neither `.exe` is committed to git (they're 50MB+ each and just build
  artifacts) — `dist/`, `build/`, `*.spec`, and both root-level `.exe`
  files are all gitignored. Anyone else working from this repo runs
  `build_exe.ps1` themselves to get their own copies.

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
