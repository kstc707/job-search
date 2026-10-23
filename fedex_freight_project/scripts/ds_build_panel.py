"""Build and validate the point-in-time carrier panel: reports/ds/panel.csv"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from ltlds import config as C  # noqa: E402
from ltlds.panel import build_panel, validate_panel  # noqa: E402

C.OUT.mkdir(parents=True, exist_ok=True)
p = build_panel()
errs = validate_panel(p)
print("validation:", "PASS" if not errs else errs)
p.to_csv(C.OUT / "panel.csv", index=False)
use = p[p["y"].notna() & ~p["covid"]]
print(f"rows {len(p)}, usable (target, non-COVID) {len(use)}, test rows (>= {C.TEST_FROM}) "
      f"{(use['tau'] >= C.TEST_FROM).sum()}")
print(use.groupby("ticker").agg(n=("y", "size"), first=("period", "first"), last=("period", "last"),
                                 own_m_avail=("own_m", lambda s: s.notna().mean()),
                                 mkt_m_avail=("mkt_m", lambda s: s.notna().mean())).round(2).to_string())
print(use[[c for g in C.FEATURE_GROUPS.values() for c in g]].describe().T[["count", "mean", "std", "min", "max"]].round(2).to_string())
if errs:
    sys.exit(1)
