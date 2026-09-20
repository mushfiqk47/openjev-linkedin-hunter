from conftest import FakeClient, probs

from linkedin_hunter.storage import JobStore
from linkedin_hunter.triage import ApplyTriage, NEXT_ACTIONS, triage_job

META = {"backend": "injected", "source": "fake"}

JOB = {
    "job_id": "1",
    "title": "Product Designer",
    "company": "Acme",
    "location": "Remote",
    "employment_type": "full-time",
    "recruiter_name": "Jane Doe",
    "recruiter_url": "https://www.linkedin.com/in/jane",
    "description": "Figma, design systems and prototyping for a SaaS dashboard.",
    "match_score": 85,
}

def triage_responses():
    return [
        probs(0.85, 0.15),
        probs(0.1, 0.7, 0.1, 0.1),
        probs(0.05, 0.6, 0.1, 0.1, 0.1, 0.05),
        probs(0.7, 0.1, 0.1, 0.1),
    ]

def test_triage_produces_next_action_and_assets():
    client = FakeClient(triage_responses())
    result = triage_job(JOB, judge_client=client, meta=META)

    assert result["next_action"] in NEXT_ACTIONS
    assert result["next_action"] == "apply_now"
    assert result["employer_fit"] == 85
    assert result["freshness"] == "this_week"
    assert result["cover_angles"][0] == "figma_craft"
    assert "Jane" in result["recruiter_message"]
    assert result["triage_calls"] == 4

def test_triage_agent_counts_its_model_calls():
    agent = ApplyTriage(client=FakeClient(triage_responses()), meta=META)
    agent.triage(JOB)
    assert agent.judge.calls == 4

def test_report_renders_triage_fields(tmp_path):
    store = JobStore(output_dir=tmp_path)
    triaged = {**JOB, "triage": triage_job(JOB, judge_client=FakeClient(triage_responses()), meta=META)}

    store.save_job(triaged)

    report = store.md_file.read_text()
    assert "Next action" in report
    assert "Recruiter opener" in report
    assert "apply_now" in report
