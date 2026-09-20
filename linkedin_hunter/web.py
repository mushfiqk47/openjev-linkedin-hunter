"""Interactive Web Dashboard & Agent Launcher for Autonomous LinkedIn Job Hunter.

Designed following the Analogue Design System:
- Pure-black canvas (#000000)
- Monochromatic palette with pure white text and refined grey hierarchy
- Negative tracking on display headings (-2.4px display)
- 18px card geometry with 26px padding rhythm
- 9999px pill geometry for interactive controls and badges
- Zero artificial drop shadows — surface contrast and hairline borders only
- Live activity terminal console with streaming execution logs and graceful stop control
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .config import DEFAULT_MIN_MATCHES
from .storage import JobStore, load_seen_state
from .evaluator import JobEvaluator
from .browser import LinkedInBrowser

PORT = 8085
STORE = JobStore()
AGENT_LOCK = threading.Lock()
AGENT_STOP_FLAG = threading.Event()
AGENT_STATE = {
    "running": False,
    "agent": "none",
    "status": "Ready",
    "logs": [
        {"time": time.strftime("%H:%M:%S"), "text": "System initialized. LinkedIn Hunter Agent ready.", "level": "info"}
    ],
}


def log_agent(text: str, level: str = "info"):
    """Appends an execution event to the in-memory terminal buffer."""
    t_str = time.strftime("%H:%M:%S")
    entry = {"time": t_str, "text": text, "level": level}
    AGENT_STATE["logs"].append(entry)
    if len(AGENT_STATE["logs"]) > 250:
        AGENT_STATE["logs"].pop(0)
    print(f"[{t_str}] [{level.upper()}] {text}")


PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Analogue · LinkedIn Job Hunter Agent</title>
  <style>
    :root {
      --canvas: #000000;
      --surface-card: #0c0c0c;
      --surface-hover: #141414;
      --surface-1: #eaeaea;
      --hairline: #222222;
      --hairline-hover: #383838;
      --hairline-active: #555555;
      --ink: #ffffff;
      --ink-muted: #bfbfbf;
      --ink-faint: #737373;
      --accent-1: #aeaeae;
      --accent-2: #595959;
      --radius-card: 18px;
      --radius-pill: 9999px;
      --spacing-card: 26px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Plus Jakarta Sans", "Inter", "Geist", system-ui, sans-serif;
      background-color: var(--canvas);
      color: var(--ink);
      padding: 0;
      margin: 0;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      line-height: 1.4;
    }

    /* Top Nav */
    .top-nav {
      height: 60px;
      border-bottom: 1px solid var(--hairline);
      padding: 0 32px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--canvas);
      position: sticky;
      top: 0;
      z-index: 50;
    }

    .brand-group {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .brand-logo {
      font-size: 17px;
      font-weight: 500;
      letter-spacing: -0.5px;
      color: var(--ink);
      text-decoration: none;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .brand-mark {
      display: inline-block;
      width: 10px;
      height: 10px;
      background: var(--ink);
      border-radius: 2px;
    }

    .candidate-pill {
      font-size: 11px;
      font-weight: 500;
      letter-spacing: 0.2px;
      text-transform: uppercase;
      color: var(--ink-muted);
      border: 1px solid var(--hairline);
      padding: 4px 12px;
      border-radius: var(--radius-pill);
    }

    .nav-actions {
      display: flex;
      align-items: center;
      gap: 20px;
    }

    .nav-link {
      font-size: 13px;
      color: var(--ink-muted);
      text-decoration: none;
      transition: color 0.15s;
    }

    .nav-link:hover {
      color: var(--ink);
    }

    /* Main Container */
    .container {
      max-width: 1100px;
      margin: 0 auto;
      padding: 56px 32px 120px;
    }

    /* Hero */
    .hero {
      margin-bottom: 40px;
    }

    .hero-title {
      font-size: 46px;
      font-weight: 500;
      letter-spacing: -2.2px;
      line-height: 1.05;
      color: var(--ink);
      margin-bottom: 10px;
    }

    .hero-sub {
      font-size: 16px;
      font-weight: 400;
      color: var(--ink-muted);
      letter-spacing: -0.3px;
    }

    /* Agent Console */
    .agent-console {
      background: var(--surface-card);
      border: 1px solid var(--hairline);
      border-radius: var(--radius-card);
      padding: 28px;
      margin-bottom: 28px;
    }

    .console-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--hairline);
      padding-bottom: 16px;
      margin-bottom: 24px;
    }

    .console-title {
      font-size: 15px;
      font-weight: 500;
      letter-spacing: -0.3px;
      color: var(--ink);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .control-grid {
      display: grid;
      grid-template-columns: 2fr 1.1fr 1.1fr 110px auto;
      gap: 16px;
      align-items: end;
    }

    @media (max-width: 820px) {
      .control-grid { grid-template-columns: 1fr; }
      .hero-title { font-size: 34px; letter-spacing: -1.4px; }
    }

    .control-item {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .control-label {
      font-size: 12px;
      font-weight: 500;
      color: var(--ink-faint);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .input-pill {
      background: var(--canvas);
      border: 1px solid var(--hairline);
      color: var(--ink);
      font-family: inherit;
      font-size: 14px;
      letter-spacing: -0.2px;
      padding: 12px 18px;
      border-radius: var(--radius-pill);
      outline: none;
      transition: border-color 0.2s;
      width: 100%;
    }

    .input-pill:focus {
      border-color: var(--ink-muted);
    }

    select.input-pill {
      appearance: none;
      cursor: pointer;
      background-image: url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23bfbfbf' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3e%3cpolyline points='6 9 12 15 18 9'%3e%3c/polyline%3e%3c/svg%3e");
      background-repeat: no-repeat;
      background-position: right 16px center;
      background-size: 14px;
      padding-right: 40px;
    }

    .btn-primary {
      background: var(--ink);
      color: var(--canvas);
      font-family: inherit;
      font-size: 14px;
      font-weight: 500;
      letter-spacing: -0.2px;
      border: none;
      padding: 13px 32px;
      border-radius: var(--radius-pill);
      cursor: pointer;
      height: 45px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      transition: opacity 0.15s, transform 0.1s;
      white-space: nowrap;
    }

    .btn-primary:hover {
      opacity: 0.88;
    }

    .btn-primary:active {
      transform: scale(0.98);
    }

    .btn-primary:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    /* Terminal Activity Console */
    .terminal-card {
      background: #060606;
      border: 1px solid var(--hairline);
      border-radius: var(--radius-card);
      margin-bottom: 36px;
      overflow: hidden;
    }

    .terminal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 20px;
      background: #0c0c0c;
      border-bottom: 1px solid var(--hairline);
    }

    .terminal-stream {
      padding: 16px 20px;
      height: 145px;
      overflow-y: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      line-height: 1.6;
      color: #999999;
      display: flex;
      flex-direction: column;
      gap: 3px;
    }

    .terminal-line {
      word-break: break-all;
    }

    .terminal-line.success {
      color: #70ff94;
    }

    .terminal-line.info {
      color: #e0e0e0;
    }

    .terminal-line.warning {
      color: #ffd166;
    }

    .terminal-line.error {
      color: #ff6b6b;
    }

    .terminal-line.match {
      color: #00f0ff;
      font-weight: 500;
    }

    /* Status Bar */
    .status-section {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--hairline);
      margin-bottom: 32px;
    }

    .status-left {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      color: var(--ink-muted);
    }

    .status-indicator {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-2);
      transition: background 0.3s;
    }

    .status-indicator.active {
      background: #00ff66;
      box-shadow: 0 0 10px rgba(0, 255, 102, 0.7);
      animation: pulse 1.6s infinite ease-in-out;
    }

    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.2); }
    }

    .count-indicator {
      font-size: 13px;
      color: var(--ink-faint);
    }

    /* View Switcher & Action Bar */
    .view-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      gap: 16px;
      flex-wrap: wrap;
    }

    .view-tabs {
      display: inline-flex;
      background: #0d0d0d;
      border: 1px solid var(--hairline);
      border-radius: var(--radius-pill);
      padding: 4px;
      gap: 4px;
    }

    .view-tab {
      background: transparent;
      border: none;
      color: var(--ink-muted);
      font-family: inherit;
      font-size: 13px;
      font-weight: 500;
      padding: 7px 18px;
      border-radius: var(--radius-pill);
      cursor: pointer;
      transition: all 0.15s ease;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .view-tab:hover {
      color: var(--ink);
    }

    .view-tab.active {
      background: var(--ink);
      color: var(--canvas);
    }

    .report-actions {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .btn-action {
      background: var(--surface-card);
      border: 1px solid var(--hairline);
      color: var(--ink-muted);
      font-family: inherit;
      font-size: 12px;
      padding: 6px 14px;
      border-radius: var(--radius-pill);
      cursor: pointer;
      text-decoration: none;
      transition: all 0.15s;
      display: inline-flex;
      align-items: center;
      gap: 5px;
    }

    .btn-action:hover {
      color: var(--ink);
      border-color: var(--hairline-hover);
      background: var(--surface-hover);
    }

    /* Jobs Grid */
    .jobs-list {
      display: flex;
      flex-direction: column;
      gap: 20px;
    }

    .job-card {
      background: var(--surface-card);
      border: 1px solid var(--hairline);
      border-radius: var(--radius-card);
      padding: var(--spacing-card);
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 24px;
      transition: border-color 0.2s, background-color 0.2s;
    }

    .job-card:hover {
      border-color: var(--hairline-hover);
      background: var(--surface-hover);
    }

    .job-content {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .job-header-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .job-title {
      font-size: 22px;
      font-weight: 500;
      letter-spacing: -0.9px;
      color: var(--ink);
      text-decoration: none;
      transition: color 0.15s;
    }

    .job-title:hover {
      color: var(--ink-muted);
    }

    .job-meta {
      font-size: 14px;
      color: var(--ink-muted);
      letter-spacing: -0.2px;
    }

    .job-reason {
      font-size: 14px;
      color: #a6a6a6;
      line-height: 1.5;
      letter-spacing: -0.15px;
    }

    .skills-container {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 8px;
    }

    .skill-chip {
      font-size: 12px;
      color: var(--ink-muted);
      background: var(--canvas);
      border: 1px solid var(--hairline);
      padding: 4px 12px;
      border-radius: var(--radius-pill);
      letter-spacing: -0.1px;
    }

    /* Score Column */
    .score-column {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      justify-content: space-between;
      min-width: 140px;
    }

    .score-box {
      text-align: right;
    }

    .score-number {
      font-size: 38px;
      font-weight: 500;
      letter-spacing: -1.8px;
      line-height: 1;
      color: var(--ink);
    }

    .score-tag {
      font-size: 11px;
      font-weight: 500;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--ink-muted);
      margin-top: 4px;
    }

    .btn-apply {
      font-size: 13px;
      font-weight: 500;
      letter-spacing: -0.2px;
      color: var(--ink);
      text-decoration: none;
      border: 1px solid var(--hairline-hover);
      padding: 8px 22px;
      border-radius: var(--radius-pill);
      background: transparent;
      transition: all 0.15s;
      white-space: nowrap;
    }

    .btn-apply:hover {
      background: var(--ink);
      color: var(--canvas);
      border-color: var(--ink);
    }

    .empty-state {
      padding: 80px 20px;
      text-align: center;
      color: var(--ink-faint);
      font-size: 15px;
      letter-spacing: -0.3px;
      border: 1px dashed var(--hairline);
      border-radius: var(--radius-card);
    }

    /* Report Card & Content */
    .report-card {
      background: var(--surface-card);
      border: 1px solid var(--hairline);
      border-radius: var(--radius-card);
      padding: 38px 40px;
      line-height: 1.65;
    }

    .report-content h1 {
      font-size: 26px;
      font-weight: 500;
      letter-spacing: -1.2px;
      margin-bottom: 8px;
      color: var(--ink);
    }

    .report-content h2 {
      font-size: 19px;
      font-weight: 500;
      letter-spacing: -0.7px;
      margin: 32px 0 14px;
      color: var(--ink);
      border-bottom: 1px solid var(--hairline);
      padding-bottom: 10px;
    }

    .report-content h3 {
      font-size: 16px;
      font-weight: 500;
      letter-spacing: -0.4px;
      margin: 24px 0 10px;
      color: var(--ink);
    }

    .report-content p, .report-content li {
      font-size: 14px;
      color: #cfcfcf;
      letter-spacing: -0.15px;
    }

    .report-content ul {
      padding-left: 20px;
      margin-bottom: 16px;
    }

    .report-content li {
      margin-bottom: 6px;
    }

    .report-content a {
      color: var(--ink);
      text-decoration: underline;
      text-underline-offset: 3px;
    }

    .report-content a:hover {
      color: #888888;
    }

    .report-content table {
      width: 100%;
      border-collapse: collapse;
      margin: 22px 0;
      font-size: 13px;
      border: 1px solid var(--hairline);
      border-radius: 8px;
      overflow: hidden;
    }

    .report-content th, .report-content td {
      padding: 12px 14px;
      border: 1px solid var(--hairline);
      text-align: left;
    }

    .report-content th {
      background: #121212;
      color: var(--ink);
      font-weight: 500;
      letter-spacing: -0.2px;
    }

    .report-content tr:hover td {
      background: #141414;
    }

    .report-content code {
      background: #161616;
      border: 1px solid #282828;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 12px;
      color: #f0f0f0;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    }

    .report-raw-box {
      width: 100%;
      background: #080808;
      border: 1px solid var(--hairline);
      border-radius: var(--radius-card);
      padding: 28px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
      color: #bfbfbf;
      line-height: 1.6;
      overflow-x: auto;
      white-space: pre-wrap;
      box-sizing: border-box;
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>

  <!-- Top Navigation -->
  <nav class="top-nav">
    <div class="brand-group">
      <a href="/" class="brand-logo">
        <span class="brand-mark"></span>
        Analogue Job Hunter
      </a>
      <span class="candidate-pill">Mushfiq Kabir</span>
    </div>
    <div class="nav-actions">
      <a href="/output/jobs_report.md" target="_blank" class="nav-link">Report (.md)</a>
      <a href="/output/jobs.csv" target="_blank" class="nav-link">Export (.csv)</a>
    </div>
  </nav>

  <div class="container">
    <!-- Editorial Hero -->
    <section class="hero">
      <h1 class="hero-title">Autonomous LinkedIn Job Hunter</h1>
      <p class="hero-sub">
        Runtime decision scoring via SemIf and LM Studio. Zero hallucinations. Real-time browser automation.
      </p>
    </section>

    <!-- Agent Console Panel -->
    <div class="agent-console">
      <div class="console-header">
        <div class="console-title">
          <span>🎯</span> LinkedIn Job Hunter Agent
        </div>
        <div style="font-size: 12px; color: var(--ink-faint);">
          Automated Search · Query Rotation · Feed Fallback · Profile Inspection
        </div>
      </div>

      <!-- Agent Controls -->
      <div class="agent-panel">
        <div class="control-grid">
          <div class="control-item">
            <label class="control-label">Target Role / Keywords</label>
            <input id="hunter-q" type="text" class="input-pill" value="UI/UX Designer" placeholder="e.g. UI/UX Designer, Product Designer" />
          </div>
          <div class="control-item">
            <label class="control-label">Recency</label>
            <select id="hunter-recency" class="input-pill">
              <option value="week" selected>Past Week</option>
              <option value="24h">Past 24 Hours</option>
              <option value="any">Any Time</option>
            </select>
          </div>
          <div class="control-item">
            <label class="control-label">Work Type</label>
            <select id="hunter-work_type" class="input-pill">
              <option value="all" selected>All / Any Work Type</option>
              <option value="remote">Remote Only</option>
              <option value="on_site">On-site</option>
              <option value="hybrid">Hybrid</option>
            </select>
          </div>
          <div class="control-item">
            <label class="control-label">Min Matches</label>
            <input id="hunter-target" type="number" min="1" max="50" value="10" class="input-pill" style="text-align: center;" />
          </div>
          <div style="display: flex; gap: 8px;">
            <button id="btn-launch-hunter" class="btn-primary" onclick="launchHunterAgent(false)">
              ▶ Search Jobs
            </button>
            <button id="btn-launch-feed" class="btn-primary" style="background: #121212; border: 1px solid var(--hairline-hover); color: var(--ink);" onclick="launchHunterAgent(true)">
              📰 Scan Feed
            </button>
          </div>
        </div>

        <!-- Hunter Options -->
        <div style="display: flex; flex-wrap: wrap; gap: 24px; align-items: center; margin-top: 16px; font-size: 13px; color: var(--ink-muted);">
          <label style="display: flex; align-items: center; gap: 7px; cursor: pointer;">
            <input type="checkbox" id="hunter-autorotate" checked style="accent-color: var(--ink);" />
            Auto-rotate queries (UI/UX, Product, Figma)
          </label>
          <label style="display: flex; align-items: center; gap: 7px; cursor: pointer;">
            <input type="checkbox" id="hunter-profiles" checked style="accent-color: var(--ink);" />
            Inspect recruiter & company profiles
          </label>
          <label style="display: flex; align-items: center; gap: 7px; cursor: pointer;">
            <input type="checkbox" id="hunter-feed" checked style="accent-color: var(--ink);" />
            Fallback to LinkedIn feed if under target matches
          </label>
          <label style="display: flex; align-items: center; gap: 7px; cursor: pointer;" title="LinkedIn f_AL=true + sort by recent">
            <input type="checkbox" id="hunter-easyapply" style="accent-color: var(--ink);" />
            Easy Apply only
          </label>
        </div>

        <div style="margin-top: 20px; border-top: 1px solid var(--hairline); padding-top: 16px;">
          <label class="control-label" style="display: flex; justify-content: space-between; align-items: center;">
            <span>Candidate Alignment Criteria (SemIf Logprob Evaluation)</span>
            <span style="color: var(--ink-faint); text-transform: none; font-size: 11px;">Mushfiq Kabir CV Profile</span>
          </label>
          <textarea id="hunter-criteria" class="input-pill" rows="3" style="border-radius: 14px; margin-top: 8px; resize: vertical; line-height: 1.5; font-size: 13px; font-family: inherit;">[Required] Role focuses on UI/UX, Product Design, Visual Interface, or Figma design.
[Required] Involves hands-on Figma wireframing, prototyping, or design systems.
[Preferred] Experience with SaaS platforms, web apps, or mobile interfaces.
[Dealbreaker] Does NOT require 8+ years executive leadership or full-stack software coding.</textarea>
        </div>
      </div>
    </div>

    <!-- Live Terminal Activity Console -->
    <div class="terminal-card">
      <div class="terminal-header">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div id="terminal-dot" class="status-indicator"></div>
          <span id="terminal-agent-title" style="font-size: 13px; font-weight: 500; color: var(--ink);">Agent Console</span>
          <span id="terminal-badge" class="candidate-pill" style="font-size: 10px; padding: 2px 10px;">IDLE</span>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
          <button id="btn-stop-agent" class="btn-action" style="color: #ff6b6b; border-color: rgba(255,107,107,0.3); display: none;" onclick="stopRunningAgent()">
            ■ Stop Agent
          </button>
          <button class="btn-action" onclick="clearTerminalLogs()">Clear Logs</button>
        </div>
      </div>
      <div id="terminal-stream" class="terminal-stream">
        <div class="terminal-line info">[System] Ready. Launch an agent or type a natural language command above.</div>
      </div>
    </div>

    <!-- View Switcher & Action Bar -->
    <div class="view-header">
      <div class="view-tabs">
        <button id="tab-btn-cards" class="view-tab active" onclick="switchView('cards')">
          Cards (<span id="cards-count-badge">0</span>)
        </button>
        <button id="tab-btn-report" class="view-tab" onclick="switchView('report')">
          Full Report (.md View)
        </button>
        <button id="tab-btn-raw" class="view-tab" onclick="switchView('raw')">
          Raw Markdown
        </button>
      </div>

      <div class="report-actions">
        <button class="btn-action" onclick="copyReportMarkdown()">Copy Markdown</button>
        <a href="/output/jobs_report.md" download="jobs_report.md" class="btn-action">Download .md ↗</a>
        <a href="/output/jobs.csv" download="jobs.csv" class="btn-action">Export .csv ↗</a>
      </div>
    </div>

    <!-- View 1: Job Cards Grid -->
    <div id="view-cards" class="jobs-list"></div>

    <!-- View 2: Formatted Markdown Report View -->
    <div id="view-report" class="report-card" style="display: none;">
      <div id="report-rendered" class="report-content"></div>
    </div>

    <!-- View 3: Raw Markdown Source View -->
    <div id="view-raw" style="display: none;">
      <pre id="report-raw" class="report-raw-box"></pre>
    </div>
  </div>

  <script>
    let currentView = 'cards';
    let cachedReportMd = '';
    let lastLogCount = 0;

    function switchView(viewName) {
      currentView = viewName;
      document.getElementById('view-cards').style.display = viewName === 'cards' ? 'flex' : 'none';
      document.getElementById('view-report').style.display = viewName === 'report' ? 'block' : 'none';
      document.getElementById('view-raw').style.display = viewName === 'raw' ? 'block' : 'none';

      document.getElementById('tab-btn-cards').className = 'view-tab' + (viewName === 'cards' ? ' active' : '');
      document.getElementById('tab-btn-report').className = 'view-tab' + (viewName === 'report' ? ' active' : '');
      document.getElementById('tab-btn-raw').className = 'view-tab' + (viewName === 'raw' ? ' active' : '');

      if (viewName === 'report' || viewName === 'raw') {
        fetchReport();
      }
    }

    async function fetchJobs() {
      try {
        const res = await fetch('/api/jobs');
        const jobs = await res.json();
        renderJobs(jobs);
      } catch (e) {
        console.error(e);
      }
      fetchReport();
    }

    async function fetchReport() {
      try {
        const res = await fetch('/output/jobs_report.md');
        if (res.ok) {
          cachedReportMd = await res.text();
          document.getElementById('report-raw').textContent = cachedReportMd;
          document.getElementById('report-rendered').innerHTML = renderMarkdown(cachedReportMd);
        }
      } catch (e) {
        console.error('Error fetching markdown report:', e);
      }
    }

    function renderMarkdown(md) {
      if (!md) return '<div class="empty-state">No report generated yet. Run an agent to find opportunities.</div>';
      if (typeof marked !== 'undefined' && marked.parse) {
        return marked.parse(md);
      }
      return md
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\\*\\*(.*?)\\*\\*/gim, '<strong>$1</strong>')
        .replace(/`([^`]+)`/gim, '<code>$1</code>')
        .replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/gim, '<a href="$2" target="_blank">$1</a>')
        .replace(/\\n\\n/gim, '<br><br>')
        .replace(/\\n/gim, '<br>');
    }

    async function copyReportMarkdown() {
      if (!cachedReportMd) await fetchReport();
      if (!cachedReportMd) {
        alert('No report data available to copy yet.');
        return;
      }
      try {
        await navigator.clipboard.writeText(cachedReportMd);
        alert('✓ Report Markdown copied to clipboard!');
      } catch (e) {
        const ta = document.createElement('textarea');
        ta.value = cachedReportMd;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        alert('✓ Report Markdown copied to clipboard!');
      }
    }

    function renderJobs(jobs) {
      const container = document.getElementById('view-cards');
      document.getElementById('cards-count-badge').textContent = jobs.length;
      
      if (!jobs.length) {
        container.innerHTML = `
          <div class="empty-state">
            No opportunities matched yet. Launch the LinkedIn Job Hunter Agent above to begin.
          </div>
        `;
        return;
      }

      container.innerHTML = jobs.map(j => {
        const skills = (j.matched_skills || []).map(s => `<span class="skill-chip">${s}</span>`).join('');
        const kws = (j.jd_keywords || []).slice(0,6).map(s => `<span class="skill-chip" style="border-style:dashed;">${s}</span>`).join('');
        const gaps = (j.missing_skills || []).slice(0,4).join(', ');
        const score = j.match_score || 0;
        const fit = j.fit_level || 'MATCH';
        const prio = j.priority ? `<div style="font-size:11px;color:var(--ink-faint);margin-top:2px;">${j.priority}${j.low_margin ? ' · low-margin' : ''}${j.employment_type ? ' · ' + j.employment_type : ''}${j.deadline ? ' · ⏳ ' + j.deadline : ''}${j.easy_apply ? ' · ⚡ Easy Apply' : ''}</div>` : '';
        const fb = j.fit_breakdown ? `<div style="font-size:12px;color:var(--ink-faint);margin-top:4px;">role ${j.fit_breakdown.role_fit}% · tools ${j.fit_breakdown.tools_fit}% · level ${j.fit_breakdown.level_fit}% · domain ${j.fit_breakdown.domain_fit}%</div>` : '';
        const hook = j.cover_hook ? `<div style="font-size:12.5px;color:#a6a6a6;margin-top:6px;font-style:italic;">“${j.cover_hook}” <button class="btn-action" style="margin-left:6px;" onclick="navigator.clipboard.writeText('${(j.cover_hook||'').replace(/'/g, "\\'")}')">Copy hook</button></div>` : '';
        const gapsHtml = gaps ? `<div style="font-size:12px;color:#ffd166;margin-top:4px;">Gaps: ${gaps}</div>` : '';
        const companyHtml = j.company_url 
          ? `<a href="${j.company_url}" target="_blank" style="color: inherit; text-decoration: none;">${j.company} ↗</a>` 
          : j.company;
        const recruiterHtml = (j.recruiter_name || j.recruiter_url)
          ? `<div style="font-size: 13px; color: var(--ink-muted); margin-top: 4px;">👤 Hiring Lead: ${j.recruiter_url ? `<a href="${j.recruiter_url}" target="_blank" style="color: var(--ink); text-decoration: underline;">${j.recruiter_name || 'View Profile'}</a>` : j.recruiter_name}</div>`
          : '';

        return `
          <article class="job-card">
            <div class="job-content">
              <div class="job-header-row">
                <a href="${j.job_url}" target="_blank" class="job-title">${j.title}</a>
                <div class="job-meta">${companyHtml} · ${j.location || 'Remote'}</div>
                ${recruiterHtml}
              </div>
              <p class="job-reason">${j.reason || ''}</p>
              ${fb}
              ${skills ? `<div class="skills-container">${skills}</div>` : ''}
              ${kws ? `<div class="skills-container" style="margin-top:4px;" title="Mirror in resume">${kws}</div>` : ''}
              ${gapsHtml}
              ${hook}
            </div>
            <div class="score-column">
              <div class="score-box">
                <div class="score-number">${score}%</div>
                <div class="score-tag">${fit}</div>
                ${j.raw_score && j.raw_score !== score ? `<div style="font-size:11px;color:var(--ink-faint);">raw ${j.raw_score}%</div>` : ''}
              </div>
              <a href="${j.job_url}" target="_blank" class="btn-apply">View Opportunity ↗</a>
            </div>
          </article>
        `;
      }).join('');
    }

    async function launchHunterAgent(feedOnly = false) {
      const q = document.getElementById('hunter-q').value;
      const recency = document.getElementById('hunter-recency').value;
      const work_type = document.getElementById('hunter-work_type').value;
      const target_matches = parseInt(document.getElementById('hunter-target').value, 10) || 10;
      const auto_rotate = document.getElementById('hunter-autorotate').checked;
      const view_profiles = document.getElementById('hunter-profiles').checked;
      const explore_feed = document.getElementById('hunter-feed').checked;
      const easy_apply = document.getElementById('hunter-easyapply') ? document.getElementById('hunter-easyapply').checked : false;
      const criteria = document.getElementById('hunter-criteria').value.split('\n').map(s => s.trim()).filter(Boolean);

      try {
        const res = await fetch('/api/agent/launch', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            agent: 'hunter',
            params: {
              query: q,
              recency: recency,
              work_type: work_type,
              target_matches: target_matches,
              auto_rotate: auto_rotate,
              view_profiles: view_profiles,
              explore_feed: explore_feed,
              easy_apply: easy_apply,
              feed_only: feedOnly,
              criteria: criteria
            }
          })
        });
        if (res.status === 409) {
          alert('An agent is already running! Check terminal console.');
        }
      } catch (e) {
        alert('Error launching hunter agent: ' + e);
      }
    }

    async function stopRunningAgent() {
      try {
        await fetch('/api/agent/stop', { method: 'POST' });
      } catch (e) {
        console.error('Error requesting agent stop:', e);
      }
    }

    async function clearTerminalLogs() {
      try {
        await fetch('/api/agent/clear_logs', { method: 'POST' });
        document.getElementById('terminal-stream').innerHTML = '<div class="terminal-line info">[System] Terminal logs cleared.</div>';
      } catch (e) {}
    }

    async function pollAgentStatus() {
      try {
        const res = await fetch('/api/agent/status');
        const data = await res.json();

        const dot = document.getElementById('terminal-dot');
        const title = document.getElementById('terminal-agent-title');
        const badge = document.getElementById('terminal-badge');
        const stopBtn = document.getElementById('btn-stop-agent');
        const hunterBtn = document.getElementById('btn-launch-hunter');
        const feedBtn = document.getElementById('btn-launch-feed');

        if (data.running) {
          dot.className = 'status-indicator active';
          title.textContent = data.agent || 'LinkedIn Hunter Agent';
          badge.textContent = 'RUNNING';
          badge.style.color = '#70ff94';
          badge.style.borderColor = '#70ff94';
          stopBtn.style.display = 'inline-flex';
          hunterBtn.disabled = true;
          if (feedBtn) feedBtn.disabled = true;
        } else {
          dot.className = 'status-indicator';
          title.textContent = 'Agent Console';
          badge.textContent = 'IDLE';
          badge.style.color = 'var(--ink-muted)';
          badge.style.borderColor = 'var(--hairline)';
          stopBtn.style.display = 'none';
          hunterBtn.disabled = false;
          if (feedBtn) feedBtn.disabled = false;
        }

        // Render logs if count changed
        const stream = document.getElementById('terminal-stream');
        if (data.logs && data.logs.length !== lastLogCount) {
          lastLogCount = data.logs.length;
          stream.innerHTML = data.logs.map(l => {
            const cls = l.level || 'info';
            return `<div class="terminal-line ${cls}">[${l.time}] ${escapeHtml(l.text)}</div>`;
          }).join('');
          stream.scrollTop = stream.scrollHeight;
          fetchJobs();
        }
      } catch (e) {}
    }

    function escapeHtml(str) {
      return (str || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    }

    fetchJobs();
    setInterval(pollAgentStatus, 1000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PAGE_HTML.encode("utf-8"))
        elif self.path == "/api/jobs":
            jobs = STORE.load_matched_jobs()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(jobs).encode("utf-8"))
        elif self.path == "/api/agent/status" or self.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(AGENT_STATE).encode("utf-8"))
        elif self.path == "/api/stats":
            from .storage import get_stats
            stats = get_stats()
            stats["matched"] = len(STORE.load_matched_jobs())
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
        elif self.path == "/output/jobs_report.md":
            md_file = STORE.md_file
            if md_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.end_headers()
                self.wfile.write(md_file.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        elif self.path == "/output/jobs.csv":
            csv_file = STORE.csv_file
            if csv_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.end_headers()
                self.wfile.write(csv_file.read_bytes())
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        payload = json.loads(body.decode("utf-8")) if body else {}

        if self.path in ("/api/agent/launch", "/api/hunt"):
            params = payload.get("params", payload)

            if not AGENT_LOCK.locked():
                thread = threading.Thread(target=run_background_hunt, args=(params,))
                thread.daemon = True
                thread.start()
                self._send_json({"status": "started", "agent": "hunter"})
            else:
                self._send_json({"error": "An agent is already running"}, status=409)

        elif self.path == "/api/agent/stop":
            AGENT_STOP_FLAG.set()
            log_agent("⏹ Stop signal sent by user. Halting current agent gracefully...", level="warning")
            self._send_json({"status": "stopping"})

        elif self.path == "/api/agent/clear_logs":
            AGENT_STATE["logs"] = []
            self._send_json({"status": "cleared"})

        else:
            self.send_response(404)
            self.end_headers()

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


def run_background_hunt(params: dict):
    """Web Adapter over the same hunt_core seam as the CLI (no duplicated hunting logic)."""
    from .hunt_core import HuntDeps, HuntHooks, HuntParams, run_hunt

    with AGENT_LOCK:
        AGENT_STOP_FLAG.clear()
        AGENT_STATE["running"] = True
        AGENT_STATE["agent"] = "LinkedIn Job Hunter Agent"

        hunt_params = HuntParams(
            query=params.get("query", "UI/UX Designer"),
            location=params.get("location", ""),
            recency=params.get("recency", "week"),
            work_type=params.get("work_type", "all"),
            target_matches=int(params.get("target_matches", DEFAULT_MIN_MATCHES)),
            min_score=int(params.get("min_score", 70)),
            max_pages=int(params.get("max_pages", 2)),
            limit=int(params.get("limit", 30)),
            daily_cap=int(params.get("daily_cap", 80)),
            auto_rotate=bool(params.get("auto_rotate", True)),
            view_profiles=bool(params.get("view_profiles", True)),
            save_on_linkedin=bool(params.get("save_on_linkedin", False)),
            easy_apply=bool(params.get("easy_apply", False)),
            explore_feed=bool(params.get("explore_feed", True)),
            feed_only=bool(params.get("feed_only", False)),
            max_feed_scrolls=int(params.get("max_feed_scrolls", 80)),
            criteria=params.get("criteria"),
            enforce_caps=bool(params.get("enforce_caps", False)),
        )
        log_agent(f"Target goal: find {hunt_params.target_matches} matching opportunities.", "info")
        if hunt_params.feed_only:
            log_agent("Mode: DIRECT FEED SCAN (Scanning candidate LinkedIn News Feed directly).", "info")
        else:
            log_agent(f"Initial query: '{hunt_params.query}' | Work Type: '{hunt_params.work_type}' | Recency: '{hunt_params.recency}'", "info")

        try:
            evaluator = JobEvaluator()
            browser = LinkedInBrowser(headless=False)
            seen_state = load_seen_state()

            log_agent("Connecting to browser session via CDP...", "info")
            browser.start()
            log_agent("✓ Browser connected.", "success")

            deps = HuntDeps(
                evaluator=evaluator, store=STORE, seen_state=seen_state,
                search_jobs=browser.search_jobs,
                browse_feed=browser.browse_feed_and_find_matches,
            )
            hooks = HuntHooks(
                on_event=log_agent, should_stop=lambda: AGENT_STOP_FLAG.is_set())
            result = run_hunt(hunt_params, deps, hooks)

            browser.close()
            if AGENT_STOP_FLAG.is_set():
                log_agent(f"Agent stopped. Processed {result.evaluated} jobs, filtered {result.skipped}, saved {result.matched} matches.", "warning")
            else:
                log_agent(f"✓ Hunt complete! Evaluated {result.evaluated}, filtered {result.skipped}, saved {result.matched}.", "success")

        except Exception as e:
            log_agent(f"Error executing hunter agent: {e}", "error")
        finally:
            AGENT_STATE["running"] = False
            AGENT_STATE["agent"] = "none"


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), DashboardHandler)
    print(f"\n🚀 Analogue LinkedIn Hunter Dashboard running on http://127.0.0.1:{PORT}\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
