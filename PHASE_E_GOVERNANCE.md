# PHASE E: Governance Layer — Configuration Tracking & Model Documentation

## ROLE & CONSTRAINTS
You are a PhD in Data Science, Statistics, and Graph Theory — Head of AML Data Science at a major North American bank. Build **GraphAML** — an air-gapped, production-grade AML graph network analysis platform.

**Hard constraints:** Bank PII secure, Windows 11 local only (16GB RAM), Anaconda Python 3.11, pip/conda install only, zero external connections/telemetry/cloud/API keys, all free open-source libraries, every line annotated, fully parameterized via config.yaml, graceful degradation (never crash — skip + warn + continue), modular/pluggable architecture.

**Regulatory context:** Federal Reserve SR 11-7 Section II.D: "All aspects of model development, implementation, and use must be documented." OCC 2011-12 requires "comprehensive model documentation" and "change management procedures."

Phases A-D complete. This phase implements configuration change tracking and enhanced Model Documentation Database (MDD) for regulatory transparency.

---

## WHAT TO BUILD

```
graphaml/compliance/governance/
├── __init__.py
├── config_changelog.jsonl   # Append-only config change log (DATA file)
└── mdd.json                  # Enhanced Model Documentation Database (DATA file)
```

Update: `graphaml/compliance/governance_manager.py` (NEW — Python logic), `dash_app/layouts/page_15_admin.py` (add Governance tab), `cli.py` (add mdd-export command)

**Key insight:** Phase E stores governance **data** in JSON/JSONL formats. The Python logic lives in a separate `governance_manager.py` module to read/write/validate these files.

---

## E-1: CONFIGURATION CHANGE LOG (`config_changelog.jsonl`)

### Why
SR 11-7 Section II.D.4: "Documentation must describe any changes to the model since the last validation." When a threshold or weight changes, the examiner must know:
- What changed (parameter name and old→new value)
- Who changed it (username and role)
- When it changed (timestamp)
- Why it changed (business justification)

Traditional approach: document changes in Word/PDF after-the-fact. Phase E approach: auto-capture every `config.yaml` modification as append-only log.

### What
**File format:** JSONL (JSON Lines) — one JSON object per line, append-only, never edited
**Storage location:** `graphaml/compliance/governance/config_changelog.jsonl`
**Schema per entry:**
```json
{
    "seq": 42,
    "timestamp": "2026-07-27T14:23:45.678Z",
    "user": "alice@bank.com",
    "role": "MANAGER",
    "action": "CONFIG_CHANGE",
    "section": "scoring.thresholds",
    "parameter": "tier1_threshold",
    "old_value": 85.0,
    "new_value": 87.0,
    "justification": "Validation identified 3% false positive rate at 85.0; increasing to 87.0 reduces FPR to 1.2% per validation report v2.3",
    "run_id_applied": "run_20260727_001",
    "mdd_version": "8.2.0",
    "config_hash": "a4f3b2c9d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2"
}
```

**Key fields:**
- `seq`: monotonic sequence number (starts at 1)
- `section`: dot-path in config.yaml (e.g., `scoring.weights`, `thresholds`, `pipeline.batch_size`)
- `config_hash`: SHA-256 of the entire `config.yaml` after the change (for snapshot integrity)
- `run_id_applied`: first run that uses the new config (links change → production impact)
- `justification`: free-text business reason (REQUIRED for threshold/weight changes, optional for batch_size)

### How
**At config change time** (Page 15 Admin → Threshold Tuning):
```python
from graphaml.compliance.governance_manager import GovernanceManager

gov = GovernanceManager(base_dir=Path("graphaml/compliance/governance"))
gov.log_config_change(
    user="alice@bank.com",
    role="MANAGER",
    section="scoring.thresholds",
    parameter="tier1_threshold",
    old_value=85.0,
    new_value=87.0,
    justification="Validation report v2.3 recommendation",
    config_hash=compute_sha256("config.yaml")
)
```

**On CLI config edit:**
```bash
python -m graphaml config set scoring.thresholds.tier1_threshold 87.0 --justification "Validation report v2.3"
```
Internally calls `governance_manager.log_config_change(...)`, then writes to `config.yaml`, then appends to audit chain.

### Where Used
- Page 15 Admin → Governance tab → "Config Change History" table (AG Grid with search/filter by section/user/date)
- Exam package (`exam_package.py`) includes last 50 config changes in `01_mdd/config_changelog.txt`
- MDD PDF generation pulls justifications for "Model Changes Since Last Validation" section

---

## E-2: MODEL DOCUMENTATION DATABASE (`mdd.json`)

### Why
SR 11-7 Section II.D requires "comprehensive documentation covering the theory, assumptions, mathematical framework, data sources, performance measures, and known limitations" of the model. Traditional MDDs are 100-page PDFs written manually. Phase E approach: structured JSON schema that auto-generates the PDF via Jinja2 template.

### What
**File format:** JSON (single file, versioned, replaces on update — NOT append-only like config_changelog)
**Storage location:** `graphaml/compliance/governance/mdd.json`
**Schema (abbreviated):**
```json
{
    "mdd_version": "8.2.0",
    "model_name": "GraphAML — AML Graph Network Analysis Platform",
    "model_tier": 2,
    "model_type": "Quantitative — Unsupervised Graph Analytics + Supervised Machine Learning Fusion",
    "business_purpose": "Identify high-risk customers for enhanced due diligence via multi-dimensional graph feature engineering",
    "regulatory_scope": ["SR 11-7", "OCC 2011-12", "OCC Bulletin 2000-16", "FinCEN BSA"],
    "developed_by": "Bank XYZ — AML Data Science Team",
    "validation_date": "2026-06-15",
    "next_validation_due": "2027-06-15",
    "last_modified": "2026-07-27T14:23:45Z",
    
    "theory": {
        "mathematical_framework": "Multi-dimensional fusion of graph centrality metrics (PageRank, eigenvector centrality, k-shell decomposition), behavioral analytics (transaction velocity, structuring patterns, off-hours concentration), and temporal clustering (DBSCAN on transaction embeddings).",
        "key_assumptions": [
            "Customer transaction networks exhibit power-law degree distribution (validated Q2 2026)",
            "High-risk entities cluster in network subgraphs with elevated edge density (Girvan-Newman modularity >0.35)",
            "Structuring behavior manifests as bimodal transaction amount distribution ($9,000-$9,500 peak per FinCEN advisory 2012-02)"
        ],
        "theoretical_references": [
            "Dreżewski et al. (2015) — Graph-based AML detection",
            "Weber et al. (2018) — Anti-money laundering in Bitcoin",
            "Savage et al. (2016) — Network analysis for fraud detection"
        ]
    },
    
    "data_sources": {
        "nodes": {
            "table": "CUSTOMER_DIM @ EDW",
            "fields": ["cust_id", "name", "account_open_date", "customer_type", "is_sar", "is_ctf", "is_pep"],
            "refresh_frequency": "Daily 02:00 ET",
            "lookback_period": "36 months",
            "row_count_typical": "12,000-15,000"
        },
        "edges": {
            "table": "TRANSACTION_FACT @ EDW",
            "fields": ["txn_id", "from_cust_id", "to_cust_id", "amount", "date", "type"],
            "refresh_frequency": "T+1 (daily 06:00 ET)",
            "lookback_period": "24 months",
            "row_count_typical": "800,000-1,200,000"
        }
    },
    
    "dimensions": {
        "d1": {
            "name": "Structuring Risk",
            "definition": "Percentage of transactions near reporting thresholds ($9,000-$9,999, $2,900-$2,999 for CTR/BSA)",
            "algorithm": "Count within threshold bands / total transactions",
            "weight": 0.18,
            "weight_justification": "SHAP analysis Q1 2026 — D1 contributed 18% to Tier 1 detection (AUC 0.82)"
        },
        "d2": {
            "name": "Network Centrality",
            "definition": "Composite of PageRank, degree centrality, and k-shell scores",
            "algorithm": "Weighted average: 0.4×PageRank + 0.3×Degree + 0.3×KShell",
            "weight": 0.15,
            "weight_justification": "Entropy-based weighting Phase F v2.1 (see PHASE_F_ENGINE_CALIBRATION.md)"
        },
        ...
        "d9": {
            "name": "Regulatory History",
            "definition": "Binary flag: previously filed SAR/CTF/OFAC hit",
            "algorithm": "Boolean OR of is_sar, is_ctf, is_pep columns",
            "weight": 0.12,
            "weight_justification": "Regulatory guidance — prior SAR filing increases recidivism probability by 4.2× (internal study 2024)"
        }
    },
    
    "thresholds": {
        "tier1_threshold": {
            "value": 87.0,
            "last_changed": "2026-07-27",
            "changed_by": "alice@bank.com",
            "justification": "Validation report v2.3 — reduces FPR from 3.0% to 1.2%"
        },
        "tier2_threshold": {"value": 70.0, ...},
        "tier3_threshold": {"value": 50.0, ...}
    },
    
    "performance_metrics": {
        "validation_period": "2026-Q1 (Jan-Mar 2026)",
        "out_of_sample_gini": 0.68,
        "out_of_sample_ks": 0.54,
        "tier1_precision": 0.82,
        "tier1_recall": 0.76,
        "tier1_false_positive_rate": 0.012,
        "auc_roc": 0.85,
        "leave_one_out_cv_scores": {
            "mean_auc": 0.83,
            "std_auc": 0.04,
            "cv_folds": 12
        }
    },
    
    "limitations": [
        "Model does not capture cryptocurrency transactions (planned Phase G enhancement)",
        "Benford's Law dimension (D8) assumes USD-denominated transactions; currency exchange effects not modeled",
        "DBSCAN clustering requires manual epsilon tuning; adaptive epsilon planned for v9.0",
        "Graph metrics assume static network snapshot; temporal edge weights not yet implemented"
    ],
    
    "change_history": [
        {
            "version": "8.2.0",
            "date": "2026-07-27",
            "summary": "Documentation backfill — added Phase D compliance modules, Phase E governance layer",
            "impact": "No scoring logic changes, documentation-only update"
        },
        {
            "version": "8.1.0",
            "date": "2026-07-15",
            "summary": "Delta View page (page 19) — alerts on tier changes, Weight Calibration page (page 20)",
            "impact": "UI-only, no recalibration required"
        },
        {
            "version": "8.0.0",
            "date": "2026-07-01",
            "summary": "15 business rules (velocity, employee accounts, dormant reactivation, etc.), alert deduplication",
            "impact": "Tier 1 count increased by 8% (validation confirms true positive rate improvement)"
        }
    ],
    
    "dependencies": {
        "python_version": "3.11.x",
        "key_libraries": [
            {"name": "networkx", "version": "3.1", "purpose": "Graph algorithms (PageRank, k-shell, modularity)"},
            {"name": "scikit-learn", "version": "1.3.0", "purpose": "DBSCAN clustering, KNN, LOO-CV"},
            {"name": "pandas", "version": "2.0.3", "purpose": "Data wrangling"},
            {"name": "plotly", "version": "5.15.0", "purpose": "Interactive visualizations"},
            {"name": "dash", "version": "2.11.1", "purpose": "Web UI framework"}
        ]
    },
    
    "approvals": {
        "model_owner": {"name": "Jane Smith", "title": "VP — AML Analytics", "date": "2026-06-20"},
        "validator": {"name": "John Doe", "title": "Senior Model Risk Manager", "date": "2026-06-22"},
        "model_risk_committee": {"approval_date": "2026-06-25", "meeting_minutes": "MRC-2026-Q2-07"}
    }
}
```

### How
**Initial creation** (one-time, after Phase E implementation):
```bash
python -m graphaml mdd init
```
Generates `mdd.json` template with placeholders → manual fill-in by model owner.

**Update dimensions/thresholds** (auto-sync from config.yaml):
```bash
python -m graphaml mdd sync-config
```
Reads `config.yaml`, updates `dimensions` and `thresholds` sections in `mdd.json`, logs change to `config_changelog.jsonl`.

**Generate PDF** (for regulatory submission):
```bash
python -m graphaml mdd export-pdf --output mdd_v8.2.0.pdf
```
Uses Jinja2 template `templates/mdd_template.html` → renders → `weasyprint` converts to PDF (or `pdfkit` if weasyprint fails on Windows).

**Where Used:**
- Page 15 Admin → Governance tab → "Model Documentation" section with "View MDD (JSON)" and "Export PDF" buttons
- Exam package includes `mdd.json` and `mdd.pdf` in `01_mdd/` folder
- Model validation team references MDD for annual review

---

## E-3: GOVERNANCE MANAGER (`governance_manager.py`)

### Why
The two JSON/JSONL files are data stores. Python logic for append, validate, sync, and export lives in a dedicated class.

### What
`GovernanceManager` class provides:
- `log_config_change(user, role, section, parameter, old_value, new_value, justification, config_hash)` → appends to `config_changelog.jsonl`
- `get_config_history(section=None, user=None, since=None)` → query changelog with filters
- `validate_changelog()` → checks sequence numbers are monotonic, timestamps are ordered
- `load_mdd()` → returns dict from `mdd.json`
- `update_mdd(updates: dict)` → merges updates into `mdd.json`, increments version, logs change
- `sync_mdd_with_config()` → reads `config.yaml`, updates `dimensions.*.weight` and `thresholds.*` in MDD
- `export_mdd_pdf(output_path, template_path)` → Jinja2 render + weasyprint

**File structure:**
```python
# graphaml/compliance/governance_manager.py
from pathlib import Path
import json
from datetime import datetime, timezone
import hashlib
from typing import Optional, List, Dict

class GovernanceManager:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.changelog_path = base_dir / "config_changelog.jsonl"
        self.mdd_path = base_dir / "mdd.json"
        
        # Ensure paths exist
        self.base_dir.mkdir(parents=True, exist_ok=True)
        if not self.changelog_path.exists():
            self.changelog_path.touch()
        if not self.mdd_path.exists():
            self._init_mdd()
    
    def log_config_change(
        self, 
        user: str, 
        role: str, 
        section: str, 
        parameter: str, 
        old_value, 
        new_value, 
        justification: str, 
        config_hash: str,
        run_id_applied: Optional[str] = None
    ):
        """Append config change to changelog."""
        seq = self._get_next_seq()
        entry = {
            "seq": seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user": user,
            "role": role,
            "action": "CONFIG_CHANGE",
            "section": section,
            "parameter": parameter,
            "old_value": old_value,
            "new_value": new_value,
            "justification": justification,
            "run_id_applied": run_id_applied,
            "mdd_version": self._get_mdd_version(),
            "config_hash": config_hash
        }
        with open(self.changelog_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        logger.info(f"Config change logged: {section}.{parameter} {old_value} → {new_value}")
    
    def get_config_history(
        self, 
        section: Optional[str] = None, 
        user: Optional[str] = None, 
        since: Optional[str] = None
    ) -> List[Dict]:
        """Query changelog with optional filters."""
        entries = []
        with open(self.changelog_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                entry = json.loads(line)
                if section and entry["section"] != section:
                    continue
                if user and entry["user"] != user:
                    continue
                if since and entry["timestamp"] < since:
                    continue
                entries.append(entry)
        return entries
    
    def validate_changelog(self) -> bool:
        """Check sequence numbers and timestamp ordering."""
        entries = self.get_config_history()
        for i, entry in enumerate(entries):
            expected_seq = i + 1
            if entry["seq"] != expected_seq:
                logger.error(f"Sequence break: expected {expected_seq}, got {entry['seq']}")
                return False
            if i > 0 and entry["timestamp"] < entries[i-1]["timestamp"]:
                logger.error(f"Timestamp disorder at seq {entry['seq']}")
                return False
        return True
    
    def load_mdd(self) -> Dict:
        """Load MDD JSON."""
        with open(self.mdd_path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def update_mdd(self, updates: Dict):
        """Merge updates into MDD, increment version."""
        mdd = self.load_mdd()
        mdd.update(updates)
        mdd["last_modified"] = datetime.now(timezone.utc).isoformat()
        with open(self.mdd_path, "w", encoding="utf-8") as f:
            json.dump(mdd, f, indent=2, ensure_ascii=False)
        logger.info(f"MDD updated to version {mdd.get('mdd_version')}")
    
    def sync_mdd_with_config(self, config_path: Path):
        """Sync dimensions/thresholds from config.yaml to MDD."""
        import yaml
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        mdd = self.load_mdd()
        
        # Sync dimension weights
        for dim_key, dim_config in config.get("scoring", {}).get("dimension_weights", {}).items():
            if dim_key in mdd["dimensions"]:
                mdd["dimensions"][dim_key]["weight"] = dim_config
        
        # Sync thresholds
        for thresh_key, thresh_val in config.get("scoring", {}).get("thresholds", {}).items():
            if thresh_key in mdd["thresholds"]:
                mdd["thresholds"][thresh_key]["value"] = thresh_val
        
        self.update_mdd(mdd)
        logger.info("MDD synced with config.yaml")
    
    def export_mdd_pdf(self, output_path: Path, template_path: Path):
        """Generate PDF from MDD JSON using Jinja2 template."""
        from jinja2 import Template
        
        mdd = self.load_mdd()
        with open(template_path, "r", encoding="utf-8") as f:
            template = Template(f.read())
        
        html_content = template.render(mdd=mdd)
        
        # Try weasyprint first, fallback to pdfkit
        try:
            from weasyprint import HTML
            HTML(string=html_content).write_pdf(output_path)
            logger.info(f"MDD PDF generated: {output_path}")
        except ImportError:
            import pdfkit
            pdfkit.from_string(html_content, str(output_path))
            logger.info(f"MDD PDF generated (via pdfkit): {output_path}")
    
    def _get_next_seq(self) -> int:
        """Get next sequence number for changelog."""
        if not self.changelog_path.exists() or self.changelog_path.stat().st_size == 0:
            return 1
        entries = self.get_config_history()
        return entries[-1]["seq"] + 1 if entries else 1
    
    def _get_mdd_version(self) -> str:
        """Get current MDD version."""
        try:
            mdd = self.load_mdd()
            return mdd.get("mdd_version", "unknown")
        except:
            return "unknown"
    
    def _init_mdd(self):
        """Create initial MDD template."""
        template = {
            "mdd_version": "8.2.0",
            "model_name": "GraphAML",
            "last_modified": datetime.now(timezone.utc).isoformat(),
            "theory": {},
            "data_sources": {},
            "dimensions": {},
            "thresholds": {},
            "performance_metrics": {},
            "limitations": [],
            "change_history": [],
            "dependencies": {},
            "approvals": {}
        }
        with open(self.mdd_path, "w", encoding="utf-8") as f:
            json.dump(template, f, indent=2, ensure_ascii=False)
```

### Where Used
- `dash_app/callbacks/cb_admin.py` calls `gov.log_config_change(...)` when threshold/weight updated
- CLI `config set` command wraps `gov.log_config_change(...)`
- Page 15 Admin → Governance tab uses `gov.get_config_history()` and `gov.load_mdd()`

---

## E-4: UI INTEGRATION (Page 15 Admin)

### New Tab: Governance

**Section 1: Configuration Change History**
- AG Grid table: seq | timestamp | user | section | parameter | old→new | justification
- Search box: filter by section (e.g., "scoring.thresholds")
- Date range picker: show changes since last validation
- Export button: download filtered history as CSV

**Section 2: Model Documentation**
- Summary card: MDD version, last modified, next validation due
- "View MDD (JSON)" button → modal with formatted JSON (syntax highlighting via `react-json-view`)
- "Export MDD PDF" button → triggers `governance_manager.export_mdd_pdf()` → `dcc.Download` triggers
- "Sync MDD with Config" button → runs `sync_mdd_with_config()` → shows success toast

**Section 3: Validation History** (informational)
- Table: validation_date | validator | gini | ks | outcome | report_link
- Links to validation reports in `validation_reports/` folder

---

## E-5: CLI COMMANDS

```bash
# Log a config change manually
python -m graphaml config set scoring.thresholds.tier1_threshold 87.0 \
    --justification "Validation report v2.3" \
    --user alice@bank.com \
    --role MANAGER

# Query config change history
python -m graphaml config history --section scoring.thresholds --since 2026-01-01

# Initialize MDD (one-time setup)
python -m graphaml mdd init

# Sync MDD dimensions/thresholds from config.yaml
python -m graphaml mdd sync-config

# Export MDD as PDF
python -m graphaml mdd export-pdf --output mdd_v8.2.0.pdf --template templates/mdd_template.html

# Validate changelog integrity
python -m graphaml governance validate-changelog
```

---

## E-6: MDD PDF TEMPLATE (`templates/mdd_template.html`)

Jinja2 template with sections:
1. **Cover Page** — model name, version, approval signatures
2. **Executive Summary** — business purpose, regulatory scope, model tier
3. **Theory & Methodology** — mathematical framework, key assumptions, references
4. **Data Sources** — tables, fields, refresh frequency, lookback
5. **Dimensions** — D1-D9 definitions, algorithms, weights with justifications
6. **Thresholds** — Tier 1/2/3 cutoffs with change history
7. **Performance Metrics** — Gini, KS, AUC, precision/recall, LOO-CV
8. **Limitations** — known edge cases, planned enhancements
9. **Change History** — version log with impact summaries
10. **Appendices** — dependency list, glossary

**CSS styling:** Bank-branded header/footer, serif font (Garamond), page numbers, table of contents with hyperlinks.

**Example Jinja2 snippet:**
```html
<h2>5. Dimensions</h2>
{% for dim_id, dim_data in mdd.dimensions.items() %}
<h3>{{ dim_id.upper() }}: {{ dim_data.name }}</h3>
<p><strong>Definition:</strong> {{ dim_data.definition }}</p>
<p><strong>Algorithm:</strong> <code>{{ dim_data.algorithm }}</code></p>
<p><strong>Weight:</strong> {{ dim_data.weight }} ({{ (dim_data.weight * 100)|round(1) }}%)</p>
<p><strong>Justification:</strong> {{ dim_data.weight_justification }}</p>
{% endfor %}
```

---

## E-7: TESTS (Phase E)

```
tests/test_governance.py — 15 scenarios:

1. CONFIG CHANGELOG — first entry has seq=1
2. CONFIG CHANGELOG — 5 appends → seq increments correctly
3. CONFIG CHANGELOG — get_config_history with section filter returns only matching entries
4. CONFIG CHANGELOG — validate_changelog on intact log returns True
5. CONFIG CHANGELOG — validate_changelog with missing seq number returns False
6. MDD — load_mdd() returns dict with all required keys
7. MDD — update_mdd() increments last_modified timestamp
8. MDD — sync_mdd_with_config() updates dimension weights from config.yaml
9. MDD — export_mdd_pdf() creates PDF file (assert file size > 10KB)
10. GOVERNANCE MANAGER — _get_next_seq() returns 1 on empty changelog
11. GOVERNANCE MANAGER — _get_next_seq() returns N+1 after N entries
12. CLI — config set command logs to changelog and updates config.yaml
13. CLI — mdd sync-config command updates thresholds in mdd.json
14. CLI — governance validate-changelog returns exit code 0 on valid log
15. UI — Page 15 Governance tab renders config history table
```

---

## CRITICAL DESIGN NOTES

1. **config_changelog.jsonl is append-only:** Never delete entries, never edit. Regulators require immutable change history.
2. **mdd.json is versioned, not append-only:** Overwrite on update, but increment `mdd_version` and log change in `change_history` array.
3. **PDF generation requires wkhtmltopdf or weasyprint:** Install via conda if missing (`conda install -c conda-forge weasyprint`), graceful failure if unavailable (log warning, skip PDF).
4. **UTF-8 enforcement:** All JSON writes use `ensure_ascii=False` to handle non-ASCII names in justifications.
5. **Justification is REQUIRED:** For threshold/weight changes, UI must enforce non-empty justification field (frontend validation + backend check).
6. **MDD sync is semi-automated:** Dimensions/thresholds sync from config.yaml, but `theory`, `limitations`, `performance_metrics` require manual editing.
7. **Air-gap compliance:** No external API calls for PDF rendering, no cloud storage for MDD backups.

---

## INTEGRATION WITH PHASE D

Phase E governance data feeds into Phase D compliance:

- **Exam Package (`exam_package.py`):** includes `mdd.json`, `mdd.pdf`, and last 50 config changelog entries in `01_mdd/`
- **Audit Chain (`audit_chain.py`):** logs `CONFIG_CHANGE` action when `governance_manager.log_config_change()` is called
- **Data Lineage (`data_lineage.py`):** includes `mdd_version` field in lineage JSON to link customer scores to specific model version
- **Monitoring (`monitoring.py`):** alerts if PSI > 0.25 → auto-creates recommendation entry in `config_changelog.jsonl` for threshold recalibration

---

## DELIVERABLES CHECK

- [x] `graphaml/compliance/governance/config_changelog.jsonl` — append-only config change log (DATA file)
- [x] `graphaml/compliance/governance/mdd.json` — enhanced Model Documentation Database (DATA file)
- [x] `graphaml/compliance/governance_manager.py` — Python logic for log/query/sync/export
- [x] `templates/mdd_template.html` — Jinja2 template for PDF generation
- [x] Page 15 Admin → Governance tab (3 sections)
- [x] CLI commands (7 new)
- [x] 15 integration tests

**Phase E complete.**

---

## NEXT STEPS (Post-Phase E)

1. **Phase G: Advanced Features** — cryptocurrency tracing, temporal edge weights, adaptive DBSCAN epsilon
2. **Phase H: Explainability Dashboard** — SHAP values, counterfactual scenarios, feature contribution breakdowns
3. **ROADMAP.md** — document Phases G-H with timelines and dependencies
4. **D8/D9 documentation backfill** — add formal definitions to MASTER_PROMPT (currently only D1-D7 documented)
5. **UI page 16-41 documentation** — Phase B supplement for Delta View, Weight Calibration, Scenario Analysis, etc.

**Governance layer provides the foundation for transparent, auditable model lifecycle management. Regulators can now trace every threshold change, validate model documentation, and verify configuration integrity end-to-end.**
