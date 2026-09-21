import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_parent = str(Path(__file__).resolve().parent.parent)
if _parent not in sys.path:
    sys.path.insert(0, _parent)

from outreach.names import clean_display_name, norm_name, profile_slug
from outreach.ledger import LEDGER_RE, count_skipped, is_messaged, sent_keys
from outreach.messaging import build_message
from outreach.dispatch import (SEND_JS, THREAD_CHECK_JS, check_existing_thread,
                                classify, thread_decision)
from outreach.harvest import CONNECTIONS_LINKS_JS, SEARCH_SWEEP_JS

CHILD_HARNESS = '''import json, os, sys, time, base64
RULES = json.loads(os.environ["TEST_JS_RULES"])
OUT = []
CDP = []

def _print_mock(*a):
    OUT.append(" ".join(str(x) for x in a))

def js(expr):
    for needle, value in RULES:
        if needle in expr:
            return value
    return None

def cdp(*a, **k):
    CDP.append(a)

print = _print_mock
time.sleep = lambda _s: None

__TEMPLATE__

sys.__stdout__.write("\\n@@RESULT@@" + json.dumps({"out": OUT, "cdp": len(CDP)}))
'''

def execute_template(template_text, rules, extra_env=None):

    with tempfile.TemporaryDirectory() as td:
        child = Path(td) / "harness.py"
        child.write_text(CHILD_HARNESS.replace("__TEMPLATE__", template_text),
                         encoding="utf-8")
        env = dict(os.environ)
        env["TEST_JS_RULES"] = json.dumps(rules)
        if extra_env:
            env.update(extra_env)
        proc = subprocess.run([sys.executable, str(child)], capture_output=True,
                              text=True, encoding="utf-8", timeout=60, env=env)
        if proc.returncode != 0:
            raise AssertionError(f"template crashed in child process:\n{proc.stderr[-800:]}")
        marker = "@@RESULT@@"
        if marker not in proc.stdout:
            raise AssertionError(f"no result marker from child. stdout={proc.stdout[-400:]!r} "
                                 f"stderr={proc.stderr[-400:]!r}")
        payload = json.loads(proc.stdout.split(marker, 1)[1].strip())
        return payload["out"], payload["cdp"]

SEND_RULES = [
    ["window.location.href", None],
    ["afterCount", {"afterCount": 3, "editorEmpty": True, "threadTail": "old ... Thank you"}],
    ["/messaging/compose", {"found": True, "href": "/messaging/compose/?recipient=1"}],
    ["msg-form__contenteditable", {"found": True}],
    ["querySelectorAll('li')", {"count": 2}],
    ["'Send'", {"found": True, "disabled": False}],
]

def send_script():
    return (SEND_JS
            .replace("__URL__", "https://www.linkedin.com/in/test-user/")
            .replace("__MSG_B64__", base64.b64encode(b"Hi, Test").decode("ascii")))

class TestNames(unittest.TestCase):
    def test_norm_strips_rtl_badge_and_lowercases(self):
        self.assertEqual(norm_name("Rahul \u200e• 1st"), "rahul")

    def test_norm_collapses_whitespace(self):
        self.assertEqual(norm_name("  Md.   Rahim  "), "md. rahim")

    def test_clean_keeps_case(self):
        self.assertEqual(clean_display_name("MD mirajul • 1st"), "MD mirajul")

    def test_first_name_machinery_removed(self):

        import outreach.names as names_module
        self.assertFalse(hasattr(names_module, "first_name_of"))

    def test_slug_basic(self):
        self.assertEqual(profile_slug("https://www.linkedin.com/in/sanzida-akter-49476340b/en/"),
                         "sanzida-akter-49476340b")

    def test_slug_with_query(self):
        self.assertEqual(profile_slug("/in/branotix?trk=xyz"), "branotix")

    def test_slug_none_for_compose_url(self):
        self.assertEqual(profile_slug("https://www.linkedin.com/messaging/compose/?recipient=1"), "")

class TestLedgerRegex(unittest.TestCase):
    def test_legacy_no_status_counts_as_sent(self):
        m = LEDGER_RE.match("- Md Hanjala (2026-08-15 10:38)")
        self.assertEqual((m.group(1), m.group(3) or "SENT"), ("Md Hanjala", "SENT"))

    def test_failed_line(self):
        m = LEDGER_RE.match("- Faysal Al Nur (2026-08-16 13:49:16) - FAILED")
        self.assertEqual((m.group(1), m.group(3)), ("Faysal Al Nur", "FAILED"))

    def test_new_line_with_url(self):
        m = LEDGER_RE.match("- Test User (2026-08-16 15:00:00) - SENT - https://www.linkedin.com/in/test-user-123/")
        self.assertEqual((m.group(1), m.group(3), m.group(4)),
                         ("Test User", "SENT", "https://www.linkedin.com/in/test-user-123/"))

    def test_unknown_status(self):
        m = LEDGER_RE.match("- Weird ? (2026-08-16 15:00:00) - UNKNOWN")
        self.assertEqual(m.group(3), "UNKNOWN")

    def test_header_and_blank_rejected(self):
        self.assertIsNone(LEDGER_RE.match("# Messaged Connections"))
        self.assertIsNone(LEDGER_RE.match(""))

class TestDedup(unittest.TestCase):
    LEDGER = [
        {"name": "Rahul", "norm": "rahul", "slug": "rahul-111", "status": "SENT", "date": "2026-08-15"},
        {"name": "Rahul", "norm": "rahul", "slug": "", "status": "SENT", "date": "2026-08-15"},
    ]

    def test_same_name_different_slug_is_new_person(self):
        sn, ss = sent_keys(self.LEDGER)
        contact = {"name": "Rahul", "profile_url": "https://www.linkedin.com/in/rahul-222/"}
        self.assertFalse(is_messaged(contact, self.LEDGER, sn, ss))

    def test_same_slug_is_messaged(self):
        sn, ss = sent_keys(self.LEDGER)
        contact = {"name": "Rahul X", "profile_url": "https://www.linkedin.com/in/rahul-111/"}
        self.assertTrue(is_messaged(contact, self.LEDGER, sn, ss))

    def test_legacy_name_only_match_is_conservative(self):
        legacy = [{"name": "Rahul", "norm": "rahul", "slug": "", "status": "SENT", "date": "2026-08-15"}]
        sn, ss = sent_keys(legacy)
        contact = {"name": "Rahul", "profile_url": "https://www.linkedin.com/in/rahul-999/"}
        self.assertTrue(is_messaged(contact, legacy, sn, ss))

    def test_failed_is_retryable(self):
        ledger = [{"name": "X Y", "norm": "x y", "slug": "x-y", "status": "FAILED", "date": "2026-08-16"}]
        sn, ss = sent_keys(ledger)
        self.assertFalse(is_messaged({"name": "X Y", "profile_url": "/in/x-y"}, ledger, sn, ss))

    def test_unknown_is_never_messaged_again(self):
        ledger = [{"name": "X Y", "norm": "x y", "slug": "x-y", "status": "UNKNOWN", "date": "2026-08-16"}]
        sn, ss = sent_keys(ledger)
        self.assertTrue(is_messaged({"name": "X Y", "profile_url": "/in/x-y"}, ledger, sn, ss))

    def test_skipped_thread_counts_as_done(self):
        ledger = [{"name": "X Y", "norm": "x y", "slug": "x-y", "status": "SKIPPED", "date": "2026-08-17"}]
        sn, ss = sent_keys(ledger)
        self.assertTrue(is_messaged({"name": "X Y", "profile_url": "/in/x-y"}, ledger, sn, ss))

    def test_count_skipped(self):
        entries = [{"status": "SKIPPED"}, {"status": "SENT"}, {"status": "SKIPPED"}]
        self.assertEqual(count_skipped(entries), 2)

class TestClassify(unittest.TestCase):
    PAYLOAD = {"stage": "sent", "beforeCount": 2, "afterCount": 3,
               "editorEmpty": True, "threadTail": "old ... Thank you"}

    def test_verified_sent(self):
        status, detail = classify(self.PAYLOAD, "Thank you")
        self.assertEqual((status, detail), ("SENT", "verified"))

    def test_sent_marker_missing(self):
        status, _ = classify(dict(self.PAYLOAD, threadTail="other"), "Thank you")
        self.assertEqual(status, "SENT")

    def test_grew_null_editor_is_unknown(self):
        status, _ = classify(dict(self.PAYLOAD, editorEmpty=None), "m")
        self.assertEqual(status, "UNKNOWN")

    def test_grew_text_stuck_is_unknown_never_retry(self):
        status, _ = classify(dict(self.PAYLOAD, editorEmpty=False), "m")
        self.assertEqual(status, "UNKNOWN")

    def test_no_growth_text_stuck_is_failed(self):
        status, _ = classify(dict(self.PAYLOAD, afterCount=2, editorEmpty=False), "m")
        self.assertEqual(status, "FAILED")

    def test_editor_cleared_no_growth_is_unknown(self):
        status, _ = classify(dict(self.PAYLOAD, afterCount=2), "m")
        self.assertEqual(status, "UNKNOWN")

    def test_timeout_no_result_is_unknown(self):
        status, _ = classify(None, "m", timed_out=True)
        self.assertEqual(status, "UNKNOWN")

    def test_plain_no_result_is_failed(self):
        status, _ = classify(None, "m", timed_out=False)
        self.assertEqual(status, "FAILED")

    def test_pre_send_stage_is_failed(self):
        status, _ = classify({"stage": "editor", "ok": False}, "m")
        self.assertEqual(status, "FAILED")

class TestThreadCheck(unittest.TestCase):

    def test_decision_skips_existing_thread(self):
        skip, reason = thread_decision(True, "conversation already has 2 message(s)")
        self.assertTrue(skip)
        self.assertIn("2", reason)

    def test_decision_sends_on_empty_thread(self):
        skip, _ = thread_decision(False, "conversation is empty")
        self.assertFalse(skip)

    def test_decision_strict_mode_skips_inconclusive(self):
        self.assertTrue(thread_decision(None, "no THREAD result", strict=True)[0])
        self.assertFalse(thread_decision(None, "no THREAD result", strict=False)[0])

    def test_check_parses_existing_thread(self):
        with patch("outreach.dispatch.run_bu_script",
                   return_value=('THREAD:{"ready": true, "hasMessages": true, "count": 3}', '')):
            has, detail = check_existing_thread({"profile_url": "https://www.linkedin.com/in/a/"})
        self.assertTrue(has)
        self.assertIn("3", detail)

    def test_check_empty_thread_is_safe_to_send(self):
        with patch("outreach.dispatch.run_bu_script",
                   return_value=('THREAD:{"ready": true, "hasMessages": false, "count": 0}', '')):
            has, _ = check_existing_thread({"profile_url": "https://www.linkedin.com/in/a/"})
        self.assertFalse(has)

    def test_check_inconclusive_on_timeout(self):
        with patch("outreach.dispatch.run_bu_script", return_value=('', 'TIMEOUT: x')):
            has, detail = check_existing_thread({"profile_url": "https://www.linkedin.com/in/a/"})
        self.assertIsNone(has)
        self.assertIn("timed out", detail)

    def test_template_has_no_leftover_placeholder(self):
        self.assertNotIn("__URL__", THREAD_CHECK_JS.replace("__URL__", "x"))

    def test_template_executes(self):
        rules = [["window.location.href", True],
                 ["msg-s-message-list", {"hasMessages": True, "count": 3}]]
        script = THREAD_CHECK_JS.replace(
            "__URL__", "https://www.linkedin.com/messaging/compose/?recipient=1")
        out, _ = execute_template(script, rules)
        lines = [l for l in out if l.startswith("THREAD:")]
        self.assertEqual(len(lines), 1)
        payload = json.loads(lines[0][len("THREAD:"):])
        self.assertTrue(payload["hasMessages"])
        self.assertEqual(payload["count"], 3)

class TestMessageTemplate(unittest.TestCase):
    def test_renders_from_user_template(self):
        msg = build_message("Sanzida Akter")
        self.assertTrue(msg.startswith("Hi, Sanzida Akter"))

    def test_headline_renders_when_template_uses_it(self):
        from outreach import messaging
        saved = list(messaging._message_template_cache)
        messaging._message_template_cache[:] = ["Hi {name} - {headline}"]
        try:
            msg = build_message("X Y", {"headline": "UX Designer at Acme"})
            self.assertEqual(msg, "Hi X Y - UX Designer at Acme")
        finally:
            messaging._message_template_cache[:] = saved

    def test_full_name_only_in_greeting(self):
        msg = build_message("Md. Hafizur Rahman")
        self.assertTrue(msg.startswith("Hi, Md. Hafizur Rahman"))

class TestBrowserUseTemplates(unittest.TestCase):

    def test_send_happy_path(self):
        out, cdp_calls = execute_template(send_script(), SEND_RULES)
        result_lines = [l for l in out if l.startswith("RESULT:")]
        self.assertEqual(len(result_lines), 1)
        payload = json.loads(result_lines[0][len("RESULT:"):])
        self.assertEqual(payload["stage"], "sent")
        self.assertEqual((payload["beforeCount"], payload["afterCount"], payload["editorEmpty"]),
                         (2, 3, True))
        self.assertEqual(cdp_calls, 1)

    def test_send_editor_never_mounts(self):
        rules = [["msg-form__contenteditable", {"found": False}]]
        out, _ = execute_template(send_script(), rules)
        result_lines = [l for l in out if l.startswith("RESULT:")]
        self.assertEqual(len(result_lines), 1)
        self.assertEqual(json.loads(result_lines[0][len("RESULT:"):])["stage"], "editor")

    def test_send_button_disabled(self):
        rules = [["msg-form__contenteditable", {"found": True}],
                 ["'Send'", {"found": True, "disabled": True}]]
        out, _ = execute_template(send_script(), rules)
        result_lines = [l for l in out if l.startswith("RESULT:")]
        self.assertEqual(json.loads(result_lines[0][len("RESULT:"):])["stage"], "send_button")

    def test_search_sweep_executes(self):
        rules = [["window.location.href", True],
                 ["scrollTo", True],
                 ["No results", True],
                 ["seenHrefs", [{"name": "A B", "headline": "H", "profile_url": "/in/a-b/"}]]]
        script = SEARCH_SWEEP_JS.replace("__SEARCH_URL__", "https://x").replace("__MARKER__", "CARDS:")
        out, _ = execute_template(script, rules)
        self.assertTrue(any(l.startswith("CARDS:") for l in out))

    def test_connections_links_executes(self):
        rules = [["Send a message", True],
                 ["'Send a message'", [{"label": "Send a message to X Y",
                                        "href": "/messaging/compose/?recipient=1"}]]]
        out, _ = execute_template(
            CONNECTIONS_LINKS_JS.replace("__CONNECTIONS_URL__", "https://x/"), rules)
        self.assertTrue(any(l.startswith("LINKS:") for l in out))

    def test_no_leftover_placeholders_after_substitution(self):
        script = send_script()
        self.assertNotIn("__URL__", script)
        self.assertNotIn("__MSG_B64__", script)

    def test_embedded_js_is_valid(self):

        try:
            subprocess.run(["node", "--version"], capture_output=True, timeout=10, check=True)
        except Exception:
            self.skipTest("node not available")
        payloads = []
        for name, tmpl in (("SEND", SEND_JS), ("SWEEP", SEARCH_SWEEP_JS),
                           ("LINKS", CONNECTIONS_LINKS_JS),
                           ("THREAD", THREAD_CHECK_JS)):
            payloads += [(name, m.group(1)) for m in
                         re.finditer(r"js\(\s*'''(.*?)'''\s*\)", tmpl, re.S)]
        self.assertGreaterEqual(len(payloads), 8)
        with tempfile.TemporaryDirectory() as td:
            for i, (name, code) in enumerate(payloads):
                p = Path(td) / f"{i}.js"
                p.write_text(code, encoding="utf-8")
                r = subprocess.run(["node", "--check", str(p)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, f"{name} JS invalid: {r.stderr[:200]}")

class TestRealLedger(unittest.TestCase):

    def test_real_ledger_parses(self):
        from outreach.config import LEDGER_FILE
        from outreach.ledger import parse_ledger
        if not os.path.exists(LEDGER_FILE):
            self.skipTest("no ledger file")
        entries = parse_ledger()
        self.assertGreater(len(entries), 100)
        self.assertTrue(all(e["status"] in ("SENT", "FAILED", "UNKNOWN", "SKIPPED") for e in entries))

class TestEvaluator(unittest.TestCase):
    def test_bm25_prescreen_disqualifies(self):
        from outreach.evaluator import bm25_prescreen
        res = bm25_prescreen("Senior Radiologist at Hospital")
        self.assertIsNotNone(res)
        self.assertEqual(res["archetype"], "disqualified")
        self.assertEqual(res["relevance"], 10)

    def test_bm25_prescreen_passes_relevant(self):
        from outreach.evaluator import bm25_prescreen
        self.assertIsNone(bm25_prescreen("Product Designer at TechCorp"))
        self.assertIsNone(bm25_prescreen("Technical Recruiter at Startup"))

    def test_heuristic_evaluates_archetypes(self):
        from outreach.evaluator import heuristic_evaluate
        r1 = heuristic_evaluate("Alice", "Head of Talent Acquisition")
        self.assertEqual(r1["archetype"], "recruiter")
        self.assertGreaterEqual(r1["relevance"], 90)

        r2 = heuristic_evaluate("Bob", "Co-Founder & CEO")
        self.assertEqual(r2["archetype"], "founder")
        self.assertGreaterEqual(r2["relevance"], 85)

        r3 = heuristic_evaluate("Charlie", "Senior UI/UX Designer")
        self.assertEqual(r3["archetype"], "peer")
        self.assertGreaterEqual(r3["relevance"], 80)

    def test_mocked_semif_judge(self):
        from outreach.evaluator import SemIfJudge
        fake_client = object()
        fake_meta = {"source": "fake", "backend": "injected"}

        judge = SemIfJudge(client=fake_client, meta=fake_meta)
        with patch("outreach.evaluator.score") as mock_score:
            mock_score.return_value = {
                "option_ids": ["recruiter", "founder", "peer", "general"],
                "probabilities": [0.92, 0.04, 0.02, 0.02],
                "forward_seconds": 0.05,
            }
            archetype, prob = judge.classify_archetype("Jane Doe", "Technical Sourcer")
            self.assertEqual(archetype, "recruiter")
            self.assertAlmostEqual(prob, 0.92)

class TestArchetypeMessaging(unittest.TestCase):
    def test_recruiter_template_used(self):
        contact = {"name": "Jane", "headline": "Talent Partner", "archetype": "recruiter"}
        msg = build_message("Jane", contact)
        self.assertIn("recruitment", msg.lower())

    def test_founder_template_used(self):
        contact = {"name": "Elon", "headline": "CEO & Founder", "archetype": "founder"}
        msg = build_message("Elon", contact)
        self.assertIn("venture", msg.lower())

    def test_peer_template_used(self):
        contact = {"name": "Jony", "headline": "Design Lead", "archetype": "peer"}
        msg = build_message("Jony", contact)
        self.assertIn("fellow designer", msg.lower())

class TestConfigAndEnv(unittest.TestCase):
    def test_get_bool_truthy_and_falsy(self):
        from outreach.config import get_bool
        with patch.dict(os.environ, {"FLAG_ON": "1", "FLAG_TRUE": "True", "FLAG_OFF": "0", "FLAG_FALSE": "false"}):
            self.assertTrue(get_bool("FLAG_ON", False))
            self.assertTrue(get_bool("FLAG_TRUE", False))
            self.assertFalse(get_bool("FLAG_OFF", True))
            self.assertFalse(get_bool("FLAG_FALSE", True))
            self.assertTrue(get_bool("FLAG_MISSING", True))

    def test_load_env_loads_key_values(self):
        from outreach.config import load_env
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".env") as tmp:
            tmp.write("# Comment\nTEST_ENV_VAR_XYZ=hello_world\nEMPTY_VAL=\n")
            tmp_path = tmp.name
        try:
            with patch.dict(os.environ, {}, clear=False):
                if "TEST_ENV_VAR_XYZ" in os.environ:
                    del os.environ["TEST_ENV_VAR_XYZ"]
                load_env(tmp_path)
                self.assertEqual(os.environ.get("TEST_ENV_VAR_XYZ"), "hello_world")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

if __name__ == "__main__":
    unittest.main()
