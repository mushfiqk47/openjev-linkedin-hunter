import time
from playwright.sync_api import sync_playwright
from .config import BASE_DIR

def main():
    user_data_dir = BASE_DIR / ".chrome_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🔑 LinkedIn One-Time Session Login Helper")
    print("=" * 60)
    print("1. A browser window will open at LinkedIn's login page.")
    print("2. Log in with your LinkedIn account.")
    print("3. Once your feed loads, your session will be saved automatically.")
    print("=" * 60)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=False,
            channel="chrome",
            args=["--start-maximized"],
            viewport=None,
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        print("\n[*] Waiting for login...")
        while True:
            time.sleep(2)
            url = page.url
            if "feed" in url or "mynetwork" in url or "jobs" in url:
                print("\n[✓] Login detected successfully!")
                print(f"[✓] Session cookies saved to: {user_data_dir}")
                print("[✓] You can now run the Job Hunter anytime without logging in again!\n")
                time.sleep(2)
                break

        ctx.close()

if __name__ == "__main__":
    main()
