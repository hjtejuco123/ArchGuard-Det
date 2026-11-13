"""Deterministic Architectural Drift & Technical Debt Rule Engine."""

from __future__ import annotations

import os
from typing import Any

from graph_builder import find_all_simple_paths, find_simple_cycles

try:
    import yaml  # type: ignore
    HAS_PYYAML = True
except ImportError:
    HAS_PYYAML = False


SEVERITY_WEIGHTS = {
    "CRITICAL": 1.0,
    "HIGH": 0.7,
    "MEDIUM": 0.4,
    "LOW": 0.2,
}


def _simple_yaml_load(text: str) -> dict[str, Any]:
    """Deterministic fallback YAML parser for architecture_rules.yaml when PyYAML is absent."""
    lines = text.splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    def parse_scalar(val: str) -> Any:
        v = val.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            return v[1:-1]
        if v == "[]":
            return []
        if v == "{}":
            return {}
        if v.lower() == "true":
            return True
        if v.lower() == "false":
            return False
        try:
            if "." in v:
                return float(v)
            return int(v)
        except ValueError:
            return v

    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        idx += 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if stripped.startswith("- "):
            item_val = parse_scalar(stripped[2:])
            if isinstance(parent, list):
                parent.append(item_val)
            continue

        if ":" in stripped:
            key, rest = stripped.split(":", 1)
            key = key.strip()
            rest = rest.strip()
            if rest:
                if isinstance(parent, dict):
                    parent[key] = parse_scalar(rest)
            else:
                # Look ahead to determine if next non-empty line is a list or dict
                container: Any = {}
                for look_idx in range(idx, len(lines)):
                    next_raw = lines[look_idx]
                    next_stripped = next_raw.strip()
                    if not next_stripped or next_stripped.startswith("#"):
                        continue
                    if next_stripped.startswith("- "):
                        container = []
                    break
                if isinstance(parent, dict):
                    parent[key] = container
                stack.append((indent, container))
    return root


def load_rules_yaml(yaml_text: str) -> dict[str, Any]:
    """Parse architecture rules YAML string deterministically."""
    if HAS_PYYAML:
        loaded = yaml.safe_load(yaml_text)
        return loaded if isinstance(loaded, dict) else {}
    return _simple_yaml_load(yaml_text)


def load_rules_from_file(rules_path: str) -> tuple[dict[str, Any], str]:
    """Load rules dict and raw YAML text from disk."""
    with open(rules_path, "r", encoding="utf-8") as fh:
        raw_text = fh.read()
    return load_rules_yaml(raw_text), raw_text


class ArchitecturalRuleEngine:
    """Evaluates a NetworkX dependency graph and AST metadata against YAML architecture rules."""

    def __init__(self, rules: dict[str, Any]) -> None:
        self.rules = rules or {}

    @staticmethod
    def _suggest_service_name(target_file: str) -> str:
        base = os.path.splitext(os.path.basename(target_file))[0]
        stem = base.replace("_repo", "").replace("_repository", "")
        pascal = "".join(part.capitalize() for part in stem.split("_") if part) or "Domain"
        return f"{pascal}Service"

    @staticmethod
    def _suggest_repo_name(target_name: str) -> str:
        stem = target_name.replace(".", "_")
        pascal = "".join(part.capitalize() for part in stem.split("_") if part) or "Data"
        return f"{pascal}Repository"

    def evaluate(self, graph: Any, summary: dict[str, Any]) -> dict[str, Any]:
        """Run all 5 deterministic architectural rule checks and compute ADI."""
        violations: list[dict[str, Any]] = []
        allowed_deps = self.rules.get("allowed_dependencies", {})
        forbidden_by_layer = self.rules.get("forbidden_direct_imports_by_layer", {})
        security_cfg = self.rules.get("security_rules", {}).get("require_auth_routes", {})
        debt_cfg = self.rules.get("debt_thresholds", {})

        max_cc = int(debt_cfg.get("max_cyclomatic_complexity", 10))
        max_fan_out = int(debt_cfg.get("max_fan_out", 6))
        max_instability = float(debt_cfg.get("max_instability", 0.85))
        min_fan_in = int(debt_cfg.get("min_fan_in_for_instability", 2))

        counters = {
            "DIR": 0,
            "TRN": 0,
            "CYC": 0,
            "SEC": 0,
            "DEBT": 0,
        }

        def next_id(prefix: str) -> str:
            counters[prefix] += 1
            return f"AG-{prefix}-{counters[prefix]:03d}"

        # ------------------------------------------------------------------
        # 1. Transitive Layer Bypass (HIGH) via all_simple_paths(cutoff=4)
        # ------------------------------------------------------------------
        presentation_nodes = sorted(
            n for n, d in graph.nodes(data=True) if d.get("layer") == "Presentation"
        )
        bypass_targets = sorted(
            n
            for n, d in graph.nodes(data=True)
            if d.get("layer") in {"ExternalDB", "Repository"}
        )

        transitive_edges: set[tuple[str, str]] = set()
        seen_transitive_pairs: set[tuple[str, str]] = set()

        for src in presentation_nodes:
            for tgt in bypass_targets:
                paths = find_all_simple_paths(graph, src, tgt, cutoff=4)
                for path in paths:
                    if len(path) < 3:
                        continue
                    intermediates = path[1:-1]
                    intermediate_layers = [graph.nodes[m].get("layer") for m in intermediates]
                    # Trigger when Presentation reaches Repository/ExternalDB through Utility without Service or prior Repository
                    if (
                        "Utility" in intermediate_layers
                        and "Service" not in intermediate_layers
                        and "Repository" not in intermediate_layers
                        and "ExternalDB" not in intermediate_layers
                    ):
                        pair_key = (src, tgt)
                        if pair_key in seen_transitive_pairs:
                            continue
                        seen_transitive_pairs.add(pair_key)

                        for idx in range(len(path) - 1):
                            edge_pair = (path[idx], path[idx + 1])
                            transitive_edges.add(edge_pair)
                            edge_data = graph.get_edge_data(*edge_pair) or {}
                            etypes = edge_data.get("edge_types", [])
                            if "transitive_bypass" not in etypes:
                                etypes.append("transitive_bypass")

                        src_file = graph.nodes[src].get("file_path", src)
                        mid_file = graph.nodes[intermediates[0]].get("file_path", intermediates[0])
                        tgt_file = graph.nodes[tgt].get("file_path", tgt)
                        first_edge = graph.get_edge_data(path[0], path[1]) or {}
                        hop_edge = graph.get_edge_data(path[-2], path[-1]) or {}
                        line_nums = sorted(
                            set(first_edge.get("line_numbers", []) + hop_edge.get("line_numbers", []))
                        ) or [1]
                        trace = " -> ".join(
                            f"{n} ({graph.nodes[n].get('layer', 'Unknown')})" for n in path
                        )
                        svc_name = self._suggest_service_name(tgt_file)
                        repo_name = self._suggest_repo_name(tgt)
                        violations.append(
                            {
                                "violation_id": next_id("TRN"),
                                "category": "Transitive Layer Bypass",
                                "severity": "HIGH",
                                "violated_rule": "TRANSITIVE_BYPASS_NO_SERVICE",
                                "source_file": src_file,
                                "source_module": src,
                                "line_numbers": line_nums,
                                "target_file": tgt_file,
                                "target_module": tgt,
                                "architectural_trace": trace,
                                "path_nodes": path,
                                "deterministic_fix": (
                                    f"In {mid_file} (lines {hop_edge.get('line_numbers', line_nums)}), remove direct "
                                    f"reference to '{tgt}'. Encapsulate data access inside {repo_name}, expose it "
                                    f"via {svc_name}, and inject {svc_name} into {src_file} instead of routing through Utility."
                                ),
                                "confidence": 1.0,
                            }
                        )

        # ------------------------------------------------------------------
        # 2. Direct Layering Violations (CRITICAL)
        # ------------------------------------------------------------------
        violating_edges: set[tuple[str, str]] = set()
        for u, v, edata in sorted(graph.edges(data=True), key=lambda x: (x[0], x[1])):
            u_layer = graph.nodes[u].get("layer", "Unassigned")
            v_layer = graph.nodes[v].get("layer", "Unassigned")
            if u_layer == "Unassigned":
                continue

            # Check explicit forbidden imports/packages first
            forbidden_list = forbidden_by_layer.get(u_layer, [])
            matches_forbidden = any(
                v == pat or v.startswith(f"{pat}.") or f".{pat}." in v
                for pat in forbidden_list
            )

            allowed_targets = allowed_deps.get(u_layer, [])
            # Same-layer peer edges are evaluated by cycle detector unless explicitly forbidden
            disallowed_cross_layer = (v_layer != u_layer) and (v_layer not in allowed_targets)

            # Avoid double-counting the Utility -> target hop when already captured as a Transitive Layer Bypass
            if (u, v) in transitive_edges and u_layer == "Utility":
                continue

            if matches_forbidden or disallowed_cross_layer:
                violating_edges.add((u, v))
                src_file = graph.nodes[u].get("file_path", u)
                tgt_file = graph.nodes[v].get("file_path", v)
                line_nums = edata.get("line_numbers", [1])
                evidence = edata.get("evidence", [])
                ev_str = evidence[0] if evidence else f"import {v}"
                svc_name = self._suggest_service_name(tgt_file)
                repo_name = self._suggest_repo_name(v)

                if u_layer == "Presentation" and v_layer == "ExternalDB":
                    fix_msg = (
                        f"Remove '{ev_str}' at {src_file}:{line_nums[0]}. Move database queries into a "
                        f"Repository class ({repo_name}) in repositories/, wrap business logic in {svc_name} "
                        f"in services/, and inject {svc_name} into {src_file}."
                    )
                elif u_layer == "Presentation" and v_layer == "Repository":
                    fix_msg = (
                        f"Remove direct repository import '{ev_str}' at {src_file}:{line_nums[0]}. "
                        f"Inject {svc_name} from services/ into {src_file} and delegate repository calls through the Service layer."
                    )
                else:
                    fix_msg = (
                        f"Remove disallowed dependency '{ev_str}' at {src_file}:{line_nums[0]} "
                        f"({u_layer} -> {v_layer}). Allowed targets for {u_layer}: {allowed_targets or 'none'}."
                    )

                violations.append(
                    {
                        "violation_id": next_id("DIR"),
                        "category": "Direct Layering Violation",
                        "severity": "CRITICAL",
                        "violated_rule": f"LAYER_DEPENDENCY_{u_layer.upper()}_TO_{v_layer.upper()}",
                        "source_file": src_file,
                        "source_module": u,
                        "line_numbers": line_nums,
                        "target_file": tgt_file,
                        "target_module": v,
                        "architectural_trace": f"{u} ({u_layer}) -> {v} ({v_layer})",
                        "path_nodes": [u, v],
                        "deterministic_fix": fix_msg,
                        "confidence": 1.0,
                    }
                )

        # ------------------------------------------------------------------
        # 3. Circular Dependencies (CRITICAL) via simple_cycles
        # ------------------------------------------------------------------
        cycles = find_simple_cycles(graph)
        cyclic_nodes: set[str] = set()
        for cycle in cycles:
            if not cycle:
                continue
            # Only report cycles across internal modules
            if any(graph.nodes[n].get("is_external", False) for n in cycle):
                continue
            cyclic_nodes.update(cycle)
            closed_cycle = cycle + [cycle[0]]
            cycle_lines: list[int] = []
            for idx in range(len(cycle)):
                a, b = cycle[idx], cycle[(idx + 1) % len(cycle)]
                violating_edges.add((a, b))
                edata = graph.get_edge_data(a, b) or {}
                cycle_lines.extend(edata.get("line_numbers", []))
            cycle_lines = sorted(set(cycle_lines)) or [1]
            src_mod = cycle[0]
            tgt_mod = cycle[-1]
            src_file = graph.nodes[src_mod].get("file_path", src_mod)
            tgt_file = graph.nodes[tgt_mod].get("file_path", tgt_mod)
            trace = " -> ".join(closed_cycle)

            violations.append(
                {
                    "violation_id": next_id("CYC"),
                    "category": "Circular Dependency",
                    "severity": "CRITICAL",
                    "violated_rule": "ACYCLIC_DEPENDENCIES_PRINCIPLE",
                    "source_file": src_file,
                    "source_module": src_mod,
                    "line_numbers": cycle_lines,
                    "target_file": tgt_file,
                    "target_module": tgt_mod,
                    "architectural_trace": trace,
                    "path_nodes": closed_cycle,
                    "deterministic_fix": (
                        f"Break import cycle ({trace}) involving lines {cycle_lines}. Extract shared contracts "
                        f"or types into a lower-tier Utility/Protocol module or invert control by injecting "
                        f"the dependency through __init__ instead of importing at module scope in {src_file}."
                    ),
                    "confidence": 1.0,
                }
            )

        # ------------------------------------------------------------------
        # 4. Security Guardrail Bypass (HIGH)
        # ------------------------------------------------------------------
        target_files = set(security_cfg.get("target_files", []))
        required_dec = security_cfg.get("required_decorator", "require_auth")
        exempt_prefix = security_cfg.get("exempt_prefix", "public_")

        parsed_modules = summary.get("parsed_modules", {})
        for mod_name in sorted(parsed_modules.keys()):
            mod_info = parsed_modules[mod_name]
            if mod_info.get("layer") != "Presentation":
                continue
            rel_path = mod_info["rel_path"]
            fname = os.path.basename(rel_path)
            if target_files and fname not in target_files and rel_path not in target_files:
                continue

            for fn in mod_info.get("functions", []):
                if not fn.get("is_route"):
                    continue
                fn_name = fn["name"]
                if exempt_prefix and fn_name.startswith(exempt_prefix):
                    continue
                decs = fn.get("decorators", [])
                has_required = any(
                    d == required_dec or d.endswith(f".{required_dec}")
                    for d in decs
                )
                if not has_required:
                    violations.append(
                        {
                            "violation_id": next_id("SEC"),
                            "category": "Security Guardrail Bypass",
                            "severity": "HIGH",
                            "violated_rule": f"REQUIRE_DECORATOR_{required_dec.upper()}",
                            "source_file": rel_path,
                            "source_module": mod_name,
                            "line_numbers": [fn["start_line"]],
                            "target_file": f"function:{fn_name}",
                            "target_module": fn_name,
                            "architectural_trace": f"{rel_path}:{fn['start_line']} def {fn_name}() missing @{required_dec}",
                            "path_nodes": [mod_name],
                            "deterministic_fix": (
                                f"Add '@{required_dec}' immediately below the route decorator on function "
                                f"'{fn_name}' at {rel_path}:{fn['start_line']} (or rename to '{exempt_prefix}{fn_name}' "
                                f"if intentionally unauthenticated)."
                            ),
                            "confidence": 1.0,
                        }
                    )

        # ------------------------------------------------------------------
        # 5. Structural Technical Debt (MEDIUM)
        # ------------------------------------------------------------------
        for mod_name in sorted(parsed_modules.keys()):
            mod_info = parsed_modules[mod_name]
            rel_path = mod_info["rel_path"]
            node_attrs = graph.nodes[mod_name]

            for fn in mod_info.get("functions", []):
                cc = fn["cyclomatic_complexity"]
                if cc > max_cc:
                    violations.append(
                        {
                            "violation_id": next_id("DEBT"),
                            "category": "Structural Technical Debt",
                            "severity": "MEDIUM",
                            "violated_rule": f"MAX_CYCLOMATIC_COMPLEXITY_{max_cc}",
                            "source_file": rel_path,
                            "source_module": mod_name,
                            "line_numbers": [fn["start_line"]],
                            "target_file": f"function:{fn['qualified_name']}",
                            "target_module": fn["qualified_name"],
                            "architectural_trace": (
                                f"{rel_path}:{fn['start_line']} {fn['qualified_name']}() "
                                f"McCabe CC={cc} > threshold {max_cc}"
                            ),
                            "path_nodes": [mod_name],
                            "deterministic_fix": (
                                f"Decompose '{fn['qualified_name']}' at {rel_path}:{fn['start_line']} "
                                f"(CC={cc}, threshold={max_cc}) into cohesive single-responsibility helper "
                                f"methods with early-return guard clauses to bring CC <= {max_cc}."
                            ),
                            "confidence": 1.0,
                        }
                    )

            ce = int(node_attrs.get("ce", 0))
            ca = int(node_attrs.get("ca", 0))
            instability = float(node_attrs.get("instability", 0.0))

            if ce > max_fan_out:
                violations.append(
                    {
                        "violation_id": next_id("DEBT"),
                        "category": "Structural Technical Debt",
                        "severity": "MEDIUM",
                        "violated_rule": f"MAX_FAN_OUT_{max_fan_out}",
                        "source_file": rel_path,
                        "source_module": mod_name,
                        "line_numbers": [1],
                        "target_file": rel_path,
                        "target_module": mod_name,
                        "architectural_trace": f"{mod_name} efferent coupling C_e={ce} > threshold {max_fan_out}",
                        "path_nodes": [mod_name],
                        "deterministic_fix": (
                            f"Split responsibilities in {rel_path} (fan-out C_e={ce} > {max_fan_out}) into "
                            f"focused domain modules or introduce a facade service to reduce outgoing coupling."
                        ),
                        "confidence": 1.0,
                    }
                )

            if ca >= min_fan_in and instability > max_instability:
                violations.append(
                    {
                        "violation_id": next_id("DEBT"),
                        "category": "Structural Technical Debt",
                        "severity": "MEDIUM",
                        "violated_rule": f"MAX_CORE_INSTABILITY_{max_instability}",
                        "source_file": rel_path,
                        "source_module": mod_name,
                        "line_numbers": [1],
                        "target_file": rel_path,
                        "target_module": mod_name,
                        "architectural_trace": (
                            f"Core module {mod_name} (C_a={ca}, C_e={ce}) instability I={instability:.3f} > {max_instability}"
                        ),
                        "path_nodes": [mod_name],
                        "deterministic_fix": (
                            f"Stabilize core module {rel_path} (C_a={ca}, I={instability:.3f} > {max_instability}) "
                            f"by removing outgoing concrete dependencies or introducing abstract interfaces."
                        ),
                        "confidence": 1.0,
                    }
                )

        # ------------------------------------------------------------------
        # Composite Architectural Drift Index (ADI in [0.000, 1.000])
        # ------------------------------------------------------------------
        internal_nodes = [
            n for n, d in graph.nodes(data=True) if not d.get("is_external", False)
        ]
        v_count = max(1, len(internal_nodes))
        w_violations = sum(SEVERITY_WEIGHTS.get(v["severity"], 0.2) for v in violations)

        core_nodes = [
            n for n in internal_nodes if int(graph.nodes[n].get("ca", 0)) >= min_fan_in
        ]
        if core_nodes:
            mean_core_instability = sum(
                float(graph.nodes[n].get("instability", 0.0)) for n in core_nodes
            ) / len(core_nodes)
        else:
            service_repo_nodes = [
                n
                for n in internal_nodes
                if graph.nodes[n].get("layer") in {"Service", "Repository"}
            ]
            mean_core_instability = (
                sum(float(graph.nodes[n].get("instability", 0.0)) for n in service_repo_nodes)
                / len(service_repo_nodes)
                if service_repo_nodes
                else 0.0
            )

        term_violations = 0.45 * (w_violations / v_count)
        term_instability = 0.30 * mean_core_instability
        term_cycles = 0.25 * (len(cyclic_nodes) / v_count)
        adi_score = round(min(1.0, term_violations + term_instability + term_cycles), 3)

        # Build serialized graph JSON for frontend visualization
        nodes_json = []
        for node_id in sorted(graph.nodes()):
            attrs = graph.nodes[node_id]
            nodes_json.append(
                {
                    "id": node_id,
                    "label": os.path.basename(attrs.get("file_path", node_id)),
                    "file_path": attrs.get("file_path", node_id),
                    "layer": attrs.get("layer", "Unassigned"),
                    "is_external": bool(attrs.get("is_external", False)),
                    "loc": attrs.get("loc", 0),
                    "ca": attrs.get("ca", 0),
                    "ce": attrs.get("ce", 0),
                    "instability": attrs.get("instability", 0.0),
                    "avg_complexity": attrs.get("avg_complexity", 0.0),
                    "max_complexity": attrs.get("max_complexity", 0),
                    "is_cyclic": node_id in cyclic_nodes,
                }
            )

        edges_json = []
        for u, v, edata in sorted(graph.edges(data=True), key=lambda x: (x[0], x[1])):
            is_violating = (u, v) in violating_edges or (u, v) in transitive_edges
            edges_json.append(
                {
                    "source": u,
                    "target": v,
                    "edge_types": edata.get("edge_types", []),
                    "line_numbers": edata.get("line_numbers", []),
                    "evidence": edata.get("evidence", []),
                    "is_violation": is_violating,
                    "is_transitive_bypass": (u, v) in transitive_edges,
                }
            )

        severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
        category_counts: dict[str, int] = {}
        for v in violations:
            severity_counts[v["severity"]] = severity_counts.get(v["severity"], 0) + 1
            cat = v["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        return {
            "adi_score": adi_score,
            "adi_components": {
                "weighted_violations": round(w_violations, 3),
                "internal_nodes": v_count,
                "mean_core_instability": round(mean_core_instability, 3),
                "cyclic_nodes": len(cyclic_nodes),
                "violation_term": round(term_violations, 3),
                "instability_term": round(term_instability, 3),
                "cycle_term": round(term_cycles, 3),
            },
            "total_violations": len(violations),
            "severity_counts": severity_counts,
            "category_counts": category_counts,
            "violations": violations,
            "graph": {
                "nodes": nodes_json,
                "edges": edges_json,
            },
            "node_metrics": summary.get("node_metrics", []),
            "parse_errors": summary.get("parse_errors", []),
        }
