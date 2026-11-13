import React, { useMemo, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import type { AdiTrendPoint } from '../types';

interface AdiTrendChartProps {
  points: AdiTrendPoint[];
  loading?: boolean;
  onRefresh?: () => void;
}

type SeriesFilter = 'all' | 'audit' | 'benchmark';

function formatShortTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 16);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatFullTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export const AdiTrendChart: React.FC<AdiTrendChartProps> = ({
  points,
  loading = false,
  onRefresh,
}) => {
  const [seriesFilter, setSeriesFilter] = useState<SeriesFilter>('all');
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const filteredPoints = useMemo(() => {
    if (seriesFilter === 'all') return points;
    return points.filter((p) => p.run_type === seriesFilter);
  }, [points, seriesFilter]);

  const stats = useMemo(() => {
    if (filteredPoints.length === 0) {
      return { latest: null, min: null, max: null, delta: null };
    }
    const scores = filteredPoints.map((p) => p.adi_score);
    const latest = scores[scores.length - 1];
    const prev = scores.length >= 2 ? scores[scores.length - 2] : null;
    return {
      latest,
      min: Math.min(...scores),
      max: Math.max(...scores),
      delta: prev !== null ? latest - prev : null,
    };
  }, [filteredPoints]);

  const chartGeom = useMemo(() => {
    const width = 960;
    const height = 250;
    const padLeft = 52;
    const padRight = 24;
    const padTop = 20;
    const padBottom = 38;
    const plotW = width - padLeft - padRight;
    const plotH = height - padTop - padBottom;

    const coords = filteredPoints.map((pt, idx) => {
      const x =
        filteredPoints.length === 1
          ? padLeft + plotW / 2
          : padLeft + (idx / (filteredPoints.length - 1)) * plotW;
      const clampedY = Math.max(0, Math.min(1, pt.adi_score));
      const y = padTop + (1 - clampedY) * plotH;
      return { x, y, pt, idx };
    });

    const linePath = coords
      .map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
      .join(' ');

    const areaPath =
      coords.length >= 2
        ? `${linePath} L ${coords[coords.length - 1].x.toFixed(1)} ${(padTop + plotH).toFixed(1)} L ${coords[0].x.toFixed(1)} ${(padTop + plotH).toFixed(1)} Z`
        : '';

    return { width, height, padLeft, padRight, padTop, padBottom, plotW, plotH, coords, linePath, areaPath };
  }, [filteredPoints]);

  const hoveredPoint =
    hoveredIdx !== null && chartGeom.coords[hoveredIdx]
      ? chartGeom.coords[hoveredIdx]
      : null;

  const activePoint =
    hoveredPoint ??
    (chartGeom.coords.length > 0 ? chartGeom.coords[chartGeom.coords.length - 1] : null);

  const tooltipGeom = useMemo(() => {
    if (!hoveredPoint) return null;
    const boxW = 240;
    const boxH = 60;
    const minX = chartGeom.padLeft;
    const maxX = chartGeom.width - chartGeom.padRight - boxW;
    const tx = Math.max(minX, Math.min(maxX, hoveredPoint.x - boxW / 2));
    const placeBelow = hoveredPoint.y - boxH - 14 < 4;
    const ty = placeBelow ? hoveredPoint.y + 14 : hoveredPoint.y - boxH - 14;
    const arrowY = placeBelow ? ty - 5 : ty + boxH;
    const arrowTipY = placeBelow ? hoveredPoint.y + 8 : hoveredPoint.y - 8;
    const arrowX = Math.max(tx + 12, Math.min(tx + boxW - 12, hoveredPoint.x));
    return { boxW, boxH, tx, ty, arrowX, arrowY, arrowTipY, placeBelow };
  }, [hoveredPoint, chartGeom]);

  const yTicks = [0, 0.25, 0.5, 0.75, 1.0];
  const thresholdY = chartGeom.padTop + (1 - 0.3) * chartGeom.plotH;

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Architectural Drift Index (ADI) Trend Over Time
          </h2>
          <p className="text-xs text-slate-500">
            Chronological history persisted in SQLite (<code className="font-mono">audit_benchmarks.db</code>)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1">
            {(
              [
                ['all', 'All Runs'],
                ['audit', 'Audits Only'],
                ['benchmark', 'Benchmarks Only'],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setSeriesFilter(key);
                  setHoveredIdx(null);
                }}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                  seriesFilter === key
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              disabled={loading}
              aria-label="Refresh ADI trend from SQLite"
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60 whitespace-nowrap shrink-0"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          )}
        </div>
      </div>

      <div className="p-5 space-y-4">
        {/* Compact Summary Telemetry Strip */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 border-b border-slate-100 pb-4">
          <div>
            <div className="text-[11px] font-medium text-slate-500">Latest ADI</div>
            <div className="mt-0.5 font-mono tabular-nums text-base font-semibold text-slate-900">
              {stats.latest !== null ? stats.latest.toFixed(3) : '—'}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium text-slate-500">Delta vs Prior</div>
            <div
              className={`mt-0.5 font-mono tabular-nums text-base font-semibold ${
                stats.delta === null
                  ? 'text-slate-500'
                  : stats.delta > 0
                  ? 'text-red-600'
                  : stats.delta < 0
                  ? 'text-emerald-600'
                  : 'text-slate-700'
              }`}
            >
              {stats.delta !== null
                ? `${stats.delta >= 0 ? '+' : ''}${stats.delta.toFixed(3)}`
                : '—'}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium text-slate-500">Min / Max ADI</div>
            <div className="mt-0.5 font-mono tabular-nums text-base font-semibold text-slate-900">
              {stats.min !== null && stats.max !== null
                ? `${stats.min.toFixed(3)} / ${stats.max.toFixed(3)}`
                : '—'}
            </div>
          </div>
          <div>
            <div className="text-[11px] font-medium text-slate-500">Persisted Runs</div>
            <div className="mt-0.5 font-mono tabular-nums text-base font-semibold text-slate-900">
              {filteredPoints.length}
            </div>
          </div>
        </div>

        {/* SVG Line Chart */}
        {filteredPoints.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 py-10 text-center text-xs text-slate-500">
            No persisted SQLite runs match this filter yet. Run an audit or benchmark to plot the ADI trend.
          </div>
        ) : (
          <div className="space-y-2">
            <div className="overflow-x-auto">
              <svg
                viewBox={`0 0 ${chartGeom.width} ${chartGeom.height}`}
                className="block w-full h-auto min-w-[620px]"
                role="img"
                aria-label="Line chart of Architectural Drift Index over time"
                onMouseLeave={() => setHoveredIdx(null)}
              >
                <defs>
                  <linearGradient id="adiAreaGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#2563eb" stopOpacity="0.18" />
                    <stop offset="100%" stopColor="#2563eb" stopOpacity="0.01" />
                  </linearGradient>
                  <filter id="adiTooltipShadow" x="-10%" y="-10%" width="120%" height="130%">
                    <feDropShadow dx="0" dy="3" stdDeviation="4" floodColor="#0f172a" floodOpacity="0.22" />
                  </filter>
                </defs>

                {/* Horizontal Gridlines & Y-Axis Labels */}
                {yTicks.map((tick) => {
                  const y = chartGeom.padTop + (1 - tick) * chartGeom.plotH;
                  return (
                    <g key={tick}>
                      <line
                        x1={chartGeom.padLeft}
                        y1={y}
                        x2={chartGeom.width - chartGeom.padRight}
                        y2={y}
                        stroke="#e2e8f0"
                        strokeWidth={1}
                      />
                      <text
                        x={chartGeom.padLeft - 8}
                        y={y + 4}
                        textAnchor="end"
                        fontSize="10.5"
                        fill="#64748b"
                        fontFamily="JetBrains Mono, monospace"
                      >
                        {tick.toFixed(2)}
                      </text>
                    </g>
                  );
                })}

                {/* Drift Alert Reference Threshold (0.30) */}
                <line
                  x1={chartGeom.padLeft}
                  y1={thresholdY}
                  x2={chartGeom.width - chartGeom.padRight}
                  y2={thresholdY}
                  stroke="#d97706"
                  strokeWidth={1}
                  strokeDasharray="4 4"
                  strokeOpacity={0.7}
                />
                <text
                  x={chartGeom.width - chartGeom.padRight - 4}
                  y={thresholdY - 5}
                  textAnchor="end"
                  fontSize="10"
                  fill="#b45309"
                  fontFamily="JetBrains Mono, monospace"
                >
                  Drift Threshold (0.30)
                </text>

                {/* Active Hover Vertical Crosshair */}
                {activePoint && (
                  <line
                    x1={activePoint.x}
                    y1={chartGeom.padTop}
                    x2={activePoint.x}
                    y2={chartGeom.padTop + chartGeom.plotH}
                    stroke="#94a3b8"
                    strokeWidth={1}
                    strokeDasharray="3 3"
                  />
                )}

                {/* Area Fill & Line Path */}
                {chartGeom.areaPath && <path d={chartGeom.areaPath} fill="url(#adiAreaGrad)" />}
                {chartGeom.coords.length >= 2 && (
                  <path
                    d={chartGeom.linePath}
                    fill="none"
                    stroke="#2563eb"
                    strokeWidth={2.2}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                )}

                {/* Data Point Markers & X-Axis Labels */}
                {chartGeom.coords.map((c) => {
                  const isActive = activePoint?.pt.point_id === c.pt.point_id;
                  const isBench = c.pt.run_type === 'benchmark';
                  const showXLabel =
                    chartGeom.coords.length <= 8 ||
                    c.idx === 0 ||
                    c.idx === chartGeom.coords.length - 1 ||
                    c.idx % Math.ceil(chartGeom.coords.length / 6) === 0;

                  return (
                    <g
                      key={c.pt.point_id}
                      tabIndex={0}
                      role="button"
                      aria-label={`${c.pt.run_type === 'benchmark' ? 'Benchmark' : 'Audit'} on ${formatFullTimestamp(c.pt.created_at)}, ADI ${c.pt.adi_score.toFixed(3)}`}
                      onMouseEnter={() => setHoveredIdx(c.idx)}
                      onMouseLeave={() => setHoveredIdx((prev) => (prev === c.idx ? null : prev))}
                      onFocus={() => setHoveredIdx(c.idx)}
                      onBlur={() => setHoveredIdx((prev) => (prev === c.idx ? null : prev))}
                      onClick={() => setHoveredIdx(c.idx)}
                      className="cursor-pointer focus:outline-none"
                    >
                      {/* Larger invisible hit target */}
                      <circle cx={c.x} cy={c.y} r={16} fill="transparent" />

                      {isActive && (
                        <circle
                          cx={c.x}
                          cy={c.y}
                          r={9}
                          fill={isBench ? '#dc2626' : '#2563eb'}
                          fillOpacity={0.16}
                        />
                      )}

                      {isBench ? (
                        <rect
                          x={c.x - (isActive ? 5.5 : 4)}
                          y={c.y - (isActive ? 5.5 : 4)}
                          width={isActive ? 11 : 8}
                          height={isActive ? 11 : 8}
                          transform={`rotate(45 ${c.x} ${c.y})`}
                          fill="#dc2626"
                          stroke="#ffffff"
                          strokeWidth={1.8}
                        />
                      ) : (
                        <circle
                          cx={c.x}
                          cy={c.y}
                          r={isActive ? 5.5 : 4}
                          fill="#2563eb"
                          stroke="#ffffff"
                          strokeWidth={1.8}
                        />
                      )}

                      {showXLabel && (
                        <text
                          x={c.x}
                          y={chartGeom.height - 12}
                          textAnchor="middle"
                          fontSize="10"
                          fill="#64748b"
                          fontFamily="JetBrains Mono, monospace"
                        >
                          {formatShortTime(c.pt.created_at)}
                        </text>
                      )}
                    </g>
                  );
                })}

                {/* Interactive Hover Tooltip */}
                {hoveredPoint && tooltipGeom && (
                  <g pointerEvents="none" filter="url(#adiTooltipShadow)">
                    <polygon
                      points={`${tooltipGeom.arrowX - 6},${tooltipGeom.arrowY} ${tooltipGeom.arrowX + 6},${tooltipGeom.arrowY} ${tooltipGeom.arrowX},${tooltipGeom.arrowTipY}`}
                      fill="#0f172a"
                    />
                    <rect
                      x={tooltipGeom.tx}
                      y={tooltipGeom.ty}
                      width={tooltipGeom.boxW}
                      height={tooltipGeom.boxH}
                      rx={6}
                      fill="#0f172a"
                      stroke="#334155"
                      strokeWidth={1}
                    />
                    <text
                      x={tooltipGeom.tx + 12}
                      y={tooltipGeom.ty + 21}
                      fontSize="10.5"
                      fill="#cbd5e1"
                      fontFamily="JetBrains Mono, monospace"
                    >
                      {formatFullTimestamp(hoveredPoint.pt.created_at)}
                    </text>
                    <text
                      x={tooltipGeom.tx + 12}
                      y={tooltipGeom.ty + 43}
                      fontSize="12.5"
                      fontWeight={700}
                      fill="#ffffff"
                      fontFamily="JetBrains Mono, monospace"
                    >
                      ADI {hoveredPoint.pt.adi_score.toFixed(3)}
                    </text>
                    <text
                      x={tooltipGeom.tx + tooltipGeom.boxW - 12}
                      y={tooltipGeom.ty + 43}
                      textAnchor="end"
                      fontSize="10.5"
                      fill={hoveredPoint.pt.run_type === 'benchmark' ? '#fca5a5' : '#93c5fd'}
                      fontFamily="JetBrains Mono, monospace"
                    >
                      {hoveredPoint.pt.run_type === 'benchmark' ? 'Bench' : 'Audit'} #{hoveredPoint.pt.run_id} · {hoveredPoint.pt.total_violations}v
                    </text>
                  </g>
                )}
              </svg>
            </div>

            {/* Legend & Selected Point Telemetry Readout */}
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-slate-100 bg-slate-50 px-3.5 py-2 text-xs">
              <div className="flex items-center gap-4 text-slate-600">
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rounded-full bg-blue-600" />
                  Audit Run
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="inline-block h-2.5 w-2.5 rotate-45 bg-red-600" />
                  Benchmark Injection Run
                </span>
              </div>

              {activePoint && (
                <div className="flex flex-wrap items-center gap-3 font-mono tabular-nums text-slate-800">
                  <span>
                    {activePoint.pt.run_type === 'benchmark' ? 'Benchmark' : 'Audit'} #{activePoint.pt.run_id}
                  </span>
                  <span className="text-slate-400">·</span>
                  <span>{formatFullTimestamp(activePoint.pt.created_at)}</span>
                  <span className="text-slate-400">·</span>
                  <span>{activePoint.pt.label}</span>
                  <span className="text-slate-400">·</span>
                  <span className="font-semibold text-slate-900">
                    ADI {activePoint.pt.adi_score.toFixed(3)} ({activePoint.pt.total_violations} violations)
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
