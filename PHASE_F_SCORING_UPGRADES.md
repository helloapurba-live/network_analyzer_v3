
# PHASE F: Scoring Engine Upgrades — Self-Calibrating Weights, Consensus Scoring, Enhanced Output

## CONTEXT
Phases A-E complete. Scoring works but uses fixed weights and pure weighted sum. This phase makes scoring self-calibrating per dataset and adds stronger consensus signals.

## WHAT THIS CHANGES
All changes in `graphaml/engine/scoring.py`, `graphaml/engine/behavioral.py`, `graphaml/engine/structural.py`, and `config.yaml`. No new pages. No schema changes. No new libraries.

---

## CHANGE 1: Risk Probability Column (F6)

After fusion scores computed, add one column:

```
risk_probability = (rank_of_score - 1) / (total_scored - 1)
```

Range: 0.00 to 1.00. Add to fusion_scores.parquet output.
Display on Page 7 header: "Higher risk than 94% of population"
Display on Page 6 AG Grid as new column: "Risk %" formatted as percentage.

---

## CHANGE 2: Disagreement Spike Suppression (F3)

After D1-D7 computed, before fusion:

```
max_dim = max(D1...D7)
other_dims_above_40 = count of remaining dimensions > 40
std_of_dims = std(D1...D7)

IF max_dim > 70 AND other_dims_above_40 < 2 AND std_of_dims > 22:
    fusion_score = fusion_score × 0.88
    flag: "spike_suppressed = True"
    reason: "Single dimension spike without corroboration"
```

Add `spike_suppressed` boolean column to fusion_scores output.
Show on Page 7: "⚠️ Score reduced 12% — single dimension spike without corroboration from other dimensions."

---

## CHANGE 3: Max-Avg Hybrid Fusion (F7)

Replace pure weighted sum with hybrid:

```
weighted_sum = Σ(Di × Wi)
max_dim_score = max(D1...D7)
entropy_weighted_avg = Σ(Di × entropy_Wi)  # entropy_Wi from Change 5

fused = 0.60 × weighted_sum + 0.40 × (0.25 × max_dim_score + 0.75 × entropy_weighted_avg)
```

Config parameter: `fusion_hybrid_ratio: 0.60` (allows tuning the split).

Purpose: a customer with D6=95 but all others at 10 no longer gets diluted to Tier 4. The max signal is preserved.

---

## CHANGE 4: Binary Evidence Boost (Post-Fusion Cap)

After fusion, apply post-fusion boost from binary flags:

```
binary_flags = [motif_circular, potential_structuring, is_layering_intermediary,
                channel_switch_flag, round_trip_detected, multi_seed_flag,
                closed_account_activity, new_account_flag]

flag_count = count of True flags
boost = min(flag_count × 0.05, 0.30)   # cap at 0.30 max

fused = fused × (1 + boost)
cap fused at 100
```

Config parameter: `binary_boost_per_flag: 0.05`, `binary_boost_cap: 0.30`

Add `binary_boost_applied` float column to output.

---

## CHANGE 5: Entropy-Based Dynamic Weights (F4)

Before fusion, auto-adjust dimension weights based on how discriminative each dimension is:

```
For each dimension Di:
    distribution = all scored nodes' Di values
    histogram = 10-bin histogram of distribution
    probabilities = histogram / sum(histogram)
    entropy_i = -Σ(p × log2(p))               # scipy.stats.entropy
    max_entropy = log2(10)                      # ~3.32
    discriminativity_i = 1 - (entropy_i / max_entropy)   # 0 = uniform noise, 1 = bimodal

    IF discriminativity_i < 0.15:
        adjusted_weight_i = max(original_weight_i × 0.30, 0.02)   # shrink to floor
    ELSE:
        adjusted_weight_i = original_weight_i × (0.5 + 0.5 × discriminativity_i)

    Normalize all weights to sum = 1.0
```

Purpose: if structuring fires on 55% of customers, D2 auto-shrinks. If Isolation Forest creates perfect bimodal split, D5 gets full weight. Self-calibrating per dataset.

Add to output: `weight_D1_adjusted...weight_D7_adjusted` columns.
Add to run_metadata: `entropy_weights: {D1: 0.12, D2: 0.28, ...}`
Show on Page 12 Validation: "Weight Adjustment" section showing original vs adjusted weights with discriminativity scores.

---

## CHANGE 6: Borda Consensus Count (F5)

After all dimensions computed, for each node:

```
For each dimension Di:
    rank_i = percentile rank of this node within Di (0 to N)

borda_count = count of dimensions where rank_i is in top 25%   # range 0-7
borda_multiplier = 1 + (0.015 × min(borda_count, 5))          # range 1.0 to 1.075

fused = fused × borda_multiplier
cap fused at 100
```

Purpose: a node ranked top 25% in 6 out of 7 dimensions gets 7.5% boost. A node top in only 1 gets 1.5% boost. Rewards BROAD consensus across dimensions.

Config parameter: `borda_boost_per_dim: 0.015`, `borda_cap: 5`

Add `borda_count` integer column to output.
Show on Page 7: "Consensus: Ranked in top 25% across 5 of 7 dimensions"

---

## CHANGE 7: Benford's Law Feature

Add to `behavioral.py` — two new features:

```
For each node, collect all transaction amounts:
    first_digits = [int(str(abs(amount))[0]) for amount in amounts]
    
    expected_benford = [log10(1 + 1/d) for d in 1..9]    # Benford's distribution
    observed = frequency count of digits 1-9 / total
    
    chi_squared = Σ((observed_d - expected_d)² / expected_d) for d=1..9
    
    benford_zscore = (chi_squared - mean_chi_population) / std_chi_population
```

Output features:
- `benford_chi_squared` — raw chi-squared statistic (higher = more deviation)
- `benford_zscore` — z-score within population (higher = more anomalous)

Add to D2 Red Flags dimension formula:
```
D2 = structuring×0.22 + pass_through×0.18 + off_hours×0.13 + round_amt×0.09 
   + channel_switch×0.09 + velocity×0.09 + new_acct×0.08 + benford_zscore×0.12
```

Library: numpy only (log10, histogram). No new dependency.

---

## CHANGE 8: Power-Law Tail Flag

Add to `structural.py` — one new feature:

```
degree_99th = numpy.percentile(all_degrees, 99)

is_powerlaw_tail = degree > degree_99th
```

Add to D3 Centrality dimension formula:
```
D3 = betweenness×0.27 + pagerank×0.23 + eigenvector×0.18 
   + kcore×0.13 + hub_auth×0.09 + powerlaw_tail×0.10
```

---

## CHANGE 9: Suspect Type Confidence %

Enhance suspect type assignment to include confidence:

```
top_dim = highest scoring dimension
second_dim = second highest dimension
gap = top_dim_score - second_dim_score

IF gap > 30:   confidence = HIGH (85-100%)
IF gap 15-30:  confidence = MEDIUM (60-84%)
IF gap < 15:   confidence = LOW (40-59%)

confidence_pct = min(40 + gap × 2, 100)
```

Output: `suspect_type_confidence` integer column (40-100).
Show on Page 7: "PROBABLE_MULE (78% confidence)"
Show on Page 6: new column in AG Grid.

---

## CHANGE 10: Shared Attribute Pair Cap

In `transformer.py`, when creating identity edges from shared_attributes:

```
For each (attribute_type, attribute_value):
    nodes_sharing = all nodes with this attribute value
    IF len(nodes_sharing) > 50:
        skip this attribute value   # corporate WiFi, shared office IP
        log warning: "Attribute {value} shared by {N} nodes — suppressed (likely benign)"
    ELSE:
        create edges as normal
```

Config parameter: `shared_attribute_max_pairs: 50`

---

## CHANGE 11: Alert Dedup (NEW / SEEN / RESOLVED)

In `pipeline.py`, after scoring, compare to previous run:

```
Load previous run's fusion_scores (if exists)

For each scored node in current run:
    IF not in previous run → alert_status = "NEW"
    IF in previous run AND was Tier 1-3 → alert_status = "RETURNING"
    IF in previous run AND was Tier 4/Normal AND now Tier 1-3 → alert_status = "ESCALATED"
    IF in previous run AND was Tier 1-3 AND now Tier 4/Normal → alert_status = "RESOLVED"
    IF in previous run AND same tier → alert_status = "UNCHANGED"
```

Output: `alert_status` column in fusion_scores.
Show on Page 3 Dashboard: KPI cards — "12 NEW | 8 RETURNING | 3 ESCALATED | 5 RESOLVED"
Show on Page 6: filterable column in AG Grid. Default sort: NEW first.

---

## CHANGE 12: Typology Library View

New tab on Page 6: "By Typology"

Group scored nodes by suspect_type:

```
┌─────────────────────────────────────────────────┐
│  STRUCTURING (8 customers)           [View All] │
│  C009 (82) C034 (77) C056 (55) ...              │
├─────────────────────────────────────────────────┤
│  LAYERING / PASS-THROUGH (5 customers) [View]   │
│  C012 (68) C089 (52) ...                        │
├─────────────────────────────────────────────────┤
│  MULE NETWORK (4 customers)          [View All] │
│  C078 (61) C045 (48) ...                        │
├─────────────────────────────────────────────────┤
│  SHELL / COLLECTION POINT (3 ext)    [View All] │
│  EXT_042 (75) EXT_088 (53) ...                  │
└─────────────────────────────────────────────────┘
```

Click "View All" → filters main suspect table to that typology.
Click any customer → navigate to Page 7.

---

## CHANGE 13: Threshold Tuning Preview

New section on Page 15 Admin: "Threshold Calibration"

```
┌───────────────────────────────────────────────────────┐
│  Tier 1 Threshold: [====●=========] 65               │
│  Tier 2 Threshold: [===●==========] 50               │
│  Tier 3 Threshold: [==●===========] 35               │
│  Tier 4 Threshold: [=●============] 20               │
│                                                       │
│  PREVIEW (live, no re-score needed):                  │
│  ┌─────────┬─────────┬─────────────────────────────┐  │
│  │ Tier    │ Current │ If Applied                  │  │
│  ├───────��─┼─────────┼─────────────────────────────┤  │
│  │ Tier 1  │ 5       │ 8 (+3 from Tier 2)          │  │
│  │ Tier 2  │ 12      │ 9 (-3 to Tier 1)            │  │
│  │ Tier 3  │ 25      │ 25 (no change)              │  │
│  │ Tier 4  │ 38      │ 38 (no change)              │  │
│  │ Normal  │ 100     │ 100 (no change)             │  │
│  └─────────┴─────────┴─────────────────────────────┘  │
│                                                       │
│  [Apply & Re-Tier]  (updates tiers without re-scoring)│
│  [Reset to Default]                                   │
└───────────────────────────────────────────────────────┘
```

"Apply & Re-Tier" → updates fusion_scores tier column + saves new thresholds to config. No pipeline re-run needed — just re-applies thresholds to existing scores.

---

## REVISED SCORING PIPELINE ORDER

```
EXISTING:
  Features → Percentile Rank → Dimension Scores → Correlation Penalty 
  → Weighted Sum → Tier → Type → Evidence

REVISED:
  Features → Percentile Rank → Dimension Scores → Correlation Penalty
  → Entropy Weight Adjustment (NEW)        # Change 5
  → Spike Suppression (NEW)                # Change 2
  → Max-Avg Hybrid Fusion (CHANGED)        # Change 3
  → Borda Consensus Boost (NEW)            # Change 6
  → Binary Evidence Boost (NEW)            # Change 4
  → Cap at 100
  → Risk Probability (NEW)                 # Change 1
  → Tier Assignment
  → Type + Confidence % (ENHANCED)         # Change 9
  → Evidence Strength
  → Alert Dedup (NEW)                      # Change 11
  → Output
```

---

## UPDATED fusion_scores.parquet COLUMNS

New columns added (no existing columns removed):

| Column | Type | Source |
|--------|------|--------|
| `risk_probability` | float 0.00-1.00 | Change 1 |
| `spike_suppressed` | bool | Change 2 |
| `binary_boost_applied` | float 0.00-0.30 | Change 4 |
| `weight_D1_adjusted` ... `weight_D7_adjusted` | float | Change 5 |
| `borda_count` | int 0-7 | Change 6 |
| `suspect_type_confidence` | int 40-100 | Change 9 |
| `alert_status` | str NEW/RETURNING/ESCALATED/RESOLVED/UNCHANGED | Change 11 |

New features added to feature matrix:

| Feature | Module | Dimension |
|---------|--------|-----------|
| `benford_chi_squared` | behavioral.py | D2 |
| `benford_zscore` | behavioral.py | D2 |
| `is_powerlaw_tail` | structural.py | D3 |

---

## TESTS

1. Risk probability: min=0.00, max=1.00, monotonic with score
2. Spike suppression: node with D3=90 and all others <30 gets 0.88× penalty
3. Spike suppression: node with D3=90 and D2=60 does NOT get penalty
4. Max-avg hybrid: D6=95 all others=10 → score higher than pure weighted sum
5. Binary boost: 6 flags → boost = 0.30 (capped), not 0.30+
6. Binary boost: 0 flags → boost = 0.00
7. Entropy weights: uniform dimension (all nodes score ~50) → weight shrinks below 0.05
8. Entropy weights: bimodal dimension → weight stays at or above original
9. Entropy weights: all adjusted weights sum to 1.00
10. Borda count: node top 25% in 7 dims → borda_count = 7
11. Borda multiplier: capped at 1.075 (5 × 0.015)
12. Benford: customer with all amounts $9,100-$9,300 → high chi_squared
13. Benford: customer with natural distribution → low chi_squared
14. Power-law tail: node with degree > 99th percentile → True
15. Suspect confidence: large gap between top dims → HIGH confidence
16. Shared attribute cap: attribute shared by 100 nodes → suppressed
17. Alert dedup: new customer not in previous run → NEW
18. Alert dedup: Tier 2 customer now Tier 4 → RESOLVED
19. Typology view: groups match suspect_type counts
20. Threshold preview: moving T1 from 65 to 60 → correct count change

---

## SUCCESS CRITERIA

```
☐ Scoring pipeline runs with all 13 changes without error
☐ Entropy weights auto-adjust per dataset (verified on sample data)
☐ Spike suppression prevents single-dimension false Tier 1
☐ Max-avg hybrid preserves strong single signals
☐ Borda count rewards broad consensus
☐ Benford features computed for all nodes
☐ Risk probability column present and correct
☐ Alert dedup shows NEW/RETURNING/RESOLVED accurately
☐ Typology tab groups suspects correctly
☐ Threshold tuning preview shows accurate counts
☐ All 20 tests PASS
☐ No existing test broken by these changes
```