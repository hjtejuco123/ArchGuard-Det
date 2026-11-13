# ArchGuard-Det: Deterministic AST-Graph Architectural Drift & Technical Debt Auditor

ArchGuard-Det is a 100% deterministic, offline-capable Python software architecture auditing and research benchmarking workbench. It parses Python repositories via the built-in `ast` module, constructs a directed dependency and call graph using NetworkX, evaluates formal `architecture_rules.yaml` constraints, computes a bounded Architectural Drift Index ($\text{ADI} \in [0.000, 1.000]$), and runs a reproducible 3-way ablation study using synthetic drift injection.

## Strict Deterministic Guarantees
- **Zero LLMs / Zero External AI APIs**: No LLM calls, vector embeddings, or external API keys required.
- **Reproducible AST + Graph Analysis**: Uses Python `ast`, `networkx.DiGraph`, `nx.all_simple_paths`, `nx.simple_cycles`, `time.perf_counter()`, `tracemalloc`, and `sqlite3`.

## Project Layout
- `app.py` — Flask server (`FLASK_PORT`, default `5000`) & CLI JSON bridge
- `graph_builder.py` — Multi-file AST & call-graph extractor (`RepositoryGraphBuilder`)
- `rule_engine.py` — Deterministic drift & technical debt rule engine (`ArchitecturalRuleEngine`)
- `benchmark_engine.py` — Synthetic drift injector (10 ground-truth violations) & 3-way ablation lab (`BenchmarkRunner`)
- `database.py` — SQLite persistence (`ARCHGUARD_DB_PATH`, default `audit_benchmarks.db`)
- `templates/index.html` — Tabler UI dashboard with interactive layered dependency graph
- `sample_repo/` — Clean 3-tier layered Flask e-commerce baseline (`0` initial violations)

## Quickstart
```bash
cd archguard-det
pip install -r requirements.txt
export FLASK_PORT=5000
export ARCHGUARD_DB_PATH=audit_benchmarks.db
python app.py
```

Open `http://127.0.0.1:5000` in your browser.
