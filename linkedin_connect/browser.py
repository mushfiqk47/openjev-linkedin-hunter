from __future__ import annotations

import random
import time
import urllib.parse
from pathlib import Path
from typing import Any

try:
    from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
except ImportError:
    BrowserContext = Page = Playwright = sync_playwright = None  # type: ignore

from .config import BASE_DIR, CHROME_CDP_URL, CONNECT_DELAY, SCROLL_DELAY

def find_active_devtools_ws_candidates() -> list[str]:
    candidate_paths = [
        Path.home() / ".config/google-chrome/DevToolsActivePort",
        Path.home() / ".config/chromium/DevToolsActivePort",
    ]
    urls = []
    for p in candidate_paths:
        if p.exists():
            try:
                lines = p.read_text().splitlines()
                if len(lines) >= 2:
                    port = lines[0].strip()
                    ws_path = lines[1].strip()
                    urls.append(f"ws://127.0.0.1:{port}{ws_path}")
            except Exception:
                continue
    return urls

def build_people_search_url(keywords: str, page: int = 1) -> str:
    params = {
        "network": '["S"]',
        "keywords": keywords,
    }
    if page > 1:
        params["page"] = str(page)
    return f"https://www.linkedin.com/search/results/people/?{urllib.parse.urlencode(params)}"

class ConnectBrowser:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright: Playwright | None = None
        self.browser = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.is_cdp = False

    def start(self):
        if sync_playwright is None:
            raise RuntimeError("Playwright is not installed in the active environment.")

        self.playwright = sync_playwright().start()

        for ws_url in find_active_devtools_ws_candidates():
            try:
                print(f"[*] Connecting to Chrome DevTools at {ws_url}...")
                browser = self.playwright.chromium.connect_over_cdp(ws_url, timeout=12000)
                self.browser = browser
                self.context = browser.contexts[0]
                self.is_cdp = True
                self.page = self.context.new_page()
                print("  [✓] Connected directly to active Chrome browser via DevTools WebSocket!")
                return
            except Exception as e:
                print(f"  [!] Could not connect via {ws_url}: {e}")

        try:
            print(f"[*] Trying to connect to existing Chrome at {CHROME_CDP_URL}...")
            browser = self.playwright.chromium.connect_over_cdp(CHROME_CDP_URL, timeout=12000)
            self.browser = browser
            self.context = browser.contexts[0]
            self.is_cdp = True
            self.page = self.context.new_page()
            print("  [✓] Connected to active Chrome browser via CDP!")
            return
        except Exception:
            print("  [!] Active Chrome CDP not found. Launching persistent browser session...")

        user_data_dir = BASE_DIR / ".chrome_profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ]

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.headless,
            args=args,
            viewport=None,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        print("  [✓] Persistent Chrome browser session launched successfully.")

    def close(self):
        try:
            if self.page and self.is_cdp:
                self.page.close()
        except Exception:
            pass
        try:
            if self.browser:
                self.browser.close()
            elif self.context and not self.is_cdp:
                self.context.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass

    def navigate_search(self, query: str, page: int = 1) -> list[dict[str, Any]]:
        url = build_people_search_url(query, page)
        print(f"  [i] Navigating to People Search: {query} (Page {page})...")
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception as e:
            print(f"  [!] Navigation warning: {e}")

        time.sleep(1.5)

        for _ in range(3):
            self.page.evaluate("window.scrollBy(0, 800)")
            if SCROLL_DELAY > 0:
                time.sleep(SCROLL_DELAY)

        cards = self.page.evaluate(r'''() => {
            const results = [];
            const containers = document.querySelectorAll('li.reusable-search__result-container, div.entity-result');

            containers.forEach((container, idx) => {
                const titleAnchor = container.querySelector('a.app-aware-link[href*="/in/"]');
                if (!titleAnchor) return;

                let href = (titleAnchor.getAttribute('href') || '').split('?')[0];
                if (!href.includes('/in/') || href.endsWith('/in/')) return;

                let name = '';
                const nameSpan = titleAnchor.querySelector('span[aria-hidden="true"]');
                if (nameSpan) {
                    name = nameSpan.innerText.trim();
                } else {
                    name = (titleAnchor.innerText || '').split('\n')[0].trim();
                }
                name = name.replace(/•.*$/, '').trim();

                const subEl = container.querySelector('.entity-result__primary-subtitle');
                const headline = subEl ? (subEl.innerText || '').trim() : '';

                const locEl = container.querySelector('.entity-result__secondary-subtitle');
                const location = locEl ? (locEl.innerText || '').trim() : '';

                let buttonType = 'unknown';
                const buttons = Array.from(container.querySelectorAll('button'));
                let connectBtnIndex = -1;

                buttons.forEach((btn, bIdx) => {
                    const text = (btn.innerText || '').toLowerCase();
                    const aria = (btn.getAttribute('aria-label') || '').toLowerCase();

                    if (aria.includes('invite') || text.includes('connect')) {
                        buttonType = 'connect';
                        connectBtnIndex = bIdx;
                    } else if (text.includes('pending') || aria.includes('pending')) {
                        if (buttonType !== 'connect') buttonType = 'pending';
                    } else if (text.includes('message') || aria.includes('message')) {
                        if (buttonType !== 'connect' && buttonType !== 'pending') buttonType = 'message';
                    } else if (text.includes('follow') || aria.includes('follow')) {
                        if (buttonType === 'unknown') buttonType = 'follow';
                    }
                });

                results.push({
                    index: idx,
                    name: name,
                    headline: headline,
                    location: location,
                    profile_url: href,
                    button_type: buttonType,
                    connect_btn_idx: connectBtnIndex
                });
            });

            return results;
        }''')

        return cards or []

    def send_connection_request(self, card_index: int, name: str) -> tuple[bool, str]:
        print(f"  [Dispatch] Clicking 'Connect' for {name} (Card #{card_index})...")

        click_success = self.page.evaluate(r'''(cardIdx) => {
            const containers = document.querySelectorAll('li.reusable-search__result-container, div.entity-result');
            if (cardIdx >= containers.length) return false;
            const container = containers[cardIdx];

            const buttons = Array.from(container.querySelectorAll('button'));
            for (let btn of buttons) {
                const text = (btn.innerText || '').toLowerCase();
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                if (aria.includes('invite') || text.includes('connect')) {
                    btn.click();
                    return true;
                }
            }

            const moreBtn = container.querySelector('button[aria-label*="More"], button.artdeco-dropdown__trigger');
            if (moreBtn) {
                moreBtn.click();
                return 'more_clicked';
            }
            return false;
        }''', card_index)

        if not click_success:
            return False, "Connect button not found on card"

        if click_success == "more_clicked":
            time.sleep(0.6)
            dropdown_clicked = self.page.evaluate(r'''() => {
                const items = document.querySelectorAll('div.artdeco-dropdown__content span, div.artdeco-dropdown__content div');
                for (let it of items) {
                    if ((it.innerText || '').toLowerCase().includes('connect')) {
                        it.click();
                        return true;
                    }
                }
                return false;
            }''')
            if not dropdown_clicked:
                return False, "Connect option not found in More dropdown"

        time.sleep(1.2)

        modal_res = self.page.evaluate(r'''() => {
            const bodyText = document.body.innerText || '';
            if (bodyText.includes("You've reached the weekly invitation limit") ||
                bodyText.includes("reached your weekly invitation limit")) {
                const dismiss = document.querySelector('button[aria-label="Dismiss"], button[data-test-modal-close-btn]');
                if (dismiss) dismiss.click();
                return 'weekly_limit';
            }

            const modal = document.querySelector('div.artdeco-modal[role="dialog"], div[data-test-modal]');
            if (!modal) {
                return 'no_modal';
            }

            const mText = (modal.innerText || '').toLowerCase();
            if (mText.includes('enter their email') || mText.includes('know this member')) {
                const dismiss = modal.querySelector('button[aria-label="Dismiss"], button[data-test-modal-close-btn]');
                if (dismiss) dismiss.click();
                return 'email_required';
            }

            const buttons = Array.from(modal.querySelectorAll('button'));
            for (let btn of buttons) {
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const text = (btn.innerText || '').toLowerCase();

                if (aria.includes('send without a note') || text.includes('send without a note')) {
                    btn.click();
                    return 'sent_without_note';
                }
            }

            for (let btn of buttons) {
                const aria = (btn.getAttribute('aria-label') || '').toLowerCase();
                const text = (btn.innerText || '').toLowerCase();
                if ((text === 'send' || aria === 'send') && !btn.disabled) {
                    btn.click();
                    return 'sent_direct';
                }
            }

            return 'modal_unknown_buttons';
        }''')

        if modal_res == "weekly_limit":
            return False, "Weekly invitation limit reached"
        elif modal_res == "email_required":
            return False, "Email required by recipient"
        elif modal_res in ("sent_without_note", "sent_direct", "no_modal"):
            time.sleep(CONNECT_DELAY)
            return True, "Invitation sent successfully (blank connection request)"
        else:
            return False, f"Modal handling: {modal_res}"
