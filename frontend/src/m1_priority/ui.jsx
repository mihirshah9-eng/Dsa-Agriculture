/**
 * KJS-AGR-01 | Member 1
 * ui.jsx -- small presentational pieces shared by the four Member-1 pages.
 * No chart library: every visual is inline CSS or inline SVG so the module has
 * zero extra frontend dependencies and renders inside an offline preview.
 */
import React from 'react';

export const STATUS_COLORS = {
  CRITICAL: '#e5484d',
  HIGH: '#f76b15',
  MODERATE: '#e8b100',
  OK: '#2f9e44',
};

export function StatusPill({ status, small }) {
  const c = STATUS_COLORS[status] || '#889096';
  return (
    <span className={`m1-pill${small ? ' m1-pill--sm' : ''}`}
          style={{ color: c, borderColor: `${c}55`, background: `${c}14` }}>
      {status}
    </span>
  );
}

export function ScoreBar({ score, max = 1000, status }) {
  const pct = Math.max(2, Math.min(100, (score / max) * 100));
  const c = STATUS_COLORS[status] || '#4c6ef5';
  return (
    <div className="m1-scorebar" title={`${score} / ${max}`}>
      <div className="m1-scorebar__fill" style={{ width: `${pct}%`, background: c }} />
      <span className="m1-scorebar__label">{score}</span>
    </div>
  );
}

export function StatCard({ label, value, hint, tone }) {
  return (
    <div className={`m1-stat${tone ? ` m1-stat--${tone}` : ''}`}>
      <div className="m1-stat__value">{value}</div>
      <div className="m1-stat__label">{label}</div>
      {hint ? <div className="m1-stat__hint">{hint}</div> : null}
    </div>
  );
}

/** Inline SVG sparkline -- no external chart dependency. */
export function Sparkline({ points, width = 240, height = 56, color = '#4c6ef5', fill = true, label }) {
  const values = (points || []).map((p) => (typeof p === 'number' ? p : p.stress_score));
  if (values.length < 2) {
    return <div className="m1-spark m1-spark--empty">not enough ticks yet</div>;
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = width / (values.length - 1);
  const coords = values.map((v, i) => [i * stepX, height - ((v - min) / span) * (height - 8) - 4]);
  const line = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${line} L${width},${height} L0,${height} Z`;
  return (
    <svg className="m1-spark" viewBox={`0 0 ${width} ${height}`} width="100%" height={height}
         preserveAspectRatio="none" role="img" aria-label={label || 'trend sparkline'}>
      {fill && <path d={area} fill={color} opacity="0.14" />}
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={coords[coords.length - 1][0]} cy={coords[coords.length - 1][1]} r="3" fill={color} />
    </svg>
  );
}

/** Horizontal comparison bar with a caption -- used by the benchmark table. */
export function CompareBar({ value, max, caption, tone = 'primary' }) {
  const pct = max > 0 ? Math.max(1, Math.min(100, (value / max) * 100)) : 1;
  return (
    <div className="m1-compare">
      <div className="m1-compare__track">
        <div className={`m1-compare__fill m1-compare__fill--${tone}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="m1-compare__caption">{caption}</span>
    </div>
  );
}

export function TrendArrow({ delta }) {
  if (delta === null || delta === undefined || delta === 0) {
    return <span className="m1-trend m1-trend--flat">— 0</span>;
  }
  const up = delta > 0;
  return (
    <span className={`m1-trend m1-trend--${up ? 'up' : 'down'}`} title={`${delta} points over the sliding window`}>
      {up ? '▲' : '▼'} {Math.abs(delta)}
    </span>
  );
}

export function fmt(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return Number(n).toLocaleString('en-IN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function DataStructureStrip({ ds, lastTick }) {
  if (!ds) return null;
  const { heap, circular_queue: queue, deque_trend: deque } = ds;
  const items = [
    {
      name: 'Indexed Max-Heap',
      icon: '⛰',
      lines: [
        `${fmt(heap.size)} entries · depth ${heap.depth}`,
        `peek ${heap.top ? `${heap.top[0]} (plot ${heap.top[1]})` : '—'}`,
        `${fmt(heap.ops.update)} update-key · ${fmt(heap.ops.extract)} extract`,
      ],
    },
    {
      name: 'Circular Queue',
      icon: '◌',
      lines: [
        `${fmt(queue.size)} / ${fmt(queue.capacity)} slots`,
        `util ${(queue.utilization * 100).toFixed(1)}% · peak ${fmt(queue.high_water)}`,
        `${fmt(queue.dropped)} dropped by policy`,
      ],
    },
    {
      name: 'Deque (sliding window)',
      icon: '≋',
      lines: [
        `${fmt(deque.tracked_plots)} plots tracked`,
        `window ${deque.window_size} ticks`,
        `rolling max/min in O(1)`,
      ],
    },
    {
      name: 'Dictionary',
      icon: '⌗',
      lines: [
        'plot_id → Plot record',
        'plot_id → heap index',
        'O(1) average lookup',
      ],
    },
  ];
  return (
    <div className="m1-dsstrip">
      {items.map((it) => (
        <div className="m1-dscard" key={it.name}>
          <div className="m1-dscard__head"><span aria-hidden>{it.icon}</span> {it.name}</div>
          {it.lines.map((l) => <div className="m1-dscard__line" key={l}>{l}</div>)}
        </div>
      ))}
      <div className="m1-dscard">
        <div className="m1-dscard__head"><span aria-hidden>⏱</span> Last tick</div>
        <div className="m1-dscard__line">{lastTick ? `${lastTick.elapsed_ms} ms wall time` : '—'}</div>
        <div className="m1-dscard__line">{lastTick ? `${fmt(lastTick.plots_updated)} plots re-scored` : '—'}</div>
        <div className="m1-dscard__line">{lastTick ? `${fmt(lastTick.critical_now)} below emergency line` : '—'}</div>
      </div>
    </div>
  );
}
