# AML GraphAML — Rollup Compensation Columns
## Ground Truth: What EXTRA Columns to Add When Rolling Daily → Weekly or Monthly

**Scope:** Edge table = `(sender_id, receiver_id, period_key)`.  
10K target customers — each can appear as sender OR receiver in any pair.  
Goal: compress rows, preserve signal, pass lost info as new columns.

---

## What Works WITHOUT Any Extra Columns

These features are immune to granularity — skip them, no action needed.

| Feature | Why It Always Works |
|---|---|
| `pagerank`, `betweenness`, `degree`, `clustering`, `reciprocity`, `avg_nbr_deg` | Computed from graph topology (edge existence), not from tx_df row count |
| `total_sent_log`, `total_received_log`, `flow_ratio` | Pure SUM/ratio — preserved at any granularity |
| `velocity_score` | Uses `SUM(tx_count)` across all rows per sender — preserved |
| `txtype_risk_score` | `tx_count`-weighted average of type risk — SUM preserves it |
| `counterparty_hhi` | Groups by receiver per sender — pair-level rows give same receiver buckets |
| `funnel_flag`, `spray_flag` | Derived from graph fan_in/fan_out counts — topology-based |

**These 13 features need zero extra columns. Focus only on what follows.**

---

## PART 1 — EDGE-LEVEL COLUMNS

Added to `tx_df`. One value per `(sender_id, receiver_id, period_key)` row.  
Computed from **daily data before rollup** — aggregate the per-individual-tx signal into scalars.

---

### E1 — `count_structuring_band` (int)
**Needed:** Weekly ✅ | Monthly ✅

**Fixes:** `structuring_score`

**Why it breaks:** The engine has 3 tiers for structuring detection. Without this column it falls to Tier 3: uses `amount / tx_count` (period average) as a proxy for individual transaction amounts. A pair with $9,700 + $9,700 rolled to $19,400 with `tx_count=2` gives average $9,700 — Tier 3 happens to be right here. But $9,700 + $500 = $10,200 / 2 = $5,100 — misses entirely. With this column the engine uses Tier 1 (exact count), which is the most accurate path.

**Logic:**
```sql
-- From individual (pre-rollup) transactions:
count_structuring_band = COUNT(*)
WHERE amount >= 9000 AND amount < 10000
GROUP BY sender_id, receiver_id, period_key
```

```python
raw_tx["in_band"] = (raw_tx["amount"] >= 9000) & (raw_tx["amount"] < 10000)
daily_rollup = raw_tx.groupby(["sender_id","receiver_id","period_key"]).agg(
    count_structuring_band=("in_band", "sum"), ...
)
```

---

### E2 — `min_amount` (float)
**Needed:** Weekly ✅ | Monthly ✅

**Fixes:** `structuring_score` (Tier 2 fallback if E1 unavailable)

**Why it breaks:** Engine Tier 2 uses `min_amount` + `max_amount` to estimate what fraction of the amount range overlaps the $9k-$10k structuring band via linear interpolation. If these columns are absent, falls to inaccurate Tier 3.

**Logic:**
```python
min_amount = MIN(individual_amount) per (sender, receiver, period)
```

---

### E3 — `max_amount` (float)
**Needed:** Weekly ✅ | Monthly ✅

**Fixes:** `structuring_score` (Tier 2, paired with E2)

**Logic:**
```python
max_amount = MAX(individual_amount) per (sender, receiver, period)
```

---

### E4 — `off_hours_tx_count` (int)
**Needed:** Weekly ✅ | Monthly ✅

**Fixes:** `off_hours_ratio`

**Why it breaks (confirmed from flow.py:251-287):**
```python
tx_df["tx_hour"] = pd.to_numeric(tx_df["tx_hour"], errors="coerce")
tx_df = tx_df.dropna(subset=["tx_hour"])
```
A weekly/monthly rollup row has no meaningful single `tx_hour` value. The column is either missing or contains a single representative value (e.g. mode). The engine reads it expecting one `tx_hour` value per row and computes `is_off` per row — with a rolled-up row this is wrong: a period with 3 off-hours and 7 on-hours transactions would show the mode hour (say, 14:00) and produce `is_off = False` for the whole week.

**Off-hours window (confirmed from constants):** `tx_hour >= 22 OR tx_hour <= 6` (22:00 through 06:00, inclusive, 9-hour window).

**Logic:**
```sql
off_hours_tx_count = COUNT(*)
WHERE (tx_hour >= 22 OR tx_hour <= 6)
GROUP BY sender_id, receiver_id, period_key
```

```python
raw_tx["is_off"] = (raw_tx["tx_hour"] >= 22) | (raw_tx["tx_hour"] <= 6)
# then aggregate: off_hours_tx_count = SUM(is_off) per group
```

**Engine patch P1 required** — add at top of `_compute_off_hours_ratios()`:
```python
if "off_hours_tx_count" in tx_df.columns:
    total = tx_df.groupby("sender_id")["tx_count"].sum()
    off   = tx_df.groupby("sender_id")["off_hours_tx_count"].sum()
    return (off / total.replace(0, np.nan)).fillna(0.0).round(4).to_dict()
# existing tx_hour logic continues...
```

---

### E5 — `round_amount_count` (int)
**Needed:** Weekly ✅ | Monthly ✅

**Fixes:** `round_amount_rate`

**Why it breaks (confirmed from flow.py:646):**  
Engine computes `amts % 1000 < 1` on the `amount` column values in tx_df.  
With weekly rollup, `amount` = SUM of individual amounts. `($9,700 + $9,800) = $19,500`.  
`$19,500 % 1000 = 500` → NOT flagged as round. Two structuring transactions completely missed.

**Logic:**
```sql
round_amount_count = COUNT(*)
WHERE amount % 1000 < 1          -- individual amounts only, before rollup
GROUP BY sender_id, receiver_id, period_key
```

```python
raw_tx["is_round"] = (raw_tx["amount"] % 1000 < 1.0)
# then aggregate: round_amount_count = SUM(is_round) per group
```

**Engine patch P2 required** — in `_compute_flow_texture_stats()`:
```python
if "round_amount_count" in tx_df.columns:
    total  = df.groupby("sender_id")["tx_count"].sum()
    rounds = df.groupby("sender_id")["round_amount_count"].sum()
    rate   = (rounds / total.replace(0, np.nan)).fillna(0.0).round(4)
    for sid, val in rate.items():
        state.round_amount_rate[str(sid)] = float(val)
    # skip the amts % 1000 computation below
```

---

### E6 — `recent_tx_count` (int) + E7 — `baseline_tx_count` (int)
**Needed:** Weekly ❌ (not needed — see below) | Monthly ✅ CRITICAL

**Fixes:** `velocity_delta_z`

**Why it breaks at MONTHLY (confirmed from flow.py:500-507):**
```python
cutoff = df["_date"].max() - pd.Timedelta(days=30)
recent   = df[df["_date"] >= cutoff]
baseline = df[df["_date"] <  cutoff]

if baseline.empty:
    return {str(s): 0.0 for s in df["sender_id"].unique()}  # ← SILENT 0.0 FOR ALL
```
Monthly tx_df has ~3 rows total per pair (Jan, Feb, Mar). The max_date = March row. cutoff = 30 days back = mid-February. Baseline = everything before mid-February = the January row only (1 row). This gives an extremely thin baseline and **for any pair active only in Q1, baseline may be empty → all nodes get 0.0 silently**.

**Why weekly is OK:** 13 rows per pair (weeks). Baseline = ~9 rows, recent = ~4 rows. Thin but non-empty, z-score computes meaningfully.

**Logic (monthly only):**
```python
# When building the monthly rollup row for (sender, receiver, month):
month_end = max(daily_dates_in_this_month)
cutoff    = month_end - pd.Timedelta(days=30)

recent_tx_count   = SUM(tx_count WHERE daily_date >= cutoff)
baseline_tx_count = SUM(tx_count WHERE daily_date < cutoff)
```

**Engine patch P3 required** — add at top of `_compute_velocity_delta_zscore()`:
```python
if "recent_tx_count" in tx_df.columns and "baseline_tx_count" in tx_df.columns:
    r = tx_df.groupby("sender_id")["recent_tx_count"].sum()
    b = tx_df.groupby("sender_id")["baseline_tx_count"].sum()
    base_mean = b.mean(); base_std = max(b.std(), 1e-9)
    z = (r - b) / base_std
    sig = (1.0 / (1.0 + np.exp(-z / 2.0))).round(4)
    return sig.to_dict()
```

---

## PART 2 — NODE-LEVEL COLUMNS

Added to `nodes_df`. One value per `customer_id` (node).  
Computed **ONCE from ALL individual raw transactions** — BEFORE any rollup.  
These are temporal behavioral signals that are fundamentally node-level, not pair-level.  
**Same columns apply to BOTH weekly and monthly.**

---

### N1 — `burstiness_b` (float, range −1 to +1)
**Definition:** Goh-Barábasi B = `(σ − μ) / (σ + μ)` where μ and σ are mean and std of inter-event times (seconds between consecutive transactions).
- B < −0.3 → scripted/automated (regular bot, equal intervals)
- B > +0.3 → bursty cluster (cash dealer, cluster-then-silent)
- B ≈ 0 → random Poisson (normal customer)

**Why it breaks (confirmed from behavioral.py):**
```python
inter = np.diff(times).astype(float)   # times = tx timestamps from tx_df rows
mu = inter.mean()
sigma = inter.std()
b = float((sigma - mu) / (sigma + mu))
```
Weekly tx_df: 1 row per pair per week → node has ~13 timestamps, all 7 days apart.  
`sigma = 0` → `b = (0 − μ) / (0 + μ) = −1.0` for every node. **All customers appear scripted-regular.**  
Monthly: same problem. The per-period timestamps carry no within-period timing variation.

**Logic — pre-compute from raw individual transactions:**
```python
for node in all_customer_ids:
    sent_tx = raw_tx[raw_tx["sender_id"] == node].sort_values("tx_timestamp")
    if len(sent_tx) < 3:
        burstiness_b[node] = 0.0
        continue
    epoch = sent_tx["tx_timestamp"].astype(np.int64) / 1e9  # seconds
    inter = np.diff(epoch.values)
    mu, sigma = inter.mean(), inter.std()
    denom = sigma + mu
    burstiness_b[node] = round(float((sigma - mu) / denom) if denom > 1e-9 else 0.0, 4)
```

---

### N2 — `benford_mad` (float, range 0 to 1)
**Definition:** Mean Absolute Deviation between the observed first-digit frequency distribution of a customer's transaction amounts and Benford's Law expected distribution `log10(1 + 1/d)` for d ∈ {1..9}.  
MAD=0 → perfectly Benford (natural, normal).  
MAD→1 → highly non-Benford (suspicious — structuring concentrates on digits 9 at $9,700-$9,900).  
Requires ≥30 individual amounts to be meaningful.

**Why it breaks (confirmed from benford.py:75):**  
Engine iterates `tx_df["amount"]` per node. After weekly rollup each node has ~100 pair-period amounts (10 pairs × 10 weeks of combined sent+received). But these amounts are SUMS: `$9,700 + $9,700 = $19,400` → leading digit "1", not "9". The entire mathematical basis of Benford's Law (natural distribution of first-order amounts) is violated when applied to aggregated sums.

**Logic — pre-compute from raw individual amounts:**
```python
BENFORD = np.array([np.log10(1 + 1/d) for d in range(1, 10)])

for node in all_customer_ids:
    amts = raw_tx.loc[
        (raw_tx["sender_id"] == node) | (raw_tx["receiver_id"] == node),
        "amount"
    ].values
    amts = amts[amts >= 0.01]
    if len(amts) < 30:
        benford_mad[node] = 0.0
        continue
    # Extract first significant digit
    first_d = np.array([int(str(int(a * 10**max(0,-int(np.floor(np.log10(a))))))) % 10
                        for a in amts], dtype=int)
    # simpler approach: shift < 1 values to >= 1
    first_d = np.array([int(str(a).lstrip("0").replace(".","")[0]) for a in amts
                        if str(a).lstrip("0").replace(".","")], dtype=int)
    first_d = first_d[(first_d >= 1) & (first_d <= 9)]
    if len(first_d) < 30:
        benford_mad[node] = 0.0
        continue
    observed = np.array([(first_d == d).mean() for d in range(1, 10)])
    benford_mad[node] = round(float(np.abs(observed - BENFORD).mean()), 6)
```

---

### N3 — `dow_entropy` (float, range 0 to log2(7) ≈ 2.807)
**Definition:** Shannon entropy of the day-of-week distribution of sent transactions.  
`−Σ p_d · log2(p_d)` for d ∈ {Mon=0 .. Sun=6}.  
High (≈2.8) → uniform spread across all 7 days (normal retail customer).  
Low (≈0) → concentrated on 1-2 days (always Friday cash-outs, Sunday structuring, etc.).

**Why it breaks (confirmed from flow.py:646):**
```python
df["_dow"] = df["_dt"].dt.dayofweek
...
dow_counts = grp["_dow"].value_counts()
```
Weekly rollup: `tx_date = week_start_date = Monday` for all rows → `_dow = 0` for every row → entropy = 0 for every node. All customers appear to transact only on Mondays.  
Monthly: `tx_date = first of month` → DOW varies by month but is fixed per month (not a distribution of actual transaction days).

**Logic — pre-compute from raw individual timestamps:**
```python
for node in all_customer_ids:
    sent_tx = raw_tx[raw_tx["sender_id"] == node]
    if len(sent_tx) < 7:
        dow_entropy[node] = 0.0
        continue
    dow_counts = sent_tx["tx_timestamp"].dt.dayofweek.value_counts()
    probs = dow_counts / dow_counts.sum()
    dow_entropy[node] = round(float(-np.sum(probs * np.log2(probs + 1e-12))), 4)
```

---

### N4 — `amount_cv` (float, coefficient of variation ≥ 0)
**Definition:** `std(individual_tx_amounts) / mean(individual_tx_amounts)` per sender.  
High CV (>1) → erratic amount distribution (unusual — many different amounts).  
Low CV (≈0) → suspiciously uniform amounts (structuring: always sending exactly $9,700).

**Why it breaks (confirmed from flow.py:646):**
```python
for sid, grp in df.groupby("sender_id"):
    amts = grp["amount"].values       # ← these are PERIOD SUMS in weekly/monthly tx_df
    mu   = float(np.mean(amts))
    sig  = float(np.std(amts, ddof=0))
    state.amount_cv[sid] = sig / max(mu, 1e-9)
```
Weekly: a structurer sending exactly $9,700 per day → weekly rollup = $67,900 every week → all 13 weekly sums identical → CV = 0. The suspicious uniformity is preserved by accident! But: a normal customer with variable amounts (ranging $500-$50,000 daily) gets weekly sums in a much tighter range → CV artificially reduced. The semantics shift — CV of sums ≠ CV of individual transactions.

**Logic — pre-compute from raw individual sent amounts:**
```python
for node in all_customer_ids:
    sent_amts = raw_tx.loc[raw_tx["sender_id"] == node, "amount"].values
    if len(sent_amts) < 2:
        amount_cv[node] = 0.0
        continue
    mu = sent_amts.mean()
    amount_cv[node] = round(float(sent_amts.std() / max(mu, 1e-9)), 4)
```

---

### N5 — `dormancy_days` (float, days)
**Definition:** `MAX(gap_in_days)` between consecutive transaction dates for a customer.  
A customer who transacts daily and suddenly stops for 45 days then restarts = sleeping mule activation pattern.

**Why it breaks:**  
- Weekly: Engine computes max gap between weekly period dates → resolution = 7 days. Missing a week shows as 14-day gap minimum. **Partially usable** — only detects multi-week dormancy.  
- Monthly: Max gap between monthly period dates ≈ 30 days for all active months. **All active customers show ~30-day dormancy. Signal is flat — useless.**

**Logic — pre-compute from raw individual transaction dates:**
```python
for node in all_customer_ids:
    dates = sorted(raw_tx.loc[raw_tx["sender_id"] == node, "tx_date"].dt.normalize().unique())
    if len(dates) < 2:
        dormancy_days[node] = 0.0
        continue
    gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
    dormancy_days[node] = round(float(max(gaps)), 2)
```

**Note:** For weekly rollup this is optional (7-day resolution sometimes acceptable). For monthly it is mandatory.

---

### N6 — `relay_ratio` (float, range 0 to 1)
**Needed:** Weekly ❌ (works approximately with merge_asof on week dates) | Monthly ✅ CRITICAL

**Definition:** Fraction of a node's outgoing flow where a matching inbound flow from ANY counterparty arrived within 24 hours BEFORE the send. Detects: receives $100K from A at 9am, sends $98K to C at 11am = relay/pass-through.

**Why it breaks at MONTHLY (confirmed from flow.py:538-610):**
```python
matched = pd.merge_asof(
    send, recv,
    on="_date",             # ← all monthly rows have same month date: 2024-01-01
    by="_node",
    tolerance=pd.Timedelta(hours=relay_window_hours),  # relay_window_hours=24
    direction="backward",
)
```
Monthly tx_df: all January rows have `tx_date = 2024-01-01`. tolerance = 24h. ALL send events in January match ALL receive events in January because `|2024-01-01 - 2024-01-01| = 0 hours < 24h`. **Every node gets relay_score ≈ 1.0. Every customer is falsely flagged as a relay agent.**

**Logic — pre-compute from raw individual timestamps:**
```python
# Same merge_asof logic as the engine, applied to raw data
send_raw = raw_tx[["sender_id", "tx_timestamp", "amount"]].rename(
    columns={"sender_id": "_node", "amount": "_send_amt"}).sort_values("tx_timestamp")
recv_raw = raw_tx[["receiver_id", "tx_timestamp", "amount"]].rename(
    columns={"receiver_id": "_node", "amount": "_recv_amt"}).sort_values("tx_timestamp")

matched = pd.merge_asof(send_raw, recv_raw, on="tx_timestamp", by="_node",
                        tolerance=pd.Timedelta(hours=24), direction="backward")
matched_valid = matched.dropna(subset=["_recv_amt"])

total_sent = send_raw.groupby("_node")["_send_amt"].sum()
relay_sent = matched_valid.groupby("_node")["_send_amt"].sum()
relay_ratio_series = (relay_sent / total_sent.replace(0, np.nan)).fillna(0.0).clip(0, 1)
relay_ratio = relay_ratio_series.to_dict()  # {node_id: ratio}
```

**Engine patch P4 required** — add at top of `_compute_temporal_relay_scores()`:
```python
if hasattr(state, "nodes_df") and state.nodes_df is not None \
        and "relay_ratio" in state.nodes_df.columns:
    ndf = state.nodes_df
    relay_map = dict(zip(ndf["cust_id"].astype(str),
                         ndf["relay_ratio"].fillna(0.0)))
    state.relay_scores = relay_map
    return
```

---

## SUMMARY TABLE

### Edge Columns (added to tx_df)

| Column | Type | Weekly | Monthly | Aggregation Logic | Fixes Feature | Engine Patch |
|---|---|---|---|---|---|---|
| `count_structuring_band` | int | ✅ | ✅ | `SUM(1 WHERE individual_amount BETWEEN 9000 AND 10000)` per pair per period | `structuring_score` (Tier 1) | No |
| `min_amount` | float | ✅ | ✅ | `MIN(individual_amount)` per pair per period | `structuring_score` (Tier 2) | No |
| `max_amount` | float | ✅ | ✅ | `MAX(individual_amount)` per pair per period | `structuring_score` (Tier 2) | No |
| `off_hours_tx_count` | int | ✅ | ✅ | `SUM(1 WHERE tx_hour >= 22 OR tx_hour <= 6)` per pair per period | `off_hours_ratio` | **P1** |
| `round_amount_count` | int | ✅ | ✅ | `SUM(1 WHERE individual_amount % 1000 < 1)` per pair per period | `round_amount_rate` | **P2** |
| `recent_tx_count` | int | ❌ not needed | ✅ | `SUM(tx_count WHERE daily_date >= month_end − 30d)` | `velocity_delta_z` | **P3** |
| `baseline_tx_count` | int | ❌ not needed | ✅ | `SUM(tx_count WHERE daily_date < month_end − 30d)` | `velocity_delta_z` | **P3** |

**Weekly: 5 edge columns.  Monthly: 7 edge columns (5 + 2 extra).**

### Node Columns (added to nodes_df, one value per customer)

| Column | Type | When | Computed From | Fixes Feature | Engine Patch |
|---|---|---|---|---|---|
| `burstiness_b` | float | Both | Individual tx timestamps (inter-event seconds) | `goh_barabasi_b` | **P5** |
| `benford_mad` | float | Both | Individual tx amounts, sent+received, min 30 | `benford_mad` | **P5** |
| `dow_entropy` | float | Both | Individual tx timestamps, day-of-week distribution | `dow_entropy` | **P5** |
| `amount_cv` | float | Both | Individual sent amounts per customer | `amount_cv` | **P5** |
| `dormancy_days` | float | Monthly ✅ critical, Weekly ⚠️ optional | Individual tx dates (max gap in days) | `dormancy_days` | **P5** |
| `relay_ratio` | float | Monthly ✅ critical only | Individual tx timestamps, merge_asof 24h window | `relay_score` | **P4** |

**Weekly: 4-5 node columns.  Monthly: 6 node columns.**

### Engine Patches Summary

| Patch | File | Trigger | Action |
|---|---|---|---|
| P1 | `engine/flow.py` line ~251 | `"off_hours_tx_count" in tx_df.columns` | Use pre-agg ratio instead of per-row tx_hour |
| P2 | `engine/flow.py` line ~646 | `"round_amount_count" in tx_df.columns` | Use pre-agg rate instead of `amts % 1000` |
| P3 | `engine/flow.py` line ~472 | `"recent_tx_count" in tx_df.columns` | Compute z-score from split columns, skip date-cutoff logic |
| P4 | `engine/flow.py` line ~538 | `"relay_ratio" in nodes_df.columns` | Use pre-computed relay_ratio, skip merge_asof entirely |
| P5 | `engine/behavioral.py`, `engine/benford.py`, `engine/flow.py:646` | Pre-computed col exists in `nodes_df` | Read from nodes_df instead of computing from tx_df |

---

## RECOMMENDATION: WEEKLY vs MONTHLY

### Weekly

| Metric | Value |
|---|---|
| Row reduction | 86% (900K daily → 130K weekly for 10K customers) |
| Extra edge columns | 5 |
| Extra node columns | 4 |
| Engine patches | 2 (P1, P2) |
| Relay score | ✅ Works — merge_asof on week dates gives real day-resolution (Mon vs Mon+7) |
| Velocity delta | ✅ Works — ~9 weeks baseline, ~4 weeks recent — non-empty |
| Layering chains | ✅ Works for multi-week chains (within-week order uncertain but minor) |
| Features fully recovered | ~22/23 |

### Monthly

| Metric | Value |
|---|---|
| Row reduction | 97% (900K daily → 30K monthly) |
| Extra edge columns | 7 |
| Extra node columns | 6 |
| Engine patches | 4 (P1, P2, P3, P4) |
| Relay score | ❌ CATASTROPHIC without P4 — all nodes get relay=1.0. Mandatory bypass. |
| Velocity delta | ❌ SILENT FAILURE without E6/E7 — all nodes get delta=0.0 |
| Layering chains | ❌ Within-month chains unorderable — cross-month chains ok |
| Features fully recovered | ~22/23 (same, but requires 2 extra patches and 2 extra columns) |

### Decision

**Use WEEKLY.**

Reason:

1. **86% row reduction is already dramatic** for a 10K node system. Monthly's additional 11% gain is marginal.

2. **Relay and velocity work natively at weekly** — no emergency patches needed for the two most catastrophic failure modes. Monthly requires P4 (relay bypass) without which the entire relay scoring is garbage.

3. **Weekly has 2 engine patches; monthly has 4.** Each patch is a maintenance liability and a potential regression.

4. **The compensation engineering cost is lower** for weekly (5 edge + 4 node columns vs 7 edge + 6 node for monthly).

5. **The 14-day maximum error** in weekly temporal resolution is acceptable for AML — most layering chains and relay patterns span multiple weeks anyway. 30-day monthly resolution turns within-month patterns invisible.

**Only use monthly if** the 10K customers generate >50M weekly rows even after daily rollup, making the 130K weekly target infeasible. That would require an average of >3,800 transactions per pair per week — unlikely for a 90-day window.

### Implementation Order

```
Step 1:  Build daily rollup with E1-E5 columns (from individual raw data)
Step 2:  Compute N1-N5 node columns (from individual raw data, one-time)
Step 3:  Aggregate daily → weekly, preserving E1-E5 via SUM/MIN/MAX
Step 4:  Merge nodes_df into app with N1-N5 columns
Step 5:  Apply engine patches P1 + P2
Step 6:  Run pipeline — validate off_hours_ratio and structuring not all-zero
```

---

*Source: flow.py lines 159-645, benford.py line 75, behavioral.py — source-confirmed, GraphAML v18.6, April 2026*
