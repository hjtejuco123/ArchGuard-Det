"""Deterministic Multi-File AST & Call-Graph Extractor for ArchGuard-Det."""

from __future__ import annotations

import ast
import fnmatch
import os
from collections import defaultdict
from typing import Any

try:
    import networkx as nx  # type: ignore
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


class _FallbackDiGraph:
    """Deterministic stdlib DiGraph fallback mirroring the NetworkX DiGraph API."""

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._succ: dict[str, dict[str, dict[str, Any]]] = {}
        self._pred: dict[str, dict[str, dict[str, Any]]] = {}

    def add_node(self, node_for_adding: str, **attr: Any) -> None:
        if node_for_adding not in self._nodes:
            self._nodes[node_for_adding] = {}
            self._succ[node_for_adding] = {}
            self._pred[node_for_adding] = {}
        self._nodes[node_for_adding].update(attr)

    def add_edge(self, u: str, v: str, **attr: Any) -> None:
        if u not in self._nodes:
            self.add_node(u)
        if v not in self._nodes:
            self.add_node(v)
        if v not in self._succ[u]:
            self._succ[u][v] = {}
            self._pred[v][u] = self._succ[u][v]
        self._succ[u][v].update(attr)

    def has_edge(self, u: str, v: str) -> bool:
        return u in self._succ and v in self._succ[u]

    def get_edge_data(self, u: str, v: str, default: Any = None) -> Any:
        if self.has_edge(u, v):
            return self._succ[u][v]
        return default

    @property
    def nodes(self) -> "_NodeView":
        return _NodeView(self._nodes)

    @property
    def edges(self) -> "_EdgeView":
        return _EdgeView(self._succ)

    def successors(self, n: str) -> list[str]:
        return list(self._succ.get(n, {}).keys())

    def predecessors(self, n: str) -> list[str]:
        return list(self._pred.get(n, {}).keys())

    def in_degree(self, n: str) -> int:
        return len(self._pred.get(n, {}))

    def out_degree(self, n: str) -> int:
        return len(self._succ.get(n, {}))

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def number_of_edges(self) -> int:
        return sum(len(targets) for targets in self._succ.values())

    def __contains__(self, n: str) -> bool:
        return n in self._nodes

    def __iter__(self):
        return iter(self._nodes)


class _NodeView:
    def __init__(self, nodes: dict[str, dict[str, Any]]) -> None:
        self._nodes = nodes

    def __getitem__(self, n: str) -> dict[str, Any]:
        return self._nodes[n]

    def __call__(self, data: bool = False):
        if data:
            return list(self._nodes.items())
        return list(self._nodes.keys())

    def __iter__(self):
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)


class _EdgeView:
    def __init__(self, succ: dict[str, dict[str, dict[str, Any]]]) -> None:
        self._succ = succ

    def __call__(self, data: bool = False):
        result = []
        for u, targets in self._succ.items():
            for v, attrs in targets.items():
                if data:
                    result.append((u, v, attrs))
                else:
                    result.append((u, v))
        return result

    def __iter__(self):
        for u, targets in self._succ.items():
            for v in targets:
                yield (u, v)


def create_digraph() -> Any:
    """Create a NetworkX DiGraph, or stdlib fallback when NetworkX is absent."""
    if HAS_NETWORKX:
        return nx.DiGraph()
    return _FallbackDiGraph()


def find_all_simple_paths(graph: Any, source: str, target: str, cutoff: int = 4) -> list[list[str]]:
    """Deterministic equivalent of nx.all_simple_paths."""
    if HAS_NETWORKX:
        if source not in graph or target not in graph:
            return []
        return list(nx.all_simple_paths(graph, source, target, cutoff=cutoff))

    if source not in graph or target not in graph:
        return []
    paths: list[list[str]] = []

    def dfs(current: str, visited: set[str], path: list[str]) -> None:
        if len(path) - 1 >= cutoff:
            return
        for nxt in sorted(graph.successors(current)):
            if nxt == target:
                paths.append(path + [nxt])
            elif nxt not in visited:
                visited.add(nxt)
                dfs(nxt, visited, path + [nxt])
                visited.remove(nxt)

    dfs(source, {source}, [source])
    return paths


def find_simple_cycles(graph: Any) -> list[list[str]]:
    """Deterministic equivalent of nx.simple_cycles using Johnson's algorithm."""
    if HAS_NETWORKX:
        return sorted(nx.simple_cycles(graph), key=lambda c: (len(c), c))

    nodes = sorted(graph.nodes())
    cycles: list[list[str]] = []

    def _tarjan_sccs(sub_nodes: set[str]) -> list[list[str]]:
        index = 0
        indices: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        stack: list[str] = []
        on_stack: set[str] = set()
        sccs: list[list[str]] = []

        def strongconnect(v: str) -> None:
            nonlocal index
            indices[v] = index
            lowlink[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w in sorted(graph.successors(v)):
                if w not in sub_nodes:
                    continue
                if w not in indices:
                    strongconnect(w)
                    lowlink[v] = min(lowlink[v], lowlink[w])
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])

            if lowlink[v] == indices[v]:
                scc: list[str] = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

        for v in sorted(sub_nodes):
            if v not in indices:
                strongconnect(v)
        return sccs

    start_index = 0
    while start_index < len(nodes):
        sub_nodes = set(nodes[start_index:])
        sccs = [scc for scc in _tarjan_sccs(sub_nodes) if len(scc) > 1 or (len(scc) == 1 and graph.has_edge(scc[0], scc[0]))]
        if not sccs:
            break
        min_scc = min(sccs, key=lambda comp: min(nodes.index(n) for n in comp))
        start_node = min(min_scc, key=lambda n: nodes.index(n))
        start_index = nodes.index(start_node)
        scc_set = set(min_scc)

        blocked: set[str] = set()
        closed: set[str] = set()
        block_map: dict[str, set[str]] = defaultdict(set)
        path: list[str] = []

        def unblock(u: str) -> None:
            stack_u = [u]
            while stack_u:
                curr = stack_u.pop()
                if curr in blocked:
                    blocked.remove(curr)
                    stack_u.extend(block_map.pop(curr, set()))

        def circuit(v: str) -> bool:
            found = False
            path.append(v)
            blocked.add(v)
            for w in sorted(graph.successors(v)):
                if w not in scc_set:
                    continue
                if w == start_node:
                    cycles.append(list(path))
                    closed.update(path)
                    found = True
                elif w not in blocked:
                    if circuit(w):
                        found = True
            if found:
                unblock(v)
            else:
                for w in sorted(graph.successors(v)):
                    if w in scc_set:
                        block_map[w].add(v)
            path.pop()
            return found

        circuit(start_node)
        start_index += 1

    return sorted(cycles, key=lambda c: (len(c), c))


IGNORED_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}
EXTERNAL_DB_MODULES = {"sqlite3", "sqlalchemy", "psycopg2", "pymysql", "mysql", "pymongo", "redis"}


class _ComplexityVisitor(ast.NodeVisitor):
    """Compute exact McCabe Cyclomatic Complexity for a single function body."""

    def __init__(self) -> None:
        self.complexity = 1

    def visit_If(self, node: ast.If) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.complexity += max(0, len(node.values) - 1)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.complexity += 1 + len(node.ifs)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Nested functions have their own independent McCabe complexity
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return


def _decorator_name(dec: ast.AST) -> str:
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        base = _decorator_name(dec.value)
        return f"{base}.{dec.attr}" if base else dec.attr
    if isinstance(dec, ast.Call):
        return _decorator_name(dec.func)
    return ast.dump(dec)


def _attr_chain(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return _attr_chain(node.value) + [node.attr]
    return []


class _ModuleASTVisitor(ast.NodeVisitor):
    """Extracts imports, function metrics, and call-graph references from a single Python AST."""

    def __init__(self, source_lines: list[str]) -> None:
        self.source_lines = source_lines
        self.scope_depth = 0
        self.imports: list[dict[str, Any]] = []
        self.functions: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.alias_to_module: dict[str, str] = {}
        self.symbol_to_module: dict[str, str] = {}
        self.self_attr_to_symbol: dict[str, str] = {}
        self.class_stack: list[str] = []

    def _line_text(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1].strip()
        return ""

    def visit_Import(self, node: ast.Import) -> None:
        scope = "top_level" if self.scope_depth == 0 else "local"
        for alias in node.names:
            bound_name = alias.asname or alias.name.split(".")[0]
            self.alias_to_module[bound_name] = alias.name
            self.imports.append(
                {
                    "kind": "import",
                    "module": alias.name,
                    "symbol": None,
                    "alias": bound_name,
                    "level": 0,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                    "scope": scope,
                    "evidence": self._line_text(node.lineno),
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        scope = "top_level" if self.scope_depth == 0 else "local"
        module_name = node.module or ""
        for alias in node.names:
            bound_name = alias.asname or alias.name
            if module_name:
                self.symbol_to_module[bound_name] = f"{module_name}.{alias.name}" if alias.name != "*" else module_name
            self.imports.append(
                {
                    "kind": "from",
                    "module": module_name,
                    "symbol": alias.name,
                    "alias": bound_name,
                    "level": node.level or 0,
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                    "scope": scope,
                    "evidence": self._line_text(node.lineno),
                }
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1
        self.class_stack.pop()

    def visit_Assign(self, node: ast.Assign) -> None:
        # Detect self.service = service or OrderService() patterns
        if isinstance(node.value, ast.Call):
            target_names = _attr_chain(node.value.func)
            resolved_cls = target_names[-1] if target_names else None
            if resolved_cls:
                for tgt in node.targets:
                    chain = _attr_chain(tgt)
                    if len(chain) == 2 and chain[0] == "self":
                        self.self_attr_to_symbol[chain[1]] = resolved_cls
        elif isinstance(node.value, ast.BoolOp) and isinstance(node.value.op, ast.Or):
            for val in node.value.values:
                if isinstance(val, ast.Call):
                    target_names = _attr_chain(val.func)
                    if target_names:
                        for tgt in node.targets:
                            chain = _attr_chain(tgt)
                            if len(chain) == 2 and chain[0] == "self":
                                self.self_attr_to_symbol[chain[1]] = target_names[-1]
        self.generic_visit(node)

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        decorators = [_decorator_name(d) for d in node.decorator_list]
        is_route = any(
            d == "route" or d.endswith(".route") or d.endswith(".get") or d.endswith(".post") or d.endswith(".put") or d.endswith(".delete")
            for d in decorators
        )
        args = node.args
        param_count = (
            len(args.posonlyargs)
            + len(args.args)
            + len(args.kwonlyargs)
            + (1 if args.vararg else 0)
            + (1 if args.kwarg else 0)
        )

        comp_visitor = _ComplexityVisitor()
        for stmt in node.body:
            comp_visitor.visit(stmt)

        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        self.functions.append(
            {
                "name": node.name,
                "qualified_name": f"{self.class_stack[-1]}.{node.name}" if self.class_stack else node.name,
                "is_async": is_async,
                "start_line": node.lineno,
                "end_line": end_line,
                "loc": max(1, end_line - node.lineno + 1),
                "decorators": decorators,
                "is_route": is_route,
                "param_count": param_count,
                "cyclomatic_complexity": comp_visitor.complexity,
            }
        )

        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_func(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_func(node, is_async=True)

    def visit_Call(self, node: ast.Call) -> None:
        chain = _attr_chain(node.func)
        if chain:
            self.calls.append(
                {
                    "chain": chain,
                    "call_expr": ".".join(chain),
                    "lineno": node.lineno,
                    "col_offset": node.col_offset,
                    "evidence": self._line_text(node.lineno),
                }
            )
        self.generic_visit(node)


class RepositoryGraphBuilder:
    """Scans a Python repository and constructs an AST-grounded NetworkX dependency graph."""

    def __init__(self, rules: dict[str, Any] | None = None) -> None:
        self.rules = rules or {}

    def classify_layer(self, rel_file_path: str) -> str:
        """Map a relative file path (using forward slashes) to an architectural layer."""
        norm_path = rel_file_path.replace("\\", "/").lstrip("./")
        layers_cfg = self.rules.get("layers", {})

        # Exact filename matches first, then directory/glob matches
        for layer_name, patterns in layers_cfg.items():
            for pat in patterns:
                if norm_path == pat or os.path.basename(norm_path) == pat:
                    return layer_name

        for layer_name, patterns in layers_cfg.items():
            for pat in patterns:
                if fnmatch.fnmatch(norm_path, pat):
                    return layer_name
                dir_prefix = pat.rstrip("*").rstrip("/")
                if dir_prefix and norm_path.startswith(f"{dir_prefix}/"):
                    return layer_name

        # Sensible architectural fallback conventions if custom repo uses standard names
        lower = norm_path.lower()
        if lower.startswith("routes/") or lower.startswith("controllers/") or lower.startswith("api/"):
            return "Presentation"
        if lower.startswith("services/"):
            return "Service"
        if lower.startswith("repositories/") or lower.startswith("dal/") or lower.startswith("models/"):
            return "Repository"
        if lower.startswith("utils/") or lower.startswith("helpers/") or lower.startswith("common/"):
            return "Utility"
        if lower in {"app.py", "main.py", "wsgi.py", "config.py", "settings.py"}:
            return "Entrypoint"
        return "Unassigned"

    def _discover_python_files(self, repo_path: str) -> list[tuple[str, str, str]]:
        """Return sorted list of (abs_path, rel_path, module_name) for all .py files."""
        abs_root = os.path.abspath(repo_path)
        discovered: list[tuple[str, str, str]] = []

        for current_root, dirs, files in os.walk(abs_root):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS and not d.startswith("."))
            for fname in sorted(files):
                if not fname.endswith(".py"):
                    continue
                abs_file = os.path.join(current_root, fname)
                rel_path = os.path.relpath(abs_file, abs_root).replace("\\", "/")
                no_ext = rel_path[:-3]
                if no_ext.endswith("/__init__"):
                    mod_name = no_ext[:-9].replace("/", ".")
                elif no_ext == "__init__":
                    mod_name = os.path.basename(abs_root)
                else:
                    mod_name = no_ext.replace("/", ".")
                if mod_name:
                    discovered.append((abs_file, rel_path, mod_name))
        return discovered

    @staticmethod
    def _resolve_relative_base(current_module: str, is_package_init: bool, level: int, module_part: str) -> str:
        if level == 0:
            return module_part
        parts = current_module.split(".")
        if not is_package_init:
            parts = parts[:-1]
        up = max(0, level - 1)
        if up > 0:
            parts = parts[:-up] if up < len(parts) else []
        if module_part:
            parts.extend(module_part.split("."))
        return ".".join(p for p in parts if p)

    def _match_target_module(
        self,
        raw_module: str,
        symbol: str | None,
        internal_modules: set[str],
        forbidden_targets: set[str],
    ) -> tuple[str | None, str]:
        """Resolve an import/reference to (target_node_id, target_kind['internal'|'external_db'|'external'])."""
        if not raw_module:
            return None, "external"

        candidates = []
        if symbol and symbol != "*":
            candidates.append(f"{raw_module}.{symbol}")
        candidates.append(raw_module)

        for cand in candidates:
            if cand in internal_modules:
                return cand, "internal"
            # Handle src.<mod> or package.<mod> prefixes if present
            for internal in sorted(internal_modules):
                if cand.endswith(f".{internal}") or internal.endswith(f".{cand}"):
                    return internal, "internal"

        top_pkg = raw_module.split(".")[0]
        if top_pkg in EXTERNAL_DB_MODULES or top_pkg in forbidden_targets:
            return top_pkg, "external_db"

        return None, "external"

    def build_graph(self, repo_path: str) -> tuple[Any, dict[str, Any]]:
        """Parse repository ASTs and return (NetworkX DiGraph, structured metadata summary)."""
        abs_root = os.path.abspath(repo_path)
        files = self._discover_python_files(abs_root)
        internal_modules = {mod for _, _, mod in files}

        forbidden_all: set[str] = set(EXTERNAL_DB_MODULES)
        for items in self.rules.get("forbidden_direct_imports_by_layer", {}).values():
            forbidden_all.update(items)

        graph = create_digraph()
        parsed_modules: dict[str, dict[str, Any]] = {}
        parse_errors: list[dict[str, Any]] = []

        # Pass 1: Parse AST for every Python file and register internal nodes
        for abs_file, rel_path, mod_name in files:
            with open(abs_file, "r", encoding="utf-8", errors="replace") as fh:
                source_text = fh.read()
            source_lines = source_text.splitlines()
            loc = len([ln for ln in source_lines if ln.strip()])

            try:
                tree = ast.parse(source_text, filename=rel_path)
            except SyntaxError as exc:
                parse_errors.append(
                    {"file": rel_path, "lineno": exc.lineno or 1, "message": str(exc)}
                )
                continue

            visitor = _ModuleASTVisitor(source_lines)
            visitor.visit(tree)

            complexities = [f["cyclomatic_complexity"] for f in visitor.functions]
            avg_comp = round(sum(complexities) / len(complexities), 2) if complexities else 1.0
            max_comp = max(complexities) if complexities else 1
            layer = self.classify_layer(rel_path)

            node_attrs = {
                "module_name": mod_name,
                "file_path": rel_path,
                "layer": layer,
                "loc": loc,
                "avg_complexity": avg_comp,
                "max_complexity": max_comp,
                "functions": visitor.functions,
                "is_external": False,
            }
            graph.add_node(mod_name, **node_attrs)

            parsed_modules[mod_name] = {
                "abs_file": abs_file,
                "rel_path": rel_path,
                "is_init": rel_path.endswith("__init__.py"),
                "visitor": visitor,
                "imports": visitor.imports,
                "calls": visitor.calls,
                "functions": visitor.functions,
                "layer": layer,
                "loc": loc,
            }

        # Helper to merge edge metadata deterministically
        def record_edge(
            src: str,
            dst: str,
            edge_type: str,
            lineno: int,
            scope: str,
            evidence: str,
        ) -> None:
            if src == dst:
                return
            if not graph.has_edge(src, dst):
                graph.add_edge(
                    src,
                    dst,
                    edge_types=[edge_type],
                    line_numbers=[lineno],
                    scopes=[scope],
                    evidence=[evidence] if evidence else [],
                )
            else:
                data = graph.get_edge_data(src, dst)
                if edge_type not in data["edge_types"]:
                    data["edge_types"].append(edge_type)
                if lineno not in data["line_numbers"]:
                    data["line_numbers"].append(lineno)
                    data["line_numbers"].sort()
                if scope not in data["scopes"]:
                    data["scopes"].append(scope)
                if evidence and evidence not in data["evidence"]:
                    data["evidence"].append(evidence)

        # Pass 2: Resolve imports and call expressions to directed graph edges
        for mod_name, mod_info in parsed_modules.items():
            visitor: _ModuleASTVisitor = mod_info["visitor"]
            local_alias_targets: dict[str, str] = {}

            for imp in mod_info["imports"]:
                resolved_base = self._resolve_relative_base(
                    current_module=mod_name,
                    is_package_init=mod_info["is_init"],
                    level=imp["level"],
                    module_part=imp["module"],
                )
                target_id, target_kind = self._match_target_module(
                    raw_module=resolved_base,
                    symbol=imp["symbol"],
                    internal_modules=internal_modules,
                    forbidden_targets=forbidden_all,
                )
                if target_id is None:
                    continue

                if target_kind == "external_db" and target_id not in graph:
                    graph.add_node(
                        target_id,
                        module_name=target_id,
                        file_path=f"external:{target_id}",
                        layer="ExternalDB",
                        loc=0,
                        avg_complexity=0.0,
                        max_complexity=0,
                        functions=[],
                        is_external=True,
                    )

                local_alias_targets[imp["alias"]] = target_id
                if imp["symbol"]:
                    local_alias_targets[imp["symbol"]] = target_id

                record_edge(
                    src=mod_name,
                    dst=target_id,
                    edge_type="import",
                    lineno=imp["lineno"],
                    scope=imp["scope"],
                    evidence=imp["evidence"],
                )

            # Resolve outgoing call expressions: module.func(), imported_symbol(), self.service.method()
            for call in mod_info["calls"]:
                chain = call["chain"]
                resolved_target: str | None = None

                if chain[0] in local_alias_targets:
                    resolved_target = local_alias_targets[chain[0]]
                elif len(chain) >= 2 and chain[0] == "self" and chain[1] in visitor.self_attr_to_symbol:
                    cls_sym = visitor.self_attr_to_symbol[chain[1]]
                    if cls_sym in local_alias_targets:
                        resolved_target = local_alias_targets[cls_sym]

                if resolved_target and resolved_target in graph:
                    record_edge(
                        src=mod_name,
                        dst=resolved_target,
                        edge_type="call",
                        lineno=call["lineno"],
                        scope="call",
                        evidence=call["evidence"],
                    )

        # Pass 3: Compute Robert C. Martin Coupling & Instability Metrics per node
        node_metrics: list[dict[str, Any]] = []
        for node_id in sorted(graph.nodes()):
            attrs = graph.nodes[node_id]
            ca = int(graph.in_degree(node_id))
            ce = int(graph.out_degree(node_id))
            denom = ca + ce
            instability = round(ce / denom, 3) if denom > 0 else 0.0
            attrs["ca"] = ca
            attrs["ce"] = ce
            attrs["instability"] = instability

            node_metrics.append(
                {
                    "module_name": node_id,
                    "file_path": attrs.get("file_path", node_id),
                    "layer": attrs.get("layer", "Unassigned"),
                    "is_external": bool(attrs.get("is_external", False)),
                    "loc": attrs.get("loc", 0),
                    "ca": ca,
                    "ce": ce,
                    "instability": instability,
                    "avg_complexity": attrs.get("avg_complexity", 0.0),
                    "max_complexity": attrs.get("max_complexity", 0),
                    "function_count": len(attrs.get("functions", [])),
                }
            )

        summary = {
            "repo_path": abs_root,
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
            "internal_file_count": len(parsed_modules),
            "parsed_modules": parsed_modules,
            "node_metrics": node_metrics,
            "parse_errors": parse_errors,
            "using_networkx": HAS_NETWORKX,
        }
        return graph, summary
