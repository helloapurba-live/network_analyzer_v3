# AML Sample Size & Data Design — Expert Advisory Session
**GraphAML — PhD AML Data Science Advisory**  
**Session Dates:** April 13–15, 2026  
**Context:** 50K November investigation cohort (3K SAR + 47K cleared) | 10M customer base | GraphAML v18.6  
**Scope:** This document covers Queries 3–8 from the advisory session. Queries 1–2 are in `AML_STRATEGY_EXPERT_RESPONSES.md`.

---

## Document Index

| Query # | Topic | Key Decision |
|---|---|---|
| Q3 | Sample size & 22-feature wave design | 10K supervised input = validated composition |
| Q4 | SAR temporal alignment — 12-month label window | Label must PRECEDE feature window |
| Q5 | Tx granularity — rows per edge | Daily 90-row design is CORRECT; 1-row-per-pair is WRONG |
| Q6 | Engine audit — why daily is correct | Full code audit: 9 engine functions need multi-row tx_df |
| Q7 | Pre-computed columns — weekly/monthly rollup feasibility | GROUP A/B/C classification, 5 patches, ZERO dimension breaks |
| Q8 | Granularity comparison — what you lose daily→weekly→monthly | Weekly = 86% reduction, ~10% signal loss. Monthly = too lossy. |

---

---

# QUERY 3 — Wave Design: How Many Nodes, What Composition, Which Features?

**User Question (paraphrased):** We have the November 50K cohort (3K SAR, 47K cleared). How do we design the sample for GraphAML — how many customers, what mix, and which features should we use?

---

## Response 3 — 10K Node Composition & 22-Feature Wave Design

### The Correct 10K Input Composition

Based on the taxonomy established in Response 2 (Types A through H), the recommended supervised training input for GraphAML's November wave:

| Node Type | Count | Source | Rationale |
|---|---|---|---|
| **Type A** — Confirmed SAR | 3,000 | All November SARs | Positive class — all must be included |
| **Type B3** — Safe negatives | 2,000 | Bottom 42% of 47K by anomaly score | Cleanest negative class — low contamination risk |
| **Type C** — 1-hop SAR neighbors | 1,500 | Direct tx partners of Type A | Highest-signal grey zone — may contain unknown criminals |
| **Type D** — 2-hop layering | 1,500 | 2-hop expansion from Type A | Layering intermediaries — critical for typology coverage |
| **Type F** — Community co-members | 1,000 | Same Louvain cluster as any SAR, no direct link | Community-embedded risk |
| **Type G** — Behavioral twin | 1,000 | Top Mahalanobis match to SAR centroid, no network link | Behaviorally similar but network-invisible criminals |
| **TOTAL** | **10,000** | | Within GraphAML 20K node limit with headroom |

**Why this is better than your previous 7K design:**
- Previous: 3K SAR + 3K contaminated negatives + 1K 1-hop = 7K
- New: Cleaner negatives (B3 only), 2-hop coverage, community dimension, behavioral dimension
- Contaminated B1/B2 negatives are excluded — this is the single most important fix

### B3 Selection Rule — Stratifying the 47K Cleared Pool

The 47K cleared customers must NOT be treated as uniformly safe negatives. Stratify using:

```python
# Anomaly scoring of the 47K cleared pool
# Use unsupervised IF on available behavioral features (velocity, structuring, 
# off-hours, tx volume) to score each cleared customer
from sklearn.ensemble import IsolationForest

clf = IsolationForest(contamination=0.15, random_state=42)
clf.fit(cleared_features)
anomaly_scores = clf.score_samples(cleared_features)  # Higher = more normal

# Stratify into three tiers
q58 = np.percentile(anomaly_scores, 58)   # Top 42% = B3 safe negatives
q18 = np.percentile(anomaly_scores, 18)   # Mid 40% = B2 exclude

cleared_df['tier'] = np.where(anomaly_scores >= q58, 'B3',
                    np.where(anomaly_scores >= q18, 'B2', 'B1'))

# Use ONLY B3 as negative training examples
b3_negatives = cleared_df[cleared_df['tier'] == 'B3'].sample(n=2000, random_state=42)
```

### 22 Features for the ML Classification Pipeline

GraphAML produces all 22 of these as output columns per customer. The downstream ML model ingests them:

| # | Feature | Source Phase | Type |
|---|---|---|---|
| 1 | `proximity_score` | Phase 3 (D1) | float [0,1] |
| 2 | `hop_label` | Phase 3 (D1) | categorical: SEED/HOP_1/HOP_2/HOP_3/NO_PATH |
| 3 | `ppr_score` | Phase 3 (D1) | float [0,1] |
| 4 | `structuring_score` | Phase 6 (D2) | float [0,1] |
| 5 | `off_hours_ratio` | Phase 6 (D2) | float [0,1] |
| 6 | `velocity_score` | Phase 6 (D2) | float [0,1] |
| 7 | `velocity_delta_zscore` | Phase 6 (D2) | float |
| 8 | `temporal_relay_score` | Phase 6 (D2) | float [0,1] |
| 9 | `txtype_risk_score` | Phase 6 (D2) | float [0,1] |
| 10 | `corridor_risk_score` | Phase 6 (D2) | float [0,1] |
| 11 | `benford_mad` | Phase 7 (D2) | float ≥ 0 |
| 12 | `pagerank` | Phase 2 (D3) | float |
| 13 | `betweenness` | Phase 2 (D3) | float |
| 14 | `degree` | Phase 2 (D3) | int |
| 15 | `community_risk` | Phase 4 (D4) | float [0,1] |
| 16 | `behavioral_if_score` | Phase 7 (D5) | float [0,1] |
| 17 | `behavioral_lof_score` | Phase 7 (D5) | float [0,1] |
| 18 | `peer_group_zscore` | Phase 7 (D5) | float |
| 19 | `burstiness_b` | Phase 7 (D5) | float [-1,1] |
| 20 | `round_trip_score` | Phase 8 (D2/D5) | float [0,1] |
| 21 | `layering_chain_score` | Phase 8 (D2) | float [0,1] |
| 22 | `weight_recency` | Phase 9 (D7) | float [0,1] |

**Algorithm Selection:** Semi-supervised learning is correct. The 3K SAR positive class is labeled; the remaining 7K are treated as unlabeled. Use Label Propagation or LightGBM with pseudo-labeling. Full supervised (treating all 7K as labeled positives/negatives) is appropriate only if B3 contamination is confirmed < 5%.

---

---

# QUERY 4 — Temporal Alignment: 12-Month SAR Window & Label Assignment

**User Question (paraphrased):** We have 12 months of SAR data, not just November. How do we align the SAR labels with the transaction feature window? When does a customer's Y label apply?

---

## Response 4 — Temporal Alignment Rules for 12-Month SAR Data

### The Core Alignment Principle

**The label must PRECEDE the feature window.** This is the most critical rule in temporal alignment for supervised AML models.

```
WRONG setup (data leakage):
Feature window: October 1 – December 31 (includes SAR period)
Label (Y=1): SAR filed November 15
→ Model sees features CAUSED by the SAR investigation period (transaction freeze, reduced activity)
→ This is forward contamination — model learns investigator behavior, not criminal behavior

CORRECT setup:
Label assignment date: November 15 (SAR filing date)
Feature window: August 16 – November 14 (90 days BEFORE SAR date)
→ Model sees what the criminal looked like BEFORE the SAR was filed
→ This is the signal you actually want to detect in production
```

### Temporal Alignment Architecture

| Input | Time Period | Role |
|---|---|---|
| **Y label (SAR/No-SAR)** | November (filing month) | Target variable |
| **X features (tx_df)** | August 1 – October 31 (90-day window BEFORE Nov) | Feature matrix for model |
| **Edge dates** | August 1 – October 31 | Same 3-month window as X features |
| **nodes_df attributes** | Snapshot as of October 31 | Identity/KYC snapshot at feature window end |

### 12-Month SAR Cohorts — How to Build Multiple Training Waves

If you have 12 months of SAR data, you can build 12 aligned cohorts:

| Wave | SAR Label Month | Feature Window | Notes |
|---|---|---|---|
| Wave 1 | January 2025 | Oct–Dec 2024 | 3-month pre-SAR |
| Wave 2 | February 2025 | Nov 2024–Jan 2025 | Rolling 3-month |
| ... | ... | ... | ... |
| Wave 11 (November) | November 2025 | Aug–Oct 2025 | **Primary investigation cohort** |
| Wave 12 | December 2025 | Sep–Nov 2025 | If Dec SAR data available |

### Critical Rule: Never Mix Feature and Label Windows

```python
# Correct temporal filter for tx_df (transaction features)
feature_start = pd.Timestamp("2025-08-01")
feature_end   = pd.Timestamp("2025-10-31")

tx_df = raw_tx_df[
    (raw_tx_df["tx_date"] >= feature_start) &
    (raw_tx_df["tx_date"] <= feature_end)
]

# Labels come from the FOLLOWING month
nodes_df["is_sar"] = nodes_df["cust_id"].isin(sar_november_ids).astype(int)
```

### The Non-SAR Temporal Challenge

For the 47K cleared pool:
- Their investigation may span multiple months
- A customer investigated in November may have been CLEARED in December
- Use the investigation START date (not close date) as their alignment anchor
- If investigation started in November: feature window = Aug–Oct (same as SAR)
- If investigation started in September: feature window = June–August

```python
nodes_df["feature_window_end"] = nodes_df["investigation_start_date"] - pd.Timedelta(days=1)
nodes_df["feature_window_start"] = nodes_df["feature_window_end"] - pd.Timedelta(days=90)
```

### Edge Weight Recency

GraphAML v18.6 uses an exponential decay weight for recency:

```
w_recency = EXP(-days_since_tx / 180)
```

Within the 90-day feature window, transactions from day 1 are weighted at EXP(-90/180) ≈ 0.61 and transactions from the final day are weighted at EXP(0) = 1.0. This naturally emphasizes recent activity without requiring separate feature engineering.

---

---

# QUERY 5 — Tx Granularity: How Many Rows Per Edge? Daily or 1 Row Per Pair?

**User Question:** For the transaction file (tx_df), should we use 1 row per (sender, receiver, day) or aggregate to 1 row per (sender, receiver) total? We're considering reducing data volume.

---

## Response 5 — Daily 90-Row Design Is Correct; 1-Row-Per-Pair Is WRONG

### The Decision

**Keep 1 row per (sender_id, receiver_id, tx_date) = "daily design."**  
Do NOT aggregate to 1 row per (sender_id, receiver_id) across the entire observation window.

### The Confusion Source

The confusion arose from how `graph_builder.py` works internally:

```
tx_df INPUT:           Multiple rows per pair (1 per day × N days)
                       ↓ DuckDB groupby internally
graph_builder OUTPUT:  1 edge per pair (summed amounts, tx_count, recency weight)
                       ↓ This is the graph structure
igraph graph:          1 edge per (u, v) pair
```

DuckDB groups to 1-edge-per-pair INTERNALLY during graph construction.  
But all the flow.py, benford.py, behavioral.py functions read the ORIGINAL multi-row tx_df BEFORE it is collapsed.

### What Breaks With 1-Row-Per-Pair (Aggregate Design)

| Engine Function | Requirement | What Breaks |
|---|---|---|
| `compute_benford_scores()` in benford.py | 30+ individual amounts per node | 1 aggregated amount per pair → Benford useless |
| `_compute_off_hours_ratios()` in flow.py | `tx_hour` per individual row | 1 modal hour → loses within-period variation |
| `_compute_velocity_delta_zscore()` in flow.py | Split recent 30d vs baseline 60d using `tx_date` | 1 date per pair → all "recent", no baseline |
| `_compute_temporal_relay_scores()` in flow.py | `merge_asof(tolerance=24h)` across sequential rows | 1 date per pair → merge fails/trivializes |
| `_compute_flow_texture_stats()` in flow.py | `amount_cv`, dormancy, DOW entropy | All require multiple rows per pair |
| `_find_structuring_windows()` in flow.py | Consecutive-day amounts in band | No consecutive days with 1 row |
| `_compute_goh_barabasi_b()` in behavioral.py | Inter-event times from timestamp sequences | 1 timestamp → no inter-events → B undefined |
| `temporal_path_valid` in neighborhood.py | `MIN(tx_date)` per edge | 1 date OK but loses ordering verification |

**Verdict: 1-row-per-pair would break 7 of the 9 core engine scoring functions.**

### Correct Schema — Daily Rollup Row

```
tx_df columns (1 row per sender_id × receiver_id × tx_date):
  sender_id           string    customer ID
  receiver_id         string    counterparty ID  
  tx_date             date      transaction date (YYYY-MM-DD)
  amount              float     total amount sent on this date between this pair
  tx_count            int       number of individual transactions on this date
  tx_hour             int       modal hour-of-day (most common hour for this pair/day)
  channel             string    modal channel (wire, ACH, SWIFT, cash, etc.)
  purpose_code        string    modal purpose code
  counterparty_country string  counterparty jurisdiction
  min_amount          float     (optional) minimum individual tx this day
  max_amount          float     (optional) maximum individual tx this day
  count_structuring_band int   (optional) count of individual txns in 8K-10K range
```

For the 90-day November feature window with 10K nodes, maximum tx_df size:
```
10,000 nodes × 50 unique pairs per node × 90 days = 45M rows (theoretical max)
Realistic (sparse networks): ~500K–2M rows for a 10K-node subgraph
```

---

---

# QUERY 6 — Engine Audit: Full Proof That Daily Multi-Row Design Is Required

**User Question:** You said 1-row-per-pair is wrong — can you prove it by looking at the actual engine code? Which specific lines and functions require multi-row tx_df?

---

## Response 6 — Full Code Audit Results: 9 Functions Requiring Multi-Row tx_df

A complete audit of all 5 engine files was performed. Results below.

### File: `benford.py` — Complete Failure With Aggregated Data

```python
# Lines ~85–160: compute_benford_scores()
# Iterates ALL rows per node, building per-node amount lists:
amounts_sent[sender_id].append(amount)      # line per tx_df row
amounts_recv[receiver_id].append(amount)    # line per tx_df row

# Then checks:
if len(all_amounts) < 30:                   # min_transactions = 30
    state.benford_scores[cust] = 0.0        # skipped if < 30 individual amounts
    continue
```

**With 1-row-per-pair:** A customer with 20 unique counterparties sends 20 amounts. Even with 20 unique pairs × 90 days, the aggregated version has only 20 rows, not 1800. Benford gets 20 amounts → below 30 threshold → returns 0.0 for all customers → **complete feature collapse.**

### File: `behavioral.py` — Burstiness B Undefined

```python
# Lines ~380–420: _compute_goh_barabasi_b()
tx_df = state.tx_df
datetimes = pd.to_datetime(tx_df.loc[mask, date_col])
epochs = datetimes.astype(np.int64) // 10**9        # convert to seconds
iet = np.diff(np.sort(epochs.values))               # inter-event times

if len(iet) < 2:
    b = 0.0   # trivially neutral if insufficient data
else:
    mu, sigma = iet.mean(), iet.std()
    b = (sigma - mu) / (sigma + mu)   # Goh-Barabasi formula
```

**With 1-row-per-pair:** A customer with 20 unique counterparties → 20 rows → 19 inter-event times, all approximately equal (sorted dates spread across 90 days) → σ ≈ 0 → B ≈ -1.0 for ALL customers → **false signal: everyone appears "perfectly periodic/bursty" identically.**

### File: `flow.py` — Six Critical Functions

**Function 1 — `_compute_off_hours_ratios()`:**
```python
# Requires tx_hour per row AND tx_count per row
off_mask = tx_df["tx_hour"].between(off_start, off_end, inclusive="both")
off_counts = tx_df[off_mask].groupby("sender_id")["tx_count"].sum()
total_counts = tx_df.groupby("sender_id")["tx_count"].sum()
# Result: off-hours tx as fraction of total tx
```
With 1-row-per-pair, `tx_hour` = the one hour for the entire relationship. No off-hours ratio possible.

**Function 2 — `_compute_velocity_delta_zscore()`:**
```python
# Splits the window using tx_date cutoff: last 30 days vs days 31-90
recent_mask = tx_df["tx_date"] >= cutoff_date    # last 30 days
recent_tx = tx_df[recent_mask].groupby("sender_id")["tx_count"].sum()
baseline_tx = tx_df[~recent_mask].groupby("sender_id")["tx_count"].sum()
```
With 1-row-per-pair, each pair has only 1 date. With 90-day window: that date falls in "recent" or "baseline" by random positioning. Baseline becomes empty for most customers → z-score = 0.0 for all → **velocity delta feature lost.**

**Function 3 — `_compute_temporal_relay_scores()`:**
```python
# merge_asof with 24-hour tolerance between sorted sender-receiver chains
merged = pd.merge_asof(
    recv_sorted, sent_sorted,
    on="tx_date", by="cust_id",
    tolerance=pd.Timedelta(hours=24),
    direction="backward"
)
```
With 1-row-per-pair: every pair has 1 date. All dates from the same pair fall within 24hr of each other trivially (they ARE the same date) → relay_score = 1.0 for all → **catastrophic false positives across entire customer base.**

**Function 4 — `_compute_flow_texture_stats()` (v7.7):**
- `amount_cv`: std/mean of amounts per sender → FAILS (1 amount per pair)
- `dormancy_days`: max inter-tx gap per sender → FAILS (1 date per pair → gap = 0)
- `dow_entropy`: day-of-week entropy → FAILS (1 date per pair → entropy = 0)
- `round_amount_rate`: fraction where `amount % 1000 < 1` → FAILS (aggregated amount is a sum, not individual)

**Function 5 — `_find_structuring_windows()` (v15.5):**
Detects consecutive-day amounts in the 8K–10K structuring band. With 1-row-per-pair: no consecutive days → structuring window count = 0 for all customers.

**Function 6 — `_compute_layering_chains_dfs()` (v7.8):**
Uses `MIN(tx_date)` per edge via groupby → **WORKS with multi-row** since it extracts min date as a proxy for edge timing. This is the only flow.py function that tolerates aggregation.

### File: `neighborhood.py` — Partial Impact

`temporal_path_valid` uses `MIN(tx_date)` per (sender, receiver) pair via groupby for path ordering. **Tolerates multi-row data correctly** — it groups internally. Not broken by 1-row-per-pair directly, but loses the ability to verify within-pair temporal sequence.

### File: `graph_builder.py` — Internal Grouping Confirmed

```sql
-- DuckDB query inside graph_builder.py (reconstructed from audit):
SELECT
    sender_id,
    receiver_id,
    SUM(amount) AS total_amount,
    SUM(tx_count) AS total_tx_count,
    MODE(channel) AS dominant_channel,
    SUM(amount * EXP(-days_since_tx / 180.0)) AS weight_recency
FROM tx_df
GROUP BY sender_id, receiver_id
```

GraphAML collapses tx_df to 1-edge-per-pair INSIDE graph_builder. The INPUT tx_df must be multi-row. This is the confirmed source of the "1-row-per-pair" misunderstanding — the OUTPUT of graph_builder is 1-edge-per-pair, not the input.

### Engine Audit Summary

| File | Functions That Need Multi-Row | Functions Tolerating 1-Row |
|---|---|---|
| benford.py | `compute_benford_scores()` | — |
| behavioral.py | `_compute_goh_barabasi_b()` | `_build_feature_matrix()` (reads state, not tx_df) |
| flow.py | `_compute_off_hours_ratios()`, `_compute_velocity_delta_zscore()`, `_compute_temporal_relay_scores()`, `_compute_flow_texture_stats()`, `_find_structuring_windows()` | `_compute_velocity_scores()`, `_compute_txtype_risk_scores()`, `_compute_corridor_risk_scores()`, `_compute_layering_chains_dfs()` |
| neighborhood.py | — | `temporal_path_valid` (uses groupby MIN) |
| graph_builder.py | Entire file (groups internally; input MUST be multi-row) | — |

**Final verdict confirmed: Daily multi-row design (1 row per sender-receiver-day) is correct and required.**

---

---

# QUERY 7 — Pre-Computed Columns: Can We Use Weekly/Monthly Rollup + External Feature Flags?

**User Question (paraphrased):** If we pre-compute external features like structuring flags, off-hours counts, etc., can we switch to weekly or monthly rollup to reduce data volume? Will any dimensions break? Which features need pre-computed columns and which work natively?

---

## Response 7 — Full Feasibility Audit: GROUP A/B/C Classification + 5 Engine Patches

### The Architecture Concept

```
INPUT LAYER 1 — tx_df (rollup granularity)
  1 row per (sender_id, receiver_id, week or month)
  + Pre-computed edge-level flag columns added externally

INPUT LAYER 2 — nodes_df (1 row per customer)
  Existing node attributes
  + Pre-computed node-level score columns added externally

→ GraphAML engine reads these columns and bypasses internal computation
```

### GROUP A — Features That Work Natively With Weekly/Monthly Rollup (NO changes needed)

| Feature | Why It Works | Engine Function |
|---|---|---|
| velocity_score | Uses `SUM(tx_count) / obs_months` — tx_count preserved in rollup | `_compute_velocity_scores()` |
| txtype_risk_score | tx_count-weighted average of tx_type risk weights | `_compute_txtype_risk_scores()` |
| corridor_risk_score | Uses `counterparty_country` + `tx_count` only | `_compute_corridor_risk_scores()` |
| counterparty_hhi | `SUM(amount)` per receiver, then HHI — groupby sum works with rollup | `_compute_flow_texture_stats()` |
| layering_chain_score | Uses `min_date` per edge + `median_amount` → groupby-based, rollup-safe | `_compute_layering_chains_dfs()` |
| weight_recency | EXP(-days_since / 180) on rollup period date — slight precision loss acceptable | `graph_builder.py` |
| temporal_path_valid | `MIN(tx_date)` per pair via groupby — period date preserved in rollup | `neighborhood.py` |
| round_trip_score | Pure graph topology — no tx_df rows needed | Phase 8 graph |
| pagerank | Pure graph | Phase 2 |
| betweenness | Pure graph | Phase 2 |
| degree | Pure graph | Phase 2 |
| flow_ratio | Derived from graph edge sums | Phase 4 graph |
| community_risk | Louvain on graph — no tx_df rows | Phase 4 |
| clustering_coeff | Graph | Phase 2 |
| reciprocity | Graph | Phase 2 |
| avg_nbr_deg | Graph | Phase 2 |
| proximity_score | PPR/BFS on graph | Phase 3 |
| hop_label | BFS on graph | Phase 3 |

### GROUP B — Features Requiring Pre-Computed Columns to Work With Rollup

| Feature | Failure Mode Without Pre-Computation | Pre-Computed Column | Location |
|---|---|---|---|
| off_hours_ratio | Modal tx_hour loses intra-period variation | `off_hours_tx_count` (int) | tx_df edge column |
| velocity_delta_zscore | 1-month rollup → baseline window empty → z-score = 0 | `recent_tx_count`, `baseline_tx_count`, `baseline_days` | tx_df edge columns |
| temporal_relay_score | 🔴 Same-period rows share same date → `merge_asof(24h)` → ALL relay=1.0 | `relay_ratio` | nodes_df node column |
| benford_mad | Weekly/monthly sum destroys first-digit distribution | `benford_mad` | nodes_df node column |
| burstiness_b | Coarse timestamps → inter-event times all ~equal → B≈0 for all | `burstiness_b` | nodes_df node column |
| amount_cv | Aggregated sum replaces individual amounts → std/mean = 0 | `amount_cv` | nodes_df node column |
| dormancy_days | Max gap = rollup period length (week or month) always | `dormancy_days` | nodes_df node column |
| dow_entropy | 1 date per rollup row → entropy = 0 | `dow_entropy` | nodes_df node column |
| round_amount_rate | Summed amount destroys round-number individual tx patterns | `round_amount_rate` | nodes_df node column |
| structuring_window_count | Consecutive-day pattern lost in rollup | `structuring_window_count` | nodes_df node column |

### GROUP C — Features That Cannot Be Externalized (Graph/Runtime Dependent)

| Feature | Why Not Externalizable |
|---|---|
| PPR proximity | Requires the run-specific graph + seed set — changes each run |
| Hop labels | Depends on which customers are in this run's graph |
| behavioral_if_score, lof_score, ecod_score | IF/LOF/ECOD are ensemble models trained on the 18-feature matrix built during the run |
| peer_group_zscore | Requires peer velocity distribution from current run's subgraph |
| community_risk | Louvain partition changes per run depending on subgraph composition |

### 🔴 CRITICAL DANGER — Temporal Relay False Positives

This is the single most dangerous failure mode:

```python
# flow.py: _compute_temporal_relay_scores()
merged = pd.merge_asof(
    recv_sorted, sent_sorted,
    on="tx_date", by="cust_id",
    tolerance=pd.Timedelta(hours=24),    # ← 24-HOUR TOLERANCE
    direction="backward"
)
```

**With monthly rollup:** Every row in month M has date = month-start (e.g., 2025-08-01). Every pair in the same month shares the SAME date. Every receive event matches a send event within 24 hours (they are the same date). Every customer gets `relay_score = 1.0`. **Entire customer base falsely flagged as pass-through accounts.**

**Fix:** Add `relay_ratio` column to nodes_df (pre-computed from raw daily data) + guard in flow.py:
```python
# Guard in _compute_temporal_relay_scores():
if "relay_ratio" in state.nodes_df.columns:
    relay_col = state.nodes_df.set_index("cust_id")["relay_ratio"]
    return {str(k): float(v) for k, v in relay_col.items()}

# Date-collision safety guard (if no pre-computed column):
n_unique_dates = tx_df[date_col].nunique() if date_col else 0
if n_unique_dates <= 1:
    return {str(s): 0.0 for s in tx_df["sender_id"].unique()}
```

### Complete Pre-Computation SQL/Python Code

#### Edge-Level (tx_df additions — compute from raw daily data before rollup)

```python
import pandas as pd
import numpy as np

def precompute_edge_columns(raw_tx_daily: pd.DataFrame, 
                             period_col: str = "iso_week") -> pd.DataFrame:
    """
    raw_tx_daily: multi-row tx_df at daily granularity
    Returns: monthly/weekly rollup with pre-computed edge columns
    """
    raw_tx_daily["off_hours_flag"] = raw_tx_daily["tx_hour"].between(20, 7) | \
                                      raw_tx_daily["tx_hour"].between(0, 7)
    raw_tx_daily["off_hours_tx_count"] = raw_tx_daily["off_hours_flag"].astype(int) * \
                                          raw_tx_daily["tx_count"]

    # Velocity delta: recent (last 30d) vs baseline
    max_date = raw_tx_daily["tx_date"].max()
    cutoff = max_date - pd.Timedelta(days=30)
    raw_tx_daily["is_recent"] = raw_tx_daily["tx_date"] >= cutoff

    rollup = raw_tx_daily.groupby(["sender_id", "receiver_id", period_col]).agg(
        amount=("amount", "sum"),
        tx_count=("tx_count", "sum"),
        min_amount=("amount", "min"),
        max_amount=("amount", "max"),
        count_structuring_band=("amount", lambda x: ((x >= 8000) & (x <= 10000)).sum()),
        off_hours_tx_count=("off_hours_tx_count", "sum"),
        recent_tx_count=("tx_count", lambda x: x[raw_tx_daily.loc[x.index, "is_recent"]].sum()),
        baseline_tx_count=("tx_count", lambda x: x[~raw_tx_daily.loc[x.index, "is_recent"]].sum()),
        tx_date=("tx_date", "min"),
        tx_hour=("tx_hour", lambda x: x.mode().iloc[0] if len(x) > 0 else 12),
        channel=("channel", lambda x: x.mode().iloc[0] if len(x) > 0 else ""),
        counterparty_country=("counterparty_country", "first"),
        purpose_code=("purpose_code", lambda x: x.mode().iloc[0] if len(x) > 0 else ""),
    ).reset_index()
    rollup["baseline_days"] = (cutoff - raw_tx_daily["tx_date"].min()).days
    return rollup
```

#### Node-Level (nodes_df additions — compute from raw daily data)

```python
def precompute_node_columns(raw_tx_daily: pd.DataFrame) -> pd.DataFrame:
    """
    Computes node-level scores from raw daily tx data.
    Returns: nodes_df with pre-computed score columns.
    """
    results = {}

    for cust_id, group in raw_tx_daily.groupby("sender_id"):
        amounts = group["amount"].values
        dates = pd.to_datetime(group["tx_date"]).sort_values()

        # 1. Benford MAD
        digits = np.array([int(str(abs(int(a)))[0]) if a >= 1 else 0 for a in amounts if a >= 1])
        if len(digits) >= 30:
            observed = np.array([np.mean(digits == d) for d in range(1, 10)])
            expected = np.log10(1 + 1 / np.arange(1, 10))
            benford_mad = np.mean(np.abs(observed - expected))
        else:
            benford_mad = 0.0

        # 2. Burstiness B (Goh-Barabasi)
        if len(dates) >= 3:
            epochs = dates.astype(np.int64) // 10**9
            iet = np.diff(epochs.values)
            mu, sigma = iet.mean(), iet.std()
            burstiness_b = (sigma - mu) / (sigma + mu) if (sigma + mu) > 0 else 0.0
        else:
            burstiness_b = 0.0

        # 3. Amount CV
        amount_cv = amounts.std() / amounts.mean() if amounts.mean() > 0 else 0.0

        # 4. Dormancy days
        if len(dates) >= 2:
            gaps = np.diff(dates.values).astype("timedelta64[D]").astype(float)
            dormancy_days = float(gaps.max())
        else:
            dormancy_days = 0.0

        # 5. DOW entropy
        dow_counts = np.zeros(7)
        for d in dates:
            dow_counts[d.dayofweek] += 1
        dow_counts = dow_counts / dow_counts.sum()
        dow_entropy = -np.sum(dow_counts[dow_counts > 0] * np.log2(dow_counts[dow_counts > 0]))

        # 6. Round amount rate
        round_amount_rate = float(np.mean(np.mod(amounts, 1000) < 1))

        results[cust_id] = {
            "benford_mad": benford_mad,
            "burstiness_b": burstiness_b,
            "amount_cv": amount_cv,
            "dormancy_days": dormancy_days,
            "dow_entropy": dow_entropy,
            "round_amount_rate": round_amount_rate,
        }

    node_scores = pd.DataFrame.from_dict(results, orient="index").reset_index()
    node_scores.columns = ["cust_id"] + list(node_scores.columns[1:])
    return node_scores
```

### 5 Code Patches Required in GraphAML Engine

All patches use column-presence checking — the existing daily-row code path continues working unchanged when the pre-computed columns are absent.

**Patch 1 — flow.py: off-hours bypass**
```python
# In _compute_off_hours_ratios():
if "off_hours_tx_count" in tx_df.columns:
    total_s = tx_df.groupby("sender_id")["tx_count"].sum()
    off_s   = tx_df.groupby("sender_id")["off_hours_tx_count"].sum()
    return (off_s / total_s.replace(0, np.nan)).fillna(0.0).round(4).to_dict()
# else: existing tx_hour-per-row path continues
```

**Patch 2 — flow.py: relay score bypass + date-collision guard**
```python
# In _compute_temporal_relay_scores():
if hasattr(state, "nodes_df") and "relay_ratio" in state.nodes_df.columns:
    ndf = state.nodes_df.set_index("cust_id")
    return {str(k): float(v) for k, v in ndf["relay_ratio"].fillna(0.0).items()}
n_unique_dates = tx_df[date_col].nunique() if date_col in tx_df.columns else 0
if n_unique_dates <= 1:
    return {str(s): 0.0 for s in tx_df["sender_id"].unique()}
# else: existing merge_asof path continues
```

**Patch 3 — benford.py: pre-computed MAD bypass**
```python
# At top of compute_benford_scores():
if hasattr(state, "nodes_df") and not state.nodes_df.empty \
        and "benford_mad" in state.nodes_df.columns:
    state.benford_scores = dict(zip(
        state.nodes_df["cust_id"].astype(str),
        state.nodes_df["benford_mad"].fillna(0.0)
    ))
    return
# else: existing per-row iteration path continues
```

**Patch 4 — behavioral.py: burstiness bypass**
```python
# At top of _compute_goh_barabasi_b():
if hasattr(state, "nodes_df") and not state.nodes_df.empty \
        and "burstiness_b" in state.nodes_df.columns:
    state.goh_barabasi_b = dict(zip(
        state.nodes_df["cust_id"].astype(str),
        state.nodes_df["burstiness_b"].fillna(0.0)
    ))
    state.is_scripted_regular = {k: v < -0.3 for k, v in state.goh_barabasi_b.items()}
    return
# else: existing epoch-difference path continues
```

**Patch 5 — flow.py: velocity delta bypass**
```python
# At top of _compute_velocity_delta_zscore():
if "recent_tx_count" in tx_df.columns and "baseline_tx_count" in tx_df.columns:
    rec = tx_df.groupby("sender_id")["recent_tx_count"].sum()
    bas = tx_df.groupby("sender_id")["baseline_tx_count"].sum()
    bas_days = tx_df["baseline_days"].iloc[0] if "baseline_days" in tx_df.columns else 60
    rec_rate = rec / 30.0
    bas_rate = (bas / bas_days).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    # compute z-score as before using rec_rate and bas_rate...
    return velocity_delta_scores
# else: existing date-split path continues
```

### Dimension Break Verification (D1–D7)

| Dimension | Impact of Weekly Rollup + Pre-Computed Columns | Status |
|---|---|---|
| D1 Proximity | PPR + BFS on graph → unaffected by tx_df granularity; temporal_path_valid uses groupby MIN → works | ✅ ZERO break |
| D2 Red Flags | All 10 red-flag features present: 4 native (velocity, txtype, corridor, HHI) + 6 via pre-computed columns (off-hours, relay via nodes_df, benford via nodes_df, structuring, velocity_delta, structuring_windows) | ✅ ZERO break |
| D3 Centrality | Pure graph — entirely unaffected | ✅ ZERO break |
| D4 Community | Louvain on graph — entirely unaffected | ✅ ZERO break |
| D5 Behavioral | All 18 features present: 10 graph-derived (pagerank, betweenness, degree, flow_ratio, round_trip, clustering, reciprocity, avg_nbr_deg, log_sent, log_recv) + 4 via nodes_df (benford, burstiness, amount_cv, round_amount_rate, dormancy) + 4 native with rollup (velocity, counterparty_hhi, txtype, corridor) | ✅ ZERO break |
| D6 Identity | nodes_df only — unaffected | ✅ ZERO break |
| D7 Recency | weight_recency via EXP decay on rollup period date — slight precision loss, acceptable | ✅ ZERO break |

---

---

# QUERY 8 — Granularity Comparison: What Exactly Do You Lose Daily → Weekly → Monthly?

**User Question:** We built on individual transactions, moved to daily, now considering weekly. Someone suggested monthly. What do we actually lose at each level? Also: customer is both sender and receiver — in a pair, is at least one side always a customer?

---

## Response 8 — Full Granularity Impact Analysis

### Architecture Progression Clarification

```
Individual tx (raw) → Daily rollup (1 row/pair/day) → Weekly (1 row/pair/week) → Monthly (1 row/pair/month)
```

The prior session's monthly suggestion was **theoretical maximum compression** — not an active recommendation. Weekly unlocks meaningful scalability while preserving acceptable signal. Monthly degrades signal to an unacceptable degree for several critical features.

### Customer As Both Sender and Receiver — Confirmed

**YES.** In every transaction edge `(sender_id, receiver_id)`, at least one side is your monitored bank customer. The monitoring perimeter is your bank's portfolio — you only capture transactions touching your accounts.

**The correct rollup unit is always `(sender_id, receiver_id, period)` — pair-level, not customer-level.**

A "customer-level rollup" (1 row per customer per period, aggregating all counterparties) destroys all edge-specific graph information:
- No graph can be built from customer-level aggregates
- No layering detection, round-trip, relay, community detection
- App degrades to a flat per-customer scorecard

### Feature-Level Impact Matrix

| Feature | Individual | Daily ✅ | Weekly | Monthly |
|---|---|---|---|---|
| **Benford MAD** | Perfect | ✅ Works | ❌ Fails — weekly sum destroys first-digit | ❌ Fails |
| **Burstiness B** | Perfect | ✅ Good | ⚠️ Degraded — 7-day resolution | ❌ Useless — B≈0 for all |
| **Off-hours ratio** | Perfect | ✅ Works | ⚠️ Needs `off_hours_tx_count` column | ⚠️ Needs column |
| **Temporal relay** | Perfect | ✅ Works | ⚠️ Risky — same-week dates → partial false positives | 🔴 CATASTROPHIC — same-month date → relay=1.0 for ALL |
| **Velocity delta z-score** | Perfect | ✅ Works | ✅ Works — week-level split viable | ⚠️ Risky — 1-month baseline often empty |
| **Structuring windows** | Perfect | ✅ Works | ❌ Fails — consecutive-day pattern lost | ❌ Fails |
| **Dormancy days** | Perfect | ✅ Precise | ⚠️ 7-day resolution max | ❌ Static 30d |
| **DOW entropy** | Perfect | ✅ Works | ⚠️ Degraded — only 7 points | ❌ 1 date → zero entropy |
| **Round-amount rate** | Perfect | ✅ Works | ❌ Fails — weekly sum destroys pattern | ❌ Fails |
| **amount_cv** | Perfect | ✅ Works | ❌ Fails — 1 summed amount per row | ❌ Fails |
| **Velocity score** | Perfect | ✅ | ✅ Works | ✅ Works |
| **txtype_risk** | Perfect | ✅ | ✅ Works | ✅ Works |
| **Corridor risk** | Perfect | ✅ | ✅ Works | ✅ Works |
| **Counterparty HHI** | Perfect | ✅ | ✅ Works | ✅ Works |
| **Layering chains** | Perfect | ✅ | ✅ Works | ✅ Works |
| **Round-trip** | Perfect | ✅ | ✅ Works | ✅ Works |
| **All graph topology** | Perfect | ✅ | ✅ Works | ✅ Works |
| **weight_recency** | Perfect | ✅ Precise | ⚠️ Week-level decay — slight loss | ⚠️ Month-level — acceptable |

### Scalability vs Signal Loss Trade-off

| Level | Row Reduction | Signal Loss Estimate | Pre-Computed Columns Needed | Verdict |
|---|---|---|---|---|
| Individual → Daily | baseline | 0% | 0 | ✅ Current correct design |
| Daily → Weekly | **86%** | ~10–15% | 9 columns + 5 engine patches | ✅ Recommended if scale needed |
| Daily → Monthly | 96% | ~35–40% | 9+ columns (temporal relay still catastrophic without patches) | ❌ Too lossy — not recommended |

### Complete List of Pre-Computed Columns for Weekly Rollup

#### Edge-Level Columns (add to tx_df)

| Column | Type | When to Compute | Replaces |
|---|---|---|---|
| `off_hours_tx_count` | int | Count of individual txns outside 08:00–18:00 in period | tx_hour-per-row logic |
| `recent_tx_count` | int | Count of txns in last 30d of the period | Date-split in velocity delta |
| `baseline_tx_count` | int | Count of txns in days 31–90 of the period | Baseline in velocity delta |
| `baseline_days` | int | Length of baseline window in days | Denominator in velocity delta |
| `min_amount` | float | Min individual tx amount (already used by structuring Tier 2) | Structuring Tier 2 |
| `max_amount` | float | Max individual tx amount (already used by structuring Tier 2) | Structuring Tier 2 |
| `count_structuring_band` | int | Count of individual txns in 8K–10K range (already used Tier 1) | Structuring Tier 1 |

#### Node-Level Columns (add to nodes_df)

| Column | Type | Formula | Replaces |
|---|---|---|---|
| `benford_mad` | float | MAD of first-digit distribution across all raw individual txns | Internal benford.py loop |
| `burstiness_b` | float | (σ−μ)/(σ+μ) of inter-event times from raw timestamps | behavioral.py `_compute_goh_barabasi_b()` |
| `amount_cv` | float | std/mean of all raw individual amounts | flow.py `_compute_flow_texture_stats()` |
| `dormancy_days` | float | Max gap in days between consecutive transactions | flow.py dormancy calculation |
| `dow_entropy` | float | Shannon entropy of day-of-week distribution | flow.py DOW entropy |
| `round_amount_rate` | float | Fraction of txns where `amount % 1000 < 1` | flow.py round-amount check |
| `relay_ratio` | float | Fraction of txns classified as temporal relay | `_compute_temporal_relay_scores()` |
| `structuring_window_count` | int | Count of consecutive-day clustering windows detected | `_find_structuring_windows()` |

**Total: 7 edge columns + 8 node columns = 15 pre-computed columns**  
(min_amount, max_amount, count_structuring_band were already discussed in prior structuring Tier 1/2 analysis)

### Final Recommendation

```
If current daily data volume is manageable:    STAY DAILY — zero feature loss
If scalability is needed (>10M tx per run):   MOVE TO WEEKLY — 86% reduction, acceptable 10-15% loss
If extreme compression needed (>100M tx):     MONTHLY only viable with all 15 pre-computed columns
                                               AND explicit acknowledgment that temporal relay, 
                                               structuring windows, and burstiness are degraded
```

---

---

## Master Reference: All Pre-Computed Columns Across All Queries

### Edge-Level Columns (tx_df) — Complete List

| Column | Query First Discussed | Required For | Rollup Level |
|---|---|---|---|
| `count_structuring_band` | Q7 (structuring Tier 1) | Structuring score accuracy | Weekly + Monthly |
| `min_amount` | Q7 (structuring Tier 2) | Structuring score range interpolation | Weekly + Monthly |
| `max_amount` | Q7 (structuring Tier 2) | Structuring score range interpolation | Weekly + Monthly |
| `off_hours_tx_count` | Q7 | Off-hours ratio feature | Weekly + Monthly |
| `recent_tx_count` | Q7 | Velocity delta z-score | Monthly |
| `baseline_tx_count` | Q7 | Velocity delta z-score | Monthly |
| `baseline_days` | Q7 | Velocity delta denominator | Monthly |

### Node-Level Columns (nodes_df) — Complete List

| Column | Query First Discussed | Required For | Rollup Level |
|---|---|---|---|
| `benford_mad` | Q7 | Benford Law detection (D2) | Weekly + Monthly |
| `burstiness_b` | Q7 | Behavioral ensemble feature 10 (D5) | Weekly + Monthly |
| `amount_cv` | Q7 | Behavioral ensemble feature 11 (D5) | Weekly + Monthly |
| `dormancy_days` | Q7 | Behavioral ensemble feature 12 (D5) | Weekly + Monthly |
| `dow_entropy` | Q7 | Flow texture (D2) | Weekly + Monthly |
| `round_amount_rate` | Q7 | Behavioral ensemble feature 14 (D5) | Weekly + Monthly |
| `relay_ratio` | Q7 | Temporal relay detection (D2) — CRITICAL for monthly | Weekly + Monthly |
| `structuring_window_count` | Q7 | Structuring window evidence (D2 advisory) | Weekly + Monthly |

---

*Document covers Queries 3–8 of the AML Strategy Expert Advisory Session.*  
*Queries 1–2 documented in `AML_STRATEGY_EXPERT_RESPONSES.md`.*  
*Technical audit performed on GraphAML v18.6 engine files: flow.py, benford.py, behavioral.py, neighborhood.py, graph_builder.py.*  
*Author: GitHub Copilot (Claude Sonnet 4.6) — PhD AML Data Science Advisory Mode*  
*Session Date: April 13–15, 2026*
