Sampling Design Decisions — Full Summary
Sources found:

sampling.txt — detailed node composition tables + 3-wave production strategy
AML_STRATEGY_EXPERT_RESPONSES.md — the 5 combinations rated A–E
AML_SAMPLE_SIZE_AND_DATA_DESIGN.md — 22-feature wave design + temporal alignment rules
The 5 Combinations Evaluated
Combination Description Rating
A 3K SAR + 3K random non-SAR + 1K 1-hop = 7K 3/10 — Baseline only. Poisoned negatives, too shallow. DO NOT USE.
B 3K SAR + 3K B3 negatives + 2K 1-hop + 2K 2-hop = 10K 7/10 — Better class boundary, no community/behavioral coverage
C 3K SAR + 3K B3 negatives + 2K community + 2K 2-hop + 2K 1-hop = 12K 9/10 — Full network neighbourhood including community structure. Recommended Wave 1.
D 3K SAR + 3K B3 + 5K PPR-top from 10M + 2K external = 13K 8/10 — PPR handles multi-hop auto; best for distant structurally similar accounts
E 3K SAR + 3K B3 + 5K high-criminal-ratio external counterparty customers + 2K behavioral = 13K 9.5/10 — Catches Type E (shared criminal infra, zero direct SAR link)
COMBINATION B — Detailed Node Composition ⭐⭐⭐⭐
COMBINATION C — Production-Grade 3-Stage Strategy ⭐⭐⭐⭐⭐ (RECOMMENDED)
This is what we decided to deploy in production. Three stages:

Stage 1 — Wave 1: Foundation Run (20,000 nodes)
Goal: Calibrate model; catch network-connected criminals; define criminal behaviour centroid.

Type Description is_sar Count
A All November SAR 1 3,000
B1 Cleared HIGH anomaly (structuring ≥30%, Benford violation, off-hours ≥25%) 0 1,000
B2 Cleared MEDIUM anomaly 0 1,000
B3 Cleared LOW anomaly (<$500, local, domestic, no structuring) 0 500
B4 Random from 47K (removes selection bias) 0 500
C 1-hop SAR neighbors (top by volume) NULL 1,500
D 2-hop neighbors (≥$5K or ≥3 tx with 1-hop) NULL 2,500
E Bank customers → HIGH-RISK external accounts (ratio ≥30%) NULL 2,000
F Peer + Geo match (same industry/state as SAR cluster, never alerted) NULL 3,000
G Top PPR-ranked from 10M not in any other category NULL 3,000
H Clean boundary (accounts >5yr, low vol, domestic) NULL 2,000
TOTAL 20,000
Transaction window: Oct + Nov + Dec (30-day each side for temporal context)

Stage 2 — Wave 2: Propagation Run (20,000 nodes)
Goal: Follow money forward from Wave 1 catches; expand into 10M population.

Seeds become 3,400–4,000 (original 3K SAR + Wave 1 Tier 1 confirmed + Tier 2 ADD_SEED)
New 1-hop/2-hop pulled from 10M counterparties of Wave 1 Tier 1+2
Geo expansion into new regions not covered in Wave 1
Stage 3 — Wave 3: Counterparty Inversion Run (20,000 nodes)
Goal: Catch criminals who share criminal banking infrastructure with SAR subjects but have ZERO direct transaction link.

Type E becomes primary suspect pool (shared external account = criminal_ratio ≥50%)
Semi-supervised + parallel unsupervised for Type G
The Parallel Unsupervised Pass — Critical Decision
We decided to run both modes simultaneously:

Mode Mechanism Catches
Semi-supervised D1–D7 active, SAR seeds anchoring Types C, D, E, F (network-connected)
Unsupervised All labels → NULL, D1 disabled, D5 uses anomaly cluster centroid Type G (behaviorally anomalous, network-invisible)
Intersection Tier 1+2 in BOTH modes 🔴 File SAR immediately — two independent signals
Customer Type Coverage Summary
Type Description Wave 1 Wave 2 Wave 3
A — SAR Seeds Seeds Seeds Seeds
B1 — Hard Negatives High anomaly cleared Lookback flags Confirmed —
C — 1-Hop Direct SAR partners ✅✅✅ Main catch ✅✅ New 1-hops ✅
D — 2-Hop Layering intermediaries ✅✅ Filtered 2K ✅✅✅ Main expansion ✅
E — Shared External Shared criminal infra ✅✅ 2K intro ✅✅ Expanded ✅✅✅ Primary
F — Community Louvain co-member, no direct link ✅ First sight ✅✅ Deeper ✅ Carried
G — Behavioral twin No network link, behaviour match ⚠️ Partial ✅ PPR grows ✅✅ PPR+D2
H — True clean Genuine negatives Correctly low Correctly low Correctly low
Expected Output (All 3 Waves)
Wave New Tier 1 New Tier 2 Primary Catch
Wave 1 50–200 200–600 C, D, partial E/F
Wave 2 80–300 300–800 D (deeper), E, F
Wave 3 50–200 200–500 E (primary), G
Total 180–700 700–1,900 All Types C–G
vs. current 7K approach: 0 new suspects outside the 7K investigated pool.

Final Triage Rules
Signal Action Timeline
Tier 1 in ≥2 waves Immediate SAR referral Same week
Tier 1 in 1 wave only Investigate ≤30 days
Tier 2 in ≥2 waves Enhanced monitoring ≤60 days
Unsupervised-only Tier 1 Type G novel pattern investigation ≤60 days
B1/B2 scoring ≥ Tier 2 in any wave SAR lookback review FinCEN obligation
This is everything we agreed on. The core decision: Combination C + E as a 3-wave semi-supervised + parallel unsupervised strategy, designed to score all 10M customers across waves rather than the original 7K investigated pool.

What is B3?
B3 is one tier within your 47K investigated-cleared pool (customers who were investigated but no SAR was filed). We stratified that pool into three tiers based on behavioral anomaly score:

Tier Name Behavioral Anomaly Approx Count from 47K Trust as Negative
B1 Hard Negative HIGH — structuring ≥30%, Benford violation, off-hours ≥25% ~4,700 (10%) ⚠️ Very low — closest to real criminals
B2 Medium Negative MEDIUM — moderate flags, insufficient evidence to file ~14,100 (30%) Medium — uncertain
B3 Soft Negative LOW — avg txn <$500, local, domestic, no structuring, no flags ~28,200 (60%) ✅ High — most trustworthy clean label
So "3K B3 negatives" = 3,000 customers drawn from the bottom 60% of the 47K cleared pool — the ones who look the most genuinely clean based on behavioral scoring. These are the only cleared customers safe to label is_sar = 0 in training.

B1 and B2 are excluded from training because they may be real criminals who evaded SAR filing — using them as negatives would poison the model.

Exact File Locations
All three files sit in the workspace root:

Document Full Path
sampling.txt sampling.txt
AML_STRATEGY_EXPERT_RESPONSES.md AML_STRATEGY_EXPERT_RESPONSES.md
AML_SAMPLE_SIZE_AND_DATA_DESIGN.md AML_SAMPLE_SIZE_AND_DATA_DESIGN.md
Not inside any version folder — they are at the root aml_graph\ level alongside the other .md planning docs.

COMBINATION B — Stratified Negatives + Counterparty Explosion ⭐⭐⭐⭐

Nodes:
Positives (8=1): 3,000 SAR (confirmed)
Hard Negatives (is_sar=0): - 1,000 investigated-cleared with HIGH behavioral anomaly scores
(Benford violations, structuring band hits, off-hours peaks) ← SMARTEST NEGATIVES - 500 investigated-cleared with MEDIUM behavioral anomaly - 500 investigated-cleared with LOW anomaly (genuinely clean-looking)
Soft Negatives (is_sar=NULL): - 1,000 truly random from 10M general population (never alerted) - 500 from specific peer groups matching SAR typology (e.g., if 60% SARs are small businesses
→ random sample 500 small businesses from 10M)
Unlabeled In-Graph: - 1,000 1-hop SAR neighbors (existing) - 2,000 2-hop SAR neighbors (filtered: >$10K with SAR network OR >5 transactions) - ALL unique external counterparty stubs from SAR transactions (auto Phase 0)

Total: ~6,000 labeled + 3,000-5,000 unlabeled + N external stubs = 10,000-12,000 nodes

Transactions: All transactions for ALL nodes above + all edges to external stubs

Rating: 7/10 — Better class boundary, richer graph structure, external counterparties now active.

COMBINATION C — Community-Seeded Expansion ⭐⭐⭐⭐⭐ (RECOMMENDED for catching unknowns in 10M)
This is the approach I would deploy in production. It has 3 stages.

Nodes:
3,000 SAR (is_sar=1)
1,500 non-SAR investigated (stratified as in B)
1,500 random general population (never alerted)
ALL external counterparties auto-stubbed

Transactions:
Full November transactions for all above
IMPORTANT: Also include Oct + Dec (30-day window each side) for temporal context

Here is the complete document with every table and structured section properly formatted using correct markdown column-alignment syntax.markdownguide+1

GRAPHAML — COMPLETE INPUT STRATEGY & PROCESS FLOW
Ground Truth: Your Full Customer Universe
Type Label Description is_sar Estimated Count Investigation Status
A SAR Filed Confirmed suspicious — your SEEDS 1 3,000 Investigated → SAR filed
B1 Cleared — High Anomaly Structuring ≥30%, Benford violation, off-hours ≥25% 0 ~15,000 Investigated → cleared
B2 Cleared — Medium Anomaly Moderate behavioral flags; insufficient evidence 0 ~17,000 Investigated → cleared
B3 Cleared — Low Anomaly Low volume, domestic, no structuring flags 0 ~15,000 Investigated → cleared
C 1-Hop SAR Neighbors Direct transaction counterparties of SAR customers NULL ~20,000–80,000 Never investigated
D 2-Hop SAR Neighbors Transacted with a Type C customer — potential layering intermediaries NULL ~100,000–500,000 Never investigated
E Shared External Counterparty Sends money to the same offshore/external account as SAR — shares criminal plumbing but not a direct SAR link NULL ~5,000–50,000 Never investigated
F Community Co-Member In the same Louvain cluster as SAR group — no direct transaction with SAR but structurally co-located NULL ~10,000–100,000 Never investigated
G Behavioral Match (no network link) Structuring/Benford/off-hours patterns matching SAR; zero network connection to any SAR customer — hardest to catch NULL Unknown Never investigated
H Clean General Population No behavioral anomaly, no network link to SAR — true negative boundary NULL ~9.9M+ Never investigated

Critical Truth About Negatives
Treatment Population is_sar Value Trust Level Why
❌ Wrong All 47K cleared → flat is_sar=0 0 — "Cleared" = insufficient evidence, NOT confirmed innocent; 5–15% may be real criminals
✅ B1 — Hard Negative HIGH behavioral anomaly (structuring, Benford, off-hours) 0 ⚠️ Use cautiously Closest to criminals — model may learn a blurry boundary
✅ B2 — Medium Negative MEDIUM behavioral anomaly 0 Medium Reasonable boundary signal
✅ B3 — Soft Negative LOW anomaly (avg txn <$500, local, domestic) 0 High Most trustworthy clean label
🔄 Lookback Flag B1/B2 that score Tier 1–2 in any GraphAML wave 0 → review — FinCEN lookback obligation — these may need SAR retroactively

Algorithm Selection — Decision Matrix
Criteria Supervised Semi-Supervised Unsupervised
You have 3,000 SAR seeds ✅ Great ✅ Great ❌ Ignores them
47K cleared are contaminated negatives ❌ Breaks the model ✅ Handles gracefully ✅ No impact
Score 10M unknowns (NULL) ❌ Must be labeled ✅ Designed for this ✅ Works
Network propagation from seeds ❌ Feature only ✅ Core mechanism (D1, D4, PPR) ❌ No seed direction
Finds Type G (no network link) ❌ Network-dependent ✅ D2 + D5 catch them ✅ Primary strength
Model risk defensibility (SR 11-7) ⚠️ Requires clean labels ✅ Explainable seed distance ✅ But no threshold
Your scenario fit 4/10 9/10 6/10 as complement
Practical rule: Run both semi-supervised AND unsupervised in parallel.
Semi-supervised → catches Types C, D, E, F (network-connected).
Unsupervised → catches Type G (behaviorally similar, network-isolated).
Intersection of both = highest-confidence SAR referrals.

Pre-Wave Preprocessing
(Run once before any GraphAML wave — plain Python, ~2 hours)
Step Name Input Action Output Est. Time
1 External Counterparty Risk Scoring Nov transaction file for all 3,000 SAR customers Compute criminal_sender_count, total_sender_count, criminal_ratio per external account HIGH-RISK list (ratio ≥ 0.30); MED-RISK list (ratio 0.10–0.29) ~30 min
2 Type E Candidate Extraction External risk list + 10M Nov transaction file Find all bank customers who sent to HIGH/MED-RISK external accounts; rank by criminal_ratio × amount Type E list: top 5,000–7,000 customers ~30 min
3 Type C + D Candidate Extraction (BFS) 3,000 SAR IDs + Nov 10M transaction file Multi-source BFS; Hop 1 = Type C; Hop 2 = Type D; rank by volume × count Type C: 3,000–5,000 customers; Type D: 5,000–8,000 customers ~1 hr
4 Type G Candidate — PPR Approximation 3,000 SAR seeds + Nov 10M transaction file Build sparse adjacency (scipy.sparse); run Personalized PageRank; exclude Types C, D, E and 50K investigated Type G: top 5,000 by PPR score ~1 hr
Pre-Wave Output Summary
List Customer Type Size Selection Criterion
Type C list 1-Hop SAR neighbors 3,000–5,000 Ranked by volume × transaction count with SAR
Type D list 2-Hop SAR neighbors 5,000–8,000 Ranked by bridge count + volume
Type E list Shared external counterparty 5,000–7,000 Ranked by criminal_ratio × amount
Type G list PPR-ranked orphan proximity 5,000 Highest PPR score from 10M, not in C/D/E/47K
Type B1/B2/B3 Cleared — stratified From 47K pool Split by behavioral anomaly score

Wave 1 — Foundation Run (20,000 Nodes)
Goal: Calibrate the model; catch network-connected criminals; define the criminal behavior centroid.
Algorithm: Semi-supervised (D1–D7 all active). # Customer Type Description is_sar Count Selection Method
A Confirmed SAR All November SAR filings 1 3,000 All SAR customers, Nov
B1 Hard Negative Cleared with HIGH behavioral anomaly: structuring ≥30%, Benford violation, off-hours ≥25% 0 1,000 Top 1K by anomaly score from 47K pool
B2 Medium Negative Cleared with MEDIUM behavioral anomaly 0 1,000 Mid-tier from 47K pool
B3 Soft Negative Cleared with LOW anomaly: avg txn <$500, local, domestic, no structuring 0 500 Bottom-tier from 47K pool
B4 Random Negative Random sample from 47K regardless of behavior — removes selection bias 0 500 Random 500 from 47K pool
C 1-Hop Neighbors Direct tx counterparties of SAR customers (Nov) NULL 1,500 Pre-wave Step 3, top by volume
D 2-Hop Neighbors Indirect counterparties — txn with 1-hop ≥$5K or ≥3 transactions NULL 2,500 Pre-wave Step 3, top by bridge count
E Shared External Counterparty Bank customers who sent to HIGH-RISK external accounts (ratio ≥30%) NULL 2,000 Pre-wave Step 2, top by ratio × volume
F Peer + Geo Match Same industry/peer group + same state as SAR cluster, never Mantas-alerted NULL 3,000 Pull from 10M: match SAR demographic profile
G PPR-Ranked Top PPR-ranked from 10M, NOT in any category above, never alerted NULL 3,000 Pre-wave Step 4
H Clean Boundary Random general population: accounts >5 years, low volume, domestic only NULL 2,000 Random from 10M, filtered for cleanliness
TOTAL 20,000
Wave 1 — Config Settings
Parameter Recommended Value Rationale
hop_depth 2 Critical — captures Type D (missed at hop=1); minimum for layering detection
lookback_months 3 Oct + Nov + Dec — velocity, dormancy, and acceleration features
consensus_runs 20 More Louvain runs → stable communities with mixed population
Wave 1 — Scoring Dimension Weights
Dimension Weight vs. Default Rationale
D1 — Proximity to SAR 0.12 ↓ Slightly lower 2-hop dilutes seed purity; don't over-weight distance
D2 — Red Flags (Benford, structuring) 0.28 ↑ Keep high Core signal; catches Type G; most reliable discriminator
D3 — Centrality 0.13 ↑ Raised Hub detection matters for large mixed graph
D4 — Community 0.12 ↑ Raised Community signal strong when SAR cluster is dense
D5 — Similarity to SAR Centroid 0.13 ↑ Raised Cosine to SAR centroid catches Type G (no network link)
D6 — Identity (device/IP/address) 0.12 Maintain Shared infrastructure for mule detection
D7 — Recency 0.10 Maintain Temporal recency of SAR-proximate behavior

Wave 2 — Propagation Run (20,000 Nodes)
Goal: Follow the money forward from Wave 1 catches; expand into the 10M population.
Algorithm: Semi-supervised with enriched seed set (3,400–4,000 seeds vs. 3,000 in Wave 1).
Before building Wave 2: export Wave 1 Tier 1+2 suspects → pull their Nov counterparties from the full 10M database.

# Customer Type Description is_sar Count Source

A Original SAR Same 3K SAR seeds carried forward 1 3,000 Wave 1 input
A2 Wave 1 Tier 1 (confirmed) Analyst-reviewed and SAR-filed after Wave 1 1 100–300 Wave 1 output, analyst confirmed
A3 Wave 1 Tier 2 (ADD_SEED) Strong suspicion — carried as ADD_SEED in seed override NULL 300–700 Wave 1 output, seed override
B Stable Negatives Best-performing negatives from Wave 1 (consistent low scorers) 0 2,000 Wave 1 stable low-scorers
C-new New 1-Hop Direct tx counterparties of Wave 1 Tier 1+2 suspects, pulled from 10M NULL 3,000 New — pulled from 10M
D-new New 2-Hop Counterparties of C-new, filtered by volume NULL 3,000 New — pulled from 10M
E-new Expanded External Bank customers who sent to external accounts used by BOTH original SAR AND Wave 1 Tier 1 NULL 2,000 Recomputed criminal_ratio
F-new Geo Expansion Different geographic regions not covered in Wave 1 (e.g., FL, TX if W1 was NJ/NY-heavy) NULL 2,500 10M geo-stratified
H-new Fresh Boundary New random clean population (different random seed) NULL 2,000 10M random
Remainder PPR Fill Top PPR from remaining 10M not seen in Wave 1 or Wave 2 yet NULL ~1,200 New PPR ranking
TOTAL ~20,000

Wave 3 — Counterparty Inversion Run (20,000 Nodes)
Goal: Find criminals who share the same criminal banking infrastructure (external accounts) as SAR subjects — but have ZERO direct transaction link to any SAR customer.
Algorithm: Semi-supervised + parallel unsupervised. Type E is now the PRIMARY suspect pool.
Before building Wave 3: union all Tier 1+2 from Waves 1+2 with original 3K SAR → recompute criminal_ratio → pull all bank customers who sent to HIGH/MED-RISK accounts not yet seen in Waves 1 or 2.

# Customer Type Description is_sar Count Notes

A SAR Seeds Original 3K — always retained for centroid anchoring and calibration 1 3,000 Required in every wave
E-high Ext. Counterparty Tier 1 Bank customers → HIGH-RISK external accounts (ratio ≥50%), not seen in W1/W2 NULL 5,000 Primary suspects; add criminal_ratio as custom feature
E-med Ext. Counterparty Tier 2 Bank customers → MED-RISK external accounts (30–50%), not seen in W1/W2 NULL 5,000 Secondary suspects
B Negatives Best negatives across W1+W2 (consistent low-scorers) 0 2,000 Boundary anchoring
G-new PPR Fresh Highest PPR from 10M not yet seen in any wave NULL 3,000 Ensures coverage of isolated criminals
H Fresh Boundary New random clean population NULL 2,000 Boundary reinforcement
TOTAL 20,000

Customer Type Coverage Matrix — All 3 Waves
Customer Type Current 7K Input Wave 1 Wave 2 Wave 3 Primary GraphAML Signals
A — SAR Seeds — — — D1 = 0 (they are seeds)
B1 — Hard Negatives Some included Confirmed + lookback-flagged Confirmed — High scorers → SAR lookback review
C — 1-Hop Partial ✅✅✅ Main catch ✅✅ New 1-hops ✅ From W1+W2 D1 proximity; D3 centrality; D4 community
D — 2-Hop Partial ✅✅ Filtered 2K ✅✅✅ Main expansion ✅ From W1+W2 D1 (2-hop distance); D4 community; D3 betweenness (bridge role)
E — Shared Ext. Counterparty ❌ Missed completely ✅✅ 2K intro ✅✅ Expanded via recomputed ratio ✅✅✅ Primary catch D2 red flags + criminal_ratio; D5 similarity; D6 identity
F — Community Co-Member ❌ Missed completely ✅ In graph via BFS ✅✅ Deeper graph ✅ Carried forward D4 community (Louvain co-member); D3 centrality (within-cluster hub)
G — Behavioral Match (no link) ❌ Missed completely ⚠️ Partial (D5 weak) ✅ PPR picks up more ✅✅ PPR + D2 D2 red flags (Benford, structuring); D5 cosine; unsupervised complement required
H — True Clean Some included ─ Correctly low ─ Correctly low ─ Correctly low Correct: score stays low throughout all waves
Coverage Summary by Wave
Wave Types Primarily Caught Key New Population Added
Wave 1 C (main), D (filtered), E (intro), F (first sight) 14K from C/D/E/F/G/H pools
Wave 2 D (deeper), E (expanded), F, G (PPR grows) New counterparties of W1 Tier 1+2 from 10M
Wave 3 E (primary), G, F (carried) External counterparty inversion: customers sharing criminal infra

Parallel Unsupervised Pass — Type G Detection
Mode Configuration Output Confidence Assignment
Semi-supervised D1–D7 active; SAR seeds anchoring Tier 1+2 with seed-proximity scoring Network-connected suspects
Unsupervised All labels → NULL; D1 disabled; D5 uses anomalous cluster centroid; D2+D3+D4 drive scoring Anomaly rank 0–100 per node Behaviorally anomalous suspects
Intersection Tier 1+2 in BOTH modes Highest confidence 🔴 File SAR immediately — two independent signals
Semi only Tier 1+2 in semi-supervised only Network connection confirmed 🟡 Investigate within 30 days
Unsupervised only Tier 1+2 in unsupervised only No SAR link; behaviorally anomalous 🟠 Type G referral — Mantas-blind customer

Expected Output — All 3 Waves
Wave New Tier 1 Suspects New Tier 2 Suspects Investigation Effort Primary Catch Type
Wave 1 50–200 200–600 1–2 weeks (10-person team) C, D, partial E/F
Wave 2 80–300 300–800 2–3 weeks D (deeper), E, F
Wave 3 50–200 200–500 1–2 weeks E (primary), G
Total 180–700 700–1,900 ~5 weeks All types C–G
vs. current 7K approach: 0 new suspects outside the 7K investigated pool.

Final Triage Rules
Signal Classification Action Timeline
Tier 1 in ≥2 waves Highest Priority Immediate SAR referral Same week
Tier 1 in 1 wave only High Priority Investigate ≤30 days
Tier 2 in ≥2 waves Medium Priority Enhanced monitoring + investigation ≤60 days
Tier 2 in 1 wave only Low-Medium Standard enhanced monitoring ≤90 days
Unsupervised-only Tier 1 Type G referral Novel pattern investigation ≤60 days
B1/B2 scoring ≥ Tier 2 in any wave Lookback Candidate SAR lookback review FinCEN obligation

5-Step Practical Process Summary
Step Name Where Key Action Output
Step Name Where Key Action Output
0 Preprocessing Outside GraphAML Score 47K → B1/B2/B3; BFS → C/D lists; counterparty ratio → E list; PPR → G list Candidate lists for all 5 types
1 Wave 1 — Foundation GraphAML pipeline 20K node file (3K SAR + 3K cleared + 14K from C/D/E/F/G/H); 3-month tx window; semi-supervised + unsupervised parallel Tier 1+2 suspects; B1/B2 lookback flags
2 Analyst Review Investigation team Tier 1 → investigate → confirm → is_sar=1 for Wave 2; Tier 2 → ADD_SEED; B1/B2 hits → SAR lookback Enriched seed set (3,400–4,000 seeds)
3 Wave 2 — Propagation GraphAML pipeline 3K SAR + analyst-confirmed + W1 Tier 2 ADD_SEED + new 10M counterparties + geo expansion + fresh boundary Second-ring catches: deeper D, expanded E, F, G
4 Wave 3 — Inversion GraphAML pipeline 3K SAR + 10K Type E (external counterparty inversion) + fresh PPR + boundary negatives; criminal_ratio as custom feature Type E primary catch + G; novel criminals with zero direct SAR link
5 Final Triage Investigation team Apply triage rules above; cross-wave comparison; ≥2-wave Tier 1 = highest SAR priority 400–1,200 new SAR referrals from 10M pool

From <https://www.perplexity.ai/search/make-proper-format-stage-1-see-ii6XXruyTmaxQiIazjAreQ?sm=d>
