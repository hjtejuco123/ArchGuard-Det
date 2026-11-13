"""ArchGuard-Det: Deterministic AST-Graph Architectural Drift & Technical Debt Auditor.

Provides both the standalone Flask web server (on FLASK_PORT, default 5000) and
a CLI JSON bridge (--bridge) for embedded runtime integration.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from typing import Any

# Ensure local modules resolve cleanly regardless of working directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from benchmark_engine import BenchmarkRunner
from database import AuditDatabase, get_db_path
from graph_builder import RepositoryGraphBuilder
from rule_engine import ArchitecturalRuleEngine, load_rules_from_file, load_rules_yaml

DEFAULT_SAMPLE_REPO = os.path.join(BASE_DIR, "sample_repo")
DEFAULT_RULES_PATH = os.path.join(DEFAULT_SAMPLE_REPO, "architecture_rules.yaml")


def _safe_extract_zip(zip_path: str, dest_dir: str) -> None:
    """Extract a ZIP archive safely preventing ZipSlip directory traversal."""
    abs_dest = os.path.abspath(dest_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = os.path.abspath(os.path.join(abs_dest, member.filename))
            if not member_path.startswith(abs_dest + os.sep) and member_path != abs_dest:
                raise ValueError(f"Unsafe ZIP entry path detected: {member.filename}")
        zf.extractall(abs_dest)


def _find_extracted_repo_root(extract_dir: str) -> str:
    """If a ZIP contains a single top-level folder, unwrap to that folder."""
    entries = [e for e in os.listdir(extract_dir) if not e.startswith("__MACOSX") and not e.startswith(".")]
    if len(entries) == 1:
        candidate = os.path.join(extract_dir, entries[0])
        if os.path.isdir(candidate):
            return candidate
    return extract_dir


def _resolve_repo_path(raw_path: str | None) -> str:
    if not raw_path or raw_path.strip() in {"./sample_repo", "sample_repo"}:
        return DEFAULT_SAMPLE_REPO
    candidate = raw_path.strip()
    if os.path.isabs(candidate):
        return candidate
    # Check relative to CWD first, then BASE_DIR
    if os.path.exists(candidate):
        return os.path.abspath(candidate)
    rel_base = os.path.abspath(os.path.join(BASE_DIR, candidate))
    if os.path.exists(rel_base):
        return rel_base
    return os.path.abspath(candidate)


def execute_audit(
    repo_path: str | None = None,
    rules_yaml_text: str | None = None,
    zip_bytes: bytes | None = None,
    db: AuditDatabase | None = None,
) -> dict[str, Any]:
    """Execute deterministic AST-Graph architectural audit and persist to SQLite."""
    db_instance = db or AuditDatabase()
    temp_dir: str | None = None
    display_path = repo_path or "./sample_repo"

    try:
        if zip_bytes is not None:
            temp_dir = tempfile.mkdtemp(prefix="archguard_zip_")
            zip_file_path = os.path.join(temp_dir, "upload.zip")
            extract_dir = os.path.join(temp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            with open(zip_file_path, "wb") as fh:
                fh.write(zip_bytes)
            _safe_extract_zip(zip_file_path, extract_dir)
            target_repo = _find_extracted_repo_root(extract_dir)
            display_path = f"zip://{os.path.basename(target_repo)}"
        else:
            target_repo = _resolve_repo_path(repo_path)
            if not os.path.isdir(target_repo):
                raise FileNotFoundError(f"Repository path not found: {target_repo}")

        if rules_yaml_text and rules_yaml_text.strip():
            rules = load_rules_yaml(rules_yaml_text)
            active_yaml = rules_yaml_text
        else:
            candidate_rules = os.path.join(target_repo, "architecture_rules.yaml")
            rules_file = candidate_rules if os.path.isfile(candidate_rules) else DEFAULT_RULES_PATH
            rules, active_yaml = load_rules_from_file(rules_file)

        t0 = time.perf_counter()
        builder = RepositoryGraphBuilder(rules)
        graph, summary = builder.build_graph(target_repo)
        engine = ArchitecturalRuleEngine(rules)
        evaluation = engine.evaluate(graph, summary)
        execution_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        result = {
            "repo_path": display_path,
            "resolved_path": target_repo if zip_bytes is None else display_path,
            "execution_ms": execution_ms,
            "node_count": summary["node_count"],
            "edge_count": summary["edge_count"],
            "internal_file_count": summary["internal_file_count"],
            "using_networkx": summary["using_networkx"],
            "rules_yaml": active_yaml,
            **evaluation,
        }

        audit_id = db_instance.save_audit_run(
            repo_path=display_path,
            node_count=summary["node_count"],
            edge_count=summary["edge_count"],
            adi_score=evaluation["adi_score"],
            total_violations=evaluation["total_violations"],
            execution_ms=execution_ms,
            result=result,
        )
        result["audit_id"] = audit_id
        return result
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


def handle_rules(action: str = "load", yaml_text: str | None = None) -> dict[str, Any]:
    """Load or save architecture_rules.yaml."""
    if action == "save" and yaml_text is not None:
        parsed = load_rules_yaml(yaml_text)
        if not parsed or "layers" not in parsed:
            raise ValueError("Invalid architecture_rules.yaml: missing 'layers' section")
        with open(DEFAULT_RULES_PATH, "w", encoding="utf-8") as fh:
            fh.write(yaml_text)
        return {"status": "saved", "rules_path": DEFAULT_RULES_PATH, "yaml_text": yaml_text, "parsed": parsed}

    parsed, current_yaml = load_rules_from_file(DEFAULT_RULES_PATH)
    return {"status": "loaded", "rules_path": DEFAULT_RULES_PATH, "yaml_text": current_yaml, "parsed": parsed}


def execute_benchmark(rules_yaml_text: str | None = None, db: AuditDatabase | None = None) -> dict[str, Any]:
    """Run Synthetic Drift Injection + 3-Way Ablation Study and persist to SQLite."""
    db_instance = db or AuditDatabase()
    rules_override = load_rules_yaml(rules_yaml_text) if rules_yaml_text and rules_yaml_text.strip() else None
    runner = BenchmarkRunner(baseline_repo_path=DEFAULT_SAMPLE_REPO, output_dir=BASE_DIR)
    bench_result = runner.run_benchmark(rules_override=rules_override)
    bench_id = db_instance.save_benchmark_run(bench_result)
    bench_result["benchmark_id"] = bench_id
    return bench_result


def export_artifact(kind: str, db: AuditDatabase | None = None) -> tuple[str, str, str]:
    """Return (filename, mimetype, content) for 'csv' or 'latex'."""
    db_instance = db or AuditDatabase()
    latest = db_instance.get_latest_benchmark()
    if latest is None:
        latest = execute_benchmark(db=db_instance)
    if kind == "csv":
        return "benchmark_results.csv", "text/csv; charset=utf-8", latest["csv_content"]
    return "results_table.tex", "application/x-tex; charset=utf-8", latest["latex_content"]


def get_history(db: AuditDatabase | None = None) -> dict[str, Any]:
    db_instance = db or AuditDatabase()
    return {
        "db_path": db_instance.db_path,
        "history": db_instance.list_history(),
        "adi_trend": db_instance.get_adi_trend(),
        "latest_audit": db_instance.get_latest_audit(),
        "latest_benchmark": db_instance.get_latest_benchmark(),
    }


def get_adi_trend_data(limit: int = 50, db: AuditDatabase | None = None) -> dict[str, Any]:
    db_instance = db or AuditDatabase()
    return {
        "db_path": db_instance.db_path,
        "points": db_instance.get_adi_trend(limit=limit),
    }


def create_flask_app():
    """Instantiate the Flask application when Flask is installed."""
    from flask import Flask, Response, jsonify, render_template, request  # type: ignore

    app = Flask(__name__, template_folder=os.path.join(BASE_DIR, "templates"))
    db = AuditDatabase(get_db_path())

    @app.route("/", methods=["GET"])
    def index():
        return render_template("index.html")

    @app.route("/api/audit", methods=["POST"])
    def api_audit():
        try:
            zip_bytes: bytes | None = None
            repo_path: str | None = None
            rules_yaml: str | None = None

            if "repo_zip" in request.files and request.files["repo_zip"].filename:
                zip_bytes = request.files["repo_zip"].read()
                rules_yaml = request.form.get("rules_yaml")
            else:
                payload = request.get_json(silent=True) or {}
                repo_path = payload.get("repo_path") or request.form.get("repo_path")
                rules_yaml = payload.get("rules_yaml") or request.form.get("rules_yaml")
                if payload.get("zip_base64"):
                    zip_bytes = base64.b64decode(payload["zip_base64"])

            result = execute_audit(
                repo_path=repo_path,
                rules_yaml_text=rules_yaml,
                zip_bytes=zip_bytes,
                db=db,
            )
            return jsonify(result), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/rules", methods=["GET", "POST"])
    def api_rules():
        try:
            if request.method == "GET":
                return jsonify(handle_rules("load")), 200
            payload = request.get_json(silent=True) or {}
            yaml_text = payload.get("yaml_text")
            action = payload.get("action") or ("save" if yaml_text is not None else "load")
            return jsonify(handle_rules(action=action, yaml_text=yaml_text)), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 400

    @app.route("/api/benchmark/run", methods=["POST"])
    def api_benchmark_run():
        try:
            payload = request.get_json(silent=True) or {}
            result = execute_benchmark(rules_yaml_text=payload.get("rules_yaml"), db=db)
            return jsonify(result), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/export/csv", methods=["GET"])
    def api_export_csv():
        filename, mimetype, content = export_artifact("csv", db=db)
        return Response(
            content,
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/api/export/latex", methods=["GET"])
    def api_export_latex():
        filename, mimetype, content = export_artifact("latex", db=db)
        return Response(
            content,
            mimetype=mimetype,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    @app.route("/api/history", methods=["GET"])
    def api_history():
        return jsonify(get_history(db=db)), 200

    @app.route("/api/adi-trend", methods=["GET"])
    def api_adi_trend():
        raw_limit = request.args.get("limit", default=50, type=int) or 50
        bounded_limit = max(1, min(200, raw_limit))
        return jsonify(get_adi_trend_data(limit=bounded_limit, db=db)), 200

    return app


def _run_cli_bridge(command: str) -> int:
    """Deterministic stdin/stdout JSON bridge for Node/Express integration."""
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    db = AuditDatabase(get_db_path())

    try:
        if command == "audit":
            zip_bytes = base64.b64decode(payload["zip_base64"]) if payload.get("zip_base64") else None
            out = execute_audit(
                repo_path=payload.get("repo_path"),
                rules_yaml_text=payload.get("rules_yaml"),
                zip_bytes=zip_bytes,
                db=db,
            )
        elif command == "rules_load":
            out = handle_rules(action="load")
        elif command == "rules_save":
            out = handle_rules(action="save", yaml_text=payload.get("yaml_text", ""))
        elif command == "benchmark":
            out = execute_benchmark(rules_yaml_text=payload.get("rules_yaml"), db=db)
        elif command == "export_csv":
            _, _, content = export_artifact("csv", db=db)
            out = {"filename": "benchmark_results.csv", "content": content}
        elif command == "export_latex":
            _, _, content = export_artifact("latex", db=db)
            out = {"filename": "results_table.tex", "content": content}
        elif command == "history":
            out = get_history(db=db)
        elif command == "adi_trend":
            limit = int(payload.get("limit", 50))
            out = get_adi_trend_data(limit=max(1, min(200, limit)), db=db)
        else:
            out = {"error": f"Unknown bridge command: {command}"}
            print(json.dumps(out))
            return 1

        print(json.dumps(out))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--bridge":
        raise SystemExit(_run_cli_bridge(sys.argv[2]))

    flask_port = int(os.environ.get("FLASK_PORT", "5000"))
    flask_app = create_flask_app()
    flask_app.run(host="0.0.0.0", port=flask_port, debug=False)
