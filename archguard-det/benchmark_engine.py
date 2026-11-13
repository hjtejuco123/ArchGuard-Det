"""Synthetic Drift Injector & 3-Way Ablation Benchmarking Engine for ArchGuard-Det."""

from __future__ import annotations

import ast
import csv
import io
import json
import os
import shutil
import tempfile
import time
import tracemalloc
from typing import Any

from graph_builder import RepositoryGraphBuilder, create_digraph, find_simple_cycles
from rule_engine import ArchitecturalRuleEngine, load_rules_from_file


CATEGORIES = [
    "Direct Layering Violation",
    "Transitive Layer Bypass",
    "Circular Dependency",
    "Security Guardrail Bypass",
    "Structural Technical Debt",
]


class BenchmarkRunner:
    """Runs deterministic synthetic drift injection and a 3-way ablation study."""

    def __init__(self, baseline_repo_path: str, output_dir: str | None = None) -> None:
        self.baseline_repo_path = os.path.abspath(baseline_repo_path)
        self.output_dir = os.path.abspath(output_dir or os.path.dirname(self.baseline_repo_path))

    @staticmethod
    def _append_snippet_and_get_line(file_path: str, snippet: str, target_marker: str) -> int:
        """Append code snippet to file_path and return exact 1-indexed line number of target_marker."""
        with open(file_path, "r", encoding="utf-8") as fh:
            original = fh.read()
        updated = original.rstrip() + "\n\n" + snippet.lstrip("\n")
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(updated)
        for idx, line in enumerate(updated.splitlines(), start=1):
            if target_marker in line:
                return idx
        return len(original.splitlines()) + 1

    @staticmethod
    def _insert_after_imports_and_get_line(file_path: str, import_line: str) -> int:
        """Insert a top-level import statement after the module docstring and existing imports."""
        with open(file_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()

        insert_idx = 0
        for idx, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_idx = idx + 1

        lines.insert(insert_idx, import_line)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        return insert_idx + 1

    def inject_synthetic_drift(self, target_repo: str) -> list[dict[str, Any]]:
        """Inject 10 deterministic ground-truth violations into a copied workspace."""
        ground_truth: list[dict[str, Any]] = []

        # ------------------------------------------------------------------
        # 1-3: Direct Layering Violations (3 direct layer skips)
        # ------------------------------------------------------------------
        # Direct #1: Top-level sqlite3 import in Presentation (routes/auth_routes.py)
        auth_routes = os.path.join(target_repo, "routes", "auth_routes.py")
        ln1 = self._insert_after_imports_and_get_line(auth_routes, "import sqlite3  # injected direct DB skip")
        ground_truth.append(
            {
                "gt_id": "GT-01",
                "source_file": "routes/auth_routes.py",
                "category": "Direct Layering Violation",
                "line_number": ln1,
                "description": "Presentation route directly imports sqlite3",
            }
        )

        # Direct #2: Top-level Repository import in Presentation (routes/order_routes.py)
        order_routes = os.path.join(target_repo, "routes", "order_routes.py")
        ln2 = self._insert_after_imports_and_get_line(
            order_routes,
            "from repositories.order_repo import OrderRepository  # injected repo skip",
        )
        ground_truth.append(
            {
                "gt_id": "GT-02",
                "source_file": "routes/order_routes.py",
                "category": "Direct Layering Violation",
                "line_number": ln2,
                "description": "Presentation route directly imports Repository layer",
            }
        )

        # Prepare Cycle #1 top-level imports first so subsequent line numbers in product_service.py stay exact
        auth_service = os.path.join(target_repo, "services", "auth_service.py")
        product_service = os.path.join(target_repo, "services", "product_service.py")
        ln_cyc1_a = self._insert_after_imports_and_get_line(
            auth_service,
            "from services.product_service import ProductService",
        )
        ln_cyc1_b = self._insert_after_imports_and_get_line(
            product_service,
            "from services.auth_service import AuthService",
        )

        # Direct #3: Function-scoped local sqlite3 import in Service (services/product_service.py)
        ln3 = self._append_snippet_and_get_line(
            product_service,
            """
def _emergency_inventory_count(db_path: str) -> int:
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM products").fetchone()
        return int(row[0]) if row else 0
""",
            "import sqlite3",
        )
        ground_truth.append(
            {
                "gt_id": "GT-03",
                "source_file": "services/product_service.py",
                "category": "Direct Layering Violation",
                "line_number": ln3,
                "description": "Service module performs function-scoped direct sqlite3 import",
            }
        )

        # ------------------------------------------------------------------
        # 4-5: Transitive Layer Bypasses (2 utility-to-DB/Repo bypasses)
        # ------------------------------------------------------------------
        # Transitive #1: routes/product_routes.py -> utils/cache_helper.py -> sqlite3
        cache_helper_py = os.path.join(target_repo, "utils", "cache_helper.py")
        with open(cache_helper_py, "w", encoding="utf-8") as fh:
            fh.write(
                '"""Injected utility helper performing hidden direct SQLite lookup."""\n\n\n'
                'def lookup_sku_exists_direct(sku: str, db_path: str = "ecommerce_baseline.db") -> bool:\n'
                "    import sqlite3\n"
                "    with sqlite3.connect(db_path) as conn:\n"
                '        row = conn.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone()\n'
                "        return row is not None\n"
            )
        ln_val_db = 5

        product_routes = os.path.join(target_repo, "routes", "product_routes.py")
        ln_pr_imp = self._insert_after_imports_and_get_line(
            product_routes,
            "from utils.cache_helper import lookup_sku_exists_direct",
        )
        self._append_snippet_and_get_line(
            product_routes,
            """
@product_bp.route("/sku-check/<sku>", methods=["GET"])
def public_check_sku(sku: str):
    exists = lookup_sku_exists_direct(sku)
    return jsonify({"sku": sku, "exists": exists}), 200
""",
            "lookup_sku_exists_direct(sku)",
        )
        ground_truth.append(
            {
                "gt_id": "GT-04",
                "source_file": "routes/product_routes.py",
                "category": "Transitive Layer Bypass",
                "line_number": ln_pr_imp,
                "alt_line_numbers": [ln_val_db],
                "description": "Presentation calls utils/cache_helper.py which directly queries sqlite3",
            }
        )

        # Transitive #2: routes/order_routes.py -> utils/audit_helper.py -> repositories/user_repo.py
        audit_helper_py = os.path.join(target_repo, "utils", "audit_helper.py")
        with open(audit_helper_py, "w", encoding="utf-8") as fh:
            fh.write(
                '"""Injected utility helper invoking Repository directly."""\n\n\n'
                "def fetch_user_role_bypass(email: str) -> str:\n"
                "    from repositories.user_repo import UserRepository\n"
                "    user = UserRepository().find_by_email(email)\n"
                '    return user["role"] if user else "guest"\n'
            )
        ln_sec_repo = 5

        ln_or_imp = self._insert_after_imports_and_get_line(
            order_routes,
            "from utils.audit_helper import fetch_user_role_bypass",
        )
        self._append_snippet_and_get_line(
            order_routes,
            """
@order_bp.route("/role-preview", methods=["GET"])
@require_auth
def preview_order_role():
    role = fetch_user_role_bypass("customer@example.com")
    return jsonify({"role": role}), 200
""",
            "fetch_user_role_bypass(",
        )
        ground_truth.append(
            {
                "gt_id": "GT-05",
                "source_file": "routes/order_routes.py",
                "category": "Transitive Layer Bypass",
                "line_number": ln_or_imp,
                "alt_line_numbers": [ln_sec_repo],
                "description": "Presentation calls utils/audit_helper.py which directly invokes UserRepository",
            }
        )

        # ------------------------------------------------------------------
        # 6-7: Circular Module Dependencies (2 cycles)
        # ------------------------------------------------------------------
        # Cycle #1 (Top-level mutual cycle): services/auth_service.py <-> services/product_service.py
        ground_truth.append(
            {
                "gt_id": "GT-06",
                "source_file": "services/auth_service.py",
                "cycle_files": ["services/auth_service.py", "services/product_service.py"],
                "category": "Circular Dependency",
                "line_number": ln_cyc1_a,
                "alt_line_numbers": [ln_cyc1_b],
                "description": "Mutual top-level cycle between auth_service and product_service",
            }
        )

        # Cycle #2 (With lazy local import on back-edge): repositories/order_repo.py <-> repositories/product_repo.py
        order_repo = os.path.join(target_repo, "repositories", "order_repo.py")
        product_repo = os.path.join(target_repo, "repositories", "product_repo.py")
        ln_cyc2_a = self._insert_after_imports_and_get_line(
            order_repo,
            "from repositories.product_repo import ProductRepository",
        )
        ln_cyc2_b = self._append_snippet_and_get_line(
            product_repo,
            """
def check_pending_orders_for_product(product_id: int) -> bool:
    from repositories.order_repo import OrderRepository
    repo = OrderRepository()
    return repo.find_by_id(product_id) is not None
""",
            "from repositories.order_repo import OrderRepository",
        )
        ground_truth.append(
            {
                "gt_id": "GT-07",
                "source_file": "repositories/order_repo.py",
                "cycle_files": ["repositories/order_repo.py", "repositories/product_repo.py"],
                "category": "Circular Dependency",
                "line_number": ln_cyc2_a,
                "alt_line_numbers": [ln_cyc2_b],
                "description": "Repository cycle involving function-scoped lazy back-import",
            }
        )

        # ------------------------------------------------------------------
        # 8-9: Missing @require_auth Security Decorators (2 bypasses)
        # ------------------------------------------------------------------
        ln_sec1 = self._append_snippet_and_get_line(
            order_routes,
            """
@order_bp.route("/export-all", methods=["GET"])
def export_all_orders_unprotected():
    return jsonify({"orders": []}), 200
""",
            "def export_all_orders_unprotected",
        )
        ground_truth.append(
            {
                "gt_id": "GT-08",
                "source_file": "routes/order_routes.py",
                "category": "Security Guardrail Bypass",
                "line_number": ln_sec1,
                "description": "Unprotected order export route missing @require_auth",
            }
        )

        ln_sec2 = self._append_snippet_and_get_line(
            product_routes,
            """
@product_bp.route("/<int:product_id>/archive", methods=["POST"])
def archive_product_unprotected(product_id: int):
    return jsonify({"archived": product_id}), 200
""",
            "def archive_product_unprotected",
        )
        ground_truth.append(
            {
                "gt_id": "GT-09",
                "source_file": "routes/product_routes.py",
                "category": "Security Guardrail Bypass",
                "line_number": ln_sec2,
                "description": "Unprotected product archive route missing @require_auth",
            }
        )

        # ------------------------------------------------------------------
        # 10: High-Complexity Technical Debt God-Function (1 violation)
        # ------------------------------------------------------------------
        order_service = os.path.join(target_repo, "services", "order_service.py")
        ln_debt = self._append_snippet_and_get_line(
            order_service,
            """
def calculate_dynamic_shipping_and_tax(
    subtotal_cents: int,
    country: str,
    tier: str,
    express: bool,
    fragile: bool,
    coupon_code: str,
    is_holiday: bool,
    weight_grams: int,
) -> int:
    fee = 0
    if country == "US" and subtotal_cents < 5000:
        fee += 600
    elif country == "CA":
        fee += 1200
    elif country == "UK":
        fee += 1500
    else:
        fee += 2200

    if tier == "gold" or tier == "platinum":
        fee = max(0, fee - 500)
    elif tier == "silver":
        fee = max(0, fee - 200)

    if express:
        fee += 1800 if weight_grams > 2000 else 1000
    if fragile:
        fee += 450
    if is_holiday:
        fee += 300
    if coupon_code == "FREESHIP" and subtotal_cents >= 2500:
        fee = 0
    for bracket in (1000, 5000, 10000):
        if weight_grams > bracket:
            fee += 150
    return fee
""",
            "def calculate_dynamic_shipping_and_tax",
        )
        ground_truth.append(
            {
                "gt_id": "GT-10",
                "source_file": "services/order_service.py",
                "category": "Structural Technical Debt",
                "line_number": ln_debt,
                "description": "God-function exceeding McCabe cyclomatic complexity threshold of 10",
            }
        )

        gt_path = os.path.join(target_repo, "ground_truth.json")
        with open(gt_path, "w", encoding="utf-8") as fh:
            json.dump(ground_truth, fh, indent=2)

        return ground_truth

    # ----------------------------------------------------------------------
    # Baseline 1: Single-File Local AST Linter (No cross-file graph)
    # ----------------------------------------------------------------------
    @staticmethod
    def run_baseline_single_file_ast(repo_path: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
        """Inspect each Python file in isolation without cross-file resolution, cycles, or paths."""
        builder = RepositoryGraphBuilder(rules)
        debt_cfg = rules.get("debt_thresholds", {})
        max_cc = int(debt_cfg.get("max_cyclomatic_complexity", 10))
        security_cfg = rules.get("security_rules", {}).get("require_auth_routes", {})
        target_files = set(security_cfg.get("target_files", []))
        required_dec = security_cfg.get("required_decorator", "require_auth")

        findings: list[dict[str, Any]] = []
        for _, rel_path, mod_name in builder._discover_python_files(repo_path):
            abs_file = os.path.join(repo_path, rel_path)
            with open(abs_file, "r", encoding="utf-8", errors="replace") as fh:
                src = fh.read()
            tree = ast.parse(src, filename=rel_path)

            # Single-file top-level hardcoded DB check (only knows raw stdlib DB names in routes)
            is_route_file = rel_path.startswith("routes/")
            for node in tree.body:
                if isinstance(node, ast.Import) and is_route_file:
                    for alias in node.names:
                        if alias.name.split(".")[0] in {"sqlite3", "sqlalchemy", "psycopg2", "pymysql"}:
                            findings.append(
                                {
                                    "source_file": rel_path,
                                    "category": "Direct Layering Violation",
                                    "line_numbers": [node.lineno],
                                }
                            )

            # Single-file function AST visitor (complexity + naive decorator check without exempt_prefix)
            from graph_builder import _ComplexityVisitor, _decorator_name

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    comp_v = _ComplexityVisitor()
                    for stmt in node.body:
                        comp_v.visit(stmt)
                    if comp_v.complexity > max_cc:
                        findings.append(
                            {
                                "source_file": rel_path,
                                "category": "Structural Technical Debt",
                                "line_numbers": [node.lineno],
                            }
                        )

                    decs = [_decorator_name(d) for d in node.decorator_list]
                    is_route = any(d == "route" or d.endswith(".route") for d in decs)
                    fname = os.path.basename(rel_path)
                    if is_route and (not target_files or fname in target_files):
                        has_req = any(d == required_dec or d.endswith(f".{required_dec}") for d in decs)
                        if not has_req:
                            findings.append(
                                {
                                    "source_file": rel_path,
                                    "category": "Security Guardrail Bypass",
                                    "line_numbers": [node.lineno],
                                }
                            )
        return findings

    # ----------------------------------------------------------------------
    # Baseline 2: Import-Only Package Checker (Top-level imports only)
    # ----------------------------------------------------------------------
    @staticmethod
    def run_baseline_import_only(repo_path: str, rules: dict[str, Any]) -> list[dict[str, Any]]:
        """Check top-level module imports only; ignores local imports, calls, decorators, and paths."""
        builder = RepositoryGraphBuilder(rules)
        discovered = builder._discover_python_files(repo_path)
        internal_modules = {mod for _, _, mod in discovered}
        allowed_deps = rules.get("allowed_dependencies", {})
        forbidden_by_layer = rules.get("forbidden_direct_imports_by_layer", {})

        g = create_digraph()
        for _, rel_path, mod_name in discovered:
            g.add_node(mod_name, file_path=rel_path, layer=builder.classify_layer(rel_path), is_external=False)

        top_edges: list[tuple[str, str, int]] = []
        for abs_file, rel_path, mod_name in discovered:
            with open(abs_file, "r", encoding="utf-8", errors="replace") as fh:
                tree = ast.parse(fh.read(), filename=rel_path)

            for stmt in tree.body:
                if isinstance(stmt, ast.Import):
                    for alias in stmt.names:
                        tgt, kind = builder._match_target_module(
                            alias.name, None, internal_modules, {"sqlite3", "sqlalchemy", "psycopg2", "pymysql"}
                        )
                        if tgt:
                            if kind == "external_db" and tgt not in g:
                                g.add_node(tgt, file_path=f"external:{tgt}", layer="ExternalDB", is_external=True)
                            g.add_edge(mod_name, tgt, line_numbers=[stmt.lineno])
                            top_edges.append((mod_name, tgt, stmt.lineno))
                elif isinstance(stmt, ast.ImportFrom):
                    mod_part = stmt.module or ""
                    for alias in stmt.names:
                        tgt, kind = builder._match_target_module(
                            mod_part, alias.name, internal_modules, {"sqlite3", "sqlalchemy", "psycopg2", "pymysql"}
                        )
                        if tgt:
                            if kind == "external_db" and tgt not in g:
                                g.add_node(tgt, file_path=f"external:{tgt}", layer="ExternalDB", is_external=True)
                            g.add_edge(mod_name, tgt, line_numbers=[stmt.lineno])
                            top_edges.append((mod_name, tgt, stmt.lineno))

        findings: list[dict[str, Any]] = []
        seen_edges: set[tuple[str, str]] = set()
        for u, v, lineno in top_edges:
            if (u, v) in seen_edges:
                continue
            seen_edges.add((u, v))
            u_layer = g.nodes[u].get("layer", "Unassigned")
            v_layer = g.nodes[v].get("layer", "Unassigned")
            forbidden = forbidden_by_layer.get(u_layer, [])
            matches_forbidden = any(v == p or v.startswith(f"{p}.") for p in forbidden)
            disallowed = (v_layer != u_layer) and (v_layer not in allowed_deps.get(u_layer, []))
            if matches_forbidden or disallowed:
                findings.append(
                    {
                        "source_file": g.nodes[u]["file_path"],
                        "category": "Direct Layering Violation",
                        "line_numbers": [lineno],
                    }
                )

        for cycle in find_simple_cycles(g):
            if any(g.nodes[n].get("is_external", False) for n in cycle):
                continue
            cycle_files = [g.nodes[n]["file_path"] for n in cycle]
            cycle_lines = []
            for idx in range(len(cycle)):
                a, b = cycle[idx], cycle[(idx + 1) % len(cycle)]
                ed = g.get_edge_data(a, b) or {}
                cycle_lines.extend(ed.get("line_numbers", []))
            findings.append(
                {
                    "source_file": cycle_files[0],
                    "cycle_files": cycle_files,
                    "category": "Circular Dependency",
                    "line_numbers": sorted(set(cycle_lines)) or [1],
                }
            )
        return findings

    # ----------------------------------------------------------------------
    # Evaluation & Metric Computation
    # ----------------------------------------------------------------------
    @staticmethod
    def _matches_ground_truth(pred: dict[str, Any], gt: dict[str, Any]) -> bool:
        if pred.get("category") != gt.get("category"):
            return False
        if gt["category"] == "Circular Dependency":
            gt_cycle_files = set(gt.get("cycle_files", [gt["source_file"]]))
            pred_trace = pred.get("architectural_trace", "")
            pred_files = set(pred.get("cycle_files", []))
            if pred.get("source_file") in gt_cycle_files:
                return True
            if pred_files and (pred_files & gt_cycle_files):
                return True
            if any(f.replace(".py", "").replace("/", ".") in pred_trace for f in gt_cycle_files):
                return True
            return False

        if pred.get("source_file") != gt.get("source_file"):
            return False

        pred_lines = set(pred.get("line_numbers", []))
        gt_lines = {gt["line_number"]} | set(gt.get("alt_line_numbers", []))
        if pred_lines and gt_lines:
            return bool(pred_lines & gt_lines)
        return True

    @classmethod
    def score_predictions(
        cls, predictions: list[dict[str, Any]], ground_truth: list[dict[str, Any]]
    ) -> dict[str, Any]:
        matched_gt: set[str] = set()
        matched_pred: set[int] = set()

        for p_idx, pred in enumerate(predictions):
            for gt in ground_truth:
                if gt["gt_id"] in matched_gt:
                    continue
                if cls._matches_ground_truth(pred, gt):
                    matched_gt.add(gt["gt_id"])
                    matched_pred.add(p_idx)
                    break

        tp = len(matched_gt)
        fp = len(predictions) - len(matched_pred)
        fn = len(ground_truth) - tp

        precision = round(tp / (tp + fp), 3) if (tp + fp) > 0 else 0.0
        recall = round(tp / (tp + fn), 3) if (tp + fn) > 0 else 0.0
        f1 = round((2 * precision * recall) / (precision + recall), 3) if (precision + recall) > 0 else 0.0

        category_recall: dict[str, dict[str, Any]] = {}
        for cat in CATEGORIES:
            cat_gts = [g for g in ground_truth if g["category"] == cat]
            cat_tp = sum(1 for g in cat_gts if g["gt_id"] in matched_gt)
            cat_total = len(cat_gts)
            category_recall[cat] = {
                "detected": cat_tp,
                "total": cat_total,
                "recall": round(cat_tp / cat_total, 3) if cat_total > 0 else 0.0,
            }

        return {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "category_recall": category_recall,
        }

    @staticmethod
    def _measure(fn, *args) -> tuple[Any, float, float]:
        tracemalloc.start()
        t0 = time.perf_counter()
        result = fn(*args)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mb = round(peak_bytes / (1024.0 * 1024.0), 4)
        return result, elapsed_ms, peak_mb

    @staticmethod
    def generate_csv(methods: list[dict[str, Any]]) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["Method", "TP", "FP", "FN", "Precision", "Recall", "F1_Score", "Latency_ms", "Peak_Memory_MB"]
        )
        for m in methods:
            writer.writerow(
                [
                    m["method"],
                    m["tp"],
                    m["fp"],
                    m["fn"],
                    f"{m['precision']:.3f}",
                    f"{m['recall']:.3f}",
                    f"{m['f1_score']:.3f}",
                    f"{m['latency_ms']:.2f}",
                    f"{m['peak_memory_mb']:.4f}",
                ]
            )
        return buf.getvalue()

    @staticmethod
    def generate_latex_table(methods: list[dict[str, Any]]) -> str:
        lines = [
            r"\begin{table}[htbp]",
            r"\centering",
            r"\caption{Ablation Study on Synthetic Architectural Drift Injection ($N=10$ Ground-Truth Violations)}",
            r"\label{tab:archguard_ablation}",
            r"\resizebox{\columnwidth}{!}{%",
            r"\begin{tabular}{lcccccccc}",
            r"\hline",
            r"\textbf{Method} & \textbf{TP} & \textbf{FP} & \textbf{FN} & \textbf{Prec.} & \textbf{Rec.} & \textbf{F1} & \textbf{Time (ms)} & \textbf{Mem (MB)} \\",
            r"\hline",
        ]
        for idx, m in enumerate(methods):
            name = m["method"].replace("_", r"\_")
            is_best = idx == len(methods) - 1
            if is_best:
                row = (
                    f"\\textbf{{{name}}} & \\textbf{{{m['tp']}}} & \\textbf{{{m['fp']}}} & "
                    f"\\textbf{{{m['fn']}}} & \\textbf{{{m['precision']:.3f}}} & "
                    f"\\textbf{{{m['recall']:.3f}}} & \\textbf{{{m['f1_score']:.3f}}} & "
                    f"{m['latency_ms']:.2f} & {m['peak_memory_mb']:.4f} \\\\"
                )
            else:
                row = (
                    f"{name} & {m['tp']} & {m['fp']} & {m['fn']} & "
                    f"{m['precision']:.3f} & {m['recall']:.3f} & {m['f1_score']:.3f} & "
                    f"{m['latency_ms']:.2f} & {m['peak_memory_mb']:.4f} \\\\"
                )
            lines.append(row)
        lines.extend(
            [
                r"\hline",
                r"\end{tabular}%",
                r"}",
                r"\end{table}",
            ]
        )
        return "\n".join(lines) + "\n"

    def run_benchmark(self, rules_override: dict[str, Any] | None = None) -> dict[str, Any]:
        """Copy sample_repo into temp workspace, inject 10 violations, and run 3-way ablation."""
        temp_dir = tempfile.mkdtemp(prefix="archguard_bench_")
        try:
            workspace_repo = os.path.join(temp_dir, "sample_repo")
            shutil.copytree(self.baseline_repo_path, workspace_repo)

            rules_path = os.path.join(workspace_repo, "architecture_rules.yaml")
            rules = rules_override
            if rules is None:
                rules, _ = load_rules_from_file(rules_path)

            ground_truth = self.inject_synthetic_drift(workspace_repo)

            # Method 1: Single-File Local AST Linter
            b1_preds, b1_ms, b1_mb = self._measure(self.run_baseline_single_file_ast, workspace_repo, rules)
            b1_scores = self.score_predictions(b1_preds, ground_truth)

            # Method 2: Import-Only Package Checker
            b2_preds, b2_ms, b2_mb = self._measure(self.run_baseline_import_only, workspace_repo, rules)
            b2_scores = self.score_predictions(b2_preds, ground_truth)

            # Method 3: Proposed ArchGuard-Det (Full AST + Call-Graph + Cycle/Path Auditor)
            def _run_proposed():
                builder = RepositoryGraphBuilder(rules)
                g, summary = builder.build_graph(workspace_repo)
                engine = ArchitecturalRuleEngine(rules)
                return engine.evaluate(g, summary)

            prop_res, prop_ms, prop_mb = self._measure(_run_proposed)
            prop_scores = self.score_predictions(prop_res["violations"], ground_truth)

            methods = [
                {
                    "method": "Single-File AST Linter",
                    **b1_scores,
                    "latency_ms": b1_ms,
                    "peak_memory_mb": b1_mb,
                },
                {
                    "method": "Import-Only Checker",
                    **b2_scores,
                    "latency_ms": b2_ms,
                    "peak_memory_mb": b2_mb,
                },
                {
                    "method": "ArchGuard-Det (Proposed)",
                    **prop_scores,
                    "latency_ms": prop_ms,
                    "peak_memory_mb": prop_mb,
                },
            ]

            csv_content = self.generate_csv(methods)
            latex_content = self.generate_latex_table(methods)

            os.makedirs(self.output_dir, exist_ok=True)
            csv_path = os.path.join(self.output_dir, "benchmark_results.csv")
            latex_path = os.path.join(self.output_dir, "results_table.tex")
            with open(csv_path, "w", encoding="utf-8") as fh:
                fh.write(csv_content)
            with open(latex_path, "w", encoding="utf-8") as fh:
                fh.write(latex_content)

            return {
                "ground_truth_count": len(ground_truth),
                "ground_truth": ground_truth,
                "methods": methods,
                "proposed_adi_score": prop_res["adi_score"],
                "proposed_adi_components": prop_res["adi_components"],
                "proposed_severity_counts": prop_res["severity_counts"],
                "proposed_violations": prop_res["violations"],
                "proposed_graph": prop_res["graph"],
                "proposed_node_metrics": prop_res["node_metrics"],
                "csv_content": csv_content,
                "latex_content": latex_content,
                "csv_path": csv_path,
                "latex_path": latex_path,
            }
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
