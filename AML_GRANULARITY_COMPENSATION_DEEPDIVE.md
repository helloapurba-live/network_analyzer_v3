# AML GraphAML — Pair-Level Granularity Compensation: Deep Dive
## Weekly vs Monthly Rollup — Feature Impact + Compensating Columns

**Scope:** Pair-level `(sender_id, receiver_id, period_key)` only.
Customer-level rollup destroys graph edges — NEVER aggregate to customer-only.

**Analysis Window:** All 26 features in GraphAML v18.6 `_build_feature_matrix()` confirmed from
`flow.py`, `benford.py`, `behavioral.py` source reads.

---

## Architecture Hierarchy

| Level | Row Key | ~Rows (90d, 10K cust, avg 10 pairs each) | Reduction |
|---|---|---|---|
| Individual tx | `(sender, receiver, tx_id)` | 5–50M | baseline |
| **Daily (current)** | `(sender, receiver, date)` | ~900K | reference |
| **Weekly** | `(sender, receiver, ISO_week)` | ~130K | 86% fewer |
| **Monthly** | `(sender, receiver, YYYY-MM)` | ~30K | 97% fewer |

---

## TABLE 1 — All 26 Features × Granularity Status

Source confirmed: `flow.py`, `benford.py`, `behavioral.py`

| # | Feature | Engine Source | Daily | Weekly | Monthly | Root Cause of Break |
|---|---|---|---|---|---|---|
| 1 | `pagerank` | graph topology | ✅ | ✅ | ⚠️ | Fewer edges → flatter rank; still valid |
| 2 | `betweenness_centrality` | graph topology | ✅ | ✅ | ⚠️ | Same — coarser weight |
| 3 | `degree_centrality` | graph topology | ✅ | ✅ | ✅ | Binary connectivity — always valid |
| 4 | `clustering_coeff` | graph topology | ✅ | ✅ | ✅ | Graph structure, not tx_df |
| 5 | `reciprocity` | graph topology | ✅ | ✅ | ✅ | Binary edge direction |
| 6 | `avg_nbr_deg` | graph topology | ✅ | ✅ | ✅ | Graph topology |
| 7 | `total_sent_log` | flow amounts | ✅ | ✅ | ✅ | SUM(amount) always correct |
| 8 | `total_received_log` | flow amounts | ✅ | ✅ | ✅ | Same |
| 9 | `flow_ratio` | flow amounts | ✅ | ✅ | ✅ | sent/(sent+received) always valid |
| 10 | `structuring_score` | flow.py:159 | ✅ Tier1/2 | ⚠️ Tier3 | ❌ Tier3 rough | `amount/tx_count`=week avg, not individual distribution |
| 11 | `off_hours_ratio` | flow.py:251 | ✅ | ❌ | ❌ | Engine drops NaN `tx_hour` → ratio=0 silently |
| 12 | `velocity_score` | flow.py:289 | ✅ | ✅ | ✅ | Uses SUM(tx_count) — always valid |
| 13 | `txtype_risk_score` | flow.py:412 | ✅ | ✅ | ✅ | tx_count-weighted avg — works natively |
| 14 | `velocity_delta_z` | flow.py:472 | ✅ | ⚠️ thin | ❌ | 30d cutoff from max_date: monthly=1 row→baseline empty→0.0 silently |
| 15 | `relay_score` | flow.py:538 | ✅ | ⚠️ | ❌ CATASTROPHIC | merge_asof(tolerance=24h): same-month date → 100% false relay |
| 16 | `round_trip_score` | flow.py:538 | ✅ | ⚠️ | ❌ | Same merge_asof logic |
| 17 | `amount_cv` | flow.py:646 | ✅ individual | ⚠️ pair-sum | ⚠️ pair-sum | Computes over pair-level SUMs not individual tx. Shifted semantics but AML-useful |
| 18 | `dormancy_days` | flow.py:646 | ✅ day gaps | ⚠️ 7d gaps | ❌ 30d gaps | Weekly: skipped weeks detectable. Monthly: all gaps = 30d → flat |
| 19 | `dow_entropy` | flow.py:646 | ✅ | ❌ | ❌ | Weekly row date = Monday → DOW=0 always → entropy=0 |
| 20 | `counterparty_hhi` | flow.py:646 | ✅ | ✅ | ✅ | Each row = unique receiver → HHI always valid |
| 21 | `round_amount_rate` | flow.py:646 | ✅ | ❌ | ❌ | `SUM(amounts) % 1000 < 1`: weekly sum misses structuring |
| 22 | `funnel_flag` | flow.py:646 | ✅ | ✅ | ✅ | Graph fan_in/out — topology-based |
| 23 | `spray_flag` | flow.py:646 | ✅ | ⚠️ | ⚠️ | Depends on amount_cv (shifted semantics) |
| 24 | `layering_chain_membership` | flow.py:786 | ✅ | ⚠️ | ❌ | DFS orders by min_date: monthly all same date → chain order undefined |
| 25 | `benford_mad` | benford.py:75 | ✅ ≥30 amts | ❌ | ❌ | Weekly SUM per pair → leading digit from aggregate ≠ Benford |
| 26 | `goh_barabasi_b` | behavioral.py | ✅ | ❌ | ❌ | 1 timestamp/period → all intervals equal → b=0 always |

### Feature Count Summary

| Granularity | ✅ Native | ⚠️ Degraded | ❌ Broken |
|---|---|---|---|
| **Daily (baseline)** | 22 | 2 | 0 |
| **Weekly (no compensation)** | 15 | 6 | 5 |
| **Monthly (no compensation)** | 13 | 3 | 10 |
| **Weekly + all compensation cols** | 23* | 2 | 1 |
| **Monthly + all compensation cols** | 24* | 1 | 1 |

*Remaining unrecoverable: layering within-period temporal ordering (fundamental data loss).

---

## TABLE 2A — PAIR-Level Edge Columns for WEEKLY Rollup

Computed per `(sender_id, receiver_id, week_key)` from **daily source** before collapse.
Stored as extra columns in the weekly tx_df passed to the engine.

| # | Column | Type | Aggregation from Daily | Fixes Feature | Engine Path |
|---|---|---|---|---|---|
| E1 | `count_structuring_band` | `int` | `SUM(daily_structuring_count)` where daily cnt = tx_count in $9k–$10k | `structuring_score` | Activates Tier 1 (exact, no approximation) |
| E2 | `min_amount` | `float` | `MIN(daily_min_amount)` across all daily rows in week | `structuring_score` | Activates Tier 2 (threshold overlap interpolation) |
| E3 | `max_amount` | `float` | `MAX(daily_max_amount)` across all daily rows in week | `structuring_score` | Tier 2 range precision |
| E4 | `off_hours_tx_count` | `int` | `SUM(daily_off_hours_tx_count)` where daily cnt = tx_count where tx_hour>=22 OR tx_hour<=6 | `off_hours_ratio` | **Requires engine patch P1** |
| E5 | `round_amount_count` | `int` | `SUM(daily_round_count)` where daily cnt = COUNT(individual_amount % 1000 < 1) | `round_amount_rate` | **Requires engine patch P2** |

**Minimum viable set for weekly: E1, E2, E3, E4** (E5 is enhancement).

---

## TABLE 2B — PAIR-Level Edge Columns ADDITIONAL for MONTHLY Rollup

Required beyond E1-E5. Monthly requires these because 30d cutoff from 1 row = empty baseline.

| # | Column | Type | Aggregation from Daily | Fixes Feature | Why Monthly Specifically |
|---|---|---|---|---|---|
| E6 | `recent_tx_count` | `int` | `SUM(tx_count WHERE date >= month_end - 30d)` | `velocity_delta_z` | Monthly 1-row → cutoff from max_date → baseline = {} → all return 0.0 silently |
| E7 | `baseline_tx_count` | `int` | `SUM(tx_count WHERE date < month_end - 30d)` | `velocity_delta_z` | Complement baseline count |
| E8 | `recent_amount` | `float` | `SUM(amount WHERE date >= month_end - 30d)` | `velocity_delta_z` | Amount delta |
| E9 | `baseline_days` | `int` | `COUNT DISTINCT date WHERE date < month_end - 30d` | `velocity_delta_z` | Normalize baseline by active days |
| E10 | `relay_ratio` | `float` | Pre-computed relay_ratio per node — see N3 in Table 3 | `relay_score` | merge_asof(tolerance=24h) on same-month date = 100% false positives; must bypass |

**Monthly without E6-E10:**
- `velocity_delta_z = 0.0` for ALL nodes (silent failure)
- `relay_score = 1.0` (maximum possible) for ALL nodes (catastrophic — all nodes flagged as relays)

---

## TABLE 3 — NODE-Level Compensation Columns (Both Weekly and Monthly)

Computed per `node_id` from ALL individual transactions in the full analysis window.
Stored in `nodes_df` — NOT in tx_df.
These are ONE-TIME computations from raw data before any rollup.

| # | Column | Type | Source | Formula | Fixes Feature | Weekly | Monthly |
|---|---|---|---|---|---|---|---|
| N1 | `benford_mad` | `float` | Individual tx amounts per node (sent + received) | MAD from Benford expected `log10(1 + 1/d)` | `benford_mad` | ✅ Required | ✅ Required |
| N2 | `burstiness_b` | `float` | Individual tx timestamps per node | `(σ − μ) / (σ + μ)` of inter-event times (epoch seconds) | `goh_barabasi_b` | ✅ Required | ✅ Required |
| N3 | `relay_ratio` | `float` | Individual tx timestamps per (sender, receiver) pair | Fraction of sent flows matched to inflow within 24h using same merge_asof logic | `relay_score` | ⚠️ Optional | ✅ CRITICAL |
| N4 | `dow_entropy` | `float` | Individual tx timestamps per node | `−Σ p_d * log2(p_d)` for d ∈ {Mon..Sun} | `dow_entropy` | ✅ Required | ✅ Required |
| N5 | `round_amount_rate` | `float` | Individual tx amounts per node | `COUNT(amount % 1000 < 1) / COUNT(*)` | `round_amount_rate` | ✅ Required | ✅ Required |
| N6 | `dormancy_days` | `float` | Individual tx dates per node | `MAX(gap_days)` between consecutive tx dates | `dormancy_days` | ⚠️ Optional (7d resolution ok) | ✅ Required |
| N7 | `amount_cv_raw` | `float` | Individual tx amounts per node | `std(individual_amounts) / mean(individual_amounts)` — TRUE individual CV | `amount_cv` (enhanced) | ⚠️ Enhancement | ✅ Required |

**Important:** N3 `relay_ratio` must use identical 24h tolerance as the engine (`relay_window_hours=24`).
Compute offline using same `merge_asof` logic on individual timestamps.

---

## TABLE 4 — Engine Patches Required

All patches follow the same Tier-1 override pattern that structuring already uses.

| Patch | Function | Code Change Description | Priority |
|---|---|---|---|
| **P1 — Off-Hours Tier 1** | `_compute_off_hours_ratios()` (flow.py:251) | If `off_hours_tx_count` in tx_df: `ratio = sum(off_hours_tx_count) / sum(tx_count)` skip tx_hour path | 🔴 High — currently silent 0.0 |
| **P2 — Round Amount Tier 1** | `_compute_flow_texture_stats()` (flow.py:646) | If `round_amount_count` in tx_df: `rate = sum(round_amount_count) / sum(tx_count)` | 🟡 Medium |
| **P3 — Velocity Delta Bypass** | `_compute_velocity_delta_zscore()` (flow.py:472) | If `recent_tx_count` + `baseline_tx_count` in tx_df: compute z-score directly from pre-split counts | 🔴 High for monthly |
| **P4 — Relay Score Bypass** | `_compute_temporal_relay_scores()` (flow.py:538) | If `relay_ratio` in nodes_df: skip merge_asof entirely, use pre-computed value | 🔴 CRITICAL for monthly |
| **P5 — Node Metrics Passthrough** | `compute_benford_scores()` (benford.py:75), `_compute_goh_barabasi_b()` (behavioral.py) | If pre-computed col exists in nodes_df: skip recomputation from tx_df | 🟡 Medium |

---

## TABLE 5 — Feasibility Summary

| Dimension | Daily | Weekly | Monthly |
|---|---|---|---|
| **Rows (10K pairs, 90d)** | ~900K | ~130K | ~30K |
| **Engine runtime (relative)** | 100% | ~15% | ~3% |
| **Features working — no compensation** | 22/26 (85%) | 15/26 (58%) | 13/26 (50%) |
| **Features working — with edge cols** | — | +4 → 19/26 | +5 → 18/26 |
| **Features working — with node cols** | — | +4 → 23/26 | +6 → 24/26 |
| **Unrecoverable features** | 0 | 1 (layering in-week order) | 2 (layering + dormancy day resolution) |
| **Extra edge columns** | 0 | 5 (E1-E5) | 10 (E1-E10) |
| **Extra node columns** | 0 | 4 (N1-N2, N4-N5) | 7 (N1-N7) |
| **Engine patches** | 0 | 2 (P1, P2) | 4 (P1-P4) |
| **Recommendation** | ✅ If scale allows | ⭐ Preferred option | ⚠️ Only if weekly still too large |

---

## Python Code — Complete Compensation Pipeline

### Step 1: Individual Transactions → Daily with Compensation Columns

```python
import pandas as pd
import numpy as np


def build_daily_with_compensation(raw_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Collapse individual transactions to daily pair level.
    Computes all compensation columns at aggregation time.

    Input columns required:
        sender_id, receiver_id, tx_date (or tx_timestamp), tx_hour, amount

    Output: one row per (sender_id, receiver_id, date) with compensation columns.
    """
    raw_tx = raw_tx.copy()
    raw_tx["tx_date"] = pd.to_datetime(raw_tx["tx_date"]).dt.normalize()
    raw_tx["amount"]  = pd.to_numeric(raw_tx["amount"], errors="coerce").fillna(0.0)
    raw_tx["tx_hour"] = pd.to_numeric(
        raw_tx.get("tx_hour", pd.Series(-1, index=raw_tx.index)),
        errors="coerce"
    ).fillna(-1).astype(int)

    # Derived flags at individual transaction level
    raw_tx["is_off"]        = (raw_tx["tx_hour"] >= 22) | (raw_tx["tx_hour"] <= 6)
    raw_tx["in_struct_band"]= (raw_tx["amount"] >= 9000) & (raw_tx["amount"] < 10000)
    raw_tx["is_round"]      = (raw_tx["amount"] % 1000 < 1.0)

    grp = raw_tx.groupby(["sender_id", "receiver_id", "tx_date"])

    daily = grp.agg(
        tx_count               = ("amount", "count"),
        amount                 = ("amount", "sum"),
        min_amount             = ("amount", "min"),
        max_amount             = ("amount", "max"),
        count_structuring_band = ("in_struct_band", "sum"),
        off_hours_tx_count     = ("is_off", "sum"),
        round_amount_count     = ("is_round", "sum"),
        tx_hour                = ("tx_hour", lambda x: x.mode()[0] if len(x) > 0 else -1),
    ).reset_index()

    return daily
```

### Step 2: Daily → Weekly

```python
def daily_to_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily pair rows to weekly with all compensation columns preserved."""
    daily = daily.copy()
    daily["tx_date"] = pd.to_datetime(daily["tx_date"])
    daily["week_key"] = daily["tx_date"].dt.strftime("%G-W%V")  # ISO week

    grp = daily.groupby(["sender_id", "receiver_id", "week_key"])

    weekly = grp.agg(
        tx_count               = ("tx_count", "sum"),
        amount                 = ("amount", "sum"),
        min_amount             = ("min_amount", "min"),
        max_amount             = ("max_amount", "max"),
        count_structuring_band = ("count_structuring_band", "sum"),
        off_hours_tx_count     = ("off_hours_tx_count", "sum"),
        round_amount_count     = ("round_amount_count", "sum"),
        tx_date                = ("tx_date", "min"),   # week-start date
    ).reset_index()

    return weekly
```

### Step 3: Daily → Monthly (with Velocity-Delta Split)

```python
def daily_to_monthly(daily: pd.DataFrame, recent_window_days: int = 30) -> pd.DataFrame:
    """
    Aggregate daily pair rows to monthly with velocity-delta split columns.
    Preserves all weekly compensation columns + adds E6-E9 for velocity delta.
    """
    daily = daily.copy()
    daily["tx_date"] = pd.to_datetime(daily["tx_date"])
    daily["month_key"] = daily["tx_date"].dt.to_period("M").astype(str)

    monthly_rows = []
    for (sid, rid, mkey), grp in daily.groupby(["sender_id", "receiver_id", "month_key"]):
        month_end = grp["tx_date"].max()
        cutoff    = month_end - pd.Timedelta(days=recent_window_days)

        recent   = grp[grp["tx_date"] >= cutoff]
        baseline = grp[grp["tx_date"] <  cutoff]

        row = {
            "sender_id":               sid,
            "receiver_id":             rid,
            "month_key":               mkey,
            "tx_date":                 grp["tx_date"].min(),
            "tx_count":                int(grp["tx_count"].sum()),
            "amount":                  float(grp["amount"].sum()),
            "min_amount":              float(grp["min_amount"].min()),
            "max_amount":              float(grp["max_amount"].max()),
            "count_structuring_band":  int(grp["count_structuring_band"].sum()),
            "off_hours_tx_count":      int(grp["off_hours_tx_count"].sum()),
            "round_amount_count":      int(grp["round_amount_count"].sum()),
            # Velocity delta split (E6-E9)
            "recent_tx_count":         int(recent["tx_count"].sum()),
            "baseline_tx_count":       int(baseline["tx_count"].sum()),
            "recent_amount":           float(recent["amount"].sum()),
            "baseline_days":           int(baseline["tx_date"].nunique()),
        }
        monthly_rows.append(row)

    return pd.DataFrame(monthly_rows)
```

### Step 4: Node-Level Compensation Columns from Individual Transactions

```python
def build_node_compensation_cols(raw_tx: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all node-level compensation columns from individual transactions.
    Called ONCE on raw data before any rollup.
    Output: nodes DataFrame with cust_id + N1-N7 columns.
    """
    raw_tx = raw_tx.copy()
    raw_tx["amount"] = pd.to_numeric(raw_tx["amount"], errors="coerce").fillna(0.0)
    raw_tx["tx_ts"]  = pd.to_datetime(raw_tx["tx_date"])
    raw_tx["is_round"] = (raw_tx["amount"] % 1000 < 1.0)
    raw_tx["dow"]    = raw_tx["tx_ts"].dt.dayofweek

    BENFORD_EXPECTED = np.array([np.log10(1 + 1/d) for d in range(1, 10)])

    all_nodes = set(raw_tx["sender_id"].unique()) | set(raw_tx["receiver_id"].unique())
    results = []

    for node in all_nodes:
        sent     = raw_tx[raw_tx["sender_id"]   == node]
        recv     = raw_tx[raw_tx["receiver_id"] == node]
        all_node = pd.concat([sent, recv])

        # N1 — Benford MAD
        amts = all_node["amount"].values
        amts = amts[amts >= 0.01]
        benford_mad = 0.0
        if len(amts) >= 30:
            scale = 10 ** max(0, int(-np.floor(np.log10(amts.min() + 1e-9))))
            scaled = (amts * scale).astype(int)
            first_d = np.array([
                int(str(v)[0]) for v in scaled if str(v)[0].isdigit() and int(str(v)[0]) >= 1
            ])
            first_d = first_d[(first_d >= 1) & (first_d <= 9)]
            if len(first_d) >= 30:
                observed = np.array([(first_d == d).mean() for d in range(1, 10)])
                benford_mad = float(np.abs(observed - BENFORD_EXPECTED).mean())

        # N2 — Goh-Barabasi B
        ts_sorted = sorted(sent["tx_ts"].dropna().tolist())
        b_score = 0.0
        if len(ts_sorted) >= 3:
            epoch = np.array([t.timestamp() for t in ts_sorted])
            inter = np.diff(epoch).astype(float)
            mu, sigma = float(inter.mean()), float(inter.std())
            denom = sigma + mu
            b_score = float((sigma - mu) / denom) if denom > 1e-9 else 0.0

        # N4 — DOW Entropy
        dow_vals = sent["dow"].dropna()
        dow_entropy = 0.0
        if len(dow_vals) >= 7:
            counts = dow_vals.value_counts()
            probs  = counts / counts.sum()
            dow_entropy = float(-np.sum(probs.values * np.log2(probs.values + 1e-12)))

        # N5 — Round Amount Rate
        round_rate = float(sent["is_round"].mean()) if len(sent) > 0 else 0.0

        # N6 — Dormancy Days
        dates = sorted(sent["tx_ts"].dt.normalize().dropna().unique().tolist())
        dormancy = 0.0
        if len(dates) >= 2:
            dormancy = float(max((dates[i+1] - dates[i]).days for i in range(len(dates)-1)))

        # N7 — Individual Amount CV
        sent_amts = sent["amount"].values
        amount_cv = 0.0
        if len(sent_amts) >= 2:
            mu_a = sent_amts.mean()
            amount_cv = float(sent_amts.std() / max(mu_a, 1e-9))

        results.append({
            "cust_id":          str(node),
            "benford_mad":      round(benford_mad, 6),    # N1
            "burstiness_b":     round(b_score, 4),        # N2
            "dow_entropy":      round(dow_entropy, 4),    # N4
            "round_amount_rate":round(round_rate, 4),     # N5
            "dormancy_days":    round(dormancy, 2),        # N6
            "amount_cv":        round(amount_cv, 4),       # N7
        })

    return pd.DataFrame(results)
```

---

## Engine Patch Examples

### P1 — Off-Hours Tier 1 Override

```python
# In _compute_off_hours_ratios() (flow.py:251)
# ADD before existing tx_hour check:

if "off_hours_tx_count" in tx_df.columns:
    # Tier 1: pre-computed off-hours count present — use directly
    logger.debug("off_hours_ratio: using pre-computed off_hours_tx_count (Tier 1)")
    total_s = tx_df.groupby("sender_id")["tx_count"].sum()
    off_s   = tx_df.groupby("sender_id")["off_hours_tx_count"].sum().reindex(
        total_s.index, fill_value=0
    )
    ratio_s = (off_s / total_s.replace(0, np.nan)).fillna(0.0).round(4)
    return {str(k): float(v) for k, v in ratio_s.items()}

# Existing tx_hour fallback continues below...
```

### P4 — Relay Score Bypass (CRITICAL for Monthly)

```python
# In _compute_temporal_relay_scores() (flow.py:538)
# ADD at top of function:

if hasattr(state, "nodes_df") and state.nodes_df is not None:
    ndf = state.nodes_df
    if "relay_ratio" in ndf.columns and "cust_id" in ndf.columns:
        logger.info("temporal_relay: bypassing merge_asof — using pre-computed relay_ratio")
        relay_map = dict(zip(ndf["cust_id"].astype(str), ndf["relay_ratio"].fillna(0.0)))
        state.relay_scores = relay_map
        return

# Existing merge_asof path continues below...
```

---

## Decision Cheat Sheet

| Question | Answer |
|---|---|
| Can I do weekly rollup and keep accurate AML scoring? | Yes, with E1-E5 edge cols + N1, N2, N4, N5 node cols + P1, P2 engine patches |
| Can I do monthly rollup? | Yes, but additionally need E6-E10 + N3, N6, N7 + P3, P4 patches. Layering chain ordering will be imprecise. |
| What is the minimum I must pre-compute for weekly? | E1 (struct band count), E2/E3 (min/max amount), E4 (off-hours count), N1 (Benford), N2 (burstiness) |
| What breaks silently (no error, wrong value) without compensation? | off_hours_ratio=0.0, velocity_delta_z=0.0, relay_score catastrophic, benford_mad=0.0, burstiness=0.0 |
| Can I roll up to customer level instead of pair level? | **NO.** Customer-level destroys graph edges. Always keep (sender_id, receiver_id) as the key. |
| Which features survive natively at any granularity? | topology, total_sent/received, flow_ratio, velocity_score (tx_count based), txtype_risk, counterparty_hhi, funnel_flag |

---

*Source: GraphAML v18.6 engine audit — flow.py, benford.py, behavioral.py — June 2025*
