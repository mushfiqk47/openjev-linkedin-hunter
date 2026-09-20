"""Unified Assistant CLI for Autonomous LinkedIn Job Hunting & Browser Automation."""

import sys
from linkedin_hunter.storage import JobStore
from linkedin_hunter.hunter import main as run_hunter
from linkedin_hunter.login import main as run_login
from linkedin_hunter.web import main as run_web


def show_banner():
    print("""
===============================================================
       🎯 Mushfiq's Autonomous LinkedIn Job Hunter Agent
===============================================================
  1. 🔍 Hunt LinkedIn Jobs (Search + Feed Fallback)
  2. 📰 Scan LinkedIn Feed Directly (Hiring Posts)
  3. 📄 View Matched Jobs Report (.md)
  4. 🔑 Login to LinkedIn (Save Browser Session)
  5. 🌐 Launch Live Web Dashboard (http://127.0.0.1:8085)
  6. 🧠 Triage Matched Jobs (next actions + recruiter openers)
  7. 💬 Run LinkedIn Network Outreach (Autonomous SemIf DM Agent)
  0. 🚪 Exit
===============================================================
""")


def handle_linkedin_search(params: dict):
    query = params.get("query", "UI/UX Designer")
    location = params.get("location", "")
    recency = params.get("recency", "week")
    work_type = params.get("work_type", "all")
    target_matches = str(params.get("target_matches", 10))

    sys.argv = [
        "hunter.py",
        "-q", query,
        "-l", location,
        "-r", recency,
        "-w", work_type,
        "-n", target_matches,
    ]
    run_hunter()


def handle_feed_scan(params: dict):
    target_matches = str(params.get("target_matches", 10))
    sys.argv = [
        "hunter.py",
        "--feed-only",
        "-n", target_matches,
    ]
    run_hunter()


def handle_triage():
    from linkedin_hunter.triage import main as run_triage
    run_triage()


def handle_view_report():
    store = JobStore()
    md_file = store.md_file
    if not md_file.exists():
        print(f"[!] No report found at {md_file}. Run a job search first!")
        return
    print(f"\n[📄] Displaying: {md_file}\n" + "-" * 60)
    print(md_file.read_text(encoding="utf-8"))
    print("-" * 60 + "\n")


def handle_outreach():
    from pathlib import Path
    import subprocess
    sms_dir = Path(__file__).resolve().parent.parent / "linkedin_connections_SMS"
    agent_py = sms_dir / "agent.py"
    
    print("\n--- 💬 LinkedIn Network Outreach Agent ---")
    mode = input("Run mode: [1] Live Send  [2] Dry-Run Simulation (safe preview) [default: 2]: ").strip() or "2"
    dry_run = mode != "1"
    limit = input("Daily send limit override (Press Enter for default): ").strip()
    
    cmd = [sys.executable, str(agent_py)]
    if dry_run:
        cmd.append("--dry-run")
    if limit:
        cmd.extend(["--limit", limit])
        
    subprocess.run(cmd, cwd=str(sms_dir))


def main():
    while True:
        try:
            show_banner()
            choice = input("Select an option (0-7): ").strip()

            if choice == "1":
                q = input("Job Title [default: 'UI/UX Designer']: ").strip() or "UI/UX Designer"
                r = input("Recency (24h / week) [default: 'week']: ").strip() or "week"
                w = input("Work Type (all / remote / on_site / hybrid) [default: 'all']: ").strip() or "all"
                n = input("Target Minimum Matches [default: 10]: ").strip() or "10"
                handle_linkedin_search({"query": q, "recency": r, "work_type": w, "target_matches": n})
            elif choice == "2":
                n = input("Target Feed Matches [default: 10]: ").strip() or "10"
                handle_feed_scan({"target_matches": n})
            elif choice == "3":
                handle_view_report()
            elif choice == "4":
                run_login()
            elif choice == "5":
                run_web()
            elif choice == "6":
                handle_triage()
            elif choice == "7":
                handle_outreach()
            elif choice == "0":
                print("\nGoodbye! 👋\n")
                break
            else:
                print("[!] Invalid option. Please choose 0 to 7.")
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye! 👋\n")
            break


if __name__ == "__main__":
    main()
