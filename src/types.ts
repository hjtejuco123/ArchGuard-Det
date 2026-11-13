export interface GraphNode {
  id: string;
  label: string;
  file_path: string;
  layer: string;
  is_external: boolean;
  loc: number;
  ca: number;
  ce: number;
  instability: number;
  avg_complexity: number;
  max_complexity: number;
  is_cyclic: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  edge_types: string[];
  line_numbers: number[];
  evidence: string[];
  is_violation: boolean;
  is_transitive_bypass: boolean;
}

export interface ViolationItem {
  violation_id: string;
  category: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  violated_rule: string;
  source_file: string;
  source_module: string;
  line_numbers: number[];
  target_file: string;
  target_module: string;
  architectural_trace: string;
  path_nodes: string[];
  deterministic_fix: string;
  confidence: number;
}

export interface NodeMetric {
  module_name: string;
  file_path: string;
  layer: string;
  is_external: boolean;
  loc: number;
  ca: number;
  ce: number;
  instability: number;
  avg_complexity: number;
  max_complexity: number;
  function_count: number;
}

export interface AuditResult {
  audit_id?: number;
  repo_path: string;
  execution_ms: number;
  node_count: number;
  edge_count: number;
  internal_file_count: number;
  using_networkx: boolean;
  rules_yaml: string;
  adi_score: number;
  adi_components: {
    weighted_violations: number;
    internal_nodes: number;
    mean_core_instability: number;
    cyclic_nodes: number;
    violation_term: number;
    instability_term: number;
    cycle_term: number;
  };
  total_violations: number;
  severity_counts: Record<string, number>;
  category_counts: Record<string, number>;
  violations: ViolationItem[];
  graph: {
    nodes: GraphNode[];
    edges: GraphEdge[];
  };
  node_metrics: NodeMetric[];
}

export interface CategoryRecallItem {
  detected: number;
  total: number;
  recall: number;
}

export interface BenchmarkMethodResult {
  method: string;
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1_score: number;
  latency_ms: number;
  peak_memory_mb: number;
  category_recall: Record<string, CategoryRecallItem>;
}

export interface GroundTruthItem {
  gt_id: string;
  source_file: string;
  category: string;
  line_number: number;
  description: string;
}

export interface BenchmarkResult {
  benchmark_id?: number;
  ground_truth_count: number;
  ground_truth: GroundTruthItem[];
  methods: BenchmarkMethodResult[];
  proposed_adi_score: number;
  proposed_adi_components?: AuditResult['adi_components'];
  proposed_severity_counts?: Record<string, number>;
  proposed_violations: ViolationItem[];
  proposed_graph?: AuditResult['graph'];
  proposed_node_metrics?: NodeMetric[];
  csv_content: string;
  latex_content: string;
}

export interface AdiTrendPoint {
  point_id: string;
  run_id: number;
  run_type: 'audit' | 'benchmark';
  created_at: string;
  label: string;
  adi_score: number;
  total_violations: number;
  execution_ms?: number;
  proposed_f1?: number;
}

