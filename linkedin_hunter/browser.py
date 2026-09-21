import random
import re
import time
import urllib.parse
try:
    from playwright.sync_api import Playwright, BrowserContext, Page, sync_playwright
except ImportError:
    Playwright = BrowserContext = Page = sync_playwright = None  # type: ignore
from .config import (
    CHROME_CDP_URL, BASE_DIR, RECENCY_FILTERS, WORK_TYPES,
    ENABLE_HUMAN_DELAYS, HUMAN_DELAY_MIN, HUMAN_DELAY_MAX,
    CARD_CLICK_DELAY_MIN, CARD_CLICK_DELAY_MAX, MAX_FEED_SCROLLS,
    SCROLL_DELAY,
)
from .storage import is_job_seen, record_skip_reason, save_seen_job, jd_hash

def human_pause(lo: float = HUMAN_DELAY_MIN, hi: float = HUMAN_DELAY_MAX):

    if not ENABLE_HUMAN_DELAYS:
        return
    delay = random.uniform(lo, hi)
    if delay > 0:
        time.sleep(delay)

def build_search_url(
    keywords: str,
    location: str = "",
    recency: str = "week",
    work_type: str = "all",
    easy_apply: bool = False,
    sort_by_recent: bool = True,
) -> str:

    params = {
        "keywords": keywords,
        "origin": "JOB_SEARCH_PAGE_SEARCH_BUTTON",
    }
    if location and location.lower() not in ("worldwide", "any", "all", ""):
        params["location"] = location

    tpr = RECENCY_FILTERS.get((recency or "").lower(), "")
    if tpr:
        params["f_TPR"] = tpr

    if work_type and work_type.lower() not in ("all", "any", "none", ""):
        wt = WORK_TYPES.get(work_type.lower(), "")
        if wt:
            params["f_WT"] = wt

    if easy_apply:
        params["f_AL"] = "true"
    if sort_by_recent:
        params["sortBy"] = "DD"

    query_str = urllib.parse.urlencode(params)
    return f"https://www.linkedin.com/jobs/search/?{query_str}"

def find_active_devtools_ws_candidates() -> list[str]:
    from pathlib import Path
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

class LinkedInBrowser:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.playwright: Playwright | None = None
        self.browser = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.is_cdp = False

    def start(self):
        if sync_playwright is None:
            raise RuntimeError("Playwright is not installed in the active environment. Please activate the virtualenv.")
        self.playwright = sync_playwright().start()

        for ws_url in find_active_devtools_ws_candidates():
            try:
                print(f"[*] Connecting to Chrome DevTools at {ws_url}...")
                browser = self.playwright.chromium.connect_over_cdp(ws_url, timeout=12000)
                self.browser = browser
                self.context = browser.contexts[0]
                self.is_cdp = True
                self.page = self.context.new_page()
                print("  [✓] Connected directly to your active Chrome browser via DevTools WebSocket!")
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
            print("  [✓] Connected to your active Chrome browser via CDP!")
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
            channel="chrome",
            args=args,
            viewport=None,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        print(f"  [✓] Persistent browser launched using profile: {user_data_dir}")

    def close(self):
        if self.page and self.is_cdp:
            try:
                self.page.close()
            except Exception:
                pass
        if self.browser and self.is_cdp:
            try:
                self.browser.close()
            except Exception:
                pass
        elif self.context and not self.is_cdp:
            try:
                self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass

    def check_login(self):

        self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
        human_pause(1.5, 2.5)
        if "login" in self.page.url or "signup" in self.page.url or "authwall" in self.page.url:
            print("\n" + "=" * 60)
            print("⚠️  ACTION REQUIRED: LinkedIn login detected.")
            print("Please log in on the opened browser window.")
            print("The agent will wait until you are logged in...")
            print("=" * 60 + "\n")
            while True:
                time.sleep(3)
                current = self.page.url
                if "feed" in current or "jobs" in current or "mynetwork" in current:
                    print("  [✓] Login detected! Proceeding...\n")
                    break

    def view_profile(self, profile_url: str, label: str = "") -> dict:

        try:
            profile_tab = self.context.new_page()
            profile_tab.goto(profile_url, wait_until="domcontentloaded", timeout=20000)
            human_pause(1.8, 2.8)
            try:
                profile_tab.wait_for_selector(".text-body-medium, h1", timeout=5000)
            except Exception:
                pass
            title = profile_tab.title()
            headline_el = profile_tab.query_selector(".text-body-medium, [data-generated-suggestion-target]")
            headline = headline_el.inner_text().strip() if headline_el else ""
            print(f"    [👁] Viewed profile {label}: '{headline or title}'")
            profile_tab.close()
            return {"title": title, "headline": headline, "url": profile_url}
        except Exception as e:
            try:
                profile_tab.close()
            except Exception:
                pass
            return {"url": profile_url}

    def scroll_and_scan_feed(self, max_scrolls: int = 4) -> list[dict]:

        leads = []
        print("\n[*] Navigating to LinkedIn Feed to scan for hiring opportunities...")
        feed_loaded = False
        for url in ("https://www.linkedin.com/feed/", "https://www.linkedin.com/"):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if "chrome-error://" not in self.page.url:
                    human_pause(0.5, 3.0)
                    feed_loaded = True
                    break
            except Exception:
                pass

        if not feed_loaded:
            print("  [!] LinkedIn feed rate-limited or unavailable.")
            return leads

        if "login" in self.page.url or "authwall" in self.page.url:
            self.check_login()

        keywords = ["hiring", "designer", "ui/ux", "product designer", "figma", "looking for"]
        for s in range(max_scrolls):
            print(f"  [Feed] Scrolling feed (step {s + 1}/{max_scrolls})...")
            self.page.evaluate("window.scrollBy(0, 900)")
            if SCROLL_DELAY > 0:
                time.sleep(SCROLL_DELAY)
            if ENABLE_HUMAN_DELAYS:
                time.sleep(random.uniform(1.8, 2.5))

            text_blocks = self.page.query_selector_all("main span, main p, div[data-id]")
            for block in text_blocks:
                txt = (block.inner_text() or "").strip()
                if len(txt) > 50 and any(k in txt.lower() for k in keywords):
                    prefix = txt[:120]
                    if not any(l["text"].startswith(prefix) for l in leads):
                        leads.append({
                            "type": "feed_post",
                            "text": txt[:250] + "...",
                            "scanned_at": time.strftime("%H:%M:%S"),
                        })
                        print(f"    [★ Feed Lead] {txt[:100]}...")
                        if len(leads) >= 5:
                            break
            if len(leads) >= 5:
                break
        return leads

    def search_jobs(
        self,
        keywords: str,
        location: str = "",
        recency: str = "week",
        work_type: str = "all",
        limit: int = 50,
        max_pages: int = 5,
        seen_state: dict | None = None,
        save_on_linkedin: bool = False,
        view_profiles: bool = True,
        stop_check=None,
        easy_apply: bool = False,
    ):

        if seen_state is None:
            from .storage import load_seen_state
            seen_state = load_seen_state()

        search_url = build_search_url(keywords, location, recency, work_type, easy_apply=easy_apply)
        print(f"\n[*] Navigating to search: {search_url}")
        self.page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
        try:

            self.page.wait_for_selector("ul.jobs-search-results-list, div.job-card-container", timeout=12000)
        except Exception:
            pass
        human_pause(2.0, 3.0)

        if "login" in self.page.url or "authwall" in self.page.url:
            self.check_login()
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            human_pause(0.5, 3.0)

        processed_count = 0
        current_page = 1
        card_selector = "div.job-card-container, li.jobs-search-results__list-item, div[data-job-id]"

        while current_page <= max_pages and processed_count < limit:
            if stop_check and stop_check():
                print("[⏹] Stop signal received. Halting search.")
                break
            print(f"\n[📄] Processing Search Page {current_page}/{max_pages} for '{keywords}'...")

            for _ in range(4):
                if stop_check and stop_check():
                    break
                self.page.evaluate(
                    """() => {
                        const list = document.querySelector('.jobs-search-results-list') || document.querySelector('.scaffold-layout__list-detail-inner');
                        if (list) list.scrollTop += 800 + Math.floor(Math.random()*400);
                        else window.scrollBy(0, 800 + Math.floor(Math.random()*400));
                    }"""
                )
                if SCROLL_DELAY > 0:
                    time.sleep(SCROLL_DELAY)
                human_pause(1.2, 2.0)

            snapshots = self.page.evaluate("""() => {
                const cards = [...document.querySelectorAll('div.job-card-container, li.jobs-search-results__list-item, div[data-job-id]')];
                return cards.slice(0, 25).map(c => {
                    const link = c.querySelector("a[href*='/jobs/view/']");
                    const href = link ? (link.getAttribute('href')||'') : '';
                    const m = href.match(/\\/jobs\\/view\\/(\\d+)/);
                    const titleEl = c.querySelector('.job-card-list__title, strong, a.job-card-container__link');
                    const compEl = c.querySelector('.job-card-container__primary-description, .artdeco-entity-lockup__subtitle');
                    const locEl = c.querySelector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption');
                    const meta = (c.innerText||'').slice(0, 400);
                    return {
                        job_id: c.getAttribute('data-job-id') || (m ? m[1] : ''),
                        title: titleEl ? titleEl.innerText.trim().split('\\n')[0] : 'Unknown Title',
                        company: compEl ? compEl.innerText.trim().split('\\n')[0] : 'Unknown Company',
                        loc: locEl ? locEl.innerText.trim().split('\\n')[0] : '',
                        href, meta,
                    };
                });
            }""")
            print(f"  [i] Found {len(snapshots)} visible job cards on page {current_page}.")

            if not snapshots:
                print("  [!] No job cards found on this page.")
                break

            for i, snap in enumerate(snapshots):
                if stop_check and stop_check():
                    print("[⏹] Stop signal received. Halting card processing.")
                    break
                if processed_count >= limit:
                    break

                try:
                    job_id = snap.get("job_id") or ""
                    title = (snap.get("title") or "Unknown Title").replace("\n", " ").strip()
                    company = (snap.get("company") or "Unknown Company").replace("\n", " ").strip()
                    loc = snap.get("loc") or location
                    meta = snap.get("meta", "")
                    if not job_id:
                        job_id = f"job_{abs(hash(title + company))}"

                    if is_job_seen(job_id, title, company, seen_state):
                        continue

                    t_lower = title.lower()
                    from .evaluator import DISQUALIFIED_TITLES
                    if any(bad in t_lower for bad in DISQUALIFIED_TITLES):
                        print(f"  [⊘] Pre-Screen: Skipping non-design '{title}' @ '{company}'.")
                        save_seen_job(job_id, title, company, seen_state, reason="prescreen:title")
                        continue

                    job_url = f"https://www.linkedin.com/jobs/view/{job_id}/" if job_id.isdigit() else self.page.url

                    try:
                        if job_id.isdigit():
                            sel = f"div.job-card-container[data-job-id='{job_id}'], a[href*='/jobs/view/{job_id}']"
                            el = self.page.query_selector(sel)
                            if el:
                                el.scroll_into_view_if_needed()
                                el.click()
                            else:

                                self.page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
                        else:
                            els = self.page.query_selector_all("div.job-card-container, li.jobs-search-results__list-item")
                            if i < len(els):
                                els[i].scroll_into_view_if_needed()
                                els[i].click()
                    except Exception:
                        pass
                    human_pause(CARD_CLICK_DELAY_MIN, CARD_CLICK_DELAY_MAX)

                    try:
                        self.page.wait_for_selector("#job-details, .jobs-description__content", timeout=6000)
                    except Exception:
                        pass
                    desc_el = self.page.query_selector("#job-details, .jobs-description__content, .jobs-box__html-content")
                    description = desc_el.inner_text().strip() if desc_el else ""
                    if not description:
                        description = f"Job Title: {title}\nCompany: {company}\nLocation: {loc}"

                    if jd_hash(description) and jd_hash(description) in seen_state.get("seen_jd_hashes", set()):
                        print(f"  [⊘] JD-dedup: identical description already seen '{title}'.")
                        save_seen_job(job_id, title, company, seen_state, description=description, reason="dedup:jd-hash")
                        continue

                    comp_link = self.page.query_selector(".job-details-jobs-unified-top-card__company-name a, a[href*='/company/']")
                    company_url = comp_link.get_attribute("href") if comp_link else ""
                    if company_url and not company_url.startswith("http"):
                        company_url = f"https://www.linkedin.com{company_url}"

                    detail_text = ""
                    try:
                        detail_text = self.page.query_selector(
                            ".job-details-jobs-unified-top-card, .jobs-unified-top-card"
                        ).inner_text() if self.page.query_selector(".job-details-jobs-unified-top-card, .jobs-unified-top-card") else meta
                    except Exception:
                        detail_text = meta
                    easy_apply_flag = bool(re.search(r"easy apply", (detail_text or ""), re.IGNORECASE))
                    posted_hint = ""
                    m_post = re.search(r"(\d+\s+(?:hour|day|week|month)s?\s+ago|just now|today|yesterday|reposted.+)", detail_text or "", re.IGNORECASE)
                    if m_post:
                        posted_hint = m_post.group(1).strip()
                    applicants = ""
                    m_app = re.search(r"(\d+[\d,]*\s+applicants?|over\s+\d+\s+applicants?)", detail_text or "", re.IGNORECASE)
                    if m_app:
                        applicants = m_app.group(1).strip()

                    recruiter_name = ""
                    recruiter_url = ""
                    hirer_card = self.page.query_selector(".hirer-card, .jobs-poster, [data-view-name*='job-poster'], .jobs-hiring-team")
                    if hirer_card:
                        rec_link = hirer_card.query_selector("a[href*='/in/']")
                        if rec_link:
                            recruiter_name = rec_link.inner_text().strip().split("\n")[0]
                            recruiter_url = rec_link.get_attribute("href") or ""
                            if recruiter_url and not recruiter_url.startswith("http"):
                                recruiter_url = f"https://www.linkedin.com{recruiter_url}"
                            print(f"    [👤] Found Hiring Lead: {recruiter_name} ({recruiter_url})")

                    if view_profiles and recruiter_url:
                        self.view_profile(recruiter_url, label=f"Recruiter: {recruiter_name}")

                    if save_on_linkedin:
                        try:
                            save_btn = self.page.query_selector("button.jobs-save-button")
                            if save_btn and "saved" not in (save_btn.inner_text() or "").lower():
                                save_btn.click()
                                print(f"    [+] Saved job '{title}' to LinkedIn Saved Jobs!")
                        except Exception:
                            pass

                    save_seen_job(job_id, title, company, seen_state, description=description)

                    processed_count += 1
                    yield {
                        "job_id": job_id,
                        "title": title,
                        "company": company,
                        "location": loc,
                        "job_url": job_url,
                        "description": description,
                        "company_url": company_url,
                        "recruiter_name": recruiter_name,
                        "recruiter_url": recruiter_url,
                        "easy_apply": easy_apply_flag,
                        "posted_hint": posted_hint,
                        "applicants": applicants,
                    }

                    human_pause(HUMAN_DELAY_MIN, HUMAN_DELAY_MAX)

                except Exception as e:
                    print(f"    [!] Error reading card {i}: {e}")
                    continue

            if current_page >= max_pages or processed_count >= limit:
                break

            current_page += 1
            print(f"[*] Navigating to page {current_page}...")

            navigated = False

            try:
                next_btn = self.page.query_selector('button[aria-label="View next page"], button[aria-label="Next"], button.jobs-search-pagination__button--next')
                if next_btn and not next_btn.get_attribute("disabled"):
                    next_btn.scroll_into_view_if_needed()
                    next_btn.click()
                    navigated = True
            except Exception:
                pass

            if not navigated:
                try:
                    p_btn = self.page.query_selector(f'button[aria-label="Page {current_page}"]')
                    if p_btn:
                        p_btn.scroll_into_view_if_needed()
                        p_btn.click()
                        navigated = True
                except Exception:
                    pass

            if not navigated:
                start_offset = (current_page - 1) * 25
                next_page_url = f"{search_url}&start={start_offset}"
                print(f"[*] Fallback: Direct pagination URL: {next_page_url}")
                self.page.goto(next_page_url, wait_until="domcontentloaded", timeout=45000)
                navigated = True

            human_pause(2.5, 4.0)

    def browse_feed_and_find_matches(
        self,
        evaluator,
        store,
        seen_state: dict,
        target_matches: int = 10,
        current_matched: int = 0,
        max_scrolls: int = MAX_FEED_SCROLLS,
        view_profiles: bool = True,
        criteria: list[str] | None = None,
        on_status_update=None,
        stop_check=None,
        exhaustive: bool = False,
    ) -> int:

        print("\n" + "=" * 65)
        print(f"📰 Navigating to LinkedIn News Feed to scan posts for hiring leads...")
        print(f"   🎯 Goal: Find at least {target_matches} matching opportunities (Current: {current_matched})")
        print("=" * 65)
        if on_status_update:
            on_status_update(f"Navigating to LinkedIn News Feed (Need {target_matches - current_matched} more matches)...")

        feed_loaded = False
        for url in ("https://www.linkedin.com/feed/", "https://www.linkedin.com/"):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=35000)
                if "chrome-error://" not in self.page.url:
                    human_pause(2.5, 3.5)
                    feed_loaded = True
                    break
            except Exception as e:
                print(f"  [!] Feed navigation to {url} failed: {e}")

        if not feed_loaded:
            print("  [!] LinkedIn feed returned rate limit or error (HTTP 429). Skipping feed scan.")
            if on_status_update:
                on_status_update("LinkedIn feed rate-limited. Skipping feed scan.")
            return current_matched

        if "login" in self.page.url or "authwall" in self.page.url:
            self.check_login()

        matched_count = current_matched
        consecutive_idle_scrolls = 0

        def target_reached() -> bool:
            return (not exhaustive) and matched_count >= target_matches

        for scroll_idx in range(max_scrolls):
            if stop_check and stop_check():
                print("[⏹] Stop signal received. Halting feed search.")
                break
            if target_reached():
                print(f"\n🎯 Target goal reached! Found {matched_count}/{target_matches} matches.")
                break

            print(f"\n[Feed Scroll {scroll_idx + 1}/{max_scrolls}] Scanning feed posts... (Matches: {matched_count}/{target_matches})")
            if on_status_update:
                on_status_update(f"Scanning LinkedIn feed (Scroll {scroll_idx + 1}/{max_scrolls}) · Matches: {matched_count}/{target_matches}")

            try:
                self.page.evaluate(r'''() => {
                    const buttons = Array.from(document.querySelectorAll("button"));
                    for (const btn of buttons) {
                        const text = (btn.innerText || "").trim().toLowerCase();
                        if (text === "… more" || text === "...more" || text === "see more" || (text.includes("more") && text.length < 10) || btn.classList.contains("feed-shared-inline-show-more-text__button")) {
                            try { btn.click(); } catch(e){}
                        }
                    }
                }''')
                human_pause(0, 0.4)
            except Exception:
                pass

            posts_data = self.page.evaluate(r'''() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
                const results = [];
                const seenContainers = new Set();
                let node;
                while (node = walker.nextNode()) {
                    const isFeedNode = node.getAttribute('aria-label') === 'Feed post' || 
                                       (node.tagName === 'H2' && node.innerText.trim() === 'Feed post') ||
                                       (node.tagName === 'DIV' && node.classList.contains('feed-shared-update-v2')) ||
                                       (node.tagName === 'DIV' && (node.getAttribute('data-urn') || '').includes('activity')) ||
                                       (node.tagName === 'DIV' && (node.getAttribute('data-id') || '').includes('activity'));
                    if (isFeedNode) {
                        const container = node.closest('div[data-id], div.feed-shared-update-v2, div[data-urn], div.relative') || node.parentElement || node;
                        if (container && !seenContainers.has(container)) {
                            seenContainers.add(container);
                            const authorLinks = container.querySelectorAll('a[href*="/in/"], a[href*="/company/"]');
                            let authorName = '';
                            let authorUrl = '';
                            for (const a of authorLinks) {
                                const t = (a.innerText || '').trim().split('\n')[0];
                                if (t && !authorName) {
                                    authorName = t;
                                }
                                if (a.href && !authorUrl) {
                                    authorUrl = a.href;
                                }
                            }
                            if (!authorName && authorUrl) {
                                const m = authorUrl.match(/\/in\/([^/?]+)/);
                                if (m) authorName = m[1].replace(/-/g, ' ');
                            }
                            if (!authorName) authorName = 'LinkedIn Member';
                            const text = container.innerText || '';
                            results.push({
                                author: authorName,
                                author_url: authorUrl,
                                text: text.slice(0, 3000),
                            });
                        }
                    }
                }
                return results;
            }''')

            new_unseen_in_batch = 0

            for p_idx, post in enumerate(posts_data):
                if stop_check and stop_check():
                    print("[⏹] Stop signal received. Halting feed post processing.")
                    break
                if target_reached():
                    break

                text = post.get("text", "").strip()
                author = post.get("author", "LinkedIn Member")
                author_url = post.get("author_url", "")

                if len(text) < 35:
                    continue

                sig = f"feed @@ {author.lower()} @@ {text[:70].lower()}"
                if sig in seen_state["seen_signatures"]:
                    continue
                seen_state["seen_signatures"].add(sig)
                new_unseen_in_batch += 1

                hiring_keywords = [
                    "hiring", "looking for", "join our team", "join us", "we're hiring", "were hiring",
                    "open role", "open position", "opening", "openings", "opportunity", "opportunities",
                    "vacancy", "vacancies", "intern", "internship", "contract", "freelance",
                    "apply", "dm me", "send cv", "send resume", "reach out", "collaborate",
                    "designer", "ui/ux", "product design", "figma", "visual design", "web design", "ux/ui",
                    "user experience", "interface design"
                ]
                t_lower = text.lower()
                if not any(k in t_lower for k in hiring_keywords):
                    continue

                print(f"\n  [Post] Evaluating feed lead by {author}...")
                if on_status_update:
                    on_status_update(f"Evaluating feed post by {author} ({matched_count}/{target_matches} matches)...")

                eval_res = evaluator.evaluate_feed_post(
                    author=author,
                    post_text=text,
                    criteria=criteria,
                )

                score = eval_res["match_score"]
                fit = eval_res["fit_level"]
                reason = eval_res["reason"]

                badge = "🟢" if score >= 80 else ("🟡" if score >= 75 else "⚪")
                print(f"    {badge} Feed Fit: {score}% ({fit}) - {author}")
                print(f"    ↳ {reason}")

                from .config import FEED_MIN_SCORE
                if score >= FEED_MIN_SCORE:
                    matched_count += 1
                    job_record = {
                        "job_id": f"feed_{abs(hash(sig))}",
                        "title": f"Design Hiring Opportunity (Post by {author})",
                        "company": author,
                        "location": "LinkedIn Feed / Network",
                        "job_url": author_url or "https://www.linkedin.com/feed/",
                        "description": text,
                        "company_url": author_url if "/company/" in author_url else "",
                        "recruiter_name": author if "/in/" in author_url else "",
                        "recruiter_url": author_url if "/in/" in author_url else "",
                        **eval_res,
                    }
                    store.save_job(job_record)
                    print(f"    [★ MATCH {matched_count}/{target_matches}] Saved feed opportunity by {author}!")
                    if on_status_update:
                        on_status_update(f"★ Match {matched_count}/{target_matches}: Opportunity by {author} ({score}%)")

                    if view_profiles and author_url:
                        self.view_profile(author_url, label=f"Post Author: {author}")

                    if target_reached():
                        print(f"\n🎯 Target reached via feed posts! ({matched_count} matches)")
                        break
                else:
                    reason = eval_res.get("skip_reason") or "Below feed threshold."
                    record_skip_reason(f"feed_{abs(hash(sig))}", reason, seen_state)
                    print(f"    [·] Not saved ({score}%) \u2014 {reason}")

            if target_reached():
                break

            if new_unseen_in_batch == 0:
                consecutive_idle_scrolls += 1
                if consecutive_idle_scrolls >= 25:
                    print("  [i] Reached end of dynamic feed updates. Halting feed scan.")
                    break
            else:
                consecutive_idle_scrolls = 0

            try:
                self.page.evaluate(r'''() => {
                    const dy = 1000 + Math.floor(Math.random()*500);
                    window.scrollBy(0, dy);
                    if (document.documentElement) document.documentElement.scrollTop += dy;
                    if (document.body) document.body.scrollTop += dy;
                    const main = document.querySelector("main#workspace") || document.querySelector("main") || document.querySelector(".scaffold-layout__main");
                    if (main && main.scrollHeight > main.clientHeight) {
                        main.scrollTop += dy;
                    }
                }''')
                self.page.keyboard.press("PageDown")
            except Exception:
                pass
            if SCROLL_DELAY > 0:
                time.sleep(SCROLL_DELAY)
            human_pause(2.4, 3.8)

        return matched_count
