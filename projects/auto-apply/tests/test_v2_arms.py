from datetime import date

from auto_apply.v2.arms import assign, fisher_two_sided, outcome, report, tally

TODAY = date(2026, 11, 20)


def test_assignment_is_stable_and_ignores_tracking_parameters():
    url = "https://boards.greenhouse.io/acme/jobs/4012345"
    assert assign(url) == assign(url + "?utm_source=indeed&gh_src=x")
    assert assign(url) in ("A", "B")


def test_assignment_splits_roughly_evenly():
    arms = [assign(f"https://example.com/jobs/{i}") for i in range(400)]
    assert 160 < arms.count("A") < 240


def row(arm, status="Applied", notes="", day="2026-11-15"):
    return {"Status": status, "date:Date:start": day,
            "Notes": f"[seeker {day} arm={arm} v=x] hypothesis: y." + notes}


def test_outcomes():
    assert outcome(row("A", notes="<br>[v2 outcome sync: Evidence: 2026-11-18 RECRUITER_MESSAGE: Hi]"), TODAY) == "callback"
    assert outcome(row("A", status="Interview Scheduled"), TODAY) == "callback"
    assert outcome(row("B", status="Waiting", notes=" Evidence: 2026-11-18 ASSESSMENT: HireVue"), TODAY) == "assessment"
    assert outcome(row("B", status="Rejected"), TODAY) == "rejected"
    assert outcome(row("B", day="2026-10-01"), TODAY) == "silent"
    assert outcome(row("B"), TODAY) == "pending"


def test_tally_counts_only_seeker_rows():
    rows = [row("A", status="Interview Scheduled"), row("A", status="Rejected"), row("B"),
            {"Status": "Applied", "Notes": "v2 drafted row", "date:Date:start": "2026-11-01"}]
    stats = tally(rows, TODAY)
    assert (stats["A"].sent, stats["B"].sent) == (2, 1)
    assert stats["A"].counts["callback"] == 1 and stats["A"].callback_rate == 0.5
    assert "hint, not a result" in report(stats)


def test_fisher_matches_known_values():
    # Classic tea-tasting table [[3, 1], [1, 3]]: two-sided p = 0.486
    assert round(fisher_two_sided(3, 1, 1, 3), 3) == 0.486
    assert fisher_two_sided(0, 30, 0, 30) == 1.0
    assert fisher_two_sided(8, 22, 0, 30) < 0.01
