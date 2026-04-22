
# PHASE F: Engine Calibration + Analytics Enhancement — Full Stack Upgrade

## CONTEXT
Phases A-E complete. Working application with scoring, UI, audit, and visual investigation. This phase makes the engine self-calibrating, adds missing analytical signals, enriches narratives, and enhances UI for power users. Changes span ALL layers.

## VERSION ROADMAP — WHAT GOES WHERE

```
v1.0: Phases A-E (SHIPPED — current working application)
v1.1: Quick wins — scoring fixes, new output columns (this phase, section 1)
v1.2: Self-calibration — entropy weights, Borda, Benford, alert dedup (this phase, section 2)
v1.3: Power user — business rules, threshold tuning, typology view (this phase, section 3)
v2.0: Future — cross-run analysis, watchlist, geo upgrades (this phase, section 4)
```

---

## SECTION 1: v1.1 — QUICK WINS (smallest effort, biggest ROI)

### F-1.1 DATA LAYER

**Shared attribute pair cap** — `transformer.py`
- When creating identity edges from shared_attributes, if a single attribute_value (e.g., one IP address) is shared by more than 50 nodes → suppress that attribute entirely
- Log warning: "Attribute {value} shared by {N} nodes — suppressed (likely corporate WiFi/shared office)"
- Config: `shared_attribute_max_pairs: 50`

### F-1.2 FEATURE LAYER

**Power-law degree tail** — `structural.py`
- New feature: `is_powerlaw_tail = degree > numpy.percentile(all_degrees, 99)`
- A node with 847 counterparties in a 10K network is structurally anomalous regardless of seeds
- Add to D3 Centrality formula with weight 0.10, reduce hub_auth to 0.05
- Feature count: 84 → 85

### F-1.3 SCORING LAYER

**Risk probability column** — `scoring.py`
- `risk_probability = (rank_of_score - 1) / (total_scored - 1)`
- Range: 0.00 to 1.00
- New column in fusion_scores.parquet
- Display: "Higher risk than 94% of population"

**Spike suppression** — `scoring.py`
- After D1-D7 computed, before fusion:
- IF max(D1..D7) > 70 AND count(other dims > 40) < 2 AND std(D1..D7) > 22 → multiply fusion by 0.88
- New columns: `spike_suppressed` (bool), `spike_reason` (str)

**Max-avg hybrid fusion** — `scoring.py`
- Replace: `fused = Σ(Di × Wi)`
- With: `fused = 0.60 × weighted_sum + 0.40 × (0.25 × max_dim + 0.75 × weighted_avg)`
- Prevents single strong signal (D6=95) being diluted when all others are low
- Config: `fusion_hybrid_ratio: 0.60`

**Binary evidence boost (post-fusion, capped)** — `scoring.py`
- Binary flags: motif_circular, potential_structuring, is_layering_intermediary, channel_switch, round_trip, multi_seed, closed_account_activity, new_account_flag
- `boost = min(flag_count × 0.05, 0.30)`
- `fused = min(fused × (1 + boost), 100)`
- New column: `binary_boost_applied` (float)
- Config: `binary_boost_per_flag: 0.05`, `binary_boost_cap: 0.30`

**Suspect type confidence %** — `scoring.py`
- `gap = top_dim_score - second_dim_score`
- `confidence_pct = min(40 + gap × 2, 100)`
- New column: `suspect_type_confidence` (int 40-100)

### F-1.4 UI LAYER

**Page 6** — Add columns to AG Grid: `risk_probability` (formatted as %), `suspect_type_confidence` (with % badge)
**Page 7** — Show in header: "PROBABLE_MULE (78% confidence)" + "Higher risk than 94% of population"
**Page 7** — If spike_suppressed: show warning "⚠️ Score reduced 12% — single dimension spike without corroboration"

### F-1.5 TESTS (v1.1)
1. Risk probability: min=0.00, max=1.00, monotonic with score
2. Spike suppression fires when 1 dim at 90, others below 30
3. Spike suppression does NOT fire when 3 dims above 50
4. Max-avg hybrid: D6=95 others=10 → score higher than pure weighted sum
5. Binary boost: 6 flags → 0.30, 0 flags → 0.00, 10 flags → 0.30 (capped)
6. Power-law tail: top 1% degree nodes flagged True
7. Shared attr cap: 100-node shared IP → suppressed
8. Confidence: large dim gap → high %, small gap → low %

---

## SECTION 2: v1.2 — SELF-CALIBRATION (engine becomes dataset-adaptive)

### F-2.1 SCORING LAYER

**Entropy-based dynamic weights** — `scoring.py`
- For each dimension Di, compute entropy of score distribution (10-bin histogram)
- `discriminativity_i = 1 - (entropy_i / log2(10))`
- If discriminativity < 0.15 → shrink weight to max(original × 0.30, 0.02)
- Else → `adjusted_weight = original × (0.5 + 0.5 × discriminativity)`
- Normalize all weights to sum = 1.0
- Library: scipy.stats.entropy (already installed)
- New columns: `weight_D1_adjusted` ... `weight_D7_adjusted`
- run_metadata: `entropy_weights: {D1: 0.12, ...}`, `discriminativity: {D1: 0.45, ...}`
- Purpose: if D2 Red Flags fires on 55% of population → uninformative → auto-shrinks

**Borda consensus count** — `scoring.py`
- For each node, count dimensions where node ranks in top 25%
- `borda_count` = 0-7 integer
- `borda_multiplier = 1 + (0.015 × min(borda_count, 5))`
- Apply post-fusion: `fused = min(fused × borda_multiplier, 100)`
- New column: `borda_count` (int)
- Config: `borda_boost_per_dim: 0.015`, `borda_cap: 5`
- Purpose: rewards BROAD consensus — top-ranked in 6 dims is much stronger than top in 1

**Norm method config** — `scoring.py` + `config.yaml`
- Config parameter: `norm_method: rank` (default)
- Options: rank / minmax / zscore / robust
- Applied at percentile ranking step
- No UI dropdown yet — config-only for power users

### F-2.2 FEATURE LAYER

**Benford's Law** — `behavioral.py`
- For each node, collect all transaction amounts
- Compute first-digit frequency distribution (digits 1-9)
- Expected: Benford distribution `[log10(1 + 1/d) for d in 1..9]`
- `benford_chi_sq = Σ((observed_d - expected_d)² / expected_d)`
- `benford_zscore = (chi_sq - population_mean_chi) / population_std_chi`
- Library: numpy only (log10, histogram)
- Two new features: `benford_chi_squared`, `benford_zscore`
- Add to D2 Red Flags with weight 0.12, redistribute other D2 sub-weights proportionally
- Feature count: 85 → 87
- Skip if node has < 10 transactions (insufficient sample for Benford) → set both to 0

### F-2.3 PIPELINE LAYER

**Alert dedup (cross-run comparison)** — `pipeline.py`
- After scoring complete, load previous run's fusion_scores (from `current_run.txt` pointer)
- For each scored node:
  - Not in previous run → `alert_status = "NEW"`
  - In previous AND was Tier 1-3 AND still Tier 1-3 → `alert_status = "RETURNING"`
  - In previous AND was Tier 4/Normal AND now Tier 1-3 → `alert_status = "ESCALATED"`
  - In previous AND was Tier 1-3 AND now Tier 4/Normal → `alert_status = "RESOLVED"`
  - In previous AND same tier → `alert_status = "UNCHANGED"`
- New column: `alert_status` (str)
- Also compute: `score_delta = current_score - previous_score` (float, NULL if new)
- If no previous run exists → all nodes = "NEW"

### F-2.4 VALIDATION LAYER

**Feature importance recalculation** — `validation.py`
- Re-run permutation importance with 87 features (was 84)
- Verify Benford features rank appropriately (not dominant, not zero)
- Verify power-law tail is not > 40% importance

**Weight adjustment transparency** — `validation.py`
- New validation section: table of original vs entropy-adjusted weights with discriminativity scores
- Flag if any dimension weight drops below 0.03 (effectively disabled) — warn in model health

**Benford validation** — `validation.py`
- Population-level check: average benford_chi_sq should be in reasonable range (0.5-50)
- If all nodes have chi_sq ≈ 0 → Benford is uninformative → warn

### F-2.5 UI LAYER

**Page 3 Dashboard** — New KPI cards: "12 NEW | 8 RETURNING | 3 ESCALATED | 5 RESOLVED" with color badges
**Page 6** — New columns: `borda_count`, `alert_status`, `score_delta`. Alert status with color: 🟢NEW 🔵RETURNING 🟠ESCALATED ⚪RESOLVED
**Page 7** — Show: "Consensus: Top 25% in 5 of 7 dimensions" + Borda count display
**Page 7** — If alert_status = ESCALATED: show banner "⚠️ This customer was previously low-risk. Score increased by +{delta} points."
**Page 12 Validation** — New section: "Weight Calibration" showing original vs adjusted weights as grouped bar chart + discriminativity scores per dimension
**Page 12 Validation** — New section: "Benford Analysis" showing expected vs observed first-digit distribution chart for selected customer

### F-2.6 TESTS (v1.2)
1. Entropy weights: uniform dimension → weight shrinks below 0.05
2. Entropy weights: bimodal dimension → weight stays at or above original
3. Entropy weights: all adjusted weights sum to 1.00
4. Borda: node top 25% in all 7 dims → borda_count = 7, multiplier = 1.075
5. Borda: node bottom 75% in all dims → borda_count = 0, multiplier = 1.0
6. Benford: amounts $9100/$9200/$9300 → high chi_squared
7. Benford: natural amount distribution → low chi_squared
8. Benford: node with < 10 tx → features = 0 (skipped)
9. Alert dedup: new node → NEW
10. Alert dedup: Tier 2 previously, now Tier 4 → RESOLVED
11. Alert dedup: Tier 4 previously, now Tier 1 → ESCALATED
12. Alert dedup: no previous run → all NEW
13. Score delta: computed correctly (current - previous)
14. Validation: weight adjustment report generated with 7 rows
15. Norm method: rank/minmax/zscore all produce valid 0-100 range

---

## SECTION 3: v1.3 — POWER USER FEATURES (investigation workflow)

### F-3.1 NARRATIVE LAYER

**Business rule templates** — new file `graphaml/utils/business_rules.py`
- 15-20 named rules, each with:
  - `rule_id`: unique identifier
  - `condition`: boolean expression on features (e.g., `structuring_pct > 0.50 AND off_hours_pct > 0.30`)
  - `severity`: HIGH / MEDIUM / LOW
  - `why_flagged`: template with value substitution — "Customer conducted {structuring_pct:.0%} of transactions in the $8,000-$10,000 range ({struct_count} of {total_count} transactions), significantly exceeding the population average of {pop_avg:.0%}."
  - `what_it_means`: plain English explanation
  - `what_to_do`: recommended investigation action

Core rules to implement:

| # | Rule Name | Condition | Severity |
|---|-----------|-----------|----------|
| 1 | potential_structuring | structuring_pct > 0.40 | HIGH |
| 2 | off_hours_activity | off_hours_pct > 0.30 | MEDIUM |
| 3 | pass_through_relay | pass_through_ratio > 0.80 AND avg_dwell < 3 days | HIGH |
| 4 | round_trip_flow | round_trip_count > 2 | HIGH |
| 5 | channel_switching | channel_switch_flag AND channels_used > 3 | MEDIUM |
| 6 | dormant_then_active | dormancy_days > 90 AND velocity_accel > 2.0 | HIGH |
| 7 | new_account_high_volume | account_age < 365 AND volume > 90th_pct | HIGH |
| 8 | pure_sink_external | is_external AND flow_type = PURE_SINK | MEDIUM |
| 9 | shell_indicator | is_external AND in_degree > 5 AND out_degree = 0 | HIGH |
| 10 | device_sharing_with_seed | shared_device_with_seed = True | HIGH |
| 11 | multi_seed_connector | connected_seeds_count > 2 | HIGH |
| 12 | benford_violation | benford_zscore > 3.0 | MEDIUM |
| 13 | velocity_spike | velocity_accel > 3.0 | MEDIUM |
| 14 | counterparty_concentration | hhi > 0.80 | LOW |
| 15 | powerlaw_hub | is_powerlaw_tail = True AND betweenness > 90th_pct | MEDIUM |
| 16 | ring_plus_relay_combo | cycle_participation > 0 AND pass_through_ratio > 0.60 | HIGH |
| 17 | funnel_collector | funnel_score > 5 AND flow_type = MOSTLY_IN | HIGH |
| 18 | spray_distributor | spray_score > 5 AND flow_type = MOSTLY_OUT | HIGH |
| 19 | cross_state_high_volume | cross_state_pct > 0.70 AND volume > 75th_pct | MEDIUM |
| 20 | closed_account_activity | closed_account_activity = True | HIGH |

**Combo rule suppression**: if rule 16 (ring_plus_relay) fires, suppress rule 4 (round_trip) and rule 3 (pass_through) individually — show only the combo. Prevents alert fatigue.

**Narrative generation**: for each customer, collect all triggered rules → sort by severity → concatenate `why_flagged` paragraphs → produce investigation-ready narrative. Accessible via `get_narrative(cust_id)`.

### F-3.2 UI LAYER

**Page 6 — Typology Library tab**
- New tab: "By Typology"
- Group scored suspects by suspect_type
- Each group shows: typology name, count, top 5 customers with scores
- Click group → filters main suspect table to that type
- Click customer → navigates to Page 7

**Page 7 — Business rules triggered section**
- New section below dimension cards: "Triggered Rules"
- List all rules that fired for this customer
- Each rule shows: severity badge (🔴HIGH 🟡MED ⚪LOW), rule name, personalized why_flagged text with actual values
- Combo rules show as single entry (components suppressed)
- "Generate Narrative" button → compiles all triggered rules into single copy-pasteable text block for investigation report

**Page 15 Admin — Threshold tuning preview**
- New section: "Threshold Calibration"
- 4 sliders: Tier 1 (default 65), Tier 2 (50), Tier 3 (35), Tier 4 (20)
- Live preview table: current count per tier vs projected count if thresholds changed
- "Apply & Re-Tier" button → updates tier column in fusion_scores without re-running pipeline, saves new thresholds to config, logs change in config_changelog
- "Reset to Default" button

**Page 15 Admin — Norm method selector**
- Dropdown: rank (default) / minmax / zscore / robust
- Changing requires pipeline re-run — show confirmation: "This requires full re-score. Proceed?"
- Save to config.yaml, log in config_changelog

### F-3.3 TESTS (v1.3)
1. Rule 1 fires: customer with 55% structuring → triggered, correct values in template
2. Rule 3 fires: pass-through 85% + dwell 1.5 days → triggered
3. Rule 16 fires: combo suppresses rules 3 and 4 individually
4. Rule does NOT fire: customer with 5% structuring → rule 1 not triggered
5. Narrative generation: 3 rules triggered → 3 paragraphs, sorted by severity
6. Typology tab: counts match suspect_type counts in fusion_scores
7. Threshold preview: moving T1 from 65 to 60 → correct count delta shown
8. Threshold apply: tier column updated, no score recalculation
9. Threshold apply: change logged in config_changelog
10. Norm method change: config updated, re-run required flag set

---

## SECTION 4: v2.0 — FUTURE ENHANCEMENTS (design only, do not build)

Document these in `docs/ROADMAP.md` for future implementation:

### F-4.1 Cross-Run Analytics
- **Dormancy activation**: compare current run degree vs previous run degree → `delta_activity` flag
- **Score trajectory**: for each customer, track score across last N runs → trend line (rising/falling/stable)
- **Network evolution**: edges added/removed between runs → "new relationship" alerts
- Requires: run comparison engine, cross-run feature store

### F-4.2 Watchlist Integration
- Upload watchlist.csv (external list of known bad actors/entities)
- Cross-match against all scored customers + external stubs
- Show hits with match confidence (exact/fuzzy name match)
- Requires: fuzzy matching library (fuzzywuzzy or rapidfuzz)

### F-4.3 Geographic Enhancements
- Treemap: country blocks sized by volume, colored by avg risk score
- Sunburst: outer ring = tier, inner ring = state/country
- World choropleth for international transaction flows
- Requires: good geographic data in input files

### F-4.4 Multi-Resolution Louvain Stability
- Run Louvain at resolutions 1.0, 1.5, 2.0
- Majority-vote community assignment
- `louvain_stability` score: fraction of resolutions agreeing
- Enhances community_stability feature (already exists)

### F-4.5 Challenger Model
- Run unsupervised scoring alongside supervised/semi-supervised
- Compare rankings: Kendall tau between approaches
- Flag nodes where approaches disagree by > 30 percentile points
- Purpose: model risk management — second opinion

---

## REVISED SCORING PIPELINE ORDER (v1.1 + v1.2 + v1.3 combined)

```
CURRENT (v1.0):
  Features(84) → Rank → D1-D7 → Correlation Penalty → Weighted Sum → Tier → Type → Evidence

REVISED (v1.3):
  Features(87)                                    # +Benford(2) +PowerLaw(1)
  → Norm (rank/minmax/zscore/robust)              # v1.3 configurable
  → D1-D7 (updated sub-weights for Benford, PL)  # v1.2
  → Correlation Penalty                           # existing
  → Entropy Weight Adjustment                     # v1.2 self-calibrating
  → Spike Suppression (0.88× if single spike)     # v1.1
  → Max-Avg Hybrid Fusion (60/40 blend)           # v1.1
  → Borda Consensus Boost (×1.015 per dim)        # v1.2
  → Binary Evidence Boost (capped 0.30)           # v1.1
  → Cap at 100
  → Risk Probability (empirical CDF)              # v1.1
  → Tier Assignment (configurable thresholds)      # v1.3 tunable
  → Type + Confidence %                           # v1.1
  → Evidence Strength
  → Business Rules Evaluation                     # v1.3
  → Alert Dedup (vs previous run)                 # v1.2
  → Output
```

---

## ALL NEW COLUMNS IN fusion_scores.parquet

| Column | Type | Version | Source |
|--------|------|---------|--------|
| `risk_probability` | float 0-1 | v1.1 | Empirical CDF |
| `spike_suppressed` | bool | v1.1 | Spike check |
| `binary_boost_applied` | float 0-0.30 | v1.1 | Flag count |
| `suspect_type_confidence` | int 40-100 | v1.1 | Dim gap |
| `weight_D1_adjusted`...`D7` | float | v1.2 | Entropy calibration |
| `borda_count` | int 0-7 | v1.2 | Consensus |
| `alert_status` | str | v1.2 | Cross-run dedup |
| `score_delta` | float | v1.2 | vs previous run |
| `triggered_rules` | str (comma-sep) | v1.3 | Business rules |
| `triggered_rules_count` | int | v1.3 | Count |
| `narrative_text` | str | v1.3 | Auto-generated |

## ALL NEW FEATURES IN feature_matrix

| Feature | Module | Dimension | Version |
|---------|--------|-----------|---------|
| `is_powerlaw_tail` | structural.py | D3 | v1.1 |
| `benford_chi_squared` | behavioral.py | D2 | v1.2 |
| `benford_zscore` | behavioral.py | D2 | v1.2 |

Total features: 84 → 87

## ALL NEW CONFIG PARAMETERS

| Parameter | Default | Version |
|-----------|---------|---------|
| `shared_attribute_max_pairs` | 50 | v1.1 |
| `fusion_hybrid_ratio` | 0.60 | v1.1 |
| `binary_boost_per_flag` | 0.05 | v1.1 |
| `binary_boost_cap` | 0.30 | v1.1 |
| `spike_suppression_factor` | 0.88 | v1.1 |
| `spike_max_dim_threshold` | 70 | v1.1 |
| `spike_min_agreeing_dims` | 2 | v1.1 |
| `spike_std_threshold` | 22 | v1.1 |
| `borda_boost_per_dim` | 0.015 | v1.2 |
| `borda_cap` | 5 | v1.2 |
| `entropy_discriminativity_floor` | 0.15 | v1.2 |
| `entropy_weight_shrink_factor` | 0.30 | v1.2 |
| `norm_method` | rank | v1.3 |
| `tier_1_threshold` | 65 | v1.3 (tunable) |
| `tier_2_threshold` | 50 | v1.3 (tunable) |
| `tier_3_threshold` | 35 | v1.3 (tunable) |
| `tier_4_threshold` | 20 | v1.3 (tunable) |

---

## ALL UI CHANGES SUMMARY

| Page | Change | Version |
|------|--------|---------|
| Page 3 | Alert dedup KPIs: NEW/RETURNING/ESCALATED/RESOLVED counts | v1.2 |
| Page 6 | New columns: risk_probability, confidence, borda, alert_status, score_delta | v1.1+v1.2 |
| Page 6 | New tab: "By Typology" — suspects grouped by type | v1.3 |
| Page 7 | Header: confidence %, risk probability text | v1.1 |
| Page 7 | Banner: spike suppression warning (if applied) | v1.1 |
| Page 7 | Banner: escalation warning (if alert_status=ESCALATED) | v1.2 |
| Page 7 | Display: "Consensus: Top 25% in N of 7 dimensions" | v1.2 |
| Page 7 | New section: Triggered business rules with severity + explanations | v1.3 |
| Page 7 | Button: "Generate Narrative" → copy-pasteable investigation text | v1.3 |
| Page 12 | New section: Weight Calibration (original vs adjusted bar chart) | v1.2 |
| Page 12 | New section: Benford Analysis (expected vs observed chart) | v1.2 |
| Page 15 | New section: Threshold Tuning sliders + live preview + apply button | v1.3 |
| Page 15 | Norm method dropdown (requires re-run confirmation) | v1.3 |

---

## COMPLETE TEST LIST

| # | Test | Version |
|---|------|---------|
| 1 | Risk probability: min=0.00, max=1.00, monotonic | v1.1 |
| 2 | Spike fires: 1 dim at 90, others <30 | v1.1 |
| 3 | Spike skips: 3 dims above 50 | v1.1 |
| 4 | Hybrid: D6=95 others=10 → higher than pure sum | v1.1 |
| 5 | Binary boost: 6 flags=0.30, 10 flags=0.30 (cap) | v1.1 |
| 6 | Power-law: top 1% degree → True | v1.1 |
| 7 | Shared attr cap: 100-node IP → suppressed | v1.1 |
| 8 | Confidence: large gap → high %, small → low % | v1.1 |
| 9 | Entropy: uniform dim → weight <0.05 | v1.2 |
| 10 | Entropy: bimodal dim → weight ≥ original | v1.2 |
| 11 | Entropy: all weights sum to 1.00 | v1.2 |
| 12 | Borda: top 25% in 7 dims → count=7, mult=1.075 | v1.2 |
| 13 | Borda: bottom in all → count=0, mult=1.0 | v1.2 |
| 14 | Benford: clustered amounts → high chi_sq | v1.2 |
| 15 | Benford: natural amounts → low chi_sq | v1.2 |
| 16 | Benford: <10 tx → features=0 (skipped) | v1.2 |
| 17 | Alert dedup: new node → NEW | v1.2 |
| 18 | Alert dedup: T2→T4 → RESOLVED | v1.2 |
| 19 | Alert dedup: T4→T1 → ESCALATED | v1.2 |
| 20 | Alert dedup: no prev run → all NEW | v1.2 |
| 21 | Score delta correct: current - previous | v1.2 |
| 22 | Validation: weight report has 7 rows | v1.2 |
| 23 | Rule 1 fires: 55% structuring → triggered | v1.3 |
| 24 | Rule 3 fires: 85% pass-through + 1.5d dwell | v1.3 |
| 25 | Combo suppression: rule 16 suppresses 3+4 | v1.3 |
| 26 | Rule skip: 5% structuring → not triggered | v1.3 |
| 27 | Narrative: 3 rules → 3 paragraphs, severity sorted | v1.3 |
| 28 | Typology tab: counts match suspect_type | v1.3 |
| 29 | Threshold preview: T1 65→60 → correct delta | v1.3 |
| 30 | Threshold apply: tiers updated, no re-score | v1.3 |

---

## SUCCESS CRITERIA

```
v1.1:
  ☐ All 8 quick-win changes functional
  ☐ Tests 1-8 PASS
  ☐ No existing test broken
  ☐ Score distribution still reasonable (no all-Tier-1 or all-Normal)

v1.2:
  ☐ Entropy weights auto-adjust per dataset
  ☐ Borda rewards broad consensus
  ☐ Benford features computed
  ☐ Alert dedup accurate across runs
  ☐ Tests 9-22 PASS

v1.3:
  ☐ 20 business rules evaluate correctly
  ☐ Combo suppression works
  ☐ Narrative generates with actual values
  ☐ Threshold tuning preview accurate
  ☐ Tests 23-30 PASS

Overall:
  ☐ Full pipeline runs end-to-end with all changes
  ☐ Sample data produces reasonable tier distribution
  ☐ All 30 tests PASS
```