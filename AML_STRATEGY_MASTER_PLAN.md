# AML Strategy Master Plan
**GraphAML v16.19 — Complete Reference Document**
*SQL-First Architecture | Graph Scoring Only | No Classification Model*
*Date: April 2026 | Cohort: November SAR Investigation*

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Key Clarifications & Locked Decisions](#2-key-clarifications--locked-decisions)
3. [Customer Taxonomy — All Types](#3-customer-taxonomy--all-types)
4. [Nodes.csv Schema — Base + Value-Addition Features](#4-nodescsv-schema--base--value-addition-features)
5. [SQL Type Extraction Queries](#5-sql-type-extraction-queries)
6. [Four-Iteration Production Run Plan](#6-four-iteration-production-run-plan)
7. [D-Score Component Weight Calibration](#7-d-score-component-weight-calibration)
8. [Improving D-Score from 6 to 8 — 5 Levers (No ML)](#8-improving-d-score-from-6-to-8--5-levers-no-ml)
9. [is_internal Column — Usage and Logic](#9-is_internal-column--usage-and-logic)
10. [Out-of-Scope Items](#10-out-of-scope-items)
11. [Next Steps — Sequenced](#11-next-steps--sequenced)
12. [Optimizing D-Score Weights — Exact Method and Values](#12-optimizing-d-score-weights--exact-method-and-values)
13. [Monthly SAR Accumulation — Using 2K–3K New SARs Each Month](#13-monthly-sar-accumulation--using-2k3k-new-sars-each-month-to-improve-performance)

---

## 1. Architecture Overview

### 1.1 System Components

| Component | Where It Lives | What It Does |
|---|---|---|
| **GraphAML Dash App** | Air-gapped Windows 11 PC, Anaconda Python 3.11, 16GB RAM | Graph scoring only: D1 Proximity, D2 Red Flags, D3 Centrality, D4 Community, D5 Similarity, D6 Identity, D7 Recency. Produces Tier1/Tier2/Tier3/Tier4 customer lists. |
| **SQL Server** | Bank's on-premise SQL Server | Holds 10M customers + all transactions. All heavy computation (aggregation, BFS, z-scores) runs here. Python receives only the 10K–20K filtered output. |
| **Classification Model** | **Does NOT exist in this architecture** | There is no PU Learning, LightGBM, XGBoost, or OCSVM anywhere in the pipeline. GraphAML is the scoring system. Period. |

### 1.2 End-to-End Data Flow

```
[SQL Server — 10M customers + transactions]
         |
         | SQL queries (all computation: BFS, aggregation, z-scores)
         |
    ┌────▼──────────────────────────────────────────────────────────┐
    │  WAVE 1: Type A + B3 + C + D + E      [SQL → 10K–15K rows]   │
    │  WAVE 2: Type G expansion              [SQL → +3K–5K rows]    │
    │  WAVE 3: Type F community              [SQL CTE → subgraph]   │
    │           ↓ subgraph only (50K–300K edges, NOT 10M)           │
    │       [Python PC: Louvain on subgraph → +1K–3K rows]          │
    └───────────────────────────────────────────────────────────────┘
         |
         | CSV Export (nodes.csv + transactions.csv, 10K–20K rows only)
         |
    [GraphAML v16.19 — Windows PC]
         |
         | 7 scoring dimensions (D1–D7)
         | Phase 0–8 pipeline (BFS, edge build, scoring, Tier assignment)
         |
    [Tier1 ≥65 / Tier2 ≥50 / Tier3 ≥35 / Tier4 ≥20]
         |
         | Investigation prioritisation list
         |
    [Analyst team — manual investigation]
```

### 1.3 Column Name Convention — CRITICAL

GraphAML expects these exact column names in `transactions.csv`:
- `originator_id` — the **sending** party (your sender/from-account column, aliased)
- `beneficiary_id` — the **receiving** party (your receiver/to-account column, aliased)

**If your SQL table uses different names, alias them in every SQL export:**
```sql
SELECT 
    t.sender_account AS originator_id,   -- alias to GraphAML required name
    t.receiver_account AS beneficiary_id, -- alias to GraphAML required name
    t.amount,
    t.date
FROM transactions t
```

---

## 2. Key Clarifications & Locked Decisions

### 2.1 No Classification Model — Anywhere

| Decision | Detail |
|---|---|
| **GraphAML role** | Graph scoring only. Outputs D1–D7 scores + Tier category. |
| **ML model** | None. No XGBoost, LightGBM, PU Learning, OCSVM. |
| **Score improvement** | Achieved through graph input quality only (see Section 8). |
| **Analyst action** | Tier1/Tier2 list → manual investigation. No model probability score. |

### 2.2 SAR Customer in originator_id OR beneficiary_id = 1-Hop Auto-Capture

**Short answer: YES — with one important nuance.**

When a SAR customer appears on either side of a transaction, that counterparty is automatically captured as a 1-hop neighbor by GraphAML's Phase 3 BFS. You do NOT need to pre-filter for directionality.

```
SAR in originator_id OR beneficiary_id
     → transaction edge captured in CSV ✅
     → GraphAML Phase 3 BFS assigns HOP_1 label ✅
     → D-score calculated fully ONLY IF node record exists in nodes.csv ✅/⚠️
     → External counterparties get stub score only (Phase 0.7) — expected ✅
```

**The nuance:** Counterparties only get full D-scores (D2–D7) if they have a complete row in `nodes.csv`. Counterparties missing from nodes.csv get Phase 0.7 external stubs with D1 proximity score only.

### 2.3 Criminal Ratio — Both Directions

The Type E criminal ratio query must capture both directions of criminal flow:

| Direction | SQL Pattern | Crime Typology |
|---|---|---|
| **Outbound from SAR** | External account is `beneficiary_id` where SAR is `originator_id` | Layering: criminal pushes funds to external account |
| **Inbound to SAR** | External account is `originator_id` where SAR is `beneficiary_id` | Placement: criminal deposits into SAR account |

Both directions must be captured. See Type E query in Section 5.

### 2.4 is_sar Column for Candidates

All candidate customers exported to `nodes.csv` (non-SAR waves: Type C, D, E, B3, G, F) must have:
```
is_sar = 0
```
Only the 3K SAR seeds have `is_sar = 1`. The candidates start at `is_sar = 0` and GraphAML scores their network risk — it does NOT assume they are guilty.

---

## 3. Customer Taxonomy — All Types

| Type | Label | Definition | How Extracted | Expected Volume |
|---|---|---|---|---|
| **A** | SAR Seeds | Confirmed SAR, filed investigation | `is_sar = 1` in SQL | 3,000 |
| **B1** | Related SAR | Different product/branch same customer | JOIN on `cust_id` across products | included in A |
| **B2** | Previous Cohort SAR | SAR in prior months (historical) | `investigation_month != current AND sar_filed = 1` | 500–2,000 |
| **B3** | Behaviorally Anomalous Cleared | Cleared customers who look statistically like SAR | SQL z-score on 47K cleared (Type B3 query) | 2,000–3,000 |
| **C** | 1-Hop Partners | Direct transaction partners of SAR customers | 1-hop JOIN on transactions (Type C query) | 4,000–8,000 |
| **D** | 2-Hop Partners | Partners of partners, not already in C | 2-hop CTE (Type D query) | 2,000–5,000 |
| **E** | Criminal Ratio | External accounts with ≥35% SAR transaction ratio | GROUP BY criminal ratio (Type E query) | 500–2,000 |
| **F** | Community Members | Same Louvain community as SAR seeds | 3-hop SQL subgraph → Python Louvain | 1,000–3,000 |
| **G** | Behaviorally Similar | Lowest distance to SAR behavioral centroid | SQL z-score distance (Type G query) | 3,000–5,000 |

### 3.1 Wave Composition Strategy

| Wave | Types Included | Target Rows | Priority |
|---|---|---|---|
| **WAVE 1** | A + B2 + B3 + C + D + E | 10,000–15,000 | Always include |
| **WAVE 2** | G (behavioral expansion) | +3,000–5,000 | Add if W1 < 15K |
| **WAVE 3** | F (community) | +1,000–3,000 | Add if coverage still low |

---

## 4. Nodes.csv Schema — Base + Value-Addition Features

### 4.1 Base Schema (GraphAML Required Columns)

| Column | Type | Tier | Default | Validation |
|---|---|---|---|---|
| `cust_id` | string | T1 | — | Required, unique |
| `name` | string | T1 | — | Required |
| `customer_type` | string | T1 | — | Required |
| `is_sar` | int | T1 | 0 | 0 or 1 |
| `sar_filing_date` | date | T1 | NULL | YYYY-MM-DD |
| `city` | string | T2 | NULL | — |
| `state` | string | T2 | NULL | 2-letter code |
| `account_open_date` | date | T2 | NULL | YYYY-MM-DD |
| `account_close_date` | date | T2 | NULL | YYYY-MM-DD or NULL |
| `case_create_date` | date | T2 | NULL | YYYY-MM-DD |
| `case_close_date` | date | T2 | NULL | YYYY-MM-DD or NULL |
| `account_status` | string | T2 | ACTIVE | ACTIVE/CLOSED/FROZEN |
| `peer_group` | string | T2 | NULL | Analyst-defined segment |
| `kyc_quality` | int | T3 | 0 | 0–100 |
| `jurisdiction_risk` | int | T3 | 0 | 0–100 |
| `ubo_identified` | int | T3 | 0 | 0 or 1 |
| `sar_confidence` | float | T3 | 0.0 | 0.0–1.0 |

### 4.2 Value-Addition Features (10 Columns — Beyond Base Schema)

These 10 columns augment the base schema. Each drives specific D-score dimensions when ingested by GraphAML.

**Column 1 — `prior_sar_count`**

| Attribute | Value |
|---|---|
| **Definition** | Number of prior SAR filings on this customer across all history |
| **D-Score Impact** | D2 Red Flags (direct financial crime indicator) |
| **Crime Typology** | Serial offenders: money launderers re-open under same cust_id |
| **Data Type** | INT |

```sql
SELECT 
    c.cust_id,
    ISNULL(h.sar_count, 0) AS prior_sar_count
FROM customer_master c
LEFT JOIN (
    SELECT cust_id, COUNT(*) AS sar_count
    FROM sar_historical_log
    WHERE filing_date < @run_date
    GROUP BY cust_id
) h ON c.cust_id = h.cust_id;
```

---

**Column 2 — `alert_count_12m`**

| Attribute | Value |
|---|---|
| **Definition** | Number of system-generated AML alerts in the past 12 months (whether investigated or not) |
| **D-Score Impact** | D2 Red Flags (alert history = system suspicion signal) |
| **Crime Typology** | Repeat-alert pattern: structuring, round-dollar, velocity alerts |
| **Data Type** | INT |

```sql
SELECT 
    c.cust_id,
    ISNULL(a.alert_count, 0) AS alert_count_12m
FROM customer_master c
LEFT JOIN (
    SELECT cust_id, COUNT(*) AS alert_count
    FROM alert_log
    WHERE alert_date >= DATEADD(MONTH, -12, @run_date)
    GROUP BY cust_id
) a ON c.cust_id = a.cust_id;
```

---

**Column 3 — `structuring_flag`**

| Attribute | Value |
|---|---|
| **Definition** | Binary: 1 if customer has ≥3 cash transactions between $8,000–$10,000 in any 30-day window in the past 12 months |
| **D-Score Impact** | D2 Red Flags (highest-weight individual flag for cash laundering) |
| **Crime Typology** | Classic structuring (smurfing): splitting deposits to stay below $10K CTR threshold |
| **Data Type** | INT (0/1) |

```sql
WITH cash_windows AS (
    SELECT 
        t.originator_id AS cust_id,
        DATEPART(YEAR, t.date) AS yr,
        DATEPART(MONTH, t.date) AS mo,
        COUNT(*) AS sub_threshold_cash_count
    FROM transactions t
    WHERE t.amount BETWEEN 8000 AND 9999.99
      AND t.transaction_type = 'CASH'
      AND t.date >= DATEADD(MONTH, -12, @run_date)
    GROUP BY t.originator_id, DATEPART(YEAR, t.date), DATEPART(MONTH, t.date)
)
SELECT 
    c.cust_id,
    CASE WHEN MAX(cw.sub_threshold_cash_count) >= 3 THEN 1 ELSE 0 END AS structuring_flag
FROM customer_master c
LEFT JOIN cash_windows cw ON c.cust_id = cw.cust_id
GROUP BY c.cust_id;
```

---

**Column 4 — `dormancy_reactivation_flag`**

| Attribute | Value |
|---|---|
| **Definition** | Binary: 1 if account had zero transactions for ≥6 months then suddenly active with high-value transactions |
| **D-Score Impact** | D7 Recency + D2 Red Flags (sudden behaviour change = layering signal) |
| **Crime Typology** | Account takeover or dormant account reactivated for layering pass |
| **Data Type** | INT (0/1) |

```sql
WITH activity_check AS (
    SELECT 
        cust_id,
        MAX(CASE WHEN date < DATEADD(MONTH, -6, @run_date) THEN 1 ELSE 0 END) AS was_dormant,
        MAX(CASE WHEN date >= DATEADD(MONTH, -3, @run_date) THEN 1 ELSE 0 END) AS recently_active,
        MAX(CASE WHEN date >= DATEADD(MONTH, -3, @run_date) THEN amount ELSE 0 END) AS recent_max_amount
    FROM (
        SELECT originator_id AS cust_id, date, amount FROM transactions
        UNION ALL
        SELECT beneficiary_id AS cust_id, date, amount FROM transactions
    ) all_tx
    WHERE date >= DATEADD(MONTH, -18, @run_date)
    GROUP BY cust_id
),
dormant_check AS (
    SELECT cust_id,
        CASE WHEN tx_count_6m_to_12m = 0 AND tx_count_recent_3m > 0 THEN 1 ELSE 0 END AS dormancy_reactivation_flag
    FROM (
        SELECT 
            cust_id,
            SUM(CASE WHEN date BETWEEN DATEADD(MONTH, -12, @run_date) 
                                    AND DATEADD(MONTH, -6, @run_date) THEN 1 ELSE 0 END) AS tx_count_6m_to_12m,
            SUM(CASE WHEN date >= DATEADD(MONTH, -3, @run_date) THEN 1 ELSE 0 END) AS tx_count_recent_3m
        FROM (
            SELECT originator_id AS cust_id, date FROM transactions
            UNION ALL
            SELECT beneficiary_id AS cust_id, date FROM transactions
        ) all_tx
        GROUP BY cust_id
    ) counts
)
SELECT c.cust_id, ISNULL(d.dormancy_reactivation_flag, 0) AS dormancy_reactivation_flag
FROM customer_master c
LEFT JOIN dormant_check d ON c.cust_id = d.cust_id;
```

---

**Column 5 — `counterparty_concentration_ratio`**

| Attribute | Value |
|---|---|
| **Definition** | Fraction of total transaction volume going to/from a single counterparty (max single-party concentration) |
| **D-Score Impact** | D5 Similarity + D3 Centrality (hub-and-spoke money flow) |
| **Crime Typology** | Hub-and-spoke layering: one controlling account receives funds from many smaller accounts |
| **Data Type** | FLOAT (0.0–1.0) |

```sql
WITH counterparty_volumes AS (
    SELECT 
        t.originator_id AS cust_id,
        t.beneficiary_id AS counterparty,
        SUM(t.amount) AS vol_to_counterparty
    FROM transactions t
    WHERE t.date >= DATEADD(MONTH, -12, @run_date)
    GROUP BY t.originator_id, t.beneficiary_id
),
total_volumes AS (
    SELECT cust_id, SUM(vol_to_counterparty) AS total_vol
    FROM counterparty_volumes
    GROUP BY cust_id
)
SELECT 
    cv.cust_id,
    MAX(cv.vol_to_counterparty) / NULLIF(tv.total_vol, 0) AS counterparty_concentration_ratio
FROM counterparty_volumes cv
JOIN total_volumes tv ON cv.cust_id = tv.cust_id
GROUP BY cv.cust_id, tv.total_vol;
```

---

**Column 6 — `high_risk_geo_tx_pct`**

| Attribute | Value |
|---|---|
| **Definition** | Percentage of transactions (by count) involving a high-risk jurisdiction or state (OFAC list, FATF grey-list, bank's own HRJ list) |
| **D-Score Impact** | D2 Red Flags + D6 Identity (geographic risk alignment) |
| **Crime Typology** | International layering, sanctions evasion, TBML from high-risk corridors |
| **Data Type** | FLOAT (0.0–1.0) |

```sql
SELECT 
    t.originator_id AS cust_id,
    COUNT(CASE WHEN c2.jurisdiction_risk >= 70 THEN 1 END) * 1.0 / NULLIF(COUNT(*), 0) 
        AS high_risk_geo_tx_pct
FROM transactions t
LEFT JOIN customer_master c2 ON t.beneficiary_id = c2.cust_id
WHERE t.date >= DATEADD(MONTH, -12, @run_date)
GROUP BY t.originator_id;
```

*Note: Replace `jurisdiction_risk >= 70` with your bank's HRJ lookup table join if available.*

---

**Column 7 — `cash_intensity_ratio`**

| Attribute | Value |
|---|---|
| **Definition** | Proportion of total transaction count that is cash-type (ATM, branch cash, cash deposit) |
| **D-Score Impact** | D2 Red Flags (cash = hardest to trace = highest layering risk) |
| **Crime Typology** | Cash placement phase: drug/trafficking proceeds entering banking system |
| **Data Type** | FLOAT (0.0–1.0) |

```sql
SELECT 
    originator_id AS cust_id,
    SUM(CASE WHEN transaction_type IN ('CASH', 'ATM', 'CASH_DEPOSIT') THEN 1.0 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS cash_intensity_ratio
FROM transactions
WHERE date >= DATEADD(MONTH, -12, @run_date)
GROUP BY originator_id;
```

---

**Column 8 — `shared_identity_count`**

| Attribute | Value |
|---|---|
| **Definition** | Number of OTHER customers who share ≥1 identity attribute with this customer (same address, phone, email, device ID, IP, or TIN) |
| **D-Score Impact** | D6 Identity (core dimension — shared identity = network cohesion) |
| **Crime Typology** | Synthetic identity fraud networks, money mule rings using shared infrastructure |
| **Data Type** | INT |

```sql
SELECT 
    c.cust_id,
    ISNULL(sa.shared_count, 0) AS shared_identity_count
FROM customer_master c
LEFT JOIN (
    SELECT cust_id_a AS cust_id, COUNT(DISTINCT cust_id_b) AS shared_count
    FROM shared_attributes_lookup  -- your identity attribute matching table
    WHERE match_type IN ('ADDRESS', 'PHONE', 'EMAIL', 'DEVICE_ID', 'TIN')
    GROUP BY cust_id_a
) sa ON c.cust_id = sa.cust_id;
```

---

**Column 9 — `account_age_risk_flag`**

| Attribute | Value |
|---|---|
| **Definition** | Binary: 1 if account is less than 6 months old AND total transaction volume exceeds 10× the peer group average |
| **D-Score Impact** | D2 Red Flags + D7 Recency (new high-volume account = mule or shell) |
| **Crime Typology** | New account abuse: mule accounts opened specifically for one layering pass then abandoned |
| **Data Type** | INT (0/1) |

```sql
WITH peer_averages AS (
    SELECT 
        c.peer_group,
        AVG(ISNULL(v.total_vol, 0)) AS peer_avg_vol
    FROM customer_master c
    LEFT JOIN (
        SELECT originator_id AS cust_id, SUM(amount) AS total_vol
        FROM transactions
        WHERE date >= DATEADD(MONTH, -12, @run_date)
        GROUP BY originator_id
    ) v ON c.cust_id = v.cust_id
    GROUP BY c.peer_group
),
customer_vol AS (
    SELECT originator_id AS cust_id, SUM(amount) AS total_vol
    FROM transactions
    WHERE date >= DATEADD(MONTH, -12, @run_date)
    GROUP BY originator_id
)
SELECT 
    c.cust_id,
    CASE 
        WHEN DATEDIFF(MONTH, c.account_open_date, @run_date) < 6
         AND ISNULL(cv.total_vol, 0) > 10 * ISNULL(pa.peer_avg_vol, 1)
        THEN 1 
        ELSE 0 
    END AS account_age_risk_flag
FROM customer_master c
LEFT JOIN customer_vol cv ON c.cust_id = cv.cust_id
LEFT JOIN peer_averages pa ON c.peer_group = pa.peer_group;
```

---

**Column 10 — `tx_velocity_change_ratio`**

| Attribute | Value |
|---|---|
| **Definition** | Ratio of transaction count in recent 90 days vs prior 90 days (recent/prior). Values >3 = sudden acceleration. |
| **D-Score Impact** | D7 Recency + D3 Centrality (sudden velocity spike = placement/layering event) |
| **Crime Typology** | Layering trigger: criminal activity creates sudden spike in normally quiet account |
| **Data Type** | FLOAT |

```sql
SELECT 
    cust_id,
    ISNULL(
        tx_count_recent_90d * 1.0 / NULLIF(tx_count_prior_90d, 0),
        CASE WHEN tx_count_recent_90d > 0 THEN 99.0 ELSE 1.0 END  -- 99 = was dormant, now active
    ) AS tx_velocity_change_ratio
FROM (
    SELECT 
        originator_id AS cust_id,
        SUM(CASE WHEN date >= DATEADD(DAY, -90, @run_date) THEN 1 ELSE 0 END) AS tx_count_recent_90d,
        SUM(CASE WHEN date BETWEEN DATEADD(DAY, -180, @run_date) 
                              AND DATEADD(DAY, -91, @run_date) THEN 1 ELSE 0 END) AS tx_count_prior_90d
    FROM transactions
    WHERE date >= DATEADD(DAY, -180, @run_date)
    GROUP BY originator_id
) velocity_calc;
```

---

### 4.3 Feature—D-Score Impact Summary Table

| # | Column | D1 | D2 | D3 | D4 | D5 | D6 | D7 |
|---|---|---|---|---|---|---|---|---|
| 1 | `prior_sar_count` | | ✅ | | | | | |
| 2 | `alert_count_12m` | | ✅ | | | | | |
| 3 | `structuring_flag` | | ✅ | | | | | |
| 4 | `dormancy_reactivation_flag` | | ✅ | | | | | ✅ |
| 5 | `counterparty_concentration_ratio` | | | ✅ | | ✅ | | |
| 6 | `high_risk_geo_tx_pct` | | ✅ | | | | ✅ | |
| 7 | `cash_intensity_ratio` | | ✅ | | | | | |
| 8 | `shared_identity_count` | | | | | | ✅ | |
| 9 | `account_age_risk_flag` | | ✅ | | | | | ✅ |
| 10 | `tx_velocity_change_ratio` | | | ✅ | | | | ✅ |

*(D1=Proximity, D2=Red Flags, D3=Centrality, D4=Community, D5=Similarity, D6=Identity, D7=Recency)*

---

## 5. SQL Type Extraction Queries

### 5.0 Prerequisite — SAR Master List

```sql
-- Small reference table — stays in SQL throughout the run
CREATE TABLE #sar_master_list AS
SELECT cust_id 
FROM customer_master 
WHERE investigation_month = 'November' AND sar_filed = 1;
-- Expected: ~3,000 rows
```

### 5.1 Prerequisite — Customer Features Precomputed Table

**Build ONCE, query instantly thereafter. Run as SQL Server Agent monthly job.**

```sql
-- Monthly refresh job (20–90 minutes to build, seconds to query thereafter)
DROP TABLE IF EXISTS customer_features_precomputed;

CREATE TABLE customer_features_precomputed AS
SELECT 
    c.cust_id,
    COUNT(t.tx_id)                                                      AS tx_count_90d,
    AVG(t.amount)                                                       AS avg_amount,
    MAX(t.amount)                                                       AS max_amount,
    SUM(t.amount)                                                       AS total_amount_90d,
    COUNT(DISTINCT CASE WHEN t.originator_id = c.cust_id 
                        THEN t.beneficiary_id END)                      AS unique_beneficiaries,
    SUM(CASE WHEN DATEPART(HOUR, t.time) BETWEEN 0 AND 5 
             THEN 1.0 ELSE 0 END) / NULLIF(COUNT(t.tx_id), 0)          AS off_hours_ratio,
    COUNT(DISTINCT t.geo_destination)                                   AS unique_destination_states
FROM customer_master c
LEFT JOIN transactions t 
    ON (t.originator_id = c.cust_id OR t.beneficiary_id = c.cust_id)
    AND t.date >= DATEADD(DAY, -90, GETDATE())
GROUP BY c.cust_id;

CREATE INDEX idx_cfp_cust_id ON customer_features_precomputed(cust_id);
-- Required by Type G and Type B3 queries
```

---

### 5.2 TYPE A — SAR Seeds

```sql
SELECT 
    cust_id, 
    'TYPE_A' AS wave_type, 
    100 AS priority_score
FROM customer_master
WHERE is_sar = 1
  AND investigation_month = @cohort_month;
-- Expected: ~3,000 rows | Time: <1 second
```

---

### 5.3 TYPE C — 1-Hop Partners of SAR

```sql
SELECT DISTINCT
    CASE 
        WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) 
        THEN t.beneficiary_id   -- SAR is sender → capture receiver
        ELSE t.originator_id    -- SAR is receiver → capture sender
    END AS cust_id,
    'TYPE_C' AS wave_type,
    COUNT(*) OVER (PARTITION BY 
        CASE WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) 
             THEN t.beneficiary_id ELSE t.originator_id END
    ) AS tx_count_with_sar
FROM transactions t
WHERE (t.originator_id IN (SELECT cust_id FROM #sar_master_list)
       OR t.beneficiary_id IN (SELECT cust_id FROM #sar_master_list))
  AND t.originator_id != t.beneficiary_id
  AND t.date >= DATEADD(MONTH, -12, @run_date)
  AND CASE 
        WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) 
        THEN t.beneficiary_id 
        ELSE t.originator_id 
      END NOT IN (SELECT cust_id FROM #sar_master_list)
ORDER BY tx_count_with_sar DESC;
-- Expected: 4,000–8,000 rows | Time: 5–30 seconds with indexes
```

---

### 5.4 TYPE D — 2-Hop Partners

```sql
WITH hop1 AS (
    SELECT DISTINCT
        CASE 
            WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) 
            THEN t.beneficiary_id 
            ELSE t.originator_id 
        END AS cust_id
    FROM transactions t
    WHERE (t.originator_id IN (SELECT cust_id FROM #sar_master_list)
           OR t.beneficiary_id IN (SELECT cust_id FROM #sar_master_list))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
),
hop2 AS (
    SELECT DISTINCT
        CASE 
            WHEN t.originator_id IN (SELECT cust_id FROM hop1) 
            THEN t.beneficiary_id 
            ELSE t.originator_id 
        END AS cust_id,
        COUNT(*) OVER (PARTITION BY 
            CASE WHEN t.originator_id IN (SELECT cust_id FROM hop1) 
                 THEN t.beneficiary_id ELSE t.originator_id END
        ) AS hop2_tx_count
    FROM transactions t
    WHERE (t.originator_id IN (SELECT cust_id FROM hop1)
           OR t.beneficiary_id IN (SELECT cust_id FROM hop1))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
)
SELECT TOP 5000
    h2.cust_id, 
    'TYPE_D' AS wave_type, 
    h2.hop2_tx_count
FROM hop2 h2
WHERE h2.cust_id NOT IN (SELECT cust_id FROM #sar_master_list)
  AND h2.cust_id NOT IN (SELECT cust_id FROM hop1)
ORDER BY h2.hop2_tx_count DESC;
-- Expected: 2,000–5,000 rows | Cap at 5K | Time: 30–120 seconds
```

---

### 5.5 TYPE E — Criminal Ratio (Both Directions)

```sql
-- Direction 1: External accounts RECEIVING from SAR customers (downstream)
SELECT 
    t.beneficiary_id AS external_acct_id,
    COUNT(*) AS total_tx,
    SUM(CASE WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) THEN 1 ELSE 0 END) AS sar_tx,
    CAST(SUM(CASE WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) THEN 1.0 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS FLOAT) AS criminal_ratio,
    SUM(t.amount) AS total_amount,
    'OUTBOUND' AS direction
FROM transactions t
WHERE t.beneficiary_id NOT IN (SELECT cust_id FROM customer_master)  -- external
  AND t.date >= DATEADD(MONTH, -12, @run_date)
GROUP BY t.beneficiary_id
HAVING CAST(SUM(CASE WHEN t.originator_id IN (SELECT cust_id FROM #sar_master_list) THEN 1.0 ELSE 0 END)
            / NULLIF(COUNT(*), 0) AS FLOAT) >= 0.35

UNION ALL

-- Direction 2: External accounts SENDING TO SAR customers (upstream/placement)
SELECT 
    t.originator_id AS external_acct_id,
    COUNT(*) AS total_tx,
    SUM(CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM #sar_master_list) THEN 1 ELSE 0 END) AS sar_tx,
    CAST(SUM(CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM #sar_master_list) THEN 1.0 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS FLOAT) AS criminal_ratio,
    SUM(t.amount) AS total_amount,
    'INBOUND' AS direction
FROM transactions t
WHERE t.originator_id NOT IN (SELECT cust_id FROM customer_master)  -- external
  AND t.date >= DATEADD(MONTH, -12, @run_date)
GROUP BY t.originator_id
HAVING CAST(SUM(CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM #sar_master_list) THEN 1.0 ELSE 0 END)
            / NULLIF(COUNT(*), 0) AS FLOAT) >= 0.35

ORDER BY criminal_ratio DESC, total_amount DESC;
-- Expected: 500–2,000 rows | Time: 10–60 seconds
```

---

### 5.6 TYPE B3 — Behaviorally Anomalous Cleared Customers

```sql
WITH cleared_features AS (
    SELECT 
        c.cust_id,
        COUNT(t.tx_id)                                                      AS tx_count_90d,
        AVG(t.amount)                                                       AS avg_amount,
        STDEV(t.amount)                                                     AS std_amount,
        MAX(t.amount)                                                       AS max_amount,
        SUM(t.amount)                                                       AS total_amount_90d,
        COUNT(DISTINCT t.beneficiary_id)                                    AS unique_beneficiaries,
        SUM(CASE WHEN DATEPART(HOUR, t.time) BETWEEN 0 AND 5 
                 THEN 1.0 ELSE 0 END) / NULLIF(COUNT(t.tx_id), 0)          AS off_hours_ratio
    FROM customer_master c
    LEFT JOIN transactions t 
        ON (t.originator_id = c.cust_id OR t.beneficiary_id = c.cust_id)
        AND t.date >= DATEADD(DAY, -90, @run_date)
    WHERE c.investigation_result = 'CLEARED'
      AND c.investigation_month = @cohort_month
    GROUP BY c.cust_id
),
global_stats AS (
    SELECT 
        AVG(tx_count_90d * 1.0)     AS mu_tx,   STDEV(tx_count_90d * 1.0) AS sd_tx,
        AVG(avg_amount)             AS mu_amt,  STDEV(avg_amount)          AS sd_amt,
        AVG(max_amount)             AS mu_max,  STDEV(max_amount)          AS sd_max,
        AVG(unique_beneficiaries * 1.0) AS mu_bene, STDEV(unique_beneficiaries * 1.0) AS sd_bene,
        AVG(off_hours_ratio)        AS mu_ohr,  STDEV(off_hours_ratio)     AS sd_ohr
    FROM cleared_features
),
anomaly_score AS (
    SELECT 
        cf.cust_id,
        POWER((cf.tx_count_90d - gs.mu_tx)           / NULLIF(gs.sd_tx,   0), 2) +
        POWER((cf.avg_amount   - gs.mu_amt)           / NULLIF(gs.sd_amt,  0), 2) +
        POWER((cf.max_amount   - gs.mu_max)           / NULLIF(gs.sd_max,  0), 2) +
        POWER((cf.unique_beneficiaries - gs.mu_bene)  / NULLIF(gs.sd_bene, 0), 2) +
        POWER((cf.off_hours_ratio - gs.mu_ohr)        / NULLIF(gs.sd_ohr,  0), 2)
            AS anomaly_score
    FROM cleared_features cf CROSS JOIN global_stats gs
)
SELECT TOP 3000 
    cust_id, 
    anomaly_score,
    'TYPE_B3' AS wave_type
FROM anomaly_score
ORDER BY anomaly_score DESC;  -- Highest anomaly = most SAR-like cleared customer
-- Expected: 2,000–3,000 rows | Time: 10–60 seconds on 47K cleared
```

---

### 5.7 TYPE G — Behaviorally Similar to SAR Centroid

*Requires `customer_features_precomputed` table (Section 5.1).*

```sql
WITH sar_centroid AS (
    SELECT 
        AVG(f.tx_count_90d * 1.0)          AS sar_mu_tx,   STDEV(f.tx_count_90d * 1.0) AS sar_sd_tx,
        AVG(f.avg_amount)                  AS sar_mu_amt,  STDEV(f.avg_amount)          AS sar_sd_amt,
        AVG(f.max_amount)                  AS sar_mu_max,  STDEV(f.max_amount)          AS sar_sd_max,
        AVG(f.off_hours_ratio)             AS sar_mu_ohr,  STDEV(f.off_hours_ratio)     AS sar_sd_ohr,
        AVG(f.unique_beneficiaries * 1.0)  AS sar_mu_bene, STDEV(f.unique_beneficiaries * 1.0) AS sar_sd_bene
    FROM customer_features_precomputed f
    WHERE f.cust_id IN (SELECT cust_id FROM #sar_master_list)
),
distance_to_sar AS (
    SELECT 
        cf.cust_id,
        POWER((cf.tx_count_90d - sc.sar_mu_tx)          / NULLIF(sc.sar_sd_tx,   0.01), 2) +
        POWER((cf.avg_amount   - sc.sar_mu_amt)          / NULLIF(sc.sar_sd_amt,  0.01), 2) +
        POWER((cf.max_amount   - sc.sar_mu_max)          / NULLIF(sc.sar_sd_max,  0.01), 2) +
        POWER((cf.off_hours_ratio - sc.sar_mu_ohr)       / NULLIF(sc.sar_sd_ohr,  0.001), 2) +
        POWER((cf.unique_beneficiaries - sc.sar_mu_bene) / NULLIF(sc.sar_sd_bene, 0.01), 2)
            AS distance_to_sar_centroid
    FROM customer_features_precomputed cf CROSS JOIN sar_centroid sc
    WHERE cf.cust_id NOT IN (SELECT cust_id FROM #sar_master_list)
)
SELECT TOP 5000 
    cust_id, 
    distance_to_sar_centroid,
    'TYPE_G' AS wave_type
FROM distance_to_sar
ORDER BY distance_to_sar_centroid ASC;  -- Smallest distance = most similar to SAR
-- Expected: 3,000–5,000 rows | Time: 5–30 seconds on precomputed table
```

---

### 5.8 TYPE F — Community Detection (SQL Subgraph → Python Louvain)

**Step 1 — SQL: Extract 3-hop subgraph edges**

```sql
WITH seeds AS (
    SELECT cust_id AS node_id FROM #sar_master_list
),
bfs_hop1 AS (
    SELECT DISTINCT
        CASE WHEN t.originator_id IN (SELECT node_id FROM seeds) 
             THEN t.beneficiary_id ELSE t.originator_id END AS node_id
    FROM transactions t
    WHERE (t.originator_id IN (SELECT node_id FROM seeds)
           OR t.beneficiary_id IN (SELECT node_id FROM seeds))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
),
bfs_hop2 AS (
    SELECT DISTINCT
        CASE WHEN t.originator_id IN (SELECT node_id FROM bfs_hop1) 
             THEN t.beneficiary_id ELSE t.originator_id END AS node_id
    FROM transactions t
    WHERE (t.originator_id IN (SELECT node_id FROM bfs_hop1)
           OR t.beneficiary_id IN (SELECT node_id FROM bfs_hop1))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
      AND CASE WHEN t.originator_id IN (SELECT node_id FROM bfs_hop1) 
               THEN t.beneficiary_id ELSE t.originator_id END 
          NOT IN (SELECT node_id FROM seeds)
),
bfs_hop3 AS (
    SELECT DISTINCT
        CASE WHEN t.originator_id IN (SELECT node_id FROM bfs_hop2) 
             THEN t.beneficiary_id ELSE t.originator_id END AS node_id
    FROM transactions t
    WHERE (t.originator_id IN (SELECT node_id FROM bfs_hop2)
           OR t.beneficiary_id IN (SELECT node_id FROM bfs_hop2))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
),
all_subgraph_nodes AS (
    SELECT node_id FROM seeds
    UNION SELECT node_id FROM bfs_hop1
    UNION SELECT node_id FROM bfs_hop2
    UNION SELECT node_id FROM bfs_hop3
)
SELECT 
    t.originator_id,
    t.beneficiary_id,
    SUM(t.amount)  AS total_amount,
    COUNT(*)       AS tx_count
FROM transactions t
WHERE t.originator_id IN (SELECT node_id FROM all_subgraph_nodes)
  AND t.beneficiary_id IN (SELECT node_id FROM all_subgraph_nodes)
  AND t.date >= DATEADD(MONTH, -12, @run_date)
GROUP BY t.originator_id, t.beneficiary_id;
-- Expected subgraph: 50K–500K nodes, 100K–2M edges | Time: 1–5 minutes
```

**Step 2 — Python on PC (subgraph only, NOT 10M rows)**

```python
import pandas as pd
import networkx as nx
import community as community_louvain  # pip install python-louvain
from collections import defaultdict

# Load subgraph edges from SQL export (small — 50K–300K rows)
edges_df = pd.read_csv('subgraph_edges.csv')
sar_seeds = set(pd.read_csv('sar_list.csv')['cust_id'])

G = nx.from_pandas_edgelist(
    edges_df,
    source='originator_id',
    target='beneficiary_id',
    edge_attr=['total_amount', 'tx_count']
)

# Louvain consensus: 10 runs, require 7/10 co-assignment
nodes = list(G.nodes())
co_occurrence = defaultdict(lambda: defaultdict(int))

for run in range(10):
    partition = community_louvain.best_partition(G, random_state=run)
    for n1 in nodes:
        for n2 in nodes:
            if partition[n1] == partition[n2]:
                co_occurrence[n1][n2] += 1

# Find non-SAR nodes that co-cluster with any SAR seed in ≥7/10 runs
type_f_candidates = set()
for node in nodes:
    if node not in sar_seeds:
        sar_co_count = sum(
            1 for sar in sar_seeds
            if sar in G.nodes() and co_occurrence[node][sar] >= 7
        )
        if sar_co_count >= 1:
            type_f_candidates.add(node)

print(f"Type F candidates: {len(type_f_candidates)}")
# Expected: 1,000–3,000 | Louvain 10x run time: 2–15 minutes on subgraph
```

---

## 6. Four-Iteration Production Run Plan

### 6.1 Run Schedule

| Run | Cohort Size | Wave Composition | Purpose |
|---|---|---|---|
| **Run 1** | 10,000 | W1 only (A+B3+C+D+E) | Baseline: tight network proximity only |
| **Run 2** | 15,000 | W1 + W2 (add Type G) | Expand: add behavioral similarity wave |
| **Run 3** | 13,000 | W1 + W2, exclude low-performing Type D tail | Prune: remove 2-hop with <2 SAR connections |
| **Run 4** | 17,000 | W1 + W2 + W3 (add Type F) | Full: community layer added |

### 6.2 Convergence Rule

Between Run N and Run N+1:
- If **Tier1 overlap ≥ 85%** → adding more nodes doesn't find new high-risk customers → stop
- If **Tier1 overlap < 85%** → still finding new high-risk customers with each expansion → continue

```python
# After each run, compute Tier1 overlap
tier1_run1 = set(run1_output[run1_output['tier'] == 'Tier1']['cust_id'])
tier1_run2 = set(run2_output[run2_output['tier'] == 'Tier1']['cust_id'])

overlap_pct = len(tier1_run1 & tier1_run2) / len(tier1_run1 | tier1_run2)
print(f"Tier1 Jaccard overlap: {overlap_pct:.2%}")

if overlap_pct >= 0.85:
    print("CONVERGED — proceed to final run only")
else:
    print("STILL EXPANDING — run next iteration")
```

### 6.3 Final Output Target

| Tier | Score Threshold | Target Volume | Action |
|---|---|---|---|
| **Tier 1** | ≥ 65 | 300–800 | Immediate investigation priority |
| **Tier 2** | 50–64 | 800–2,000 | Secondary investigation queue |
| **Tier 3** | 35–49 | 2,000–5,000 | Monitoring / enhanced due diligence |
| **Tier 4** | 20–34 | remaining | Passive watch list |

---

## 7. D-Score Component Weight Calibration

### 7.1 Why Calibrate

GraphAML default weights (D1–D7) are designed for a generic bank. Your bank's fraud mix, typology, and data quality will favour different dimensions. Calibration on YOUR data moves D-score from 6 to 8 without changing any algorithm.

### 7.2 Calibration Process — November Cohort

```
Step 1: Run GraphAML on calibration set
        Input: 3K SAR (November) + 5K known-cleared (lowest anomaly B3 score)
        Total: 8K customers
        
Step 2: Export D1–D7 component scores per customer
        (GraphAML outputs component breakdown in the export CSV)
        
Step 3: For each dimension Di:
        Compute:
            mean_Di_SAR     = average Di score for the 3K SAR customers
            mean_Di_Cleared = average Di score for the 5K cleared customers
            separation_ratio = (mean_Di_SAR - mean_Di_Cleared) / pooled_std_Di
            
Step 4: Set weight_i proportional to separation_ratio
        Dimensions where SAR and cleared are furthest apart → highest weight
        Dimensions where they overlap → lowest weight
        
Step 5: Normalize weights to sum to 1.0
        Write final weights to GraphAML config.yaml
        Lock these weights for all 4 production runs
```

### 7.3 Expected Calibration Outcome

| Dimension | Default Weight | Typical After Calibration | Reasoning |
|---|---|---|---|
| D1 Proximity | 0.20 | 0.15–0.18 | Network hop is good but not discriminating alone |
| D2 Red Flags | 0.20 | 0.25–0.30 | Alert history and SAR flags are strongest discriminators |
| D3 Centrality | 0.15 | 0.12–0.15 | Good for hubs; less useful for peripheral criminals |
| D4 Community | 0.15 | 0.10–0.15 | Community membership helps but noisy for small banks |
| D5 Similarity | 0.10 | 0.08–0.12 | Peer comparison useful if peer groups well-defined |
| D6 Identity | 0.10 | 0.12–0.18 | Shared identity is very discriminating (mule rings) |
| D7 Recency | 0.10 | 0.10–0.15 | Velocity change is strong signal for sudden-onset crime |

---

## 8. Improving D-Score from 6 to 8 — 5 Levers (No ML)

**Context:** There is no classification model. The D-score IS the scoring output. These 5 levers improve it through better graph inputs only.

### 8.1 Lever 1 — Seed Quality (highest impact: +0.8 points)

**Problem:** If `is_sar=1` seeds include incorrectly labeled customers (false SAR flags, data entry errors), BFS radiates from wrong nodes and the entire proximity scoring is corrupted.

**Fix:**
```sql
-- Audit seed quality before every run
SELECT 
    s.cust_id,
    c.sar_confidence,        -- should be ≥ 0.7 for high-quality seeds
    c.sar_filing_date,       -- should not be NULL
    c.investigation_month,   -- should match @cohort_month
    c.account_status         -- CLOSED seeds are fine; ACTIVE seeds are better
FROM #sar_master_list s
JOIN customer_master c ON s.cust_id = c.cust_id
WHERE c.sar_confidence < 0.5  -- flag for review
   OR c.sar_filing_date IS NULL;  -- flag for review
```

- Remove seeds with `sar_confidence < 0.5` or `sar_filing_date IS NULL` from the seed set
- A clean 2,500-seed set beats a contaminated 3,500-seed set every time

### 8.2 Lever 2 — Wave Composition (impact: +0.4 points)

**Problem:** Including too many Type D (2-hop) or Type G (behavioral) nodes dilutes the graph with weakly connected candidates who pull D3 Centrality scores down.

**Fix: Apply minimum connectivity thresholds before including a type:**

| Type | Minimum Requirement to Include |
|---|---|
| Type C | Any SAR connection in window → always include |
| Type D | Must have ≥2 distinct SAR-connected hop-1 partners |
| Type B3 | Anomaly score must be in top 30% of cleared pool |
| Type G | Distance-to-centroid must be ≤ 2.0 standard deviations |
| Type E | Criminal ratio must be ≥ 0.35 AND total SAR transaction volume ≥ $50K |
| Type F | Community must contain ≥2 SAR seeds |

### 8.3 Lever 3 — Nodes.csv Completeness (impact: +0.5 points)

**Problem:** If a non-SAR candidate node is missing from `nodes.csv`, it becomes a Phase 0.7 stub. D2–D7 scores are all zero or minimal. The node's true risk is invisible to the scorer.

**Fix:**
```sql
-- BEFORE export: verify every cust_id in your candidate list has a full row
-- Step 1: Build your candidate list
CREATE TABLE #all_candidates AS
    SELECT cust_id FROM type_a_results
    UNION SELECT cust_id FROM type_c_results
    UNION SELECT cust_id FROM type_d_results
    UNION SELECT cust_id FROM type_e_results
    UNION SELECT cust_id FROM type_b3_results
    UNION SELECT cust_id FROM type_g_results;

-- Step 2: Find any candidates with no data in customer_master
SELECT ac.cust_id, 'MISSING_FROM_MASTER' AS status
FROM #all_candidates ac
LEFT JOIN customer_master cm ON ac.cust_id = cm.cust_id
WHERE cm.cust_id IS NULL;

-- These will become stubs. If they are your bank's own customers (is_internal=1),
-- this is a data problem. Fix the ETL before running GraphAML.
-- If they are truly external (is_internal=0), stubs are expected and acceptable.
```

### 8.4 Lever 4 — D-Score Weight Calibration (impact: +0.6 points)

See Section 7. Calibrating weights to your bank's actual SAR vs cleared separation ratios is the single most systematic improvement available within the graph framework.

**Minimum calibration run size:**
- ≥ 500 confirmed SAR (for reliable mean computation)
- ≥ 1,000 confirmed cleared (lower-anomaly half of the pool)
- 3K + 5K as described in Section 7.2 is ideal

### 8.5 Lever 5 — Transaction Window Length Tuning (impact: +0.3 points)

**Problem:** Using 12 months as a fixed window captures old, stale transactions that no longer reflect current typology. Using 3 months misses slow-burn money laundering (trade-based ML, real estate ML) that unfolds over 6–18 months.

**Tuning approach (run on calibration set):**

| Window | Best For | Risk of Too Short | Risk of Too Long |
|---|---|---|---|
| 3 months | Velocity-based detection, account hijack | Misses slow laundering | N/A |
| 6 months | Most typologies — recommended default | Some slow burn missed | N/A |
| 12 months | Real estate ML, TBML, slow layering | N/A | Stale edges inflate hop counts |
| 18 months | Truly long-arc cases | N/A | Graph too large, scores diluted |

**Recommendation:** Run calibration at 6 months and 12 months. Compare Tier1 precision (SAR seeds landing in Tier1 ÷ total Tier1). Use the window that gives higher precision.

### 8.6 Score Improvement Summary

| Lever | Action | Effort | Impact |
|---|---|---|---|
| **1 — Seed Quality** | Audit and filter SAR seeds by confidence and filing date | SQL audit query: 5 min | **+0.8** |
| **2 — Wave Composition** | Apply minimum thresholds before including each type | SQL filter: 15 min | **+0.4** |
| **3 — Nodes Completeness** | Verify all candidate IDs have full rows; fix ETL gaps | SQL gap check + ETL: 1–2 hrs | **+0.5** |
| **4 — Weight Calibration** | Data-driven D1–D7 weights from November cohort separation ratios | Calibration run: 2–4 hrs | **+0.6** |
| **5 — Window Tuning** | Test 6-month vs 12-month, pick higher Tier1 precision | Two GraphAML runs: 1 hr | **+0.3** |
| **TOTAL** | | | **~+2.6 (6→8.6)** |

---

## 9. is_internal Column — Usage and Logic

### 9.1 Column Definition

`is_internal` is YOUR bank's own column (not in GraphAML base schema). It must be populated in your `customer_master` table and used in your SQL export logic.

| Value | Meaning | Example |
|---|---|---|
| `1` | This is YOUR bank's own customer — full KYC data available | Account holders at your institution |
| `0` | External counterparty — another bank's customer, you have limited data | Beneficiaries at other institutions |

### 9.2 Nodes.csv Population Logic

```
                    ┌─────────────────────────────┐
                    │   All cust_ids in candidate  │
                    │          pool                │
                    └──────────┬──────────────────┘
                               │
              ┌────────────────┴───────────────────┐
              │                                    │
    is_internal = 1                      is_internal = 0
    (YOUR customers)                     (External counterparty)
              │                                    │
    MUST have full row                   Two options:
    in nodes.csv with                    ├─ Has row in nodes.csv:
    all feature columns                  │   Full stub + whatever
    (base 17 + 10 value- │               │   data you have → OK
    addition columns)    │               └─ NOT in nodes.csv:
              │                               Phase 0.7 auto-creates
    If missing → DATA    │               external stub (D1 only)
    QUALITY PROBLEM      │               This is EXPECTED and OK
    Fix ETL              │
              │                                    │
              └────────────────┬───────────────────┘
                               │
                    Final nodes.csv export
```

### 9.3 SQL Export with is_internal Logic

```sql
-- nodes.csv export: filter and populate based on is_internal
SELECT 
    c.cust_id,
    c.name,
    c.customer_type,
    c.is_sar,
    c.sar_filing_date,
    c.city,
    c.state,
    c.account_open_date,
    c.account_close_date,
    c.case_create_date,
    c.case_close_date,
    c.account_status,
    c.peer_group,
    c.kyc_quality,
    c.jurisdiction_risk,
    c.ubo_identified,
    c.sar_confidence,
    -- Value-addition columns (for internal customers only; NULL for external)
    CASE WHEN c.is_internal = 1 THEN f.prior_sar_count           ELSE NULL END AS prior_sar_count,
    CASE WHEN c.is_internal = 1 THEN f.alert_count_12m           ELSE NULL END AS alert_count_12m,
    CASE WHEN c.is_internal = 1 THEN f.structuring_flag          ELSE NULL END AS structuring_flag,
    CASE WHEN c.is_internal = 1 THEN f.dormancy_reactivation_flag ELSE NULL END AS dormancy_reactivation_flag,
    CASE WHEN c.is_internal = 1 THEN f.counterparty_concentration_ratio ELSE NULL END AS counterparty_concentration_ratio,
    CASE WHEN c.is_internal = 1 THEN f.high_risk_geo_tx_pct      ELSE NULL END AS high_risk_geo_tx_pct,
    CASE WHEN c.is_internal = 1 THEN f.cash_intensity_ratio       ELSE NULL END AS cash_intensity_ratio,
    CASE WHEN c.is_internal = 1 THEN f.shared_identity_count     ELSE NULL END AS shared_identity_count,
    CASE WHEN c.is_internal = 1 THEN f.account_age_risk_flag     ELSE NULL END AS account_age_risk_flag,
    CASE WHEN c.is_internal = 1 THEN f.tx_velocity_change_ratio  ELSE NULL END AS tx_velocity_change_ratio
FROM customer_master c
JOIN #all_candidates ac ON c.cust_id = ac.cust_id      -- only export candidates, not all 10M
LEFT JOIN customer_features_derived f ON c.cust_id = f.cust_id  -- your precomputed feature table
WHERE c.is_internal = 1    -- include only internal customers in nodes.csv
                           -- external counterparties: let Phase 0.7 create stubs OR add manually
ORDER BY c.is_sar DESC, c.cust_id;
```

**Decision rule for external counterparties:**
- If you have partial data on them (account type, country) → include them in nodes.csv manually with NULLs for unknown columns
- If you have no data → let Phase 0.7 create the stub automatically — D1 score will be based on hop distance only

---

## 10. Out-of-Scope Items

| Item | Reason Out of Scope |
|---|---|
| PU Learning (Positive-Unlabeled) | No classification model in architecture |
| XGBoost / LightGBM scoring | No classification model in architecture |
| One-Class SVM | No classification model in architecture |
| Mahalanobis-in-Python on 10M customers | SQL-first constraint: Python cannot load 10M rows |
| Loading all cleared customers to pandas | Same constraint — only 10K–50K rows come to Python |
| Training/test split, PR-AUC measurement | No model to train or evaluate |
| Model serialization / versioning (pickle/ONNX) | No model in architecture |
| Azure ML / cloud deployment | Air-gapped Windows 11, on-premise only |
| Real-time scoring API | Batch-only architecture, not real-time |
| SHAP / feature importance | No model, hence no SHAP |

---

## 11. Next Steps — Sequenced

| # | Step | Prerequisite | Owner | Effort |
|---|---|---|---|---|
| **1** | Build `customer_features_precomputed` SQL table and index | Access to transactions table + 2-hour SQL Server window | Data Engineer | 2–4 hrs |
| **2** | Validate originator_id/beneficiary_id aliases in export queries | SQL table schema | Data Engineer | 30 min |
| **3** | Run seed quality audit (Section 8.1) on November SAR cohort | SAR master list | Analyst | 1 hr |
| **4** | Run Type A + Type C SQL queries on test set — verify row counts | Steps 1 + 2 | Data Engineer | 1 hr |
| **5** | Run all Wave 1 SQL queries → export nodes.csv + transactions.csv | Steps 1–4 | Data Engineer | 2–4 hrs |
| **6** | Run GraphAML v16.19 Run 1 (10K cohort) | Step 5 | Analyst | 30–90 min |
| **7** | Run calibration set against November cohort → compute D1–D7 separation ratios → set config.yaml weights | Step 6 | Data Scientist | 2–4 hrs |
| **8** | Run GraphAML Runs 2, 3, 4 with calibrated weights | Step 7 | Analyst | 1 day |
| **9** | Lock Tier1+Tier2 output → pass to investigation team | Run 4 completion | Analyst | 30 min |

---

## 12. Optimizing D-Score Weights — Exact Method and Values

### 12.1 Why Weights Matter

GraphAML computes a composite D-score as a weighted sum:

$$D_{composite} = w_1 \cdot D1 + w_2 \cdot D2 + w_3 \cdot D3 + w_4 \cdot D4 + w_5 \cdot D5 + w_6 \cdot D6 + w_7 \cdot D7$$

Default weights are equal or near-equal across all 7 dimensions. This is wrong for your bank because each dimension's ability to separate SAR from non-SAR customers differs based on your transaction mix, typology profile, and data quality. The optimal weights are derived from your own data — not guessed.

---

### 12.2 Step-by-Step Weight Derivation

**Step 1 — Run GraphAML on Calibration Set and Export Component Scores**

Run GraphAML on a labeled set: 3K confirmed SAR (November) + 5K confirmed cleared (bottom anomaly score pool from Type B3).

After the run, export the full score breakdown CSV from GraphAML. This will have one row per customer with columns:
```
cust_id, is_sar, D1, D2, D3, D4, D5, D6, D7, D_composite
```

**Step 2 — Compute Separation Ratio for Each Dimension**

For each dimension Di, compute how well it separates SAR from cleared:

$$\text{Separation Ratio}_i = \frac{\mu_{Di}^{SAR} - \mu_{Di}^{Cleared}}{\sqrt{\frac{\sigma_{Di}^{SAR,2} + \sigma_{Di}^{Cleared,2}}{2}}}$$

This is Cohen's d — a standardised effect size. The higher it is, the more discriminating that dimension is for YOUR data.

```python
import pandas as pd
import numpy as np

# Load calibration run output from GraphAML export
df = pd.read_csv('graphaml_calibration_run_scores.csv')

dimensions = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']
separation = {}

for d in dimensions:
    sar_scores    = df[df['is_sar'] == 1][d].dropna()
    clear_scores  = df[df['is_sar'] == 0][d].dropna()
    
    mu_sar    = sar_scores.mean()
    mu_clear  = clear_scores.mean()
    sd_sar    = sar_scores.std()
    sd_clear  = clear_scores.std()
    
    pooled_sd = np.sqrt((sd_sar**2 + sd_clear**2) / 2)
    cohens_d  = (mu_sar - mu_clear) / pooled_sd if pooled_sd > 0 else 0
    
    separation[d] = {
        'mu_sar':   round(mu_sar, 3),
        'mu_clear': round(mu_clear, 3),
        'cohens_d': round(cohens_d, 3)
    }
    print(f"{d}: SAR mean={mu_sar:.2f}, Cleared mean={mu_clear:.2f}, Cohen's d={cohens_d:.3f}")

sep_df = pd.DataFrame(separation).T
print("\n", sep_df.sort_values('cohens_d', ascending=False))
```

**Step 3 — Convert Separation Ratios to Weights**

```python
# Raw weights = Cohen's d for each dimension (only positive values contribute)
raw_weights = {d: max(separation[d]['cohens_d'], 0) for d in dimensions}

# Normalize so weights sum to 1.0
total = sum(raw_weights.values())
final_weights = {d: round(v / total, 4) for d, v in raw_weights.items()}

print("\nFinal calibrated weights:")
for d, w in sorted(final_weights.items(), key=lambda x: -x[1]):
    print(f"  {d}: {w:.4f}  ({w*100:.1f}%)")
```

**Step 4 — Apply Minimum Weight Floor**

No dimension should be completely zeroed out — even a weak signal has marginal value and prevents blind spots. Apply a minimum of 5% to any dimension:

```python
min_floor = 0.05
floored = {d: max(w, min_floor) for d, w in final_weights.items()}
total_floored = sum(floored.values())
final_weights_floored = {d: round(v / total_floored, 4) for d, v in floored.items()}

print("\nFinal weights with 5% floor applied:")
for d, w in sorted(final_weights_floored.items(), key=lambda x: -x[1]):
    print(f"  {d}: {w:.4f}  ({w*100:.1f}%)")
```

**Step 5 — Write to config.yaml**

```python
import yaml

config_path = r'D:\Asus_Onedrive\OneDrive\Desktop\desktop_samsung_may_2024\C\git\aml_graph\GraphAML_v16.19\graphaml\config\config.yaml'

with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

# Update the weights section (adjust key names to match your config.yaml structure)
config['scoring']['weights']['D1_proximity']   = final_weights_floored['D1']
config['scoring']['weights']['D2_red_flags']   = final_weights_floored['D2']
config['scoring']['weights']['D3_centrality']  = final_weights_floored['D3']
config['scoring']['weights']['D4_community']   = final_weights_floored['D4']
config['scoring']['weights']['D5_similarity']  = final_weights_floored['D5']
config['scoring']['weights']['D6_identity']    = final_weights_floored['D6']
config['scoring']['weights']['D7_recency']     = final_weights_floored['D7']

with open(config_path, 'w') as f:
    yaml.dump(config, f, default_flow_style=False)

print(f"Weights written to config.yaml — run GraphAML to apply.")
```

---

### 12.3 Expected Weight Values — Your Bank Profile

Based on typical AML typology at a mid-size bank with the November SAR cohort profile:

| Dimension | What It Measures | Expected Cohen's d | Expected Weight |
|---|---|---|---|
| **D2 — Red Flags** | Prior SAR, alerts, structuring, dormancy | 1.8–2.5 | **28–32%** |
| **D6 — Identity** | Shared address/phone/device/TIN | 1.4–2.0 | **20–25%** |
| **D1 — Proximity** | Hop distance to SAR seed | 1.2–1.8 | **18–22%** |
| **D7 — Recency** | Transaction velocity change | 0.8–1.4 | **10–14%** |
| **D3 — Centrality** | Hub/spoke network position | 0.6–1.2 | **8–12%** |
| **D5 — Similarity** | Peer group behavioral alignment | 0.4–0.9 | **6–9%** |
| **D4 — Community** | Louvain cluster with SAR seeds | 0.3–0.8 | **5–8%** |

**D2 will almost always dominate** because prior SAR history and alert count are the strongest single-customer signals in any labeled SAR dataset. D4 Community tends to be weakest because Louvain partitions are unstable across runs for peripheral nodes.

---

### 12.4 Weight Stability Check (Run After Each Monthly Cohort)

After computing weights for each new monthly cohort, check that they are not drifting significantly:

```python
# Track weights across cohorts in a running log
import json, os
from datetime import datetime

weight_log_path = 'weight_calibration_log.json'

# Load existing log or start fresh
if os.path.exists(weight_log_path):
    with open(weight_log_path, 'r') as f:
        weight_log = json.load(f)
else:
    weight_log = []

# Append this month's calibration result
weight_log.append({
    'cohort_month': 'November',
    'run_date': datetime.today().strftime('%Y-%m-%d'),
    'n_sar': 3000,
    'n_cleared': 5000,
    'weights': final_weights_floored,
    'cohens_d': separation
})

with open(weight_log_path, 'w') as f:
    json.dump(weight_log, f, indent=2)

# Drift check: if any weight changed by >0.05 vs prior month → flag for review
if len(weight_log) >= 2:
    prev = weight_log[-2]['weights']
    curr = weight_log[-1]['weights']
    for d in dimensions:
        drift = abs(curr[d] - prev[d])
        if drift > 0.05:
            print(f"WARNING: {d} weight drifted {drift:.3f} — review typology shift")
        else:
            print(f"OK: {d} weight stable (drift={drift:.3f})")
```

**If drift > 0.05 in D2 or D6**: new crime typology entering your SAR population (e.g. synthetic identity fraud increasing → D6 rises). Investigate the composition of the new SAR cohort before accepting new weights.

**If drift > 0.05 in D1 or D4**: Likely a data quality shift (new counterparty stub coverage, Louvain instability) rather than a true typology change. Inspect the nodes.csv completeness first.

---

### 12.5 Quick Reference — Weight Calibration Checklist

```
□ Run GraphAML on calibration set (3K SAR + 5K reliable cleared)
□ Export score breakdown CSV (D1–D7 per customer)
□ Run Python Step 2: compute Cohen's d for each dimension
□ Run Python Step 3: normalize raw weights
□ Run Python Step 4: apply 5% floor
□ Run Python Step 5: write to config.yaml
□ Re-run GraphAML Run 1 with new weights
□ Check: Tier1 precision (SAR seeds in Tier1 ÷ total Tier1) must be ≥ 80%
□ If precision < 80%: inspect lowest-Cohen's-d dimensions and lower their floor to 3%
□ Log weights to weight_calibration_log.json
□ Lock weights — do NOT change during the 4-iteration run cycle
```

---

## 13. Monthly SAR Accumulation — Using 2K–3K New SARs Each Month to Improve Performance

### 13.1 The Asset You Are Building

Every month you receive 2K–3K new confirmed SAR customers. Over time this builds into a **growing labeled dataset** that makes GraphAML progressively more accurate — both in seed quality and in weight calibration precision.

| Month | Cumulative SAR Count | Calibration Quality | Weight Precision |
|---|---|---|---|
| Month 1 (November) | 3,000 | Baseline | ±15% uncertainty |
| Month 3 | 8,000 | Good | ±8% uncertainty |
| Month 6 | 16,000 | Strong | ±5% uncertainty |
| Month 12 | 34,000 | Excellent | ±3% uncertainty |
| Month 24 | 70,000+ | Bank-grade reference set | ±1–2% uncertainty |

The goal: by Month 6, your weights are stable and your D-score Tier1 precision is consistently ≥85%.

---

### 13.2 Monthly Accumulation Pipeline

```
[Each Month — New SAR Batch: 2K–3K customers]
         |
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 1: Append to sar_historical_log             │
    │         (permanent labeled dataset)              │
    └────┬─────────────────────────────────────────────┘
         |
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 2: Update prior_sar_count feature           │
    │         for all customers in customer_master     │
    │         (affects D2 Red Flags score)             │
    └────┬─────────────────────────────────────────────┘
         |
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 3: Recalibrate weights using rolling        │
    │         12-month SAR pool (not just current month)│
    └────┬─────────────────────────────────────────────┘
         |
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 4: Validate SAR typology mix hasn't shifted │
    │         (Cohen's d drift check)                  │
    └────┬─────────────────────────────────────────────┘
         |
    ┌────▼─────────────────────────────────────────────┐
    │ STEP 5: Run next month's GraphAML with           │
    │         updated weights and enlarged seed pool   │
    └──────────────────────────────────────────────────┘
```

---

### 13.3 Step 1 — Append to sar_historical_log (SQL)

```sql
-- Run every month after new SAR list is received
-- This table is your permanent labeled training reservoir

CREATE TABLE IF NOT EXISTS sar_historical_log (
    cust_id          VARCHAR(50),
    sar_filing_date  DATE,
    cohort_month     VARCHAR(20),
    sar_type         VARCHAR(50),    -- e.g. STRUCTURING, LAYERING, PLACEMENT
    d_composite      FLOAT,          -- D-score GraphAML assigned BEFORE SAR was confirmed
    tier_assigned    VARCHAR(10),    -- Tier1/Tier2/Tier3/Tier4
    was_in_graphaml  BIT,            -- 1 if this SAR appeared in that month's run
    PRIMARY KEY (cust_id, cohort_month)
);

-- Insert new month's SARs
INSERT INTO sar_historical_log (cust_id, sar_filing_date, cohort_month, sar_type, was_in_graphaml)
SELECT 
    cm.cust_id,
    cm.sar_filing_date,
    @new_cohort_month,
    cm.sar_type,
    CASE WHEN gr.cust_id IS NOT NULL THEN 1 ELSE 0 END AS was_in_graphaml
FROM customer_master cm
LEFT JOIN graphaml_run_results gr ON cm.cust_id = gr.cust_id 
    AND gr.run_month = @new_cohort_month
WHERE cm.investigation_month = @new_cohort_month
  AND cm.sar_filed = 1
  AND NOT EXISTS (
    SELECT 1 FROM sar_historical_log h 
    WHERE h.cust_id = cm.cust_id AND h.cohort_month = @new_cohort_month
  );
```

**The `was_in_graphaml` column is critical** — it tracks whether GraphAML successfully surfaced each SAR before it was confirmed. This is your monthly recall score.

---

### 13.4 Step 2 — Update prior_sar_count Feature (SQL)

Every time a new SAR batch lands, `prior_sar_count` changes for those customers' network neighbors too (their counterparties now have a higher-risk partner).

```sql
-- Refresh prior_sar_count for all customers (run as monthly SQL Server Agent job)
UPDATE customer_master
SET prior_sar_count = (
    SELECT COUNT(*)
    FROM sar_historical_log h
    WHERE h.cust_id = customer_master.cust_id
      AND h.sar_filing_date < @run_date  -- only count historical SARs, not current month
)
WHERE customer_master.cust_id IN (
    SELECT DISTINCT cust_id FROM sar_historical_log  -- only update affected customers
);
```

---

### 13.5 Step 3 — Rolling Calibration (Recalibrate Weights Monthly)

Do NOT re-calibrate on just the new 2K–3K SARs each month — too few to be statistically stable. Use a **rolling 12-month SAR pool**:

```python
import pandas as pd
import numpy as np

# Load rolling 12-month labeled set from sar_historical_log
# (SQL export: last 12 months of SAR + their D-scores from GraphAML runs)
rolling_labeled = pd.read_csv('rolling_12month_sar_scores.sql_export.csv')
# Columns: cust_id, cohort_month, is_sar=1, D1, D2, D3, D4, D5, D6, D7

# Load rolling 12-month cleared set (low-anomaly cleared from each month)
rolling_cleared = pd.read_csv('rolling_12month_cleared_scores.sql_export.csv')
# Columns: cust_id, cohort_month, is_sar=0, D1, D2, D3, D4, D5, D6, D7

# Combine and recalibrate using the methodology in Section 12.2
calibration_df = pd.concat([
    rolling_labeled.assign(is_sar=1),
    rolling_cleared.assign(is_sar=0)
])

dimensions = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']
separation = {}

for d in dimensions:
    sar_scores   = calibration_df[calibration_df['is_sar'] == 1][d].dropna()
    clear_scores = calibration_df[calibration_df['is_sar'] == 0][d].dropna()
    pooled_sd    = np.sqrt((sar_scores.std()**2 + clear_scores.std()**2) / 2)
    cohens_d     = (sar_scores.mean() - clear_scores.mean()) / pooled_sd if pooled_sd > 0 else 0
    separation[d] = max(cohens_d, 0)

raw_total = sum(separation.values())
raw_weights = {d: separation[d] / raw_total for d in dimensions}

# Apply 5% floor
min_floor = 0.05
floored = {d: max(w, min_floor) for d, w in raw_weights.items()}
total_f = sum(floored.values())
final_weights = {d: round(v / total_f, 4) for d, v in floored.items()}

print("\nRolling 12-month calibrated weights:")
for d, w in sorted(final_weights.items(), key=lambda x: -x[1]):
    print(f"  {d}: {w*100:.1f}%")
```

**SQL export query for the rolling labeled set:**
```sql
-- Export: last 12 months of SAR customers with their GraphAML scores
SELECT 
    h.cust_id,
    h.cohort_month,
    1 AS is_sar,
    r.D1, r.D2, r.D3, r.D4, r.D5, r.D6, r.D7
FROM sar_historical_log h
JOIN graphaml_run_results r ON h.cust_id = r.cust_id 
    AND r.run_month = h.cohort_month
WHERE h.sar_filing_date >= DATEADD(MONTH, -12, @run_date)
  AND h.was_in_graphaml = 1;  -- only include SARs that were in the GraphAML run
```

---

### 13.6 Step 4 — Monthly Recall Tracking (Core Performance Metric)

**Recall** = of all confirmed SARs this month, what % did GraphAML surface in Tier1+Tier2 BEFORE they were confirmed?

This is the single most important performance metric for your setup. It tells you whether the graph is getting better.

```sql
-- Recall computation: run after each month's investigation closes
SELECT 
    h.cohort_month,
    COUNT(*) AS total_sar_confirmed,
    SUM(CASE WHEN r.tier IN ('Tier1', 'Tier2') THEN 1 ELSE 0 END) AS surfaced_in_tier1_2,
    SUM(CASE WHEN r.tier = 'Tier1' THEN 1 ELSE 0 END) AS surfaced_in_tier1,
    CAST(SUM(CASE WHEN r.tier IN ('Tier1', 'Tier2') THEN 1.0 ELSE 0 END) 
         / COUNT(*) AS FLOAT) AS recall_tier1_2,
    CAST(SUM(CASE WHEN r.tier = 'Tier1' THEN 1.0 ELSE 0 END) 
         / COUNT(*) AS FLOAT) AS recall_tier1
FROM sar_historical_log h
LEFT JOIN graphaml_run_results r ON h.cust_id = r.cust_id 
    AND r.run_month = h.cohort_month
GROUP BY h.cohort_month
ORDER BY h.cohort_month;
```

| Month | Target Recall (Tier1+2) | Target Recall (Tier1 only) |
|---|---|---|
| Month 1 (baseline) | ≥ 60% | ≥ 35% |
| Month 3 | ≥ 70% | ≥ 45% |
| Month 6 | ≥ 78% | ≥ 55% |
| Month 12 | ≥ 85% | ≥ 65% |

If recall is below target at Month 3: revisit seed quality (Lever 1) and nodes.csv completeness (Lever 3) before touching weights.

---

### 13.7 Step 5 — Missed SAR Analysis (Learning From Failures)

Every month, some SARs will NOT have been in Tier1 or Tier2. These are false negatives — missed cases. Analyzing them tells you exactly which part of the graph input to fix.

```sql
-- Identify missed SARs (confirmed SAR not in Tier1 or Tier2)
SELECT 
    h.cust_id,
    h.cohort_month,
    h.sar_type,
    r.tier          AS tier_assigned,
    r.D1, r.D2, r.D3, r.D4, r.D5, r.D6, r.D7,
    r.D_composite,
    h.was_in_graphaml
FROM sar_historical_log h
LEFT JOIN graphaml_run_results r ON h.cust_id = r.cust_id 
    AND r.run_month = h.cohort_month
WHERE h.cohort_month = @review_month
  AND (r.tier NOT IN ('Tier1', 'Tier2') OR r.tier IS NULL)
ORDER BY r.D_composite DESC;
```

**For each missed SAR, diagnose using this decision tree:**

```
Was the customer in nodes.csv?
│
├─ NO → Data gap: is_internal=1 but missing from ETL export
│        FIX: Fix the nodes.csv export query (Section 9.3)
│
└─ YES → Was D_composite very low (< 30)?
          │
          ├─ YES, D1 was low (hop distance ≥ 3) 
          │        → SAR had no strong network connection to seed pool
          │        FIX: Expand wave — add Type G or Type F
          │
          ├─ YES, D2 was low (no prior alerts/SAR)
          │        → First-time offender with no prior history
          │        FIX: Increase D7 Recency weight (velocity change catches first-timers)
          │
          ├─ YES, D6 was low (no shared identity)
          │        → Sophisticated criminal using clean identity
          │        FIX: No easy graph fix — these are the hardest cases
          │
          └─ D_composite was medium (30–50 = Tier3/Tier4)?
                   → Correct signal but wrong tier threshold
                   FIX: Lower Tier2 threshold from 50 to 45 for next run
```

---

### 13.8 Cumulative SAR Pool — Value Addition Over Time

As the SAR pool grows, use it to improve 3 specific things each quarter:

| Quarter | SAR Pool Size | New Capability Unlocked |
|---|---|---|
| **Q1** (Months 1–3) | 8K–10K SAR | Stable weight calibration (replace November-only calibration) |
| **Q2** (Months 4–6) | 16K–20K SAR | Typology-specific weight sets (separate weights for structuring vs layering vs placement) |
| **Q3** (Months 7–9) | 24K–30K SAR | Seasonal pattern detection (structuring spikes at tax season, year-end) |
| **Q4** (Months 10–12) | 34K+ SAR | Cross-month network expansion — SAR in Month N who transact with SAR in Month N-3 creates a 2-month-separated network edge |

---

### 13.9 Typology-Specific Weight Sets (Month 4+ Capability)

Once you have 3+ months of SAR, split the calibration pool by crime typology. Different crime types have very different network signatures:

| Typology | Dominant D-Scores | Why |
|---|---|---|
| **Structuring** | D2 very high, D1 low | Single-customer behavior, not network-based |
| **Layering** | D1 high, D3 high, D4 medium | Multi-hop fund movement through network |
| **Placement** | D2 high, D6 medium | Cash-intensive, often shared identity with criminal network |
| **Trade-Based ML** | D3 high, D7 medium | Hub accounts, slow velocity change |
| **Mule Networks** | D6 very high, D4 high | Shared identity + community clustering |

```python
# After Month 3: calibrate separate weight sets per typology
typologies = df['sar_type'].unique()

typology_weights = {}
for typology in typologies:
    sar_subset  = df[(df['is_sar'] == 1) & (df['sar_type'] == typology)]
    clear_subset = df[df['is_sar'] == 0]
    
    if len(sar_subset) < 200:
        print(f"Skip {typology}: too few examples ({len(sar_subset)} SAR)")
        continue
    
    weights_for_type = {}
    for d in dimensions:
        pooled_sd  = np.sqrt((sar_subset[d].std()**2 + clear_subset[d].std()**2) / 2)
        cohens_d   = (sar_subset[d].mean() - clear_subset[d].mean()) / pooled_sd if pooled_sd > 0 else 0
        weights_for_type[d] = max(cohens_d, 0)
    
    total = sum(weights_for_type.values())
    typology_weights[typology] = {
        d: round(max(v / total, 0.05), 4) 
        for d, v in weights_for_type.items()
    }
    print(f"\n{typology} weights: {typology_weights[typology]}")

# Write typology-specific weight sets to config.yaml
# GraphAML applies the matching weight set based on sar_type label on seeds
```

---

### 13.10 Monthly Operations Calendar

| Week | Action | Time Required |
|---|---|---|
| **Week 1, Day 1** | Receive new SAR list from investigation team | — |
| **Week 1, Day 1** | Append to `sar_historical_log` (SQL Step 1) | 15 min |
| **Week 1, Day 1** | Refresh `prior_sar_count` and `customer_features_precomputed` | 30–90 min (SQL Server Agent) |
| **Week 1, Day 2** | Recall computation — how many prior-month SARs were in Tier1/2? | 30 min |
| **Week 1, Day 2** | Missed SAR analysis — diagnose false negatives | 1–2 hrs |
| **Week 1, Day 3** | Re-calibrate weights using rolling 12-month pool | 2–3 hrs |
| **Week 1, Day 3** | Drift check — compare new weights vs prior month | 15 min |
| **Week 1, Day 4** | Write calibrated weights to config.yaml | 15 min |
| **Week 1, Day 4–5** | Run 4-iteration GraphAML production runs (Section 6) | 1 day |
| **Week 2, Day 1** | Deliver Tier1+Tier2 list to investigation team | 30 min |
| **Weeks 2–4** | Investigation team works through Tier1+Tier2 | Analyst time |

---

*GraphAML v16.19 | AML Strategy Master Plan | April 2026 — Updated with Sections 12 and 13*
*Companion documents: AML_STRATEGY_EXPERT_RESPONSES.md (V1), AML_STRATEGY_EXPERT_RESPONSES_V2.md (V2), AML_STRATEGY_EXPERT_RESPONSES_V3.md (V3)*
