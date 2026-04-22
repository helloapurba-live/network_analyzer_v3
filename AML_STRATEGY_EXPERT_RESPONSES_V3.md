# AML Strategy Expert Responses — Volume 3
**Four Context-Specific Queries**
*GraphAML v16.19 | SQL-first 10M Architecture | Separate ML Pipeline*

---

## Query 1 — "No Classification Model in GraphAML App — It Will Be Separate"

**Acknowledgement and Reframing**

This is a critical architecture clarification. All advice going forward is framed accordingly:

| Component | Where It Lives | What It Does |
|---|---|---|
| **GraphAML Dash App** | Air-gapped Windows PC, Anaconda Python 3.11 | Graph scoring only: D1 Proximity, D2 Red Flags, D3 Centrality, D4 Community, D5 Similarity, D6 Identity, D7 Recency. Produces Tier1/Tier2/Tier3/Tier4 customer lists. |
| **ML Classification Pipeline** | Separate Python script (runs independently of Dash app) | Reads the Tier1/Tier2 export from GraphAML, applies supervised/semi-supervised model, produces a binary classification (SAR/No-SAR) plus probability score. |
| **Interaction point** | Optional feed-back | The ML probability score CAN be written back as a feature column and re-ingested into GraphAML as a D2 Red Flag input — but this is optional and runs the graph a second time. |

**What this means for all previous ML advice (V1 and V2 documents):**
- Every reference to "train a model" = runs in the separate Python script, NOT inside GraphAML
- GraphAML's job is to PRODUCE the 10K–20K customer list that feeds the ML pipeline
- The ML model is trained offline, versioned separately, and called from a standalone script
- The 6→8 improvement steps (Query 4 below) all apply to that standalone script

---

## Query 2 — "SAR in Sender/Receiver = 1-Hop Auto-Capture — Is This Correct?"

**Short answer: YES — you are correct. With one important nuance.**

### GraphAML Transaction Column Names (from MASTER_PROMPT_GRAPHAML.md TABLE 2)
GraphAML uses these exact column names in the transaction file:
- `originator_id` — the sending party
- `beneficiary_id` — the receiving party

(NOT `sender_id/receiver_id`, NOT `from_account/to_account`. If your SQL table uses different names, rename or alias in the SQL query before export.)

### How the 1-Hop Capture Works

**Step 1 — Your transaction filter (SQL server side):**
```sql
-- Capture all transactions WHERE the SAR customer appears on EITHER side
SELECT *
FROM transactions t
WHERE t.originator_id IN (SELECT cust_id FROM sar_master_list)
   OR t.beneficiary_id IN (SELECT cust_id FROM sar_master_list);
```

This returns every transaction edge that directly touches a SAR customer.

**What this gives you automatically:**
- Every non-SAR `beneficiary_id` in rows where `originator_id` is SAR → these are **1-hop downstream** from SAR
- Every non-SAR `originator_id` in rows where `beneficiary_id` is SAR → these are **1-hop upstream** from SAR
- All of these counterparties are Type C by definition

**Step 2 — GraphAML Phase 3 BFS confirms and labels:**
When this filtered transaction file is loaded into GraphAML alongside the SAR-flagged nodes file, Phase 3 runs multi-source BFS from all seed nodes (is_sar=1) across both monetary edges (transactions) and identity edges (shared attributes). The result:
- SAR customers → labelled `SEED`
- Direct counterparties from the transaction filter above → labelled `HOP_1`
- Their counterparties → labelled `HOP_2`
- And so on to `HOP_3`, then `NO_PATH`

**Your understanding is correct: the transaction edge filter and GraphAML BFS reinforce each other.**

### The One Important Nuance — Nodes.csv Must Include the Counterparties

The transaction edge alone (in the CSV) is NOT enough for the counterparty to receive a meaningful D-score.

| Scenario | What Happens in GraphAML |
|---|---|
| Counterparty ID exists in `nodes.csv` with full feature data | ✅ GraphAML scores them on all D1–D7 dimensions. They appear in Tier output. |
| Counterparty ID is NOT in `nodes.csv` — external orphan | GraphAML Phase 0.7 auto-creates an **external counterparty stub** — a minimal placeholder row. D1 Proximity score based on hop distance only. D2–D7 mostly zero (no feature data). They appear in output with very low composite score. |

**What this means for your data prep:**
- For internal customers (SAR counterparties who are YOUR bank's customers): they MUST have a row in `nodes.csv` with all their feature columns. If you pre-filter `nodes.csv` to only the SAR seeds, their counterparties become orphans and get stub scores only.
- **Correct approach**: Your `nodes.csv` must include ALL customers you want scored — not just the SAR seeds. The BFS determines which ones are reachable, but every candidate needs a node record.
- For external counterparties (other-bank customers you have no data on): the stub is expected and acceptable. You score them on network position only (D1, D3, D4).

### SQL Query to Extract Type C Counterparties for Node Inclusion

```sql
-- Get all 1-hop counterparties of SAR customers
SELECT DISTINCT
    CASE 
        WHEN t.originator_id IN (SELECT cust_id FROM sar_master_list) 
        THEN t.beneficiary_id   -- downstream hop
        ELSE t.originator_id    -- upstream hop
    END AS cust_id,
    'TYPE_C' AS customer_type_label,
    1 AS hop_distance
FROM transactions t
WHERE (t.originator_id IN (SELECT cust_id FROM sar_master_list)
       OR t.beneficiary_id IN (SELECT cust_id FROM sar_master_list))
  AND t.originator_id NOT IN (SELECT cust_id FROM sar_master_list)  -- exclude SAR themselves
  AND t.beneficiary_id NOT IN (SELECT cust_id FROM sar_master_list)
  AND t.date >= DATEADD(MONTH, -12, @run_date);
```

This list becomes your inclusion filter: any customer ID in this result MUST have a full row in `nodes.csv`.

**Summary — Query 2:**
```
SAR in originator_id OR beneficiary_id
     → transaction edge captured ✅
     → GraphAML Phase 3 BFS assigns HOP_1 label ✅  
     → D-score calculated fully ONLY IF node record exists in nodes.csv ✅/⚠️
     → External counterparties get stub score only (Phase 0.7) — expected ✅
```

---

## Query 3 — "With 10M Customers, Must Use SQL Server — Cannot Load All to Python"

**This is completely correct and was the missing constraint in V2. All preprocessing must run as SQL queries on the server. Python only receives the pre-selected 10K–20K output.**

The Mahalanobis-in-Python approach described in V2 (loading 100K chunks to pandas) is **NOT viable** given this constraint. Below is the fully redesigned SQL-first pipeline.

### Architecture — SQL-First Preprocessing

```
[SQL Server — 10M customers]
         |
         | SQL queries (all computation happens here)
         |
    ┌────▼─────────────────────────────────────────────────┐
    │  WAVE 1: Type A + B + C + D + E  [SQL → 10K rows]   │
    │  WAVE 2: Type G expansion        [SQL → +5K rows]    │
    │  WAVE 3: Type F community        [SQL → subgraph]    │
    │           ↓ only for F                               │
    │       [Python: Louvain on subgraph only]             │
    └──────────────────────────────────────────────────────┘
         |
         | Export CSV (10K–20K rows only)
         |
    [GraphAML — Windows PC, Python]
```

Python sees **ONLY** the filtered output from SQL. GraphAML ingests only these rows.

---

### SQL Type Extraction Queries

**Prerequisite table — SAR master list (small, stays in SQL):**
```sql
CREATE TABLE sar_master_list AS
SELECT cust_id FROM customer_master WHERE is_sar = 1;
-- Or for your November cohort:
SELECT cust_id FROM customer_master 
WHERE investigation_month = 'November' AND sar_filed = 1;
```

---

**TYPE A — Direct SAR Customers (already flagged):**
```sql
SELECT cust_id, 'TYPE_A' AS wave_type, 100 AS priority_score
FROM customer_master
WHERE is_sar = 1
  AND investigation_month = @cohort_month;
```

---

**TYPE C — 1-Hop (direct transaction partners of SAR customers):**
```sql
SELECT DISTINCT
    CASE 
        WHEN t.originator_id IN (SELECT cust_id FROM sar_master_list) 
        THEN t.beneficiary_id 
        ELSE t.originator_id 
    END AS cust_id,
    'TYPE_C' AS wave_type,
    COUNT(*) OVER (PARTITION BY 
        CASE WHEN t.originator_id IN (SELECT cust_id FROM sar_master_list) 
             THEN t.beneficiary_id ELSE t.originator_id END
    ) AS tx_count_with_sar
FROM transactions t
WHERE (t.originator_id IN (SELECT cust_id FROM sar_master_list)
       OR t.beneficiary_id IN (SELECT cust_id FROM sar_master_list))
  AND t.originator_id != t.beneficiary_id
  AND t.date >= DATEADD(MONTH, -12, @run_date)
  AND CASE 
        WHEN t.originator_id IN (SELECT cust_id FROM sar_master_list) 
        THEN t.beneficiary_id 
        ELSE t.originator_id 
      END NOT IN (SELECT cust_id FROM sar_master_list)
ORDER BY tx_count_with_sar DESC;
```

**Expected run time on SQL Server with indexes on originator_id, beneficiary_id, date: 5–30 seconds for 10M rows.**

---

**TYPE D — 2-Hop (partners of partners of SAR, not already in C):**
```sql
WITH hop1 AS (
    SELECT DISTINCT
        CASE 
            WHEN t.originator_id IN (SELECT cust_id FROM sar_master_list) 
            THEN t.beneficiary_id 
            ELSE t.originator_id 
        END AS cust_id
    FROM transactions t
    WHERE (t.originator_id IN (SELECT cust_id FROM sar_master_list)
           OR t.beneficiary_id IN (SELECT cust_id FROM sar_master_list))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
),
hop2 AS (
    -- Partners of hop1 who are NOT SAR and NOT already in hop1
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
SELECT h2.cust_id, 'TYPE_D' AS wave_type, h2.hop2_tx_count
FROM hop2 h2
WHERE h2.cust_id NOT IN (SELECT cust_id FROM sar_master_list)
  AND h2.cust_id NOT IN (SELECT cust_id FROM hop1)
ORDER BY h2.hop2_tx_count DESC
FETCH FIRST 5000 ROWS ONLY;  -- cap at 5K for Type D in a 20K run
```

---

**TYPE E — Criminal Ratio (external accounts with high SAR transaction ratio):**
```sql
SELECT 
    t.originator_id AS external_acct_id,
    COUNT(*) AS total_tx,
    SUM(CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM sar_master_list) THEN 1 ELSE 0 END) AS sar_tx,
    CAST(
        SUM(CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM sar_master_list) THEN 1.0 ELSE 0 END) 
        / NULLIF(COUNT(*), 0) 
    AS FLOAT) AS criminal_ratio,
    SUM(t.amount) AS total_amount_to_sar
FROM transactions t
WHERE t.originator_id NOT IN (SELECT cust_id FROM customer_master)  -- external = not your customer
  AND t.date >= DATEADD(MONTH, -12, @run_date)
GROUP BY t.originator_id
HAVING 
    CAST(
        SUM(CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM sar_master_list) THEN 1.0 ELSE 0 END)
        / NULLIF(COUNT(*), 0)
    AS FLOAT) >= 0.35
ORDER BY criminal_ratio DESC, total_amount_to_sar DESC
FETCH FIRST 2000 ROWS ONLY;
```

---

**TYPE B3 — Behaviorally Anomalous Cleared Customers (SQL window function approach):**

This replaces the Mahalanobis-in-Python approach for behavioral outlier detection. SQL window functions compute z-scores across all cleared customers entirely on the server.

```sql
WITH cleared_features AS (
    -- Compute behavioral features for all 47K cleared customers
    SELECT 
        c.cust_id,
        COUNT(t.tx_id) AS tx_count_90d,
        AVG(t.amount) AS avg_amount,
        STDEV(t.amount) AS std_amount,
        MAX(t.amount) AS max_amount,
        SUM(t.amount) AS total_amount_90d,
        COUNT(DISTINCT t.beneficiary_id) AS unique_beneficiaries,
        SUM(CASE WHEN DATEPART(HOUR, t.time) BETWEEN 0 AND 5 THEN 1.0 ELSE 0 END) 
            / NULLIF(COUNT(t.tx_id), 0) AS off_hours_ratio,
        COUNT(DISTINCT t.geo_destination) AS unique_destination_states
    FROM customer_master c
    LEFT JOIN transactions t 
        ON (t.originator_id = c.cust_id OR t.beneficiary_id = c.cust_id)
        AND t.date >= DATEADD(DAY, -90, @run_date)
    WHERE c.investigation_result = 'CLEARED'
      AND c.investigation_month = @cohort_month
    GROUP BY c.cust_id
),
global_stats AS (
    -- Compute mean and SD across all cleared customers (for z-score normalization)
    SELECT 
        AVG(tx_count_90d) AS mu_tx, STDEV(tx_count_90d) AS sd_tx,
        AVG(avg_amount) AS mu_amt, STDEV(avg_amount) AS sd_amt,
        AVG(max_amount) AS mu_max, STDEV(max_amount) AS sd_max,
        AVG(unique_beneficiaries * 1.0) AS mu_bene, STDEV(unique_beneficiaries * 1.0) AS sd_bene,
        AVG(off_hours_ratio) AS mu_ohr, STDEV(off_hours_ratio) AS sd_ohr
    FROM cleared_features
),
anomaly_score AS (
    -- Sum of squared z-scores = approximate Mahalanobis with diagonal covariance
    SELECT 
        cf.cust_id,
        POWER((cf.tx_count_90d - gs.mu_tx) / NULLIF(gs.sd_tx, 0), 2) +
        POWER((cf.avg_amount - gs.mu_amt) / NULLIF(gs.sd_amt, 0), 2) +
        POWER((cf.max_amount - gs.mu_max) / NULLIF(gs.sd_max, 0), 2) +
        POWER((cf.unique_beneficiaries - gs.mu_bene) / NULLIF(gs.sd_bene, 0), 2) +
        POWER((cf.off_hours_ratio - gs.mu_ohr) / NULLIF(gs.sd_ohr, 0), 2)
        AS anomaly_score,
        cf.tx_count_90d,
        cf.avg_amount,
        cf.total_amount_90d
    FROM cleared_features cf CROSS JOIN global_stats gs
)
SELECT TOP 3000 
    cust_id, 
    anomaly_score,
    'TYPE_B3' AS wave_type
FROM anomaly_score
ORDER BY anomaly_score DESC;  -- highest anomaly score = most SAR-like behavior
```

**Note:** The z-score sum approximates Mahalanobis distance with a diagonal covariance matrix (assumes features are independent). This is slightly less accurate than true Mahalanobis but runs in SQL in ~10–60 seconds on 47K customers. For the purpose of filtering 3K top anomalies from 47K cleared, it is more than adequate.

---

**TYPE G — Behaviorally Similar to SAR Centroid (SQL z-score distance to SAR mean):**

This completely replaces the Mahalanobis-in-Python-100K-chunks approach. All computation on SQL server.

```sql
WITH sar_features AS (
    -- Compute behavioral features for SAR customers (3K rows — fast)
    SELECT 
        AVG(f.tx_count_90d * 1.0) AS sar_mu_tx, STDEV(f.tx_count_90d * 1.0) AS sar_sd_tx,
        AVG(f.avg_amount) AS sar_mu_amt, STDEV(f.avg_amount) AS sar_sd_amt,
        AVG(f.max_amount) AS sar_mu_max, STDEV(f.max_amount) AS sar_sd_max,
        AVG(f.off_hours_ratio) AS sar_mu_ohr, STDEV(f.off_hours_ratio) AS sar_sd_ohr,
        AVG(f.unique_beneficiaries * 1.0) AS sar_mu_bene, STDEV(f.unique_beneficiaries * 1.0) AS sar_sd_bene
    FROM customer_features_precomputed f  -- precomputed feature table for all 10M
    WHERE f.cust_id IN (SELECT cust_id FROM sar_master_list)
),
all_customer_distance AS (
    -- For every non-SAR customer, compute distance to SAR centroid
    SELECT 
        cf.cust_id,
        POWER((cf.tx_count_90d - sf.sar_mu_tx) / NULLIF(sf.sar_sd_tx, 0.01), 2) +
        POWER((cf.avg_amount - sf.sar_mu_amt) / NULLIF(sf.sar_sd_amt, 0.01), 2) +
        POWER((cf.max_amount - sf.sar_mu_max) / NULLIF(sf.sar_sd_max, 0.01), 2) +
        POWER((cf.off_hours_ratio - sf.sar_mu_ohr) / NULLIF(sf.sar_sd_ohr, 0.001), 2) +
        POWER((cf.unique_beneficiaries - sf.sar_mu_bene) / NULLIF(sf.sar_sd_bene, 0.01), 2)
        AS distance_to_sar_centroid
    FROM customer_features_precomputed cf CROSS JOIN sar_features sf
    WHERE cf.cust_id NOT IN (SELECT cust_id FROM sar_master_list)
      AND cf.cust_id NOT IN (SELECT cust_id FROM type_c_already_extracted)
      AND cf.cust_id NOT IN (SELECT cust_id FROM type_d_already_extracted)
      AND cf.cust_id NOT IN (SELECT cust_id FROM type_b3_already_extracted)
)
SELECT TOP 5000 
    cust_id, 
    distance_to_sar_centroid,
    'TYPE_G' AS wave_type
FROM all_customer_distance
ORDER BY distance_to_sar_centroid ASC;  -- smallest distance = most similar to SAR
```

**Prerequisite:** `customer_features_precomputed` — a SQL table of pre-computed behavioral features for all 10M customers. This table is computed **once per month** using a batch SQL job (GROUP BY over transactions table) and stored. Then each run queries it in seconds. This is standard practice at banks — the feature table is refreshed nightly or monthly, not recomputed per analysis run.

**If you don't have the precomputed feature table yet, create it:**
```sql
-- One-time monthly refresh job (run as SQL Server Agent job)
CREATE TABLE customer_features_precomputed AS
SELECT 
    COALESCE(t.originator_id, t.beneficiary_id) AS cust_id,
    COUNT(*) AS tx_count_90d,
    AVG(t.amount) AS avg_amount,
    MAX(t.amount) AS max_amount,
    SUM(t.amount) AS total_amount_90d,
    COUNT(DISTINCT CASE WHEN t.originator_id = c.cust_id THEN t.beneficiary_id END) AS unique_beneficiaries,
    SUM(CASE WHEN DATEPART(HOUR, t.time) BETWEEN 0 AND 5 THEN 1.0 ELSE 0 END) 
        / NULLIF(COUNT(*), 0) AS off_hours_ratio
FROM customer_master c
JOIN transactions t ON (t.originator_id = c.cust_id OR t.beneficiary_id = c.cust_id)
WHERE t.date >= DATEADD(DAY, -90, GETDATE())
GROUP BY c.cust_id;
CREATE INDEX idx_cfp_cust_id ON customer_features_precomputed(cust_id);
```
Expected build time: 20–90 minutes once. Subsequent query: seconds.

---

**TYPE F — Community-Based (the ONLY SQL→Python handoff):**

Community detection (Louvain) cannot run in SQL — it requires graph structure. This is the single acceptable Python step, but the graph loaded to Python is only the subgraph, NOT the 10M full graph.

```sql
-- Step 1 (SQL Server): Extract 3-hop subgraph edges around SAR seeds
-- This is a bounded BFS via recursive CTE
WITH seeds AS (
    SELECT cust_id AS node_id, 0 AS hop FROM sar_master_list
),
bfs_hop1 AS (
    SELECT DISTINCT
        CASE WHEN t.originator_id IN (SELECT node_id FROM seeds) 
             THEN t.beneficiary_id ELSE t.originator_id END AS node_id,
        1 AS hop
    FROM transactions t
    WHERE (t.originator_id IN (SELECT node_id FROM seeds)
           OR t.beneficiary_id IN (SELECT node_id FROM seeds))
      AND t.date >= DATEADD(MONTH, -12, @run_date)
),
bfs_hop2 AS (
    SELECT DISTINCT
        CASE WHEN t.originator_id IN (SELECT node_id FROM bfs_hop1) 
             THEN t.beneficiary_id ELSE t.originator_id END AS node_id,
        2 AS hop
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
             THEN t.beneficiary_id ELSE t.originator_id END AS node_id,
        3 AS hop
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
-- Export ONLY subgraph edges (small: 50K–500K rows, not 10M)
SELECT 
    t.originator_id,
    t.beneficiary_id,
    SUM(t.amount) AS total_amount,
    COUNT(*) AS tx_count
FROM transactions t
WHERE t.originator_id IN (SELECT node_id FROM all_subgraph_nodes)
  AND t.beneficiary_id IN (SELECT node_id FROM all_subgraph_nodes)
  AND t.date >= DATEADD(MONTH, -12, @run_date)
GROUP BY t.originator_id, t.beneficiary_id;
```

```python
# Step 2 (Python — runs on LOCAL PC with subgraph only, NOT 10M rows)
import pandas as pd
import networkx as nx
import community as community_louvain  # python-louvain

# Load just the subgraph edges from SQL export (pyodbc or csv)
edges_df = pd.read_csv('subgraph_edges.csv')  # typically 50K–300K rows

G = nx.from_pandas_edgelist(
    edges_df, 
    source='originator_id', 
    target='beneficiary_id',
    edge_attr=['total_amount', 'tx_count']
)

# Run Louvain N=10 times for consensus
from collections import defaultdict
co_occurrence = defaultdict(lambda: defaultdict(int))
nodes = list(G.nodes())

for run in range(10):
    partition = community_louvain.best_partition(G, random_state=run)
    for n1 in nodes:
        for n2 in nodes:
            if partition[n1] == partition[n2]:
                co_occurrence[n1][n2] += 1

# Consensus: same community if co-occurrence >= 7/10
# Find communities with >=1 SAR seed member
sar_seeds = set(pd.read_csv('sar_list.csv')['cust_id'])
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
```

**Expected sizes:** Subgraph for 3K SAR seeds = 50K–500K nodes, 100K–2M edges. Louvain 10 runs on this subgraph: 2–15 minutes on local PC. This is the only Python computation that uses network structure — and it uses only the subgraph, not the full 10M.

---

### Complete Wave Plan — SQL-First (Revised from V2)

| Wave | Source | SQL Query | Expected Output | Where Computed |
|---|---|---|---|---|
| W1.1 | SAR seeds | Direct IS SAR filter | 3,000 rows | SQL |
| W1.2 | Type C | 1-hop JOIN on transactions | 4,000–8,000 rows | SQL |
| W1.3 | Type D | 2-hop CTE | 2,000–5,000 rows | SQL |
| W1.4 | Type E | GROUP BY criminal ratio | 500–2,000 rows | SQL |
| W1.5 | Type B3 | Z-score anomaly on cleared | 2,000–3,000 rows | SQL |
| **W1 Total** | | | ≈ **12,000–20,000** | **All SQL** |
| W2.1 | Type G | Z-score distance to SAR centroid | Top 3,000–5,000 rows | SQL |
| **W2 Total** | | Apply if W1 < 15K | ≈ **+3,000–5,000** | **All SQL** |
| W3.1 | Type F | 3-hop subgraph via SQL CTE → Louvain in Python | 1,000–3,000 rows | SQL + Python |

**Final export to GraphAML:** Combine all wave outputs (deduplicated), pull full node feature rows from `customer_master` for all included cust_ids, format as `nodes.csv`. Pull all transactions between included nodes + SAR nodes, format as `transactions.csv` using `originator_id`/`beneficiary_id` column names.

---

## Query 4 — "In Our Context, How Do We Improve Supervised Score From 6 to 8?"

**Context locked in:**
- Separate Python pipeline (not inside GraphAML Dash app)
- Positive labels: SAR transaction history customers (3K November cohort)
- Negative labels: currently the 47K cleared customers — this is the problem
- Data source: SQL Server, 10M customers, cannot all go to Python
- Air-gapped, 16GB RAM, Anaconda Python 3.11
- Current score: 6/10 (approximately F1 ≈ 0.35–0.45 in AML industry terms)

### Why Your Score Is 6 (Root Cause Diagnosis)

| Root Cause | Impact on Score | Likelihood |
|---|---|---|
| **Contaminated negatives**: 47K cleared ≠ truly not-criminal. Bank cleared them but many may be undetected crime. Using them all as negatives poisons the model. | -2 points | Very high |
| **Class imbalance** (3K positive vs 47K negative = 1:16 ratio) with default weights | -1 point | High |
| **Missing graph features**: tabular model has no idea about hop distance, counterparty SAR ratio | -1 point | High |
| **Temporal data leakage**: random train/test split on transaction data leaks future patterns into training | -0.5 points | Medium |
| **Feature set too shallow**: basic demographics + transaction aggregates only | -0.5 points | Medium |

Fix these five in order and you reach 8.

---

### Step 1 — Fix the Negative Class (6 → 7) — Highest Impact

**The problem:** Your 47K cleared customers were cleared by analysts, not by ground truth. Some percentage are genuinely suspicious but not caught. Training a model to predict "not SAR" on this group teaches the model the wrong pattern.

**SQL-based solution (Query 3 TYPE B3 query already written above):**

1. Run the TYPE B3 SQL query on your 47K cleared customers
2. This computes a behavioral anomaly score for each cleared customer
3. Sort by anomaly score ascending (least anomalous = most "normal")
4. Take the BOTTOM 60% of cleared customers by anomaly score → these are your **reliable negatives**
5. The top 40% (most anomalous cleared) → exclude from training entirely (uncertain label)

```python
# After running TYPE B3 SQL query and exporting to CSV:
import pandas as pd

cleared_scored = pd.read_csv('cleared_anomaly_scores.csv')
threshold = cleared_scored['anomaly_score'].quantile(0.60)  # bottom 60%

reliable_negatives = cleared_scored[cleared_scored['anomaly_score'] <= threshold]['cust_id'].tolist()
uncertain_cleared = cleared_scored[cleared_scored['anomaly_score'] > threshold]['cust_id'].tolist()

print(f"Reliable negatives: {len(reliable_negatives)}")   # ~28K
print(f"Excluded uncertain: {len(uncertain_cleared)}")    # ~19K
# Now train ONLY on 3K SAR + 28K reliable negatives (~9K if you want 1:3 ratio)
```

**Expected impact:** F1 score improvement from ≈0.35 to ≈0.50–0.55 (this single step is worth more than any algorithm change).

---

### Step 2 — Add 4 SQL-Derivable Graph Features to ML Input (7 → 7.5)

These 4 features encode network position in tabular form without needing Python graph computation. All computable in SQL and joined to your training set.

```sql
-- Feature 1: Hop distance to nearest SAR customer
-- (Use the hop assignment from your wave extraction: 1 for Type C, 2 for Type D, 99 for others)
SELECT cust_id, 
    CASE 
        WHEN cust_id IN (SELECT cust_id FROM type_c_extracted) THEN 1
        WHEN cust_id IN (SELECT cust_id FROM type_d_extracted) THEN 2
        WHEN cust_id IN (SELECT cust_id FROM type_f_extracted) THEN 3
        ELSE 99 
    END AS hop_distance_to_sar

-- Feature 2: Counterparty SAR ratio (what % of this customer's partners are SAR customers)
SELECT 
    t.originator_id AS cust_id,
    COUNT(DISTINCT CASE WHEN t.beneficiary_id IN (SELECT cust_id FROM sar_master_list) 
                        THEN t.beneficiary_id END) * 1.0 / 
    COUNT(DISTINCT t.beneficiary_id) AS counterparty_sar_ratio
FROM transactions t
GROUP BY t.originator_id;

-- Feature 3: Shared network exposure (do they share addresses/devices with SAR customers?)
SELECT 
    sa.cust_id_a AS cust_id,
    COUNT(DISTINCT CASE WHEN sa.cust_id_b IN (SELECT cust_id FROM sar_master_list) 
                        THEN sa.cust_id_b END) AS shared_attr_sar_count
FROM shared_attributes sa
GROUP BY sa.cust_id_a;

-- Feature 4: Transaction velocity change (3-month vs prior 3-month ratio — detects sudden behavior change)
SELECT 
    cust_id,
    tx_count_recent_90d * 1.0 / NULLIF(tx_count_prior_90d, 0) AS tx_velocity_change_ratio
FROM (
    SELECT 
        cust_id,
        SUM(CASE WHEN date >= DATEADD(DAY, -90, @run_date) THEN 1 ELSE 0 END) AS tx_count_recent_90d,
        SUM(CASE WHEN date >= DATEADD(DAY, -180, @run_date) 
                  AND date < DATEADD(DAY, -90, @run_date) THEN 1 ELSE 0 END) AS tx_count_prior_90d
    FROM transactions
    GROUP BY cust_id
) velocity_subquery;
```

```python
# Join all 4 features to your training set
training_df = pd.merge(training_df, hop_distance_df, on='cust_id', how='left')
training_df = pd.merge(training_df, counterparty_sar_ratio_df, on='cust_id', how='left')
training_df = pd.merge(training_df, shared_attr_exposure_df, on='cust_id', how='left')
training_df = pd.merge(training_df, velocity_change_df, on='cust_id', how='left')

# Fill nulls (customers with no transactions in period)
training_df['hop_distance_to_sar'].fillna(99, inplace=True)
training_df['counterparty_sar_ratio'].fillna(0, inplace=True)
training_df['shared_attr_sar_count'].fillna(0, inplace=True)
training_df['tx_velocity_change_ratio'].fillna(1.0, inplace=True)
```

---

### Step 3 — Cost-Sensitive Weighting (7.5 → 7.8) — 1 Line of Code

```python
from xgboost import XGBClassifier

# Calculate ratio of reliable negatives to positives
ratio = len(reliable_negatives) / len(sar_positives)  # ~9.3 if using full B3 pool

model = XGBClassifier(
    scale_pos_weight=ratio,    # This is the 1 line that fixes imbalance
    n_estimators=300,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    eval_metric='aucpr',       # Use PR-AUC not ROC-AUC for imbalanced data
    random_state=42
)

model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    early_stopping_rounds=20,
    verbose=50
)
```

**Note:** Use `average_precision_score` (PR-AUC) as your metric, NOT `roc_auc_score`. ROC-AUC is misleading for AML imbalanced data. PR-AUC is honest.

---

### Step 4 — PU Learning for Reliable Negatives (7.8 → 8+)

PU (Positive-Unlabeled) Learning formally handles the "I know my positives but negatives are uncertain" problem. You have exact positives (3K SAR) and uncertain negatives (47K cleared — unknown how many are actually criminals).

```python
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
import numpy as np

# Load features for 3K SAR customers only (already in Python — small set)
sar_features_df = training_df[training_df['is_sar'] == 1][feature_columns]

# Fit One-Class SVM on SAR customers only
scaler = StandardScaler()
sar_features_scaled = scaler.fit_transform(sar_features_df)

ocsvm = OneClassSVM(nu=0.1, kernel='rbf', gamma='scale')
ocsvm.fit(sar_features_scaled)

# Apply to cleared customers — those the OCSVM rejects are "SAR-like"
cleared_features_df = training_df[training_df['is_sar'] == 0][feature_columns]
cleared_features_scaled = scaler.transform(cleared_features_df)
cleared_prediction = ocsvm.predict(cleared_features_scaled)  # 1=inlier, -1=outlier

# -1 (outlier) means One-Class SVM thinks they look like SAR customers → EXCLUDE from negatives
# +1 (inlier) means OCSVM thinks they look like non-SAR → keep as reliable negatives
reliable_negatives_mask = cleared_prediction == 1
reliable_negative_ids = training_df[training_df['is_sar'] == 0].loc[reliable_negatives_mask, 'cust_id']

print(f"OCSVM reliable negatives: {reliable_negatives_mask.sum()}")    # ~60-70% of cleared
print(f"OCSVM flagged as SAR-like (excluded): {(~reliable_negatives_mask).sum()}")

# Build final training set: SAR positives + OCSVM reliable negatives
final_training = pd.concat([
    training_df[training_df['is_sar'] == 1],
    training_df[training_df['cust_id'].isin(reliable_negative_ids)]
])

# Retrain XGBoost on this cleaner set
final_ratio = (final_training['is_sar'] == 0).sum() / (final_training['is_sar'] == 1).sum()
model_v2 = XGBClassifier(scale_pos_weight=final_ratio, ...)
model_v2.fit(final_training[feature_columns], final_training['is_sar'])
```

**Memory constraint check:** 3K SAR feature rows + 28K–47K cleared feature rows = 31K–50K rows × 30–50 features = ~30MB maximum. This easily fits in 16GB RAM. PU Learning runs on the EXTRACTED subset, not the 10M.

---

### Step 5 — Temporal Cross-Validation (Accurate Measurement, Not Score Improvement)

```python
from sklearn.model_selection import TimeSeriesSplit

# Sort your training data by investigation_month or transaction_date
training_df_sorted = training_df.sort_values('first_sar_date')

# TimeSeriesSplit: train on past, test on future
tscv = TimeSeriesSplit(n_splits=5)

pr_auc_scores = []
for fold, (train_idx, test_idx) in enumerate(tscv.split(training_df_sorted)):
    X_train_fold = training_df_sorted.iloc[train_idx][feature_columns]
    y_train_fold = training_df_sorted.iloc[train_idx]['is_sar']
    X_test_fold  = training_df_sorted.iloc[test_idx][feature_columns]
    y_test_fold  = training_df_sorted.iloc[test_idx]['is_sar']
    
    fold_model = XGBClassifier(scale_pos_weight=ratio, ...)
    fold_model.fit(X_train_fold, y_train_fold)
    
    y_proba = fold_model.predict_proba(X_test_fold)[:, 1]
    
    from sklearn.metrics import average_precision_score
    pr_auc = average_precision_score(y_test_fold, y_proba)
    pr_auc_scores.append(pr_auc)
    print(f"Fold {fold+1}: PR-AUC = {pr_auc:.4f}")

print(f"Mean PR-AUC: {np.mean(pr_auc_scores):.4f} ± {np.std(pr_auc_scores):.4f}")
```

**Why this matters:** Random CV on AML data gives PR-AUC ≈ 0.70+ (optimistic). Temporal CV gives PR-AUC ≈ 0.45–0.55 (honest). Your "score 6 out of 10" may already reflect this — but if measured with random CV, the real score is lower. Temporal CV gives you the real number and tells you if you've actually reached 8.

---

### Summary — Score Improvement Roadmap

| Step | Action | Where | Effort | Score Impact |
|---|---|---|---|---|
| **1** | Fix negative class: SQL B3 z-score on 47K cleared → reliable bottom 60% only | SQL query (written above) + 5 lines Python | Low | **6 → 7** |
| **2** | Add 4 graph features from SQL: hop distance, SAR ratio, shared attr, velocity change | 4 SQL queries (written above) + pandas merge | Low | **7 → 7.5** |
| **3** | Cost-sensitive weight = negative/positive ratio | 1 line in XGBClassifier constructor | Trivial | **7.5 → 7.8** |
| **4** | PU Learning: OCSVM on SAR features → further purify negatives → retrain | ~30 lines Python (written above) | Medium | **7.8 → 8+** |
| **5** | Temporal cross-validation | 20 lines Python (written above), framework change | Low | Accurate measurement |

**No steps require loading 10M rows to Python. All heavy computation stays in SQL. Python only processes the extracted 10K–50K subset.**

---

*Document created: GraphAML v16.19 advisory session*
*Companion documents: AML_STRATEGY_EXPERT_RESPONSES.md (V1) and AML_STRATEGY_EXPERT_RESPONSES_V2.md (V2)*
