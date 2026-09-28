"""
Land-dispute risk model — a small, explainable logistic regression trained
with plain numpy (no ML framework needed).

HONESTY NOTE (read this before quoting any number from this model):
There is no public dataset of real Indian land-dispute outcomes tied to
these features. This model is therefore trained on SYNTHETIC records whose
"dispute" labels come from a documented data-generating process plus noise.
That makes it a working demonstration of the pipeline — feature extraction,
training, held-out evaluation, per-parcel explanations, a model card — NOT
evidence of real-world predictive accuracy. Replace `synthetic_training_data`
with labelled case data from courts / revenue departments to make it real.
The rule-based score stays alongside it as a transparent baseline.
"""
import math
from datetime import datetime, date

import numpy as np

FEATURES = [
    ("reg_owner_mismatch", "RoR vs Registration owner mismatch"),
    ("tax_owner_mismatch", "RoR vs Property Tax assessee mismatch"),
    ("has_encumbrance", "Existing mortgage / encumbrance"),
    ("ownership_changes", "Number of ownership changes on record"),
    ("recent_transaction", "Transaction within the last 12 months"),
    ("tax_due", "Property tax unpaid"),
    ("unauthorized_change", "Satellite: possible unauthorised construction"),
    ("area_log", "Plot size (log sq.m)"),
    ("agri_land", "Agricultural land use"),
]
NAMES = [f[0] for f in FEATURES]
LABELS = dict(FEATURES)

# The documented ground-truth process used ONLY to synthesise training labels.
_TRUE_W = {"reg_owner_mismatch": 1.6, "tax_owner_mismatch": 1.3, "has_encumbrance": 0.6,
           "ownership_changes": 0.45, "recent_transaction": 0.5, "tax_due": 0.4,
           "unauthorized_change": 1.1, "area_log": 0.15, "agri_land": 0.25}
_TRUE_B = -3.2


def synthetic_training_data(n=6000, seed=7):
    rng = np.random.default_rng(seed)
    reg = rng.binomial(1, 0.12, n)
    tax = np.where(reg == 1, rng.binomial(1, 0.40, n), rng.binomial(1, 0.06, n))
    enc = rng.binomial(1, 0.25, n)
    chg = np.minimum(rng.poisson(0.8, n), 6)
    rec = rng.binomial(1, 0.20, n)
    due = rng.binomial(1, 0.25, n)
    uns = rng.binomial(1, 0.06, n)
    area = rng.normal(6.2, 0.9, n)
    agri = rng.binomial(1, 0.30, n)
    X = np.column_stack([reg, tax, enc, chg, rec, due, uns, area, agri]).astype(float)
    logit = _TRUE_B + sum(_TRUE_W[k] * X[:, i] for i, k in enumerate(NAMES)) - _TRUE_W["area_log"] * 6.2
    logit = logit + rng.normal(0, 0.5, n)
    y = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    return X, y


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def _auc(y, score):
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    pos = y == 1
    n1, n0 = pos.sum(), (~pos).sum()
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


class RiskModel:
    def __init__(self):
        self.w = None
        self.b = 0.0
        self.mean = None
        self.std = None
        self.card = {}

    def train(self, seed=7, n=6000, iters=1500, lr=0.15, l2=1e-3):
        X, y = synthetic_training_data(n, seed)
        idx = np.random.default_rng(seed + 1).permutation(len(y))
        cut = int(0.75 * len(y))
        tr, te = idx[:cut], idx[cut:]
        self.mean = X[tr].mean(axis=0)
        self.std = X[tr].std(axis=0)
        self.std[self.std == 0] = 1.0
        Z = (X - self.mean) / self.std
        w = np.zeros(Z.shape[1])
        b = 0.0
        for _ in range(iters):
            p = _sigmoid(Z[tr] @ w + b)
            g = p - y[tr]
            w -= lr * (Z[tr].T @ g / len(tr) + l2 * w)
            b -= lr * g.mean()
        self.w, self.b = w, float(b)

        p_te = _sigmoid(Z[te] @ w + b)
        rule = 40 * X[te][:, 0] + 30 * X[te][:, 1] + 15 * X[te][:, 2]
        top = np.argsort(-p_te)[: max(1, len(te) // 10)]
        self.card = {
            "model": "L2-regularised logistic regression (numpy, gradient descent)",
            "training_data": f"{cut} synthetic parcels; labels from a documented generating process + noise",
            "test_data": f"{len(te)} held-out synthetic parcels",
            "dispute_base_rate": round(float(y.mean()), 4),
            "auc_test": round(_auc(y[te], p_te), 4),
            "auc_rule_baseline": round(_auc(y[te], rule), 4),
            "precision_top_decile": round(float(y[te][top].mean()), 4),
            "recall_top_decile": round(float(y[te][top].sum() / max(1, y[te].sum())), 4),
            "features": [{"name": n_, "label": LABELS[n_]} for n_ in NAMES],
            "learned_weights_standardised": {n_: round(float(w[i]), 4) for i, n_ in enumerate(NAMES)},
            "limitations": [
                "Trained on synthetic data — the AUC measures how well the model recovers the synthetic "
                "generating process, not real-world predictive power.",
                "The rule baseline scores lower partly because it ignores features the synthetic labels use; "
                "that gap would need to be re-measured on real case data.",
                "Risk scores are decision support for officers, never a basis for automated action.",
                "Features are limited to what the record layers contain; no personal or demographic data is used.",
            ],
        }
        return self

    def predict(self, feats):
        """feats: dict name->number. Returns risk probability and the top contributing factors."""
        x = np.array([float(feats.get(n_, 0)) for n_ in NAMES])
        z = (x - self.mean) / self.std
        contrib = self.w * z
        p = float(_sigmoid(contrib.sum() + self.b))
        order = np.argsort(-contrib)
        factors = []
        for i in order[:4]:
            if contrib[i] > 0.05:
                factors.append({"feature": NAMES[i], "label": LABELS[NAMES[i]],
                                "contribution": round(float(contrib[i]), 3), "value": float(x[i])})
        return {"risk": round(p, 4), "factors": factors}


def _days_since(date_str):
    try:
        return (date.today() - datetime.strptime(date_str[:10], "%Y-%m-%d").date()).days
    except (TypeError, ValueError):
        return 99999


def features_from_parcel(parcel, satellite_flag=False):
    ror = parcel["record_of_rights"]["owner_name"]
    return {
        "reg_owner_mismatch": int(ror != parcel["registration"]["latest_owner_name"]),
        "tax_owner_mismatch": int(ror != parcel["property_tax"]["assessee_name"]),
        "has_encumbrance": int(parcel["encumbrance"]["has_encumbrance"]),
        "ownership_changes": min(6, max(0, len(parcel.get("ownership_history", [])) - 1)),
        "recent_transaction": int(_days_since(parcel["registration"]["last_transaction_date"]) <= 365),
        "tax_due": int(parcel["property_tax"]["status"] == "Due"),
        "unauthorized_change": int(bool(satellite_flag)),
        "area_log": math.log(max(1.0, parcel["record_of_rights"]["area_sqm"])),
        "agri_land": int(parcel["zone_code"] == "A"),
    }
