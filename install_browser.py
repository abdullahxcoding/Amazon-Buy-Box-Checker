"""
One-time setup for a new device: installs the Chromium browser Playwright
needs to scrape Amazon pages. Run this once (InstallBrowser.exe) before
using AmazonBuyBoxChecker.exe on a machine for the first time.

Packaged as its own small exe (see build_exe.ps1) using the same Playwright
version bundled into the main app, so there's no version-mismatch risk
between what this installs and what the main app expects to find.
"""

import sys

from playwright.__main__ import main as playwright_main


def main():
    print("Installing the Chromium browser for Amazon Buy Box Checker...")
    print("This downloads ~100-150MB and may take a minute or two.\n")

    sys.argv = ["playwright", "install", "chromium"]
    try:
        playwright_main()
        print("\nDone! You can now run AmazonBuyBoxChecker.exe normally.")
    except SystemExit as e:
        if e.code in (0, None):
            print("\nDone! You can now run AmazonBuyBoxChecker.exe normally.")
        else:
            print(f"\nInstall failed (exit code {e.code}). Check your internet "
                  f"connection and try running this again.")
    except Exception as e:
        print(f"\nSomething went wrong: {e}")
        print("Try running this again, or check your internet connection.")

    input("\nPress Enter to close this window...")


if __name__ == "__main__":
    main()
