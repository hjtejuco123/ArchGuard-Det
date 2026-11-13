import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Check,
  Copy,
  Download,
  FileCode2,
  FlaskConical,
  FolderOpen,
  Play,
  RefreshCw,
  Save,
  Search,
  Upload,
} from 'lucide-react';
import { DependencyGraph } from './components/DependencyGraph';
import type { AuditResult, BenchmarkResult } from './types';

type TabKey = 'spec' | 'findings' | 'benchmark' | 'export';

const CATEGORIES = [
  'Direct Layering Violation',
  'Transitive Layer Bypass',
  'Circular Dependency',
  'Security Guardrail Bypass',
  'Structural Technical Debt',
];

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      const commaIdx = result.indexOf(',');
      resolve(commaIdx >= 0 ? result.slice(commaIdx + 1) : result);
    };
    reader.onerror = () => reject(new Error('Failed to read ZIP file'));
    reader.readAsDataURL(file);
  });
}

export default function App() {
  const [activeTab, setActiveTab] = useState<TabKey>('spec');
  const [repoPath, setRepoPath] = useState('./sample_repo');
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [yamlText, setYamlText] = useState('');
  const [rulesNotice, setRulesNotice] = useState<string | null>(null);

  const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkResult | null>(null);
  const [findingsSource, setFindingsSource] = useState<'audited' | 'drifted'>('audited');

  const [loadingAudit, setLoadingAudit] = useState(false);
  const [loadingBenchmark, setLoadingBenchmark] = useState(false);
  const [savingRules, setSavingRules] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [categoryFilter, setCategoryFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [copiedLatex, setCopiedLatex] = useState(false);

  const loadRules = useCallback(async () => {
    setErrorMsg(null);
    try {
      const res = await fetch('/api/rules');
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to load architecture_rules.yaml');
      setYamlText(data.yaml_text || '');
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to load YAML specification');
    }
  }, []);

  const saveRules = useCallback(async () => {
    setErrorMsg(null);
    setRulesNotice(null);
    setSavingRules(true);
    try {
      const res = await fetch('/api/rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'save', yaml_text: yamlText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to save architecture_rules.yaml');
      setRulesNotice('Saved architecture_rules.yaml');
      setTimeout(() => setRulesNotice(null), 3000);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Failed to save rules');
    } finally {
      setSavingRules(false);
    }
  }, [yamlText]);

  const runAudit = useCallback(
    async (switchTab = true) => {
      setErrorMsg(null);
      setLoadingAudit(true);
      try {
        let zipBase64: string | undefined;
        if (zipFile) {
          zipBase64 = await fileToBase64(zipFile);
        }
        const res = await fetch('/api/audit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            repo_path: repoPath.trim() || './sample_repo',
            rules_yaml: yamlText,
            zip_base64: zipBase64,
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Audit execution failed');
        setAuditResult(data);
        setFindingsSource('audited');
        if (switchTab) setActiveTab('findings');
      } catch (err: any) {
        setErrorMsg(err?.message || 'Audit execution failed');
      } finally {
        setLoadingAudit(false);
      }
    },
    [repoPath, zipFile, yamlText]
  );

  const runBenchmark = useCallback(async () => {
    setErrorMsg(null);
    setLoadingBenchmark(true);
    try {
      const res = await fetch('/api/benchmark/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rules_yaml: yamlText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Benchmark execution failed');
      setBenchmarkResult(data);
    } catch (err: any) {
      setErrorMsg(err?.message || 'Benchmark execution failed');
    } finally {
      setLoadingBenchmark(false);
    }
  }, [yamlText]);

  useEffect(() => {
    (async () => {
      try {
        const [rulesRes, histRes] = await Promise.all([
          fetch('/api/rules'),
          fetch('/api/history'),
        ]);
        const rulesData = await rulesRes.json();
        if (rulesRes.ok && rulesData.yaml_text) {
          setYamlText(rulesData.yaml_text);
        }
        const histData = await histRes.json();
        if (histRes.ok) {
          if (histData.latest_benchmark) {
            setBenchmarkResult(histData.latest_benchmark);
          }
          if (histData.latest_audit) {
            setAuditResult(histData.latest_audit);
            return;
          }
        }
        // Run initial clean baseline audit on first visit
        const initAudit = await fetch('/api/audit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo_path: './sample_repo' }),
        });
        const initData = await initAudit.json();
        if (initAudit.ok) setAuditResult(initData);
      } catch {
        // Ignore silent bootstrap errors; user can trigger manually
      }
    })();
  }, []);

  const activeFindings = useMemo(() => {
    if (findingsSource === 'drifted' && benchmarkResult?.proposed_graph) {
      const proposed = benchmarkResult.methods[benchmarkResult.methods.length - 1];
      return {
        label: 'Synthetic Drifted Workspace (10 Injected Violations)',
        adiScore: benchmarkResult.proposed_adi_score,
        adiComponents: benchmarkResult.proposed_adi_components,
        totalViolations: benchmarkResult.proposed_violations.length,
        severityCounts: benchmarkResult.proposed_severity_counts || { CRITICAL: 5, HIGH: 4, MEDIUM: 1 },
        nodeCount: benchmarkResult.proposed_graph.nodes.length,
        edgeCount: benchmarkResult.proposed_graph.edges.length,
        executionMs: proposed?.latency_ms ?? 0,
        graph: benchmarkResult.proposed_graph,
        violations: benchmarkResult.proposed_violations,
        nodeMetrics: benchmarkResult.proposed_node_metrics || [],
      };
    }
    if (!auditResult) return null;
    return {
      label: auditResult.repo_path,
      adiScore: auditResult.adi_score,
      adiComponents: auditResult.adi_components,
      totalViolations: auditResult.total_violations,
      severityCounts: auditResult.severity_counts,
      nodeCount: auditResult.node_count,
      edgeCount: auditResult.edge_count,
      executionMs: auditResult.execution_ms,
      graph: auditResult.graph,
      violations: auditResult.violations,
      nodeMetrics: auditResult.node_metrics,
    };
  }, [auditResult, benchmarkResult, findingsSource]);

  const filteredViolations = useMemo(() => {
    const items = activeFindings?.violations || [];
    const q = searchQuery.trim().toLowerCase();
    return items.filter((v) => {
      if (severityFilter !== 'ALL' && v.severity !== severityFilter) return false;
      if (categoryFilter !== 'ALL' && v.category !== categoryFilter) return false;
      if (q) {
        const hay = `${v.violation_id} ${v.violated_rule} ${v.source_file} ${v.architectural_trace} ${v.deterministic_fix}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [activeFindings, severityFilter, categoryFilter, searchQuery]);

  const handleCopyLatex = async () => {
    if (!benchmarkResult?.latex_content) return;
    await navigator.clipboard.writeText(benchmarkResult.latex_content);
    setCopiedLatex(true);
    setTimeout(() => setCopiedLatex(false), 2000);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      {/* Three-Zone Top Bar */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1360px] items-center justify-between gap-8 px-6 py-3.5">
          <a
            href="#top"
            onClick={(e) => {
              e.preventDefault();
              setActiveTab('spec');
            }}
            className="text-lg font-bold tracking-tight text-slate-900 whitespace-nowrap shrink-0"
          >
            ArchGuard-Det
          </a>

          <nav className="flex items-center gap-6 overflow-x-auto" aria-label="Workbench sections">
            {(
              [
                ['spec', 'Repository & Spec'],
                ['findings', 'Findings & Graph'],
                ['benchmark', 'Benchmark & Ablation'],
                ['export', 'IEEE Paper Export'],
              ] as const
            ).map(([key, label]) => {
              const active = activeTab === key;
              return (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`py-1.5 text-sm font-medium whitespace-nowrap shrink-0 border-b-2 transition-colors ${
                    active
                      ? 'border-blue-600 text-slate-900'
                      : 'border-transparent text-slate-600 hover:text-slate-900'
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </nav>

          <div className="shrink-0">
            <button
              onClick={() => runAudit(true)}
              disabled={loadingAudit}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-60 transition-colors whitespace-nowrap shrink-0"
            >
              <Play className="h-3.5 w-3.5" />
              {loadingAudit ? 'Auditing...' : 'Run Deterministic Audit'}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1360px] px-6 py-6">
        {errorMsg && (
          <div className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 flex items-center justify-between">
            <span>{errorMsg}</span>
            <button
              onClick={() => setErrorMsg(null)}
              className="text-xs font-medium text-red-700 hover:text-red-900"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* TAB 1: Repository & Architecture Spec */}
        {activeTab === 'spec' && (
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 items-start">
            <div className="lg:col-span-5 space-y-5">
              <section className="rounded-lg border border-slate-200 bg-white p-5">
                <h2 className="text-base font-semibold text-slate-900">
                  Target Python Repository
                </h2>
                <p className="mt-1 text-xs text-slate-500">
                  Point to a local directory or upload a ZIP archive for multi-file AST parsing and NetworkX graph verification.
                </p>

                <div className="mt-4 space-y-4">
                  <div>
                    <label htmlFor="repo-path" className="block text-xs font-medium text-slate-700 mb-1.5">
                      Local Repository Path
                    </label>
                    <div className="relative">
                      <FolderOpen className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                      <input
                        id="repo-path"
                        type="text"
                        value={repoPath}
                        onChange={(e) => {
                          setRepoPath(e.target.value);
                          setZipFile(null);
                        }}
                        className="w-full rounded-lg border border-slate-300 bg-white pl-9 pr-3 py-2 text-sm font-mono text-slate-900 focus:border-blue-600 focus:outline-none"
                        placeholder="./sample_repo"
                      />
                    </div>
                  </div>

                  <div>
                    <label htmlFor="repo-zip" className="block text-xs font-medium text-slate-700 mb-1.5">
                      Or Upload Repository Archive (.zip)
                    </label>
                    <label
                      htmlFor="repo-zip"
                      className="flex cursor-pointer items-center justify-between rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3.5 py-2.5 text-xs text-slate-600 hover:border-slate-400"
                    >
                      <span className="flex items-center gap-2 truncate">
                        <Upload className="h-4 w-4 text-slate-500 shrink-0" />
                        {zipFile ? zipFile.name : 'Choose .zip archive (optional)'}
                      </span>
                      {zipFile && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault();
                            setZipFile(null);
                          }}
                          className="text-slate-500 hover:text-slate-800 ml-2"
                        >
                          Clear
                        </button>
                      )}
                      <input
                        id="repo-zip"
                        type="file"
                        accept=".zip"
                        className="sr-only"
                        onChange={(e) => setZipFile(e.target.files?.[0] || null)}
                      />
                    </label>
                  </div>

                  <button
                    onClick={() => runAudit(true)}
                    disabled={loadingAudit}
                    className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors"
                  >
                    <Play className="h-4 w-4" />
                    {loadingAudit ? 'Running AST-Graph Audit...' : 'Run Deterministic Audit'}
                  </button>
                </div>
              </section>

              <section className="rounded-lg border border-slate-200 bg-white p-5">
                <h2 className="text-base font-semibold text-slate-900">
                  Deterministic Engine Specification
                </h2>
                <div className="mt-3 space-y-2.5 text-xs text-slate-600 leading-relaxed">
                  <p>
                    100% algorithmic verification without LLMs or network calls. Extracts module imports, call-chain targets, function decorators, and McCabe cyclomatic complexity via Python&apos;s <code className="font-mono text-slate-800">ast</code> module.
                  </p>
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 font-mono text-[11px] text-slate-800 tabular-nums">
                    ADI = min(1.0, 0.45·(Wv / |V|) + 0.30·I_core + 0.25·(Cyclic / |V|))
                  </div>
                  <div className="grid grid-cols-2 gap-2 pt-1 text-[11px] text-slate-500">
                    <div>Weights: CRITICAL=1.0, HIGH=0.7</div>
                    <div>MEDIUM=0.4, LOW=0.2</div>
                  </div>
                </div>
              </section>
            </div>

            <section className="lg:col-span-7 rounded-lg border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
                <div className="flex items-center gap-2">
                  <FileCode2 className="h-4 w-4 text-slate-500" />
                  <h2 className="text-sm font-semibold text-slate-900">
                    architecture_rules.yaml
                  </h2>
                  {rulesNotice && (
                    <span className="text-xs font-medium text-emerald-700">{rulesNotice}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={loadRules}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    Reload YAML
                  </button>
                  <button
                    onClick={saveRules}
                    disabled={savingRules}
                    className="inline-flex items-center gap-1.5 rounded-md border border-blue-600 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-100 disabled:opacity-60"
                  >
                    <Save className="h-3.5 w-3.5" />
                    {savingRules ? 'Saving...' : 'Save YAML'}
                  </button>
                </div>
              </div>
              <div className="p-4">
                <textarea
                  value={yamlText}
                  onChange={(e) => setYamlText(e.target.value)}
                  spellCheck={false}
                  aria-label="architecture_rules.yaml editor"
                  className="w-full min-h-[440px] rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100 focus:border-blue-500 focus:outline-none"
                />
              </div>
            </section>
          </div>
        )}

        {/* TAB 2: Audit Findings & Interactive Dependency Graph */}
        {activeTab === 'findings' && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h1 className="text-lg font-semibold text-slate-900">
                  Audit Findings &amp; Layered Dependency Graph
                </h1>
                <p className="text-xs text-slate-500 font-mono">
                  Source: {activeFindings?.label || './sample_repo'}
                </p>
              </div>
              {benchmarkResult?.proposed_graph && (
                <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-white p-1">
                  <button
                    onClick={() => setFindingsSource('audited')}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      findingsSource === 'audited'
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Audited Repository
                  </button>
                  <button
                    onClick={() => setFindingsSource('drifted')}
                    className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      findingsSource === 'drifted'
                        ? 'bg-slate-900 text-white'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    Drifted Benchmark Repo
                  </button>
                </div>
              )}
            </div>

            {/* 4 KPI Summary Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="text-xs font-medium text-slate-500">Architectural Drift Index (ADI)</div>
                <div className="mt-2 text-2xl font-bold font-mono tabular-nums text-slate-900">
                  {activeFindings ? activeFindings.adiScore.toFixed(3) : '0.000'}
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono tabular-nums">
                  {activeFindings?.adiComponents
                    ? `Wv:${activeFindings.adiComponents.weighted_violations} · I_core:${activeFindings.adiComponents.mean_core_instability}`
                    : 'Bounded [0.000, 1.000]'}
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="text-xs font-medium text-slate-500">Total Violations</div>
                <div className="mt-2 text-2xl font-bold font-mono tabular-nums text-slate-900">
                  {activeFindings?.totalViolations ?? 0}
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono tabular-nums">
                  {activeFindings?.severityCounts?.CRITICAL ?? 0} Critical · {activeFindings?.severityCounts?.HIGH ?? 0} High · {activeFindings?.severityCounts?.MEDIUM ?? 0} Medium
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="text-xs font-medium text-slate-500">Graph Nodes / Edges</div>
                <div className="mt-2 text-2xl font-bold font-mono tabular-nums text-slate-900">
                  {activeFindings?.nodeCount ?? 0} / {activeFindings?.edgeCount ?? 0}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Internal AST Modules &amp; ExternalDB
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <div className="text-xs font-medium text-slate-500">Execution Time</div>
                <div className="mt-2 text-2xl font-bold font-mono tabular-nums text-slate-900">
                  {activeFindings ? `${activeFindings.executionMs.toFixed(2)} ms` : '0.00 ms'}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  Deterministic Wall-Clock
                </div>
              </div>
            </div>

            {/* Layered Dependency Graph */}
            <section className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm font-semibold text-slate-900">
                  Interactive Layered Dependency Graph
                </h2>
                <div className="flex items-center gap-4 text-xs text-slate-600">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-0.5 w-4 bg-emerald-600" />
                    Valid Dependency
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="inline-block h-0.5 w-4 bg-red-600" />
                    Architectural Violation
                  </span>
                </div>
              </div>
              <DependencyGraph
                nodes={activeFindings?.graph?.nodes || []}
                edges={activeFindings?.graph?.edges || []}
              />
            </section>

            {/* Filterable Violations Table */}
            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
                <h2 className="text-sm font-semibold text-slate-900">
                  Detected Architectural Violations ({filteredViolations.length})
                </h2>
                <div className="flex flex-wrap items-center gap-2">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="Filter file or rule..."
                      className="rounded-md border border-slate-300 bg-white pl-8 pr-2.5 py-1.5 text-xs text-slate-900 focus:border-blue-600 focus:outline-none"
                    />
                  </div>
                  <select
                    value={severityFilter}
                    onChange={(e) => setSeverityFilter(e.target.value)}
                    aria-label="Filter by severity"
                    className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-700"
                  >
                    <option value="ALL">All Severities</option>
                    <option value="CRITICAL">CRITICAL</option>
                    <option value="HIGH">HIGH</option>
                    <option value="MEDIUM">MEDIUM</option>
                  </select>
                  <select
                    value={categoryFilter}
                    onChange={(e) => setCategoryFilter(e.target.value)}
                    aria-label="Filter by category"
                    className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-700"
                  >
                    <option value="ALL">All Categories</option>
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {c}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">Rule ID</th>
                      <th className="px-4 py-2.5 font-semibold">Category</th>
                      <th className="px-4 py-2.5 font-semibold">Severity</th>
                      <th className="px-4 py-2.5 font-semibold">File &amp; Line</th>
                      <th className="px-4 py-2.5 font-semibold">Architectural Trace</th>
                      <th className="px-4 py-2.5 font-semibold">Deterministic Refactoring Fix</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredViolations.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-slate-500">
                          <div>
                            No architectural violations detected ({activeFindings?.totalViolations === 0 ? 'clean 3-tier baseline verified' : 'try clearing active filters'}).
                          </div>
                          {activeFindings?.totalViolations === 0 && (
                            <button
                              onClick={() => setActiveTab('benchmark')}
                              className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                            >
                              <FlaskConical className="h-3.5 w-3.5" />
                              Inject Synthetic Drift in Benchmark Lab
                            </button>
                          )}
                        </td>
                      </tr>
                    ) : (
                      filteredViolations.map((v) => {
                        const sevStyle =
                          v.severity === 'CRITICAL'
                            ? 'text-red-700 bg-red-50 border-red-200'
                            : v.severity === 'HIGH'
                            ? 'text-amber-700 bg-amber-50 border-amber-200'
                            : 'text-sky-700 bg-sky-50 border-sky-200';
                        return (
                          <tr key={v.violation_id} className="hover:bg-slate-50 align-top">
                            <td className="px-4 py-3 font-mono font-semibold text-slate-900 whitespace-nowrap">
                              <div>{v.violation_id}</div>
                              <div className="mt-0.5 text-[11px] font-normal text-slate-500">{v.violated_rule}</div>
                            </td>
                            <td className="px-4 py-3 text-slate-800 whitespace-nowrap">{v.category}</td>
                            <td className="px-4 py-3 whitespace-nowrap">
                              <span className={`inline-block rounded border px-2 py-0.5 text-[11px] font-semibold ${sevStyle}`}>
                                {v.severity}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono tabular-nums text-slate-800 whitespace-nowrap">
                              {v.source_file}:{v.line_numbers.join(', ')}
                            </td>
                            <td className="px-4 py-3 font-mono text-[11px] text-slate-700 max-w-xs break-words">
                              {v.architectural_trace}
                            </td>
                            <td className="px-4 py-3 text-slate-700 max-w-md leading-relaxed">
                              {v.deterministic_fix}
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Module Structural Coupling Metrics Table */}
            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="border-b border-slate-200 px-5 py-3.5">
                <h2 className="text-sm font-semibold text-slate-900">
                  Module Coupling &amp; Complexity Metrics
                </h2>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">Module</th>
                      <th className="px-4 py-2.5 font-semibold">Layer</th>
                      <th className="px-4 py-2.5 font-semibold text-right">LOC</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Ca (In)</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Ce (Out)</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Instability I</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Avg CC</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Max CC</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(activeFindings?.nodeMetrics || []).map((m) => (
                      <tr key={m.module_name} className="hover:bg-slate-50">
                        <td className="px-4 py-2 font-mono text-slate-900">{m.file_path}</td>
                        <td className="px-4 py-2 text-slate-700">{m.layer}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-700">{m.loc}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-700">{m.ca}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-700">{m.ce}</td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-900 font-medium">
                          {m.instability.toFixed(3)}
                        </td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-700">
                          {m.avg_complexity.toFixed(2)}
                        </td>
                        <td className="px-4 py-2 text-right font-mono tabular-nums text-slate-700">{m.max_complexity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        )}

        {/* TAB 3: Research Benchmark & Ablation Lab */}
        {activeTab === 'benchmark' && (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 bg-white p-5 flex flex-wrap items-center justify-between gap-4">
              <div className="max-w-2xl">
                <h1 className="text-base font-semibold text-slate-900">
                  Synthetic Drift Injection &amp; 3-Way Ablation Benchmark
                </h1>
                <p className="mt-1 text-xs text-slate-600 leading-relaxed">
                  Copies <code className="font-mono text-slate-800">./sample_repo</code> into an isolated temporary workspace, injects 10 ground-truth violations (3 direct layer skips, 2 transitive utility-to-DB bypasses, 2 circular dependencies, 2 missing <code className="font-mono text-slate-800">@require_auth</code> decorators, 1 high-complexity god-function), and benchmarks all 3 analyzers.
                </p>
              </div>
              <button
                onClick={runBenchmark}
                disabled={loadingBenchmark}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white hover:bg-blue-700 disabled:opacity-60 transition-colors whitespace-nowrap shrink-0"
              >
                <FlaskConical className="h-4 w-4" />
                {loadingBenchmark
                  ? 'Running Drift Injection & Ablation...'
                  : 'Run Synthetic Drift Injection & 3-Way Ablation Benchmark'}
              </button>
            </section>

            {/* 3-Way Ablation Table */}
            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3.5">
                <h2 className="text-sm font-semibold text-slate-900">
                  Ablation Study Results (Ground Truth N = {benchmarkResult?.ground_truth_count ?? 10})
                </h2>
                {benchmarkResult?.proposed_graph && (
                  <button
                    onClick={() => {
                      setFindingsSource('drifted');
                      setActiveTab('findings');
                    }}
                    className="text-xs font-medium text-blue-600 hover:text-blue-800"
                  >
                    Inspect Drifted Dependency Graph -&gt;
                  </button>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                    <tr>
                      <th className="px-4 py-2.5 font-semibold">Method</th>
                      <th className="px-4 py-2.5 font-semibold text-right">TP</th>
                      <th className="px-4 py-2.5 font-semibold text-right">FP</th>
                      <th className="px-4 py-2.5 font-semibold text-right">FN</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Precision</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Recall</th>
                      <th className="px-4 py-2.5 font-semibold text-right">F1-Score</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Latency (ms)</th>
                      <th className="px-4 py-2.5 font-semibold text-right">Peak Mem (MB)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {!benchmarkResult ? (
                      <tr>
                        <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                          Click &quot;Run Synthetic Drift Injection &amp; 3-Way Ablation Benchmark&quot; to execute the experiment.
                        </td>
                      </tr>
                    ) : (
                      benchmarkResult.methods.map((m, idx) => {
                        const isProposed = idx === benchmarkResult.methods.length - 1;
                        return (
                          <tr
                            key={m.method}
                            className={isProposed ? 'bg-blue-50/50 font-semibold text-slate-900' : 'text-slate-700'}
                          >
                            <td className="px-4 py-3">{m.method}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.tp}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.fp}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.fn}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.precision.toFixed(3)}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.recall.toFixed(3)}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.f1_score.toFixed(3)}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.latency_ms.toFixed(2)}</td>
                            <td className="px-4 py-3 text-right font-mono tabular-nums">{m.peak_memory_mb.toFixed(4)}</td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Category-Level Recall Breakdown */}
            {benchmarkResult && (
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <section className="rounded-lg border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 px-5 py-3.5">
                    <h2 className="text-sm font-semibold text-slate-900">
                      Category-Level Recall Breakdown
                    </h2>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-slate-200 bg-slate-50 text-slate-600">
                        <tr>
                          <th className="px-4 py-2.5 font-semibold">Category</th>
                          <th className="px-4 py-2.5 font-semibold text-right">Single-File</th>
                          <th className="px-4 py-2.5 font-semibold text-right">Import-Only</th>
                          <th className="px-4 py-2.5 font-semibold text-right">ArchGuard-Det</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {CATEGORIES.map((cat) => (
                          <tr key={cat}>
                            <td className="px-4 py-2.5 text-slate-800">{cat}</td>
                            {benchmarkResult.methods.map((m) => {
                              const rec = m.category_recall[cat] || { detected: 0, total: 0, recall: 0 };
                              return (
                                <td key={`${cat}-${m.method}`} className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-700">
                                  {rec.detected}/{rec.total} ({Math.round(rec.recall * 100)}%)
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>

                <section className="rounded-lg border border-slate-200 bg-white">
                  <div className="border-b border-slate-200 px-5 py-3.5">
                    <h2 className="text-sm font-semibold text-slate-900">
                      Injected Ground-Truth Manifest (ground_truth.json)
                    </h2>
                  </div>
                  <div className="divide-y divide-slate-100 max-h-[340px] overflow-y-auto">
                    {benchmarkResult.ground_truth.map((gt) => (
                      <div key={gt.gt_id} className="px-4 py-2.5 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-mono font-semibold text-slate-900">
                            {gt.gt_id} · {gt.source_file}:{gt.line_number}
                          </span>
                          <span className="text-slate-500">{gt.category}</span>
                        </div>
                        <div className="mt-0.5 text-slate-600">{gt.description}</div>
                      </div>
                    ))}
                  </div>
                </section>
              </div>
            )}
          </div>
        )}

        {/* TAB 4: IEEE Paper Export */}
        {activeTab === 'export' && (
          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
                <div>
                  <h1 className="text-sm font-semibold text-slate-900">
                    IEEE Two-Column LaTeX Results Table (results_table.tex)
                  </h1>
                  <p className="text-xs text-slate-500">
                    Publication-ready ablation table generated from the deterministic SQLite benchmark record.
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={handleCopyLatex}
                    disabled={!benchmarkResult}
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    {copiedLatex ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                    {copiedLatex ? 'Copied' : 'Copy LaTeX'}
                  </button>
                  <a
                    href="/api/export/latex"
                    download="results_table.tex"
                    className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download results_table.tex
                  </a>
                  <a
                    href="/api/export/csv"
                    download="benchmark_results.csv"
                    className="inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
                  >
                    <Download className="h-3.5 w-3.5" />
                    Download benchmark_results.csv
                  </a>
                </div>
              </div>
              <div className="p-5 space-y-4">
                {!benchmarkResult ? (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-600">
                    <p>No benchmark run found yet. Run the 3-way ablation benchmark to populate the LaTeX and CSV exports.</p>
                    <button
                      onClick={() => {
                        setActiveTab('benchmark');
                        runBenchmark();
                      }}
                      className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-blue-600 px-3.5 py-2 text-xs font-semibold text-white hover:bg-blue-700"
                    >
                      <FlaskConical className="h-3.5 w-3.5" />
                      Run Benchmark Now
                    </button>
                  </div>
                ) : (
                  <>
                    <pre className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-4 font-mono text-xs leading-relaxed text-slate-100">
                      {benchmarkResult.latex_content}
                    </pre>
                    <div>
                      <div className="mb-2 text-xs font-semibold text-slate-700">
                        CSV Export Preview (benchmark_results.csv)
                      </div>
                      <pre className="overflow-x-auto rounded-lg border border-slate-200 bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-800">
                        {benchmarkResult.csv_content}
                      </pre>
                    </div>
                  </>
                )}
              </div>
            </section>
          </div>
        )}
      </main>
    </div>
  );
}
