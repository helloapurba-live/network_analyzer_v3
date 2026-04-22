# AML GraphAML — 13 Compensation Columns: Full Oracle SQL + Python
**GraphAML — PhD AML Data Science Advisory**
**Date:** April 15, 2026
**Context:** Monthly rollup compensation for GraphAML v18.6 | 90-day raw transaction window
**Scope:** All 13 columns (E1–E7 edge + N1–N6 node) with complete Oracle SQL and Python code

---

## Why These 13 Columns Exist

GraphAML v18.6 ingests `transactions.csv` (edge table) and `nodes.csv` (node table) in **daily rollup** format.
When the source data is **monthly-rolled** (one row per sender–receiver–month), the engine silently fails on:

- **Relay detection** → relay=1.0 for every bidirectional pair (same-date sends and receives)
- **Velocity baseline** → baseline.empty → all velocity = 0.0
- **Burstiness** → period dates produce 30-day flat gaps → B=−1 for ALL
- **Benford** → monthly sums destroy first-digit law; <30 rows → threshold failure
- **Off-hours ratio** → engine drops NaN tx_hour → ratio=0 for all
- **DOW entropy** → 1–3 unique dates per month → entropy → near 0 for all

These 13 columns are pre-computed from **individual raw transactions** (before rollup) and injected into the rolled-up CSV files so the engine recovers the lost signal.

---

## Table of All 13 Columns

### EDGE Columns (E1–E7) → added to `transactions.csv`

| # | Column | Type | Engine Signal Fixed | Impact If Missing |
|---|---|---|---|---|
| E1 | `count_structuring_band` | int | `structuring_score` | 🟠 MEDIUM — falls to Tier 3 unit_amount proxy |
| E2 | `min_amount` | float | min/max spread signals | 🟠 MEDIUM |
| E3 | `max_amount` | float | min/max spread signals | 🟠 MEDIUM |
| E4 | `off_hours_tx_count` | int | `off_hours_ratio` | 🟡 HIGH — engine drops NaN tx_hour → ratio=0 ALL |
| E5 | `round_amount_count` | int | `round_amount_ratio` | 🟠 MEDIUM — engine applies %1000 on monthly SUM (wrong) |
| E6 | `recent_tx_count` | int | `velocity_score` recent leg | 🟡 HIGH — velocity rate distorted |
| E7 | `baseline_tx_count` | int | `velocity_score` baseline leg | 🟡 HIGH — baseline.empty → all velocity = 0.0 |

**Structuring band definition used here:** `amount >= 8000 AND amount <= 9999.99`
(Engine uses $8K–$10K; tune to your jurisdiction — UK may use £8,500–£9,999)

**E6 + E7 boundary:** 30 days before the MAX individual `TX_DATETIME` in your data window.
- Recent = within last 30 days
- Baseline = older than 30 days

---

### NODE Columns (N1–N6) → added to `nodes.csv`

| # | Column | Type | Engine Signal Fixed | Impact If Missing |
|---|---|---|---|---|
| N1 | `burstiness_b` | float −1 to +1 | `behavioral.burstiness_score` | 🟡 HIGH — period gaps flat → B=−1 for ALL |
| N2 | `benford_mad` | float 0–1 | `benford.mad_score` | 🟡 HIGH — monthly sums destroy first-digit law |
| N3 | `dow_entropy` | float 0–2.807 | `behavioral.dow_entropy` | 🟡 HIGH — monthly tx_date collapses DOW to 1–3 values |
| N4 | `amount_cv` | float ≥0 | `behavioral.amount_cv` | 🟠 MEDIUM — CV of 3 monthly sums ≠ CV of 60+ individual amounts |
| N5 | `dormancy_days` | float | `behavioral.dormancy` | 🟡 HIGH — monthly dates = 30d gap for every active customer |
| N6 | `relay_ratio` | float 0–1 | `flow.relay_ratio` | 🔴 CRITICAL — monthly same-date → relay=1.0 for EVERYONE |

**Node time window:** 90 days of individual raw transactions, NOT pre-aggregated monthly batches.
- Benford needs ≥30 individual amounts (min threshold)
- Burstiness needs stable σ/μ estimates from raw inter-event gaps
- DOW needs 7+ weeks of individual send dates
- Monthly Dec run: shift window Oct–Nov–Dec individual data (rolling 90-day advance)

---

## Raw Table Structure Assumed

```sql
-- Source table for ALL SQL below
RAW_TRANSACTIONS (
  SENDER_ID    VARCHAR2(50),   -- who sent
  RECEIVER_ID  VARCHAR2(50),   -- who received
  AMOUNT       NUMBER(18,2),   -- individual transaction amount (NOT aggregated)
  TX_DATETIME  DATE            -- exact timestamp of individual transaction
)
```

---

---

# BLOCK 1 — EDGE TABLE: All E1–E7 in One Oracle SQL

**Output grain:** one row per `(SENDER_ID, RECEIVER_ID, TX_DATE)` where TX_DATE = LAST_DAY of month.
For a 90-day window (Sep–Oct–Nov), each sender–receiver pair produces 3 rows.

```sql
-- ============================================================
-- BLOCK 1: EDGE TABLE — All 7 Compensation Columns
-- Output: TRANSACTIONS.CSV for GraphAML
-- Grain: 1 row per (SENDER_ID, RECEIVER_ID, TX_DATE=month-end)
-- ============================================================

WITH

-- ----------------------------------------------------------
-- STEP 1: Base prep — clean and flag individual transactions
-- ----------------------------------------------------------
base_prep AS (
  SELECT
    SENDER_ID,
    RECEIVER_ID,
    AMOUNT,
    TX_DATETIME,

    -- Month-end key: all Nov txns → 2025-11-30, all Oct → 2025-10-31, etc.
    LAST_DAY(TRUNC(TX_DATETIME, 'MM'))                       AS TX_MONTH,

    -- E1: Is this individual txn in the structuring band ($8,000–$9,999.99)?
    CASE WHEN AMOUNT >= 8000 AND AMOUNT <= 9999.99 THEN 1
         ELSE 0 END                                          AS IS_STRUCTURING_BAND,

    -- E4: Is this individual txn off-hours? (10PM–6AM)
    CASE WHEN TO_NUMBER(TO_CHAR(TX_DATETIME, 'HH24')) >= 22
           OR TO_NUMBER(TO_CHAR(TX_DATETIME, 'HH24')) <= 6
         THEN 1 ELSE 0 END                                   AS IS_OFF_HOURS,

    -- E5: Is this individual txn a round amount? (multiple of $1,000)
    CASE WHEN MOD(AMOUNT, 1000) < 1.0 THEN 1
         ELSE 0 END                                          AS IS_ROUND_AMOUNT

  FROM RAW_TRANSACTIONS
  WHERE AMOUNT > 0                  -- exclude reversals / zero-value entries
    AND TX_DATETIME IS NOT NULL
),

-- ----------------------------------------------------------
-- STEP 2: Find the global latest transaction date
-- This is needed to define the "last 30 days" cutoff for E6/E7.
-- Single row — safe to CROSS JOIN below.
-- ----------------------------------------------------------
max_date AS (
  SELECT MAX(TX_DATETIME) AS MAX_DT
  FROM RAW_TRANSACTIONS
  WHERE AMOUNT > 0
),

-- ----------------------------------------------------------
-- STEP 3: Tag each txn as recent or baseline using 30-day cutoff
-- E6 = recent (last 30 days from max date)
-- E7 = baseline (older than 30 days from max date)
-- ----------------------------------------------------------
tagged AS (
  SELECT
    b.*,
    CASE WHEN b.TX_DATETIME >= m.MAX_DT - 30 THEN 1
         ELSE 0 END AS IS_RECENT
  FROM base_prep b
  CROSS JOIN max_date m    -- safe: max_date always returns exactly 1 row
),

-- ----------------------------------------------------------
-- STEP 4: Aggregate all E1–E7 per (SENDER_ID, RECEIVER_ID, TX_MONTH)
-- ----------------------------------------------------------
aggregated AS (
  SELECT
    SENDER_ID,
    RECEIVER_ID,
    TX_MONTH,

    -- Base edge metrics (standard rollup columns)
    COUNT(*)                          AS TX_COUNT,
    SUM(AMOUNT)                       AS TOTAL_AMOUNT,
    AVG(AMOUNT)                       AS AVG_AMOUNT,

    -- E1: Count of structuring-band individual transactions
    SUM(IS_STRUCTURING_BAND)          AS COUNT_STRUCTURING_BAND,

    -- E2 + E3: Min and max individual amounts in this pair-month
    MIN(AMOUNT)                       AS MIN_AMOUNT,
    MAX(AMOUNT)                       AS MAX_AMOUNT,

    -- E4: Count of off-hours individual transactions
    SUM(IS_OFF_HOURS)                 AS OFF_HOURS_TX_COUNT,

    -- E5: Count of round-amount individual transactions
    SUM(IS_ROUND_AMOUNT)              AS ROUND_AMOUNT_COUNT,

    -- E6: Recent transaction count (last 30 days)
    SUM(IS_RECENT)                    AS RECENT_TX_COUNT,

    -- E7: Baseline transaction count (older than 30 days)
    SUM(1 - IS_RECENT)               AS BASELINE_TX_COUNT

  FROM tagged
  GROUP BY SENDER_ID, RECEIVER_ID, TX_MONTH
)

-- ----------------------------------------------------------
-- FINAL SELECT: Edge table output
-- ----------------------------------------------------------
SELECT
  SENDER_ID,
  RECEIVER_ID,
  TX_MONTH                AS TX_DATE,            -- month-end date (YYYY-MM-30/28/31)
  TX_COUNT,
  TOTAL_AMOUNT,
  AVG_AMOUNT,

  -- E1–E7 compensation columns
  COUNT_STRUCTURING_BAND,
  MIN_AMOUNT,
  MAX_AMOUNT,
  OFF_HOURS_TX_COUNT,
  ROUND_AMOUNT_COUNT,
  RECENT_TX_COUNT,
  BASELINE_TX_COUNT

FROM aggregated
ORDER BY SENDER_ID, RECEIVER_ID, TX_DATE;
```

---

---

# BLOCK 2 — NODE TABLE: All N1–N6 in One Oracle SQL

**Output grain:** one row per `CUSTOMER_ID` — timeless behavioral fingerprint.
Nodes with insufficient data for a metric receive the safe default (NULL or 0) via LEFT JOIN + NVL.

```sql
-- ============================================================
-- BLOCK 2: NODE TABLE — All 6 Behavioral Compensation Columns
-- Output: NODES.CSV for GraphAML
-- Grain: 1 row per CUSTOMER_ID (all customers: senders + receivers)
-- Window: ALL individual transactions in your 90-day input data
-- ============================================================

WITH

-- ==========================================================
-- LAYER 0: BASE DATA VIEWS
-- ==========================================================

-- All send events (a customer sending money)
sends AS (
  SELECT
    SENDER_ID                              AS NODE_ID,
    TX_DATETIME,
    AMOUNT,
    TRUNC(TX_DATETIME)                     AS TX_DATE    -- date only, for dormancy
  FROM RAW_TRANSACTIONS
  WHERE AMOUNT > 0
    AND TX_DATETIME IS NOT NULL
),

-- All receive events (a customer receiving money)
recvs AS (
  SELECT
    RECEIVER_ID                            AS NODE_ID,
    TX_DATETIME,
    AMOUNT
  FROM RAW_TRANSACTIONS
  WHERE AMOUNT > 0
    AND TX_DATETIME IS NOT NULL
),

-- All amounts per customer (sent + received) — used for Benford analysis
all_amounts AS (
  SELECT NODE_ID, TX_DATETIME, AMOUNT FROM sends
  UNION ALL
  SELECT NODE_ID, TX_DATETIME, AMOUNT FROM recvs
),

-- Universe of all customers (appear as sender OR receiver)
all_nodes AS (
  SELECT DISTINCT SENDER_ID AS CUSTOMER_ID FROM RAW_TRANSACTIONS WHERE AMOUNT > 0
  UNION
  SELECT DISTINCT RECEIVER_ID             FROM RAW_TRANSACTIONS WHERE AMOUNT > 0
),


-- ==========================================================
-- N1: BURSTINESS (B = (σ−μ)/(σ+μ) of inter-event gaps)
-- Measures: do transactions arrive in unpredictable bursts?
-- Range: −1 (perfectly regular) to +1 (extremely bursty)
-- Minimum: 3 send events (need at least 2 gaps)
-- ==========================================================

-- Step N1a: Calculate gap between consecutive sends (in seconds)
send_gaps AS (
  SELECT
    NODE_ID,
    (TX_DATETIME - LAG(TX_DATETIME) OVER (
        PARTITION BY NODE_ID ORDER BY TX_DATETIME
    )) * 86400                             AS GAP_SECONDS   -- days × 86400 = seconds
  FROM sends
),

-- Step N1b: Compute burstiness = (stddev - mean) / (stddev + mean) per node
n1_burstiness AS (
  SELECT
    NODE_ID,
    -- Need at least 2 gaps (i.e. 3 send events)
    (STDDEV_POP(GAP_SECONDS) - AVG(GAP_SECONDS))
    / NULLIF((STDDEV_POP(GAP_SECONDS) + AVG(GAP_SECONDS)), 0)    AS BURSTINESS_B
  FROM send_gaps
  WHERE GAP_SECONDS IS NOT NULL          -- exclude the first row per node (LAG = NULL)
  GROUP BY NODE_ID
  HAVING COUNT(*) >= 2                   -- at least 2 gaps = 3 send events minimum
),


-- ==========================================================
-- N2: BENFORD MAD (Mean Absolute Deviation from Benford's Law)
-- Measures: do transaction amount first digits follow natural law?
-- High MAD (> 0.1) = Benford violation = potential fabrication
-- Minimum: 30 individual amounts (sent + received combined)
-- ==========================================================

-- Step N2a: Extract first significant digit from each individual amount
fd_extracted AS (
  SELECT
    NODE_ID,
    AMOUNT,
    -- First digit: e.g. $9,432 → 9,  $123 → 1,  $50 → 5
    TRUNC(AMOUNT / POWER(10, FLOOR(LOG(10, AMOUNT))))            AS FIRST_DIGIT
  FROM all_amounts
  WHERE AMOUNT >= 1   -- LOG(10, 0) is undefined; amounts < 1 have no meaningful first digit
),

-- Step N2b: Keep only valid first digits (1–9); exclude edge cases
fd_valid AS (
  SELECT NODE_ID, AMOUNT, FIRST_DIGIT
  FROM fd_extracted
  WHERE FIRST_DIGIT BETWEEN 1 AND 9
),

-- Step N2c: Total valid count per node (minimum threshold check)
fd_totals AS (
  SELECT
    NODE_ID,
    COUNT(*) AS TOTAL_CNT
  FROM fd_valid
  GROUP BY NODE_ID
  HAVING COUNT(*) >= 30           -- Benford needs 30+ amounts to be meaningful
),

-- Step N2d: Observed count per (node, digit)
fd_by_digit AS (
  SELECT
    NODE_ID,
    FIRST_DIGIT,
    COUNT(*) AS D_CNT
  FROM fd_valid
  GROUP BY NODE_ID, FIRST_DIGIT
),

-- Step N2e: Benford expected probabilities for digits 1–9 (constants)
-- P(d) = log10(1 + 1/d) — Benford's Law
benford_expected AS (
  SELECT 1 AS DIGIT, LOG(10, 1 + 1/1) AS EXPECTED FROM DUAL UNION ALL
  SELECT 2,          LOG(10, 1 + 1/2)             FROM DUAL UNION ALL
  SELECT 3,          LOG(10, 1 + 1/3)             FROM DUAL UNION ALL
  SELECT 4,          LOG(10, 1 + 1/4)             FROM DUAL UNION ALL
  SELECT 5,          LOG(10, 1 + 1/5)             FROM DUAL UNION ALL
  SELECT 6,          LOG(10, 1 + 1/6)             FROM DUAL UNION ALL
  SELECT 7,          LOG(10, 1 + 1/7)             FROM DUAL UNION ALL
  SELECT 8,          LOG(10, 1 + 1/8)             FROM DUAL UNION ALL
  SELECT 9,          LOG(10, 1 + 1/9)             FROM DUAL
),

-- Step N2f: Cross-join node × 9 digits to ensure all slots exist (even if observed=0)
all_digit_slots AS (
  SELECT f.NODE_ID, b.DIGIT, b.EXPECTED, f.TOTAL_CNT
  FROM fd_totals f
  CROSS JOIN benford_expected b
),

-- Step N2g: Join observed counts; missing digits get count=0
digit_obs AS (
  SELECT
    s.NODE_ID,
    s.DIGIT,
    s.EXPECTED,
    NVL(d.D_CNT, 0) / s.TOTAL_CNT     AS OBSERVED   -- proportion observed for this digit
  FROM all_digit_slots s
  LEFT JOIN fd_by_digit d
         ON d.NODE_ID = s.NODE_ID AND d.FIRST_DIGIT = s.DIGIT
),

-- Step N2h: Compute MAD = AVG(|observed − expected|) per node
-- Normalize by 0.10 so that 1.0 = "maximally violating" (GraphAML engine convention)
n2_benford AS (
  SELECT
    NODE_ID,
    AVG(ABS(OBSERVED - EXPECTED)) / 0.10     AS BENFORD_MAD   -- normalized MAD score
  FROM digit_obs
  GROUP BY NODE_ID
),


-- ==========================================================
-- N3: DOW ENTROPY (Shannon entropy of day-of-week distribution)
-- Measures: are sends spread across all weekdays (entropy≈2.8)
--           or clustered on specific days (entropy≈0)?
-- Range: 0 (one day only) to log2(7) ≈ 2.807 (perfectly uniform)
-- Minimum: 7 send events minimum
-- ==========================================================

-- Step N3a: Extract day of week for each send
-- TO_CHAR(date, 'D'): 1=Sunday, 2=Monday, ..., 7=Saturday (Oracle)
send_dow AS (
  SELECT
    NODE_ID,
    TO_NUMBER(TO_CHAR(TX_DATETIME, 'D'))     AS DOW
  FROM sends
),

-- Step N3b: Total send count per node (minimum threshold)
dow_totals AS (
  SELECT NODE_ID, COUNT(*) AS TOTAL_TX
  FROM send_dow
  GROUP BY NODE_ID
  HAVING COUNT(*) >= 7            -- need at least 1 full week of sends
),

-- Step N3c: Proportion of sends on each DOW per node
dow_probs AS (
  SELECT
    s.NODE_ID,
    s.DOW,
    COUNT(*) / t.TOTAL_TX         AS PROB
  FROM send_dow s
  JOIN dow_totals t ON t.NODE_ID = s.NODE_ID
  GROUP BY s.NODE_ID, s.DOW, t.TOTAL_TX
),

-- Step N3d: Shannon entropy H = −Σ p_d × log2(p_d)
n3_entropy AS (
  SELECT
    NODE_ID,
    -SUM(PROB * LOG(2, PROB + 1E-12))    AS DOW_ENTROPY   -- 1E-12 avoids log(0)
  FROM dow_probs
  GROUP BY NODE_ID
),


-- ==========================================================
-- N4: AMOUNT CV (Coefficient of Variation = σ/μ of send amounts)
-- Measures: how variable are this customer's send amounts?
-- High CV = amounts vary wildly (layering laundering pattern)
-- Low CV = highly uniform amounts (structuring pattern or normal salary)
-- Minimum: 2 send events
-- ==========================================================

n4_cv AS (
  SELECT
    NODE_ID,
    STDDEV_POP(AMOUNT) / NULLIF(AVG(AMOUNT), 0)    AS AMOUNT_CV
  FROM sends
  GROUP BY NODE_ID
  HAVING COUNT(*) >= 2
),


-- ==========================================================
-- N5: DORMANCY DAYS (maximum gap between consecutive send dates)
-- Measures: longest period this customer went silent (stopped sending)
-- High dormancy = sudden reactivation — common in layering accounts
-- Uses DISTINCT dates to handle multiple txns on same day
-- ==========================================================

-- Step N5a: Get distinct send dates per node
distinct_send_dates AS (
  SELECT DISTINCT NODE_ID, TX_DATE
  FROM sends
),

-- Step N5b: Gap between each consecutive send date (in days)
-- Oracle: DATE minus DATE = number of days (integer arithmetic)
date_gaps AS (
  SELECT
    NODE_ID,
    TX_DATE - LAG(TX_DATE) OVER (
        PARTITION BY NODE_ID ORDER BY TX_DATE
    )                                    AS GAP_DAYS
  FROM distinct_send_dates
),

-- Step N5c: Maximum dormancy period per node
n5_dormancy AS (
  SELECT NODE_ID, MAX(GAP_DAYS) AS DORMANCY_DAYS
  FROM date_gaps
  WHERE GAP_DAYS IS NOT NULL             -- exclude first row per node (LAG = NULL)
  GROUP BY NODE_ID
),


-- ==========================================================
-- N6: RELAY RATIO (proportion of funds immediately passed on)
-- Measures: does this customer receive money and quickly re-send it?
-- Pattern: RECEIVE → SEND within 24 hours (classic relay/passthrough)
-- Range: 0 (no relay) to 1.0 (all received funds immediately forwarded)
-- Formula: MIN(relay_amount, send_amount) / total_sent per node
-- ==========================================================

-- Step N6a: Match each send with a receive on the SAME node within the prior 24 hours
-- This joins sends to recvs: "did this node receive, then send, within 24h?"
-- LEAST(send_amt, recv_amt) = the amount that was "relayed" (capped at smaller leg)
matched_relay AS (
  SELECT
    s.NODE_ID,
    s.TX_DATETIME                         AS SEND_DT,
    r.TX_DATETIME                         AS RECV_DT,
    LEAST(s.AMOUNT, r.AMOUNT)             AS RELAY_AMT
  FROM sends s
  JOIN recvs r
    ON r.NODE_ID = s.NODE_ID              -- same customer
   AND r.TX_DATETIME <= s.TX_DATETIME     -- received BEFORE the send
   AND r.TX_DATETIME >= s.TX_DATETIME - 1 -- received within 24 hours (1 day in Oracle)
),

-- Step N6b: Total sent per node (denominator)
send_totals AS (
  SELECT NODE_ID, SUM(AMOUNT) AS TOTAL_SENT
  FROM sends
  GROUP BY NODE_ID
),

-- Step N6c: Total relay amount per node (sum of all matched relay events)
relay_totals AS (
  SELECT NODE_ID, SUM(RELAY_AMT) AS TOTAL_RELAY
  FROM matched_relay
  GROUP BY NODE_ID
),

-- Step N6d: Relay ratio = total_relay / total_sent, capped at 1.0
n6_relay AS (
  SELECT
    s.NODE_ID,
    LEAST(
      NVL(r.TOTAL_RELAY, 0) / NULLIF(s.TOTAL_SENT, 0),   -- NULLIF: divide-by-zero guard
      1.0                                                   -- cap at 1.0 (can't relay > 100%)
    )                                                      AS RELAY_RATIO
  FROM send_totals s
  LEFT JOIN relay_totals r ON r.NODE_ID = s.NODE_ID
),


-- ==========================================================
-- FINAL ASSEMBLY: Join all N1–N6 onto the full customer list
-- LEFT JOIN ensures every customer appears even if below threshold
-- NVL/CASE provides safe default values for missing columns
-- ==========================================================

final_nodes AS (
  SELECT
    n.CUSTOMER_ID,

    -- N1: Burstiness (default −1 = perfectly regular if not enough data)
    NVL(b1.BURSTINESS_B, -1)             AS BURSTINESS_B,

    -- N2: Benford MAD (default 0 = no Benford violation if not enough data)
    NVL(b2.BENFORD_MAD,   0)             AS BENFORD_MAD,

    -- N3: DOW Entropy (default 0 = no spread if not enough data)
    NVL(e3.DOW_ENTROPY,   0)             AS DOW_ENTROPY,

    -- N4: Amount CV (default 0 = no variability if not enough data)
    NVL(c4.AMOUNT_CV,     0)             AS AMOUNT_CV,

    -- N5: Dormancy Days (default 0 = no gap seen if not enough data)
    NVL(d5.DORMANCY_DAYS, 0)             AS DORMANCY_DAYS,

    -- N6: Relay Ratio (default 0 = no relay detected if no sends)
    NVL(r6.RELAY_RATIO,   0)             AS RELAY_RATIO

  FROM all_nodes n
  LEFT JOIN n1_burstiness  b1 ON b1.NODE_ID   = n.CUSTOMER_ID
  LEFT JOIN n2_benford      b2 ON b2.NODE_ID   = n.CUSTOMER_ID
  LEFT JOIN n3_entropy      e3 ON e3.NODE_ID   = n.CUSTOMER_ID
  LEFT JOIN n4_cv           c4 ON c4.NODE_ID   = n.CUSTOMER_ID
  LEFT JOIN n5_dormancy     d5 ON d5.NODE_ID   = n.CUSTOMER_ID
  LEFT JOIN n6_relay        r6 ON r6.NODE_ID   = n.CUSTOMER_ID
)

-- ----------------------------------------------------------
-- FINAL OUTPUT
-- ----------------------------------------------------------
SELECT *
FROM   final_nodes
ORDER BY CUSTOMER_ID;
```

---

---

# BLOCK 3 — Python: Complete Functions for All 13 Columns

```python
"""
AML GraphAML — 13 Compensation Columns: Complete Python Implementation
Computes all E1–E7 (edge) and N1–N6 (node) columns from raw transaction data.

Input: raw_df — DataFrame with columns:
  sender_id    : str    — who sent
  receiver_id  : str    — who received
  amount       : float  — INDIVIDUAL transaction amount (not pre-aggregated)
  tx_datetime  : datetime — exact transaction timestamp
"""

import pandas as pd
import numpy as np
from scipy.stats import entropy as scipy_entropy


# ===========================================================
# BLOCK 1 — EDGE TABLE (E1–E7)
# ===========================================================

def build_edge_compensation(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregates raw individual transactions to monthly rollup with
    all 7 compensation columns (E1–E7) added.

    Args:
        raw_df: DataFrame with sender_id, receiver_id, amount, tx_datetime

    Returns:
        edge_df: Monthly rollup edge DataFrame ready for transactions.csv
    """
    df = raw_df.copy()

    # Ensure datetime type
    df["tx_dt"] = pd.to_datetime(df["tx_datetime"])

    # ----- Month-end key (TX_DATE) -----
    # All Nov txns → 2025-11-30, all Oct → 2025-10-31, etc.
    df["tx_date"] = df["tx_dt"].dt.to_period("M").dt.to_timestamp("M")

    # Group key
    grp = ["sender_id", "receiver_id", "tx_date"]

    # ----- Base aggregation -----
    base = df.groupby(grp).agg(
        tx_count   = ("amount", "count"),
        total_amount = ("amount", "sum"),
        avg_amount = ("amount", "mean"),
    ).reset_index()

    # ----- E1: Count structuring band ($8,000–$9,999.99) -----
    band = df[(df["amount"] >= 8000) & (df["amount"] <= 9999.99)]
    e1 = band.groupby(grp).size().rename("count_structuring_band").reset_index()

    # ----- E2 + E3: Min and max individual amounts -----
    e2e3 = df.groupby(grp).agg(
        min_amount = ("amount", "min"),
        max_amount = ("amount", "max"),
    ).reset_index()

    # ----- E4: Off-hours individual transactions (10PM–6AM) -----
    df["tx_hour"] = df["tx_dt"].dt.hour
    off = df[(df["tx_hour"] >= 22) | (df["tx_hour"] <= 6)]
    e4 = off.groupby(grp).size().rename("off_hours_tx_count").reset_index()

    # ----- E5: Round-amount individual transactions (%1000 < 1.0) -----
    rnd = df[(df["amount"] % 1000) < 1.0]
    e5 = rnd.groupby(grp).size().rename("round_amount_count").reset_index()

    # ----- E6 + E7: Recent vs baseline (30-day split from max date) -----
    max_dt = df["tx_dt"].max()
    cutoff = max_dt - pd.Timedelta(days=30)

    recent = df[df["tx_dt"] >= cutoff]
    baseline = df[df["tx_dt"] < cutoff]

    e6 = recent.groupby(grp).size().rename("recent_tx_count").reset_index()
    e7 = baseline.groupby(grp).size().rename("baseline_tx_count").reset_index()

    # ----- Merge all columns -----
    result = base
    for col_df in [e1, e2e3, e4, e5, e6, e7]:
        result = result.merge(col_df, on=grp, how="left")

    # Fill missing counts with 0
    int_cols = ["count_structuring_band", "off_hours_tx_count",
                "round_amount_count", "recent_tx_count", "baseline_tx_count"]
    result[int_cols] = result[int_cols].fillna(0).astype(int)

    return result.sort_values(["sender_id", "receiver_id", "tx_date"])


# ===========================================================
# BLOCK 2 — NODE TABLE (N1–N6)
# ===========================================================

def _compute_burstiness(timestamps: pd.Series) -> float:
    """
    N1: Burstiness B = (σ − μ) / (σ + μ) of inter-event gaps.
    Returns -1.0 if fewer than 3 timestamps (not enough gaps).
    """
    ts = timestamps.sort_values().values
    if len(ts) < 3:       # need at least 2 gaps
        return -1.0
    gaps = np.diff(ts.astype("int64")) / 1e9  # nanoseconds → seconds
    mu, sigma = gaps.mean(), gaps.std(ddof=0)
    denom = sigma + mu
    if denom == 0:
        return -1.0   # perfectly regular (all gaps = 0)
    return float((sigma - mu) / denom)


def _compute_benford_mad(amounts: pd.Series) -> float:
    """
    N2: Mean Absolute Deviation from Benford's Law.
    Uses individual transaction amounts (sent + received).
    Returns 0.0 if fewer than 30 amounts.
    Normalized by 0.10 (GraphAML engine convention).
    """
    if len(amounts) < 30:
        return 0.0
    valid = amounts[amounts >= 1.0]
    if len(valid) < 30:
        return 0.0

    # Extract first significant digit
    first_digits = (valid / 10 ** np.floor(np.log10(valid))).astype(int)
    first_digits = first_digits[(first_digits >= 1) & (first_digits <= 9)]
    if len(first_digits) < 30:
        return 0.0

    # Benford expected probabilities (log10(1 + 1/d))
    benford_exp = {d: np.log10(1 + 1/d) for d in range(1, 10)}
    total = len(first_digits)
    observed = first_digits.value_counts() / total

    mad = np.mean([abs(observed.get(d, 0) - benford_exp[d]) for d in range(1, 10)])
    return float(mad / 0.10)   # normalize


def _compute_dow_entropy(send_timestamps: pd.Series) -> float:
    """
    N3: Shannon entropy of day-of-week distribution of sends.
    H = −Σ p_d × log2(p_d). Range: 0 to log2(7) ≈ 2.807.
    Returns 0.0 if fewer than 7 sends.
    """
    if len(send_timestamps) < 7:
        return 0.0
    dow_counts = pd.to_datetime(send_timestamps).dt.dayofweek.value_counts(normalize=True)
    probs = dow_counts.values
    return float(-np.sum(probs * np.log2(probs + 1e-12)))


def _compute_amount_cv(send_amounts: pd.Series) -> float:
    """
    N4: Coefficient of Variation = σ / μ of individual send amounts.
    Returns 0.0 if fewer than 2 sends.
    """
    if len(send_amounts) < 2:
        return 0.0
    mu = send_amounts.mean()
    if mu == 0:
        return 0.0
    return float(send_amounts.std(ddof=0) / mu)


def _compute_dormancy_days(send_timestamps: pd.Series) -> float:
    """
    N5: Maximum gap in days between consecutive send dates.
    Uses DISTINCT dates to handle multiple txns on same day.
    Returns 0.0 if fewer than 2 distinct send dates.
    """
    dt = pd.to_datetime(send_timestamps)
    unique_dates = sorted(set(dt.dt.date))
    if len(unique_dates) < 2:
        return 0.0
    gaps = [(unique_dates[i+1] - unique_dates[i]).days
            for i in range(len(unique_dates) - 1)]
    return float(max(gaps))


def _compute_relay_ratio_all_nodes(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    N6: Relay ratio for ALL nodes — vectorized using merge_asof.
    Relay = receive money then re-send within 24 hours.
    Formula: LEAST(relay_amount, send_amount) / total_sent per node.

    Returns DataFrame with columns: [node_id, relay_ratio]
    """
    sends = raw_df[["sender_id", "tx_datetime", "amount"]].copy()
    sends = sends.rename(columns={"sender_id": "node_id", "amount": "send_amt"})
    sends["tx_dt"] = pd.to_datetime(sends["tx_datetime"])
    sends = sends[["node_id", "tx_dt", "send_amt"]].sort_values(["node_id", "tx_dt"])

    recvs = raw_df[["receiver_id", "tx_datetime", "amount"]].copy()
    recvs = recvs.rename(columns={"receiver_id": "node_id", "amount": "recv_amt"})
    recvs["tx_dt"] = pd.to_datetime(recvs["tx_datetime"])
    recvs = recvs[["node_id", "tx_dt", "recv_amt"]].sort_values(["node_id", "tx_dt"])

    # merge_asof: for each send, find the most recent receive within 24h before
    matched = pd.merge_asof(
        sends,
        recvs,
        on="tx_dt",
        by="node_id",
        tolerance=pd.Timedelta(hours=24),
        direction="backward",
    )

    matched = matched.dropna(subset=["recv_amt"])
    matched["relay_amt"] = np.minimum(matched["send_amt"], matched["recv_amt"])

    relay_sum = matched.groupby("node_id")["relay_amt"].sum()
    send_sum  = sends.groupby("node_id")["send_amt"].sum()

    ratio = (relay_sum / send_sum).clip(upper=1.0).fillna(0.0).rename("relay_ratio")
    return ratio.reset_index()


def build_node_profiles(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Master function: computes all N1–N6 for every customer in raw_df.
    Uses individual raw transactions (90-day window, NOT pre-aggregated).

    Args:
        raw_df: DataFrame with sender_id, receiver_id, amount, tx_datetime

    Returns:
        node_df: One row per customer with N1–N6 columns → ready for nodes.csv
    """
    df = raw_df.copy()
    df["tx_dt"] = pd.to_datetime(df["tx_datetime"])

    # All customer IDs (union of senders and receivers)
    all_customers = set(df["sender_id"].unique()) | set(df["receiver_id"].unique())

    # Split into send and receive views
    sends = df.groupby("sender_id")
    all_send_recv_amounts = pd.concat([
        df[["sender_id",   "tx_dt", "amount"]].rename(columns={"sender_id":   "node_id"}),
        df[["receiver_id", "tx_dt", "amount"]].rename(columns={"receiver_id": "node_id"}),
    ])

    records = {}

    for cust in all_customers:
        send_rows   = df[df["sender_id"] == cust]
        all_amounts = all_send_recv_amounts[all_send_recv_amounts["node_id"] == cust]

        records[cust] = {
            # N1 — burstiness of send inter-event gaps
            "burstiness_b":  _compute_burstiness(send_rows["tx_dt"])
                             if len(send_rows) >= 3 else -1.0,

            # N2 — Benford MAD on all individual amounts (sent + received)
            "benford_mad":   _compute_benford_mad(all_amounts["amount"])
                             if len(all_amounts) >= 30 else 0.0,

            # N3 — DOW entropy of send timestamps
            "dow_entropy":   _compute_dow_entropy(send_rows["tx_dt"])
                             if len(send_rows) >= 7 else 0.0,

            # N4 — CV of individual send amounts
            "amount_cv":     _compute_amount_cv(send_rows["amount"])
                             if len(send_rows) >= 2 else 0.0,

            # N5 — max dormancy gap between consecutive send dates
            "dormancy_days": _compute_dormancy_days(send_rows["tx_dt"])
                             if len(send_rows) >= 2 else 0.0,

            # N6 — placeholder (computed vectorized below)
            "relay_ratio":   0.0,
        }

    node_df = pd.DataFrame.from_dict(records, orient="index")
    node_df.index.name = "customer_id"
    node_df = node_df.reset_index()

    # N6 — vectorized relay ratio (faster than per-customer loop)
    relay_df = _compute_relay_ratio_all_nodes(df)
    node_df = node_df.merge(
        relay_df.rename(columns={"node_id": "customer_id"}),
        on="customer_id", how="left", suffixes=("_drop", "")
    )
    node_df["relay_ratio"] = node_df["relay_ratio"].fillna(0.0)
    if "relay_ratio_drop" in node_df.columns:
        node_df = node_df.drop(columns=["relay_ratio_drop"])

    return node_df.sort_values("customer_id").reset_index(drop=True)
```

---

---

## Quick Reference — All 13 Columns at a Glance

| # | Column | Table | Type | Default | Min Data |
|---|---|---|---|---|---|
| E1 | `count_structuring_band` | edge | int | 0 | any |
| E2 | `min_amount` | edge | float | — | any |
| E3 | `max_amount` | edge | float | — | any |
| E4 | `off_hours_tx_count` | edge | int | 0 | any |
| E5 | `round_amount_count` | edge | int | 0 | any |
| E6 | `recent_tx_count` | edge | int | 0 | any |
| E7 | `baseline_tx_count` | edge | int | 0 | any |
| N1 | `burstiness_b` | node | float | −1.0 | ≥3 sends |
| N2 | `benford_mad` | node | float | 0.0 | ≥30 amounts |
| N3 | `dow_entropy` | node | float | 0.0 | ≥7 sends |
| N4 | `amount_cv` | node | float | 0.0 | ≥2 sends |
| N5 | `dormancy_days` | node | float | 0.0 | ≥2 distinct dates |
| N6 | `relay_ratio` | node | float | 0.0 | ≥1 send |

---

## Usage Pattern (Monthly Pipeline Run)

```
1. Load 90 days of RAW_TRANSACTIONS into Oracle working table
2. Run BLOCK 1 SQL → export to transactions.csv (edge table)
3. Run BLOCK 2 SQL → export to nodes.csv (node table)
4. Upload both CSVs to GraphAML v18.6 via web UI
5. GraphAML detects compensation columns → uses Tier 1/2 guards instead of failing silently
```

```python
# Python equivalent
import pandas as pd

raw_df = pd.read_csv("raw_transactions_90d.csv", parse_dates=["tx_datetime"])

edge_df = build_edge_compensation(raw_df)
edge_df.to_csv("transactions.csv", index=False)

node_df = build_node_profiles(raw_df)
node_df.to_csv("nodes.csv", index=False)

print(f"Edge rows: {len(edge_df)} | Node rows: {len(node_df)}")
```

---

*Generated by GitHub Copilot (Claude Sonnet 4.6) — April 15, 2026*
*GraphAML v18.6 | AML PhD Advisory Session*
*Companion docs: AML_ROLLUP_COMPENSATION_COLUMNS.md | AML_SAMPLE_SIZE_AND_DATA_DESIGN.md*
