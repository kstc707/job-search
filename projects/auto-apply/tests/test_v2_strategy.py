"""Strategy arms: outcome tally and Thompson-sampling slot split (made-up rows)."""

from datetime import date

from auto_apply.v2.strategy import allocate, tally

TODAY = date(2026, 11, 2)


def row(arm, status, day="2026-10-30", notes=""):
    return {"Status": [status], "Notes": f"{notes} [arm:{arm}]", "date:Date:start": day}


def test_tally_counts_positive_rejected_silent_and_pending():
    rows = [
        row("A", "Interview Scheduled"),
        row("A", "Applied", notes="[v2 outcome sync: Applied -> Waiting. Evidence: RECRUITER_MESSAGE]"),
        row("A", "Rejected"),
        row("A", "Applied", day="2026-10-01"),      # 32 days, no answer: silent failure
        row("A", "Applied", day="2026-10-30"),      # 3 days: still pending
        row("B", "Drafted"),                        # never sent: ignored
        {"Status": ["Applied"], "Notes": "no arm tag", "date:Date:start": "2026-10-01"},
    ]
    s = tally(rows, TODAY)
    a = s["A"]
    assert (a.sent, a.positive, a.rejected, a.silent, a.pending) == (5, 2, 1, 1, 1)
    assert "B" not in s
    assert round(a.mean, 3) == round(3 / 6, 3)


def test_notion_escaped_brackets_and_json_status_are_read():
    s = tally([{"Status": '["Rejected"]', "Notes": "\\[arm:C\\]"}], TODAY)
    assert s["C"].rejected == 1


def test_allocation_favours_the_arm_that_gets_callbacks_but_keeps_exploring():
    rows = [row("good", "Interview Scheduled") for _ in range(3)] + \
           [row("good", "Rejected") for _ in range(7)] + \
           [row("bad", "Rejected") for _ in range(10)]
    plan = allocate(tally(rows, TODAY), ["good", "bad", "new"], slots=40, seed=1)
    assert sum(plan.values()) == 40
    assert plan["good"] > plan["bad"]
    assert plan["new"] > 0            # an untried arm still gets slots
