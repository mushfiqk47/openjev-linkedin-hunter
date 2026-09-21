from linkedin_connect.evaluator import ProfileEvaluator, prescreen_headline

def test_prescreen_design_leaders():
    res = prescreen_headline("Head of Design at TechCorp | Design Systems & UX")
    assert res is not None
    assert res["archetype"] == "design_leader"
    assert res["score"] >= 85
    assert res["fit_level"] == "EXCELLENT"

    res2 = prescreen_headline("Creative Director | Brand & Product Experience")
    assert res2 is not None
    assert res2["archetype"] == "design_leader"

def test_prescreen_recruiters():
    res = prescreen_headline("Technical Recruiter @ Google | Hiring Senior Designers")
    assert res is not None
    assert res["archetype"] == "recruiter"
    assert res["score"] >= 80

def test_prescreen_founders():
    res = prescreen_headline("Founder & CEO @ AI Startup | Building the future")
    assert res is not None
    assert res["archetype"] == "founder"
    assert res["score"] >= 85

def test_prescreen_disqualified():
    res = prescreen_headline("Computer Science Student | Intern seeking summer roles")
    assert res is not None
    assert res["archetype"] == "disqualified"
    assert res["score"] < 50
    assert res["fit_level"] == "SKIP"

    res2 = prescreen_headline("Registered Nurse | Clinical Care Specialist")
    assert res2 is not None
    assert res2["archetype"] == "disqualified"

def test_evaluator_qualified_flag():
    evaluator = ProfileEvaluator()
    res = evaluator.evaluate("Sarah Connor", "Head of Product Design @ Cyberdyne")
    assert res["qualified"] is True
    assert res["archetype"] == "design_leader"

    res_bad = evaluator.evaluate("Bob Student", "Junior Student Intern")
    assert res_bad["qualified"] is False
