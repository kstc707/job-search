"""Account-month features: the signals a fraud analyst would look at, computed only from
data available at the end of that month (no peeking at later months, no answer key).

Three families
  behavioural  volume spike, new devices, new destinations, express mix, weight declared vs measured
  text mining  claim narratives: TF-IDF, near-duplicate stories across different accounts, urgency terms
  network      accounts linked through shared devices or recipient addresses (union-find)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

URGENCY = ["urgent", "urgently", "asap", "full declared", "high value", "refund"]


# ---------------------------------------------------------------- behavioural ----
def behavioural(ship: pd.DataFrame) -> pd.DataFrame:
    s = ship.sort_values(["account_id", "month"]).copy()
    s["ratio"] = s.declared_lb / s.measured_lb.clip(lower=0.1)

    # first month each (account, device) and (account, destination) pair was seen
    s["dev_first"] = s.groupby(["account_id", "device_id"]).month.transform("min")
    s["dest_first"] = s.groupby(["account_id", "dest_address"]).month.transform("min")
    s["new_device"] = s.dev_first == s.month
    s["new_dest"] = s.dest_first == s.month

    # addresses receiving from many unrelated accounts in the same month (possible drop/mule)
    senders = s.groupby(["month", "dest_address"]).account_id.nunique().rename("senders")
    s = s.join(senders, on=["month", "dest_address"])
    # devices used by several accounts in the same month
    dev_accts = s.groupby(["month", "device_id"]).account_id.nunique().rename("dev_accounts")
    s = s.join(dev_accts, on=["month", "device_id"])

    g = s.groupby(["account_id", "month"])
    f = pd.DataFrame({
        "n_ship": g.size(),
        "new_device_share": g.new_device.mean(),
        "new_dest_share": g.new_dest.mean(),
        "express_share": g.service.apply(lambda x: (x != "ground").mean()),
        "weight_ratio_median": g.ratio.median(),
        "low_weight_share": g.ratio.apply(lambda x: (x < 0.8).mean()),
        "drop_dest_share": g.senders.apply(lambda x: (x >= 8).mean()),
        "max_device_accounts": g.dev_accounts.max(),
        "billed": g.billed.sum(),
    }).reset_index()

    # volume spike against the account's own trailing 3-month median
    f = f.sort_values(["account_id", "month"])
    f["trailing_median"] = (f.groupby("account_id").n_ship
                            .transform(lambda x: x.shift(1).rolling(3, min_periods=1).median()))
    f["volume_ratio"] = f.n_ship / (f.trailing_median.fillna(f.n_ship) + 1)
    return f


# ---------------------------------------------------------------- text mining ----
def claim_text(claims: pd.DataFrame) -> pd.DataFrame:
    """For each claim: highest similarity to an earlier-or-same-month claim from a DIFFERENT
    account, plus urgency-term hits. Near-identical stories across unrelated accounts are a
    classic sign of scripted claims."""
    c = claims.reset_index(drop=True).copy()
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2)
    x = vec.fit_transform(c.narrative).toarray()            # small vocabulary: dense is fine
    acct = c.account_id.to_numpy()
    month = c.month.to_numpy()
    best = np.zeros(len(c))
    near_dups = np.zeros(len(c), dtype=int)
    for start in range(0, len(c), 1000):
        stop = min(start + 1000, len(c))
        sim = x[start:stop] @ x.T                           # cosine: rows are L2-normalised
        same_acct = acct[start:stop, None] == acct[None, :]
        future = month[None, :] > month[start:stop, None]
        sim[same_acct | future] = 0.0
        best[start:stop] = sim.max(axis=1)
        near_dups[start:stop] = (sim >= 0.9).sum(axis=1)
    c["max_sim_other_account"] = best
    c["near_dup_claims"] = near_dups
    text = c.narrative.str.lower()
    c["urgency_hits"] = sum(text.str.contains(term, regex=False).astype(int) for term in URGENCY)
    return c


def claim_features(c: pd.DataFrame) -> pd.DataFrame:
    g = c.groupby(["account_id", "month"])
    return pd.DataFrame({
        "n_claims": g.size(),
        "claim_amount": g.amount.sum(),
        "not_received_share": g.claim_type.apply(lambda x: (x == "not_received").mean()),
        "max_text_sim": g.max_sim_other_account.max(),
        "near_dup_claims": g.near_dup_claims.max(),
        "urgency_hits": g.urgency_hits.max(),
    }).reset_index()


# ---------------------------------------------------------------- network --------
class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, a: str) -> str:
        self.parent.setdefault(a, a)
        while self.parent[a] != a:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def network(ship: pd.DataFrame) -> pd.DataFrame:
    """Size of each account's linked cluster, built cumulatively month by month from shared
    devices and shared recipient addresses (only links seen up to that month count)."""
    rows = []
    uf = UnionFind()
    for m in sorted(ship.month.unique()):
        cur = ship[ship.month == m]
        for key in ("device_id", "dest_address"):
            shared = cur.groupby(key).account_id.unique()
            for accts in shared[shared.map(len) > 1]:
                for other in accts[1:]:
                    uf.union(accts[0], other)
        active = cur.account_id.unique()
        roots = pd.Series([uf.find(a) for a in active], index=active)
        # cluster size counts every account linked so far, not only those active this month
        full = pd.Series({a: uf.find(a) for a in uf.parent}).value_counts()
        rows.append(pd.DataFrame({"account_id": active, "month": m,
                                  "cluster_size": roots.map(full).fillna(1).astype(int).to_numpy()}))
    return pd.concat(rows, ignore_index=True)


# ---------------------------------------------------------------- assemble -------
def build(ship: pd.DataFrame, claims: pd.DataFrame, truth: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    f = behavioural(ship)
    ct = claim_text(claims)
    f = f.merge(claim_features(ct), on=["account_id", "month"], how="left")
    f = f.merge(network(ship), on=["account_id", "month"], how="left")
    fill = ["n_claims", "claim_amount", "not_received_share", "max_text_sim", "near_dup_claims", "urgency_hits"]
    f[fill] = f[fill].fillna(0)
    f["cluster_size"] = f.cluster_size.fillna(1)
    f["claim_rate"] = f.n_claims / f.n_ship.clip(lower=1)

    # answer key and dollars at stake (used for scoring only, never as a feature)
    lab = truth.assign(fraud=1).groupby(["account_id", "month"]).agg(fraud=("fraud", "max"),
                                                                      schemes=("scheme", lambda x: "+".join(sorted(x))))
    f = f.merge(lab.reset_index(), on=["account_id", "month"], how="left")
    f["fraud"] = f.fraud.fillna(0).astype(int)
    f["schemes"] = f.schemes.fillna("")
    loss = (ship[ship.is_fraud].assign(loss=lambda d: np.where(d.scheme == "UNDER", d.lost_revenue, d.billed))
            .groupby(["account_id", "month"]).loss.sum())
    claim_loss = claims[claims.is_fraud].groupby(["account_id", "month"]).amount.sum()
    f = f.join(loss.rename("ship_loss"), on=["account_id", "month"]).join(claim_loss.rename("claim_loss"),
                                                                          on=["account_id", "month"])
    f["dollars_at_risk"] = f.ship_loss.fillna(0) + f.claim_loss.fillna(0)
    f = f.drop(columns=["ship_loss", "claim_loss"])
    return f, ct


FEATURES = ["n_ship", "volume_ratio", "new_device_share", "new_dest_share", "express_share",
            "weight_ratio_median", "low_weight_share", "drop_dest_share", "max_device_accounts",
            "n_claims", "claim_rate", "claim_amount", "not_received_share", "max_text_sim",
            "near_dup_claims", "urgency_hits", "cluster_size"]
