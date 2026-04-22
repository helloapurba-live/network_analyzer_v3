
# PHASE G: Complete All Missing — Audit Controls, Visual Investigation, Engine Calibration, External Handling

## CONTEXT
Phases A-E designed, partially built. Phase F designed, 0% built. Audit reveals 65% overall coverage. This single phase completes ALL remaining gaps identified in the comprehensive audit. Changes span every layer.

## PRIORITY ORDER WITHIN THIS PHASE
Build in this exact sequence — each section may depend on previous:
```
G-1: Audit Controls (Phase D gaps)          ← BLOCKS BANK EXAM
G-2: Scoring Engine Upgrades (Phase F)      ← IMPROVES SCORE QUALITY
G-3: Feature Additions (Phase F)            ← NEW ANALYTICAL SIGNALS
G-4: Pipeline Enhancements (Phase F)        ← CROSS-RUN INTELLIGENCE
G-5: Visual Investigation Charts (Phase E)  ← ANALYST UX
G-6: External Party Handling (Patch)        ← SCOPE CONTROLS
G-7: Business Rules & Narratives (Phase F)  ← EXPLAINABILITY
G-8: UI Enhancements (Phase E+F)           ← FINAL POLISH
```

---

## G-1: AUDIT CONTROLS

### G-1.1: Hash-Chained Audit Trail

New file: `graphaml/compliance/audit_chain.py`

Every auditable action creates an entry:
- `timestamp` (ISO 8601 UTC)
- `run_id`
- `user`
- `action` (SCORE_RUN, FLAG_CHANGE, CONFIG_CHANGE, EXPORT, LOGIN, THRESHOLD_CHANGE, SIGN_OFF, PURGE)
- `details` (action-specific dict)
- `prev_hash` (SHA-256 of previous entry — genesis entry has prev_hash = "0" × 64)
- `entry_hash` (SHA-256 of: prev_hash + timestamp + action + details serialized)

Storage: `governance/audit_chain.jsonl` — append-only.

On each pipeline run: auto-verify entire chain integrity (recompute all hashes, compare). If ANY hash mismatch detected → log `INTEGRITY_VIOLATION` entry → set `model_health = RED` → show red banner on Page 3 and Page 15.

Functions:
- `append_entry(action, details, user)` → computes hash, appends
- `verify_chain()` → returns (is_valid: bool, broken_at: int | None)
- `get_chain_summary()` → returns entry count, date range, last action

Integrate: every existing callback that changes state (flag, note, config, export, login, run) must call `append_entry`.

### G-1.2: File Integrity Hashes

After pipeline completes, compute SHA-256 of every output file:
- `fusion_scores.parquet`
- `dimension_scores.parquet`
- `behavioral_features.parquet`
- `edges_aggregated.parquet`
- `nodes_validated.parquet`
- `chain_analysis.parquet`
- `community_assignments.parquet`
- `run_metadata.json`
- `mdd.json`

Store in `run_metadata.json` as:
```
"file_integrity": {
  "fusion_scores.parquet": "sha256:abc123...",
  "dimension_scores.parquet": "sha256:def456...",
  ...
}
```

On Page 15 Admin → "Run History" tab → each run shows integrity status:
- 🟢 "All files verified" (all hashes match)
- 🔴 "Integrity violation — N files modified" (hash mismatch)

Add function: `verify_run_integrity(run_id)` → recomputes hashes, compares against stored.

### G-1.3: Dual Control on Tier 1

Flag workflow change for Tier 1 suspects:

Current: analyst flags → saved immediately.

New:
- If suspect is Tier 1 AND action is CLEARED_NO_ACTION or CLEARED_FALSE_POSITIVE:
  - Status set to `PENDING_CLEARANCE` (not final)
  - Audit entry: `CLEARANCE_REQUESTED` with analyst name
  - Requires MANAGER or ADMIN to approve
  - Until approved: suspect remains Tier 1 in all views, marked with "⏳ Pending Approval" badge
- MANAGER/ADMIN can:
  - `APPROVE_CLEARANCE` → status changes to final CLEARED, audit entry logged
  - `REJECT_CLEARANCE` → status reverts, audit entry logged, analyst notified

UI changes:
- Page 7: if Tier 1 and role=analyst, "Clear" button label changes to "Request Clearance"
- Page 7: if Tier 1 and role=manager/admin, show "Approve" / "Reject" buttons on pending items
- Page 15 Admin: new "Pending Approvals" section showing all PENDING_CLEARANCE items with approve/reject buttons
- Page 3 Dashboard: KPI "N Pending Approvals" (yellow badge)

Storage: add `clearance_status` column to manual_flags: NULL / PENDING / APPROVED / REJECTED. Add `clearance_by` and `clearance_date` columns.

### G-1.4: EXAMINER Role

Add 5th role: EXAMINER (read-only, no PII, no export).

Permissions:
| Action | ADMIN | MANAGER | ANALYST | VIEWER | EXAMINER |
|--------|-------|---------|---------|--------|----------|
| View all pages | ✅ | ✅ | ✅ | ✅ | ✅ |
| See PII (names, accounts) | ✅ | ✅ | ✅ | ✅ | ❌ masked |
| Flag/note suspects | ✅ | ✅ | ✅ | ❌ | ❌ |
| Export CSV/PDF | ✅ | ✅ | ✅ | ❌ | ❌ |
| Run pipeline | ✅ | ✅ | ❌ | ❌ | ❌ |
| Change config | ✅ | ❌ | ❌ | ❌ | ❌ |
| Approve clearances | ✅ | ✅ | ❌ | ❌ | ❌ |
| View audit chain | ✅ | ✅ | ❌ | ❌ | ✅ |

PII masking for EXAMINER: replace customer names with "Customer_XXX", account numbers with "****XXXX" (last 4 only), addresses with "[REDACTED]". Apply at render time in callbacks, not at data level.

Add EXAMINER to login page dropdown and session store role list.

### G-1.5: Retention Lock

Config parameter: `retention_days: 1825` (5 years = BSA minimum).

On Page 15 Admin → "Run History":
- Each run shows retention status:
  - 🔒 "Locked until {date}" if within retention period
  - 🔓 "Eligible for deletion" if past retention
- Delete button disabled for locked runs
- Override: ADMIN can force-delete with confirmation modal + audit entry `RETENTION_OVERRIDE`

On pipeline run: calculate `retention_expires = run_date + retention_days`, store in run_metadata.

### G-1.6: Auto-Escalation

Background check on each page load (or scheduled interval):

```
For each Tier 1 suspect:
  IF flag_status is NULL (not flagged) AND score_date > 7 days ago:
    Set flag_status = "AUTO_ESCALATED"
    Create audit entry: OVERDUE_ESCALATION
    Notify: show on Page 3 as red KPI "N Overdue Tier 1"

For each Tier 2 suspect:
  IF flag_status is NULL AND score_date > 14 days ago:
    Same logic with 14-day SLA
```

Config: `sla_tier1_days: 7`, `sla_tier2_days: 14`, `sla_tier3_days: 30`

Page 3 Dashboard: new KPI card "Overdue SLA" with count + red/green indicator.
Page 6: sortable column `sla_status` (ON_TIME / APPROACHING / OVERDUE).

### G-1.7: MDD Auto-Sync

On every pipeline run, auto-update `governance/mdd.json`:
- `tier_thresholds` → pull from active config.yaml (not hardcoded)
- `dimension_weights` → pull current weights (including entropy-adjusted if Phase F active)
- `features` → list all 87 features with names and dimension mapping
- `validation_summary` → pull from latest validation results
- `change_log` → append new entry with run stats

Add: MDD diff check — if thresholds in MDD differ from config.yaml, log WARNING in run_metadata.

### G-1.8: Sign-Off Workflow

Page 15 Admin → new "Model Sign-Off" section:

4 sign-off slots: Model Owner, Risk Owner, Compliance, Senior Management.
Each slot:
- Name field (text input)
- "Sign Off" button → records name + timestamp + creates audit entry
- Once signed: shows ✅ badge with name and date, button disabled
- Reset: only ADMIN can clear sign-offs (audit logged)

Sign-offs stored in `governance/mdd.json` under `sign_offs` (already exists, just null).

After all 4 signed: show "✅ Model Fully Approved" banner on Page 12 Validation.

### G-1.9: One-Click Exam Package

Page 14 Reports → new button "📦 Generate Exam Package"

Creates ZIP containing:
- `run_metadata.json`
- `mdd.json`
- `config.yaml`
- `audit_chain.jsonl`
- `config_changelog.jsonl`
- `fusion_scores.csv` (top 50 suspects only)
- `validation_summary.json`
- `tier_distribution_chart.png` (auto-generated plotly static image)
- `README_EXAM.txt` (auto-generated: run date, approach, seed count, tier counts, model health, sign-off status)

PII handling: if EXAMINER role → all PII masked in exported CSV.

### G-1.10: Sensitivity Analysis

Page 12 Validation → new section "Sensitivity Analysis"

On-demand (button click), compute:
- For each dimension weight: perturb ±20% → recompute fusion scores → measure rank change
- Output: table of 7 rows showing dimension name, original weight, +20% rank correlation (Kendall tau), -20% rank correlation
- If ANY perturbation causes tau < 0.80 → flag "⚠️ Model sensitive to {dimension} weight changes"

Also: perturb tier thresholds ±5 points → show customer migration count.

Store results in run output folder as `sensitivity_analysis.json`.

### G-1.11: PSI Monitoring

On pipeline run, if previous run exists:
- Compute Population Stability Index between current and previous fusion_score distributions
- `PSI = Σ((actual_pct - expected_pct) × ln(actual_pct / expected_pct))` across 10 bins

Thresholds: PSI < 0.10 → 🟢 Stable, 0.10-0.25 → 🟡 Moderate drift, > 0.25 → 🔴 Significant drift

Store in `run_metadata.json` as `psi_vs_previous`.
Show on Page 12 Validation as gauge/indicator.
If PSI > 0.25 → model_health downgrades to YELLOW minimum.

### G-1.12: QA Sampling

Page 15 Admin → new section "QA Spot Check"

Button: "Generate QA Sample" → randomly select 10% of Tier 1-3 suspects (min 5, max 50).
Display as AG Grid with columns: cust_id, score, tier, type, top 2 dimensions, top red flag.
Analyst reviews each row → marks "✅ Agree" or "❌ Disagree" with optional comment.
Results stored in `governance/qa_samples.jsonl` with timestamp, reviewer, agreement rate.
Show agreement rate on Page 12: "QA Agreement: 92% (23/25 agreed)"

### G-1.13: Right-to-Delete

Page 15 Admin → "Data Management" section

"Purge Customer" button (ADMIN only):
- Input: customer ID
- Action: remove customer from ALL parquet files across ALL runs within retention scope
- Audit entry: `CUSTOMER_PURGE` with customer ID, reason, timestamp
- Confirmation modal: "This will permanently remove all data for {customer_id} across {N} runs. This action cannot be undone."

---

## G-2: SCORING ENGINE UPGRADES

### G-2.1: Risk Probability Column

After fusion scores computed:
`risk_probability = (rank_of_score - 1) / (total_scored - 1)`

New column in fusion_scores output. Range 0.00-1.00.

### G-2.2: Spike Suppression

After D1-D7, before fusion:
```
IF max(D1..D7) > 70 AND count(other dims > 40) < 2 AND std(D1..D7) > 22:
  fusion_score *= 0.88
  spike_suppressed = True
```

New columns: `spike_suppressed` (bool), `spike_reason` (str).
Config: `spike_suppression_factor: 0.88`, `spike_max_dim_threshold: 70`, `spike_min_agreeing_dims: 2`, `spike_std_threshold: 22`

### G-2.3: Max-Avg Hybrid Fusion

Replace pure weighted sum:
```
fused = 0.60 × weighted_sum + 0.40 × (0.25 × max_dim_score + 0.75 × weighted_avg)
```

Config: `fusion_hybrid_ratio: 0.60`

### G-2.4: Binary Evidence Boost

Post-fusion, capped:
```
flags = [motif_circular, potential_structuring, is_layering_intermediary,
         channel_switch_flag, round_trip_detected, multi_seed_flag,
         closed_account_activity, new_account_flag]
boost = min(count_true(flags) × 0.05, 0.30)
fused = min(fused × (1 + boost), 100)
```

New column: `binary_boost_applied` (float).
Config: `binary_boost_per_flag: 0.05`, `binary_boost_cap: 0.30`

### G-2.5: Entropy-Based Dynamic Weights

Before fusion, for each dimension Di:
```
histogram = 10-bin of all nodes' Di scores
entropy_i = scipy.stats.entropy(histogram_probabilities)
discriminativity_i = 1 - (entropy_i / log2(10))

IF discriminativity < 0.15: adjusted_weight = max(original × 0.30, 0.02)
ELSE: adjusted_weight = original × (0.5 + 0.5 × discriminativity)

Normalize all weights to sum = 1.0
```

New columns: `weight_D1_adjusted` ... `weight_D7_adjusted`.
Store in run_metadata: `entropy_weights`, `discriminativity_per_dim`.

### G-2.6: Borda Consensus Count

```
For each node: count dimensions where node ranks in top 25%
borda_count = 0-7
borda_multiplier = 1 + (0.015 × min(borda_count, 5))
fused = min(fused × borda_multiplier, 100)
```

New column: `borda_count` (int).
Config: `borda_boost_per_dim: 0.015`, `borda_cap: 5`

### G-2.7: Suspect Type Confidence %

```
gap = top_dim_score - second_dim_score
confidence_pct = min(40 + gap × 2, 100)
```

New column: `suspect_type_confidence` (int 40-100).

### G-2.8: Norm Method Config

Config: `norm_method: rank` (default). Options: rank / minmax / zscore / robust.
Applied at percentile ranking step in scoring.py.
No UI dropdown — config-only for now.

### G-2.9: Revised Scoring Pipeline Order

```
Features(87) → Norm → D1-D7 → Correlation Penalty → Entropy Weight Adjustment
→ Spike Suppression → Max-Avg Hybrid Fusion → Borda Boost → Binary Boost
→ Cap at 100 → Risk Probability → Tier Assignment (configurable thresholds)
→ Type + Confidence % → Evidence Strength → Output
```

---

## G-3: FEATURE ADDITIONS

### G-3.1: Benford's Law

In `behavioral.py`, two new features:
- For each node, collect all transaction amounts
- Compute first-digit frequency (digits 1-9)
- Expected: Benford distribution `[log10(1 + 1/d)]`
- `benford_chi_sq = Σ((observed - expected)² / expected)`
- `benford_zscore = (chi_sq - population_mean) / population_std`
- Skip if node has < 10 transactions → set both to 0

Add to D2 Red Flags with weight 0.12, redistribute other D2 sub-weights proportionally.
Library: numpy only. Feature count: 84 → 86.

### G-3.2: Power-Law Degree Tail

In `structural.py`:
- `is_powerlaw_tail = degree > numpy.percentile(all_degrees, 99)`

Add to D3 Centrality with weight 0.10, reduce hub_auth to 0.05.
Feature count: 86 → 87.

### G-3.3: Shared Attribute Pair Cap

In `transformer.py`, when creating identity edges:
```
For each (attribute_type, attribute_value):
  IF count(nodes sharing this value) > 50:
    Skip entirely → log warning
```

Config: `shared_attribute_max_pairs: 50`

---

## G-4: PIPELINE ENHANCEMENTS

### G-4.1: Alert Dedup (Cross-Run Comparison)

After scoring, load previous run's fusion_scores:
```
For each node:
  Not in previous → alert_status = "NEW"
  Was Tier 1-3, still Tier 1-3 → "RETURNING"
  Was Tier 4/Normal, now Tier 1-3 → "ESCALATED"
  Was Tier 1-3, now Tier 4/Normal → "RESOLVED"
  Same tier → "UNCHANGED"
```

New columns: `alert_status` (str), `score_delta` (float = current - previous).
If no previous run → all "NEW".

### G-4.2: Outcome Tracking

When analyst flags a suspect with final disposition (IR_FILED, CLEARED_NO_ACTION, CLEARED_FALSE_POSITIVE):
- Store in `governance/outcomes.jsonl`: cust_id, disposition, score_at_disposition, tier_at_disposition, date, analyst
- On next validation run: compute true positive rate = IR_FILED / (IR_FILED + CLEARED) among Tier 1
- Show on Page 12: "Tier 1 True Positive Rate: 78% (14/18)"

---

## G-5: VISUAL INVESTIGATION CHARTS

### G-5.1: Transaction Timeline (Page 7 — New Tab)

Tab name: "Transaction Timeline"

Plotly scatter:
- X: date, Y: amount ($)
- Each dot = one transaction for selected customer
- Color: 🔴 outbound, 🟢 inbound
- Size: proportional to amount
- Hover: date, amount, counterparty, channel, direction

Controls:
- Toggle: Inbound / Outbound / Both (default Both)
- Checkbox: "Show structuring band" → shaded $8K-$10K zone
- Checkbox: "Highlight off-hours" → darker dots for 10pm-6am
- Dropdown: "Filter counterparty" → show only selected counterparty's transactions

Interactivity:
- Brush select date range → store in `dcc.Store('selected-date-range')` → filters Charts 5.2, 5.3, 5.4
- Click dot → highlight counterparty in network graph if open

Data: `transactions_validated.parquet` filtered by selected customer.

### G-5.2: Counterparty Flow Sankey (Page 7 — New Tab)

Tab name: "Money Flow"

Plotly Sankey:
- LEFT: entities sending TO customer (sources)
- CENTER: selected customer
- RIGHT: entities receiving FROM customer (destinations)
- Link width: proportional to total amount
- Link color: red if counterparty is seed/Tier 1, orange Tier 2, gray otherwise
- Node color: tier coloring
- Node label: cust_id + truncated name + total amount

Controls:
- Slider: "Min amount" → hide links below threshold
- Date range picker
- Channel dropdown filter

Interactivity:
- Click node → navigate to Page 7 for that customer
- Hover link → tooltip: total amount, tx count, date range, channel

Data: `transactions_validated.parquet` + `fusion_scores.parquet`

### G-5.3: Activity Heatmap (Page 7 — New Tab)

Tab name: "Activity Pattern"

Plotly heatmap:
- X: day of week (Mon-Sun), Y: time blocks (8 blocks: 3-hour windows)
- Cell color: transaction count (white → yellow → red)
- If no hour data: fallback to day-of-week bar chart only, log warning

Controls:
- Toggle: "Show population average overlay"
- Toggle: "Highlight off-hours"

Interactivity:
- Click cell → modal with transaction list for that slot

Data: `transactions_validated.parquet`, parse date into day_of_week + hour_bucket.

### G-5.4: Amount Distribution Histogram (Page 7 — New Tab)

Tab name: "Amount Profile"

Plotly histogram:
- X: amount ($) binned, Y: count
- Shaded zone: $8K-$10K in red ("Structuring Zone")
- Overlay line: population average distribution (KDE)

Controls:
- Slider: bin size ($500 / $1K / $2K / $5K)
- Toggle: "Show peer group average"
- Toggle: "Highlight round amounts"

Interactivity:
- Click bar → modal listing transactions in that range

### G-5.5: Risk Radar Comparison (Page 6 + Page 7)

Page 6: "Compare" button → select up to 3 customers → modal with radar chart.
Page 7: "Compare with..." button → dropdown to pick 1-2 others.

Plotly scatterpolar:
- 7 axes: D1-D7
- Each customer = one colored polygon
- Scale 0-100, dashed circle at 50
- Legend: cust_id + score + tier

Controls:
- Toggle each customer on/off
- "Add population average" button → gray dashed polygon

Interactivity:
- Hover axis point → tooltip: exact score + top contributing feature
- Click axis label → navigate to dimension breakdown

Data: `dimension_scores.parquet`

### G-5.6: Top Risk Network Mini-Map (Page 3)

Dashboard card: "Top Risk Network"

Dash-cytoscape:
- Nodes: top 10 highest-scored + their direct seed connections + direct external counterparties
- Max 50 nodes (pruned by edge weight)
- Node size: proportional to score
- Node color: tier (red T1, orange T2, yellow T3, gray normal, black seed, light gray external)
- Edge width: transaction volume
- Edge style: solid internal, dashed external
- Layout: force-directed (cose)

Interactivity:
- Click node → navigate to Page 7
- Hover → tooltip: name, score, tier, top flag
- Zoom/pan enabled

### G-5.7: Score vs Volume Scatter (Page 6 — New Tab)

Tab name: "Risk vs Activity"

Plotly scatter:
- X: total volume (log scale), Y: fusion score (0-100)
- Dot color by tier, size fixed default
- Quadrant lines: horizontal at Tier 1 threshold, vertical at median volume
- Quadrant labels: "High Risk High Volume" (top-right = priority)

Controls:
- Dropdown "Color by": Tier / Suspect Type / Community / Entity Source
- Dropdown "Size by": Fixed / Tx Count / Counterparty Count / Score
- Toggle: "Show externals"
- Slider: "Min score"

Interactivity:
- Click dot → navigate to Page 7
- Lasso select → "Flag Selected" button for bulk flagging

### G-5.8: Full Investigation Canvas Enhancements (Page 7/13)

Enhance existing Cytoscape with:

**Controls bar:**
- Depth: 1/2/3 hops (default 2)
- Min amount: filter edges below threshold
- Date range picker
- Channel dropdown
- Color by: Tier (default) / Community / Hop / Type / Flow Direction
- Size by: Score (default) / Volume / Tx Count / Degree
- Show: All / Internal / External / Seeds / Flagged
- Edge width by: Amount / Tx Count / Recency
- Layout: Force-directed / Hierarchical / Circular / Grid / Breadthfirst

**Right-click context menu — NODE** (positioned `dbc.Card` at mouse position):
- 👤 View Investigation → navigate to Page 7
- 🔍 Expand Neighborhood → add node's neighbors to canvas
- ➖ Collapse Neighborhood → remove non-shared neighbors
- 🏷️ Flag As... → open flag modal pre-filled
- 📌 Pin/Unpin → lock position (cytoscape `locked: true`)
- 🔗 Show Paths to Seeds → highlight shortest paths, dim others to 0.2 opacity
- 🔄 Show Chains Through → highlight layering chains from chain_analysis
- 📊 Show Transactions → open side panel with AG Grid
- ❌ Hide Node → remove from view, add to hidden set
- 📋 Compare With... → open radar modal
- 📝 Add Note → note input modal

**Right-click context menu — EDGE:**
- 💰 Show Transactions → side panel: all tx between A↔B
- 📅 Show Timeline → mini timeline for this edge
- 🔄 Show Reverse Flow → highlight B→A if exists
- ⛓️ Show Chain Context → highlight full chain

**Side panel** (right side, 350px, collapsible):
- Node selected: cust_id, name, score, tier, type, evidence strength, transaction table, red flag bullets, notes
- Edge selected: A→B header, total amount, tx count, date range, channels, transaction table

**Toolbar** (bottom):
- Reset View, Screenshot (PNG export), Show Hidden (N), Clear Highlights, Toggle Labels, Toggle Edge Labels, Zoom slider

**Node rendering:**
- Shape: circle=internal, diamond=external, hexagon=seed
- Border: solid=internal, dashed=external
- Badge: 🚩 overlay if flagged
- Opacity: 1.0 Tier 1-2, 0.7 Tier 3, 0.5 Normal

**Edge rendering:**
- Arrow direction of money flow
- Color: red between Tier 1-2 nodes, gray otherwise
- Style: solid=single channel, dashed=multi-channel

### G-5.9: Chain Visualization (Page 9 — New Tab)

Tab name: "Chain Explorer"

Plotly connected scatter OR Cytoscape breadthfirst (left-to-right):
- Nodes: chain origin → intermediaries → destination
- Above node: amount at that stage
- Below node: date
- Between nodes: channel label
- Below edge: "kept $X (Y%)" showing decay
- Node color: tier

Controls:
- Dropdown: select chain (sorted by value/length/decay)
- Slider: min chain length, min chain value
- Toggle: "Color by channel"

Interactivity:
- Click node → navigate to Page 7
- Hover edge → tooltip: amount, date, channel, delay days

### G-5.10: Counterparty Relationship Matrix (Page 9 — New Tab)

Tab name: "Relationship Matrix"

Plotly heatmap:
- Rows/columns: top N suspects (default 20)
- Cell value: total amount between pair
- Color: white (none) → yellow → red
- Diagonal blocked

Controls:
- Slider: Top N (10/20/30/50)
- Dropdown: Internal only / All
- Dropdown: Sort by Score / Volume / Name

Interactivity:
- Click cell → modal with transactions between that pair
- Click header → navigate to Page 7

### G-5.11: Investigation Progress Funnel (Page 3)

Dashboard card: "Investigation Progress"

Plotly funnel:
- Total Scored → Tier 1-3 Suspects → Under Investigation → Flagged → IR Filed → Cleared → Pending
- Bar color: green if within SLA, yellow approaching, red overdue

Interactivity:
- Click stage → navigate to Page 6 filtered to that subset

### G-5.12: Cross-Chart Linking

Shared `dcc.Store` components on Page 7:
- `selected-date-range` — date brush from Timeline filters Sankey, Heatmap, Histogram
- `selected-counterparty` — dot click on Timeline highlights in Canvas
- `selected-node-canvas` — canvas click opens side panel with mini-timeline
- `hidden-nodes` — track hidden nodes on canvas
- `highlighted-paths` — path/chain highlight state

Each chart callback reads from relevant stores. Debounce 300ms.

### G-5.13: Performance Guardrails

| Scenario | Action |
|----------|--------|
| Canvas > 500 nodes | Auto "Simple mode": hide labels, reduce opacity, no animations |
| Canvas > 1000 nodes | Warning + cap at 500 by score |
| Sankey > 50 links | Collapse smallest into "Other" |
| Heatmap no time data | Fallback to day-of-week bar |
| Matrix > 50×50 | Cap at 50, show "Showing top 50" |
| Chain list > 100 | Paginate 20 per page |

---

## G-6: EXTERNAL PARTY HANDLING

### G-6.1: Entity Source Column

Ensure `entity_source` column (INTERNAL / EXTERNAL) is present in fusion_scores.parquet output. INTERNAL = from nodes.xlsx. EXTERNAL = stubs created from transactions. Already partially implemented — verify and fix if missing.

### G-6.2: Report Scope Dropdown

Add dropdown to Page 3, Page 6, Page 14: "Scope: 🏦 Internal Only (default) | 🌐 External Only | 📋 All Entities"

All KPIs, tables, charts on those pages filter by selected scope.
Default: Internal Only (banks care about their own customers first).

### G-6.3: Page 7 External Party Banner

If selected customer is EXTERNAL:
- Show banner: "⚠️ External Party — This entity is not a customer of this institution. Investigation actions are limited."
- Disable: Flag, Generate PDF, Add Note buttons (grayed out with tooltip "Not available for external parties")
- Show: "Refer to counterparty institution for investigation"

### G-6.4: Dashboard External Subtitle

Page 3 KPIs: main count = internal only.
Below each KPI value: subtitle "(+ N external)" in smaller muted text.

### G-6.5: Network Graph External Styling

All network graphs (Page 7, 8, 13):
- External nodes: diamond shape, dashed border, lighter opacity (0.6)
- Internal nodes: circle shape, solid border, full opacity
- Seed nodes: hexagon shape

---

## G-7: BUSINESS RULES & NARRATIVES

### G-7.1: Business Rule Templates

New file: `graphaml/utils/business_rules.py`

20 named rules, each with:
- `rule_id`, `name`
- `condition`: boolean expression on features
- `severity`: HIGH / MEDIUM / LOW
- `why_flagged`: template with `{value}` substitution using actual customer values
- `what_it_means`: plain English
- `what_to_do`: recommended action

Rules:

| # | Name | Condition | Severity |
|---|------|-----------|----------|
| 1 | potential_structuring | structuring_pct > 0.40 | HIGH |
| 2 | off_hours_activity | off_hours_pct > 0.30 | MEDIUM |
| 3 | pass_through_relay | pass_through_ratio > 0.80 AND avg_dwell < 3 | HIGH |
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
| 15 | powerlaw_hub | is_powerlaw_tail AND betweenness > 90th_pct | MEDIUM |
| 16 | ring_plus_relay_combo | cycle_participation > 0 AND pass_through_ratio > 0.60 | HIGH |
| 17 | funnel_collector | funnel_score > 5 AND flow_type = MOSTLY_IN | HIGH |
| 18 | spray_distributor | spray_score > 5 AND flow_type = MOSTLY_OUT | HIGH |
| 19 | cross_state_high_volume | cross_state_pct > 0.70 AND volume > 75th_pct | MEDIUM |
| 20 | closed_account_activity | closed_account_activity = True | HIGH |

### G-7.2: Combo Rule Suppression

If rule 16 (ring_plus_relay) fires → suppress rules 3 and 4 individually.
General: combo rules suppress their component rules.

### G-7.3: Narrative Generation

Function: `get_narrative(cust_id)`:
- Collect all triggered rules for customer
- Sort by severity (HIGH first)
- For each triggered rule: render `why_flagged` template with actual values
- Concatenate into single investigation-ready text block

New columns in fusion_scores:
- `triggered_rules` (comma-separated rule IDs)
- `triggered_rules_count` (int)

---

## G-8: UI ENHANCEMENTS

### G-8.1: Page 3 Dashboard — New Elements

- KPI card: "N Overdue SLA" (red if any, green if zero)
- KPI card: "N Pending Approvals" (yellow badge)
- KPI cards: Alert dedup counters "12 NEW | 8 RETURNING | 3 ESCALATED | 5 RESOLVED"
- Card: "Top Risk Network" mini-map (G-5.6)
- Card: "Investigation Progress" funnel (G-5.11)
- All KPIs: internal count main, "(+ N external)" subtitle (G-6.4)

### G-8.2: Page 6 Suspect Discovery — New Elements

- New columns in AG Grid: `risk_probability`, `suspect_type_confidence`, `borda_count`, `alert_status`, `score_delta`, `sla_status`
- Alert status with color badges: 🟢NEW 🔵RETURNING 🟠ESCALATED ⚪RESOLVED
- New tab: "By Typology" — suspects grouped by suspect_type with counts (G-5.10 from Phase F)
- New tab: "Risk vs Activity" scatter (G-5.7)
- "Compare" button → radar modal (G-5.5)
- Scope dropdown (G-6.2)

### G-8.3: Page 7 Investigation — New Elements

- Header: "PROBABLE_MULE (78% confidence)" + "Higher risk than 94% of population"
- Banner: spike suppression warning if applied
- Banner: escalation warning if alert_status=ESCALATED with score delta
- Banner: external party warning if is_external (G-6.3)
- Display: "Consensus: Top 25% in N of 7 dimensions"
- New section: "Triggered Rules" — severity badges + personalized why_flagged text
- Button: "Generate Narrative" → copy-pasteable investigation text
- Button: "Compare with..." → radar modal
- New tabs: Transaction Timeline, Money Flow, Activity Pattern, Amount Profile (G-5.1-5.4)
- Enhanced network tab with right-click menus + side panel (G-5.8)

Tab order: Overview | Network Investigation | Transactions | Timeline | Money Flow | Activity Pattern | Amount Profile

### G-8.4: Page 9 Red Flags — New Elements

- New tab: "Chain Explorer" (G-5.9)
- New tab: "Relationship Matrix" (G-5.10)

### G-8.5: Page 12 Validation — New Elements

- New section: "Weight Calibration" — grouped bar chart: original vs entropy-adjusted weights + discriminativity scores per dimension
- New section: "Benford Analysis" — expected vs observed first-digit distribution chart
- New section: "Sensitivity Analysis" — weight perturbation results table (G-1.10)
- New section: "PSI Monitoring" — gauge showing current PSI vs previous run (G-1.11)
- New section: "Outcome Tracking" — Tier 1 true positive rate (G-4.2)
- New section: "QA Agreement" — latest QA sample agreement rate (G-1.12)
- Banner: "✅ Model Fully Approved" if all 4 MDD sign-offs complete

### G-8.6: Page 14 Reports — New Elements

- Scope dropdown: Internal / External / All (G-6.2)
- Button: "📦 Generate Exam Package" (G-1.9)

### G-8.7: Page 15 Admin — New Elements

- Section: "Pending Approvals" — Tier 1 clearance requests with approve/reject (G-1.3)
- Section: "Model Sign-Off" — 4 sign-off slots (G-1.8)
- Section: "Threshold Calibration" — 4 sliders + live preview table + "Apply & Re-Tier" button
- Section: "QA Spot Check" — generate sample + review grid (G-1.12)
- Section: "Data Management" — "Purge Customer" button ADMIN only (G-1.13)
- Section: "Audit Chain" — show last 50 entries + "Verify Integrity" button + status
- Run History: integrity status per run (🟢/🔴) + retention lock status (🔒/🔓) (G-1.2, G-1.5)
- Norm method dropdown (requires re-run confirmation)

---

## ALL NEW OUTPUT COLUMNS (fusion_scores.parquet)

| Column | Type | Source |
|--------|------|--------|
| `risk_probability` | float 0-1 | G-2.1 |
| `spike_suppressed` | bool | G-2.2 |
| `spike_reason` | str | G-2.2 |
| `binary_boost_applied` | float 0-0.30 | G-2.4 |
| `weight_D1_adjusted`...`D7` | float | G-2.5 |
| `borda_count` | int 0-7 | G-2.6 |
| `suspect_type_confidence` | int 40-100 | G-2.7 |
| `alert_status` | str | G-4.1 |
| `score_delta` | float | G-4.1 |
| `triggered_rules` | str | G-7.1 |
| `triggered_rules_count` | int | G-7.1 |
| `sla_status` | str ON_TIME/APPROACHING/OVERDUE | G-1.6 |
| `clearance_status` | str | G-1.3 |

## ALL NEW FEATURES (feature_matrix)

| Feature | Module | Dimension |
|---------|--------|-----------|
| `benford_chi_squared` | behavioral.py | D2 |
| `benford_zscore` | behavioral.py | D2 |
| `is_powerlaw_tail` | structural.py | D3 |

Total: 84 → 87

## ALL NEW CONFIG PARAMETERS

| Parameter | Default |
|-----------|---------|
| `fusion_hybrid_ratio` | 0.60 |
| `binary_boost_per_flag` | 0.05 |
| `binary_boost_cap` | 0.30 |
| `spike_suppression_factor` | 0.88 |
| `spike_max_dim_threshold` | 70 |
| `spike_min_agreeing_dims` | 2 |
| `spike_std_threshold` | 22 |
| `borda_boost_per_dim` | 0.015 |
| `borda_cap` | 5 |
| `entropy_discriminativity_floor` | 0.15 |
| `entropy_weight_shrink_factor` | 0.30 |
| `norm_method` | rank |
| `shared_attribute_max_pairs` | 50 |
| `sla_tier1_days` | 7 |
| `sla_tier2_days` | 14 |
| `sla_tier3_days` | 30 |
| `retention_days` | 1825 |

## ALL NEW FILES

| File | Purpose |
|------|---------|
| `graphaml/compliance/audit_chain.py` | Hash-chained audit trail |
| `graphaml/utils/business_rules.py` | 20 rule templates + combo suppression + narrative generation |
| `governance/audit_chain.jsonl` | Append-only audit log (auto-created) |
| `governance/outcomes.jsonl` | Disposition tracking (auto-created) |
| `governance/qa_samples.jsonl` | QA spot-check results (auto-created) |

---

## TESTS

| # | Test | Section |
|---|------|---------|
| 1 | Audit chain: append 3 entries → verify_chain returns True | G-1.1 |
| 2 | Audit chain: tamper entry 2 → verify_chain returns False, broken_at=2 | G-1.1 |
| 3 | File integrity: modify parquet → verify_run_integrity detects mismatch | G-1.2 |
| 4 | Dual control: analyst clears Tier 1 → status = PENDING, not CLEARED | G-1.3 |
| 5 | Dual control: manager approves → status = CLEARED, audit logged | G-1.3 |
| 6 | Dual control: Tier 2 clearance → no approval needed, direct CLEARED | G-1.3 |
| 7 | EXAMINER: PII masked in all views | G-1.4 |
| 8 | EXAMINER: export buttons disabled | G-1.4 |
| 9 | Retention: run within 5 years → delete disabled | G-1.5 |
| 10 | Auto-escalation: Tier 1 unflagged 8 days → AUTO_ESCALATED | G-1.6 |
| 11 | MDD sync: config thresholds differ → warning logged | G-1.7 |
| 12 | PSI: identical distributions → PSI ≈ 0 (green) | G-1.11 |
| 13 | PSI: shifted distribution → PSI > 0.25 (red) | G-1.11 |
| 14 | Risk probability: min=0, max=1, monotonic with score | G-2.1 |
| 15 | Spike fires: 1 dim=90, others<30 → 0.88× applied | G-2.2 |
| 16 | Spike skips: 3 dims>50 → no penalty | G-2.2 |
| 17 | Hybrid: D6=95 others=10 → higher than pure weighted sum | G-2.3 |
| 18 | Binary boost: 6 flags=0.30, 10 flags=0.30 (capped) | G-2.4 |
| 19 | Entropy: uniform dim → weight<0.05 | G-2.5 |
| 20 | Entropy: bimodal dim → weight≥original | G-2.5 |
| 21 | Entropy: all weights sum=1.00 | G-2.5 |
| 22 | Borda: top 25% in 7 dims → count=7, mult=1.075 | G-2.6 |
| 23 | Confidence: large gap → high %, small gap → low % | G-2.7 |
| 24 | Benford: clustered amounts → high chi_sq | G-3.1 |
| 25 | Benford: <10 tx → features=0 | G-3.1 |
| 26 | Power-law: top 1% degree → True | G-3.2 |
| 27 | Shared attr cap: 100-node IP → suppressed | G-3.3 |
| 28 | Alert dedup: new node → NEW | G-4.1 |
| 29 | Alert dedup: T2→T4 → RESOLVED | G-4.1 |
| 30 | Alert dedup: T4→T1 → ESCALATED | G-4.1 |
| 31 | Rule 1 fires: 55% structuring → triggered with correct values | G-7.1 |
| 32 | Combo: rule 16 fires → rules 3,4 suppressed | G-7.2 |
| 33 | Narrative: 3 rules triggered → 3 paragraphs, severity sorted | G-7.3 |
| 34 | Timeline renders: dot count = transaction count for customer | G-5.1 |
| 35 | Sankey: source + destination amounts balance | G-5.2 |
| 36 | Canvas: right-click menu appears with 11 options on node | G-5.8 |
| 37 | Canvas: "Expand Neighborhood" adds correct neighbors | G-5.8 |
| 38 | External: scope dropdown filters KPIs correctly | G-6.2 |
| 39 | External: Page 7 banner shows for external party | G-6.3 |
| 40 | Threshold preview: T1 65→60 → correct count delta | G-8.7 |

---

## SUCCESS CRITERIA

```
AUDIT CONTROLS (G-1):
☐ Audit chain creates, appends, verifies correctly
☐ Tampered chain detected on verify
☐ File integrity hashes computed and verified per run
☐ Dual control blocks analyst from clearing Tier 1 directly
☐ EXAMINER sees masked PII, cannot export
☐ Retention lock prevents deletion within 5 years
☐ Auto-escalation fires for overdue Tier 1
☐ MDD auto-syncs thresholds from config
☐ Sign-off workflow records 4 approvals
☐ Exam package ZIP generated with all required files
☐ Sensitivity analysis shows rank stability per dimension
☐ PSI computed and displayed correctly

SCORING ENGINE (G-2):
☐ All 8 scoring enhancements functional
☐ Entropy weights auto-adjust per dataset
☐ Spike suppression prevents false Tier 1 from single dimension
☐ Hybrid fusion preserves strong single signals
☐ Borda rewards broad consensus
☐ Score distribution remains reasonable

FEATURES (G-3):
☐ Benford features computed for all nodes (skipped if <10 tx)
☐ Power-law tail flagged for top 1%
☐ Shared attr cap suppresses >50-node attributes

PIPELINE (G-4):
☐ Alert dedup accurate across runs
☐ Outcome tracking records dispositions

VISUAL CHARTS (G-5):
☐ All 12 charts render with sample data
☐ Canvas right-click menus work for nodes and edges
☐ Side panel opens with correct data
☐ Cross-chart linking works (date brush filters others)
☐ Performance guardrails activate at thresholds

EXTERNAL HANDLING (G-6):
☐ Scope dropdown filters all pages correctly
☐ External party banner disables actions on Page 7
☐ Network graphs show correct node shapes

BUSINESS RULES (G-7):
☐ 20 rules evaluate correctly
☐ Combo suppression works
☐ Narrative generates with actual values

UI (G-8):
☐ All new Page 3, 6, 7, 9, 12, 14, 15 sections render
☐ All new AG Grid columns display correctly
☐ All 40 tests PASS
```