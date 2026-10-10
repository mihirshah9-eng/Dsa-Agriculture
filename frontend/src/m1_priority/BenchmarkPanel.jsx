/**
 * KJS-AGR-01 | Member 1
 * BenchmarkPanel.jsx -- measured timings for every structure in this module.
 *
 * Nothing here is hard-coded: the numbers come from /api/priority/benchmarks,
 * which times the real structures in the running process.  Each result carries
 * the machine-readable figure, its complexity, and the caveat where one exists.
 */
import React, { useEffect, useState } from 'react';
import { getBenchmarks } from './m1Api';
import { CompareBar, fmt } from './ui';

const SORT_LABELS = {
  counting: { label: 'Counting sort', complexity: 'O(n + k)' },
  heap: { label: 'Heap sort', complexity: 'O(n log n)' },
  insertion: { label: 'Insertion sort', complexity: 'O(n + inversions)' },
  bubble: { label: 'Bubble sort', complexity: 'O(n²)' },
};

export default function BenchmarkPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);

  const load = async () => {
    setLoading(true);
    setErr(null);
    try {
      setData(await getBenchmarks());
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading && !data) return <div className="m1-muted">running benchmarks on the live 25,000-plot farm…</div>;
  if (err) return <div className="m1-banner m1-banner--error">Benchmark error: {err}</div>;
  if (!data) return null;

  const sortRows = data.sorts?.rows || [];
  const largest = sortRows[sortRows.length - 1];
  const maxSortMs = Math.max(
    ...sortRows.flatMap((row) => Object.values(row.results)
      .map((r) => (r.skipped ? r.projected_ms.projected_ms_at_n : r.time_ms))),
    1,
  );

  return (
    <div className="m1-page">
      <div className="m1-page__head">
        <div>
          <h2 className="m1-page__title">Complexity Benchmarks</h2>
          <p className="m1-page__sub">
            Measured in-process on this machine{data.cached ? ' (cached result)' : ''} ·
            {' '}{fmt(data.total_ms)} ms total · {data.pipeline ? `${data.pipeline.plots} live plots` : ''}
          </p>
        </div>
        <button className="m1-btn" onClick={load} disabled={loading}>
          {loading ? 're-running…' : '↻ Re-run benchmarks'}
        </button>
      </div>

      <h3 className="m1-h3">The four sorts, measured on identical inputs</h3>
      <div className="m1-tablewrap">
        <table className="m1-table">
          <thead>
            <tr>
              <th>Algorithm</th><th>Complexity</th><th>Space</th>
              {sortRows.map((r) => <th key={r.n}>{fmt(r.n)}{r.label ? '*' : ''}</th>)}
            </tr>
          </thead>
          <tbody>
            {Object.keys(SORT_LABELS).map((algo) => (
              <tr key={algo}>
                <td><strong>{SORT_LABELS[algo].label}</strong></td>
                <td className="m1-muted">{SORT_LABELS[algo].complexity}</td>
                <td className="m1-muted">{sortRows[0]?.results?.[algo]?.extra_space || '—'}</td>
                {sortRows.map((row) => {
                  const r = row.results[algo];
                  if (!r) return <td key={row.n} className="m1-muted">—</td>;
                  if (r.skipped) {
                    const p = r.projected_ms.projected_ms_at_n;
                    return (
                      <td key={row.n} className="m1-td-skip">
                        {fmt(p)} ms*
                        <div className="m1-muted">extrapolated from n={fmt(r.projected_ms.measured_at)}</div>
                      </td>
                    );
                  }
                  return (
                    <td key={row.n}>
                      <strong>{r.time_ms} ms</strong>
                      <div className="m1-muted">
                        {typeof r.comparisons === 'number' ? `${fmt(r.comparisons)} comp · ` : ''}
                        {typeof r.swaps === 'number' ? `${fmt(r.swaps)} swaps` : r.swaps || ''}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="m1-muted">
        * Bubble and insertion sort are O(n²); above n={fmt(data.sorts?.quadratic_cap)} they are measured at the cap and
        scaled by n², clearly labelled rather than left out. The last column is a nearly-sorted list
        (25 swapped pairs), which is the realistic between-tick case — insertion sort collapses to
        {' '}{sortRows[sortRows.length - 1]?.results?.insertion?.time_ms} ms there, which is why it is kept.
      </p>

      <h3 className="m1-h3">Relative cost at the largest measured size</h3>
      <div className="m1-bars">
        {Object.keys(SORT_LABELS).map((algo) => {
          const r = largest?.results?.[algo];
          if (!r) return null;
          const v = r.skipped ? r.projected_ms.projected_ms_at_n : r.time_ms;
          return (
            <CompareBar key={algo} value={v} max={maxSortMs}
                        caption={`${SORT_LABELS[algo].label}: ${fmt(v, v < 100 ? 2 : 0)} ms`}
                        tone={algo === 'counting' ? 'ok' : algo === 'bubble' ? 'err' : 'primary'} />
          );
        })}
      </div>

      <h3 className="m1-h3">Data structures</h3>
      <div className="m1-benchgrid">
        <BenchCard title="Indexed max-heap" note={data.heap.note}>
          <Row k="peek (O(1))" v={`${data.heap.peek_per_call_us} µs per call`} />
          <Row k="update-key with index dict (O(log n))" v={`${data.heap.update_key_per_call_us} µs per call`} />
          <Row k="find + update by linear scan (O(n))" v={`${data.heap.naive_linear_search_per_call_us} µs per call`} />
          <Row k="speed-up from keeping the index"
               v={`${fmt(data.heap.naive_linear_search_per_call_us / data.heap.update_key_per_call_us, 0)}×`} highlight />
          <Row k="heap depth vs log₂ n" v={`${data.heap.heap_depth} vs ${data.heap.log2_n}`} />
          <Row k="build 25,000 entries" v={`${data.heap.build_heap_ms} ms`} />
        </BenchCard>

        <BenchCard title="Circular queue (ingest buffer)" note={data.circular_queue.complexity}>
          <Row k="steady state, ring enqueue" v={`${data.circular_queue.steady_state.ring_enqueue_ms} ms`} />
          <Row k="steady state, list + pop(0)" v={`${data.circular_queue.steady_state.list_fifo_ms} ms`} />
          <Row k="speed-up vs list" v={`${data.circular_queue.steady_state.speedup_vs_list}×`} highlight />
          <Row k="drain: ring vs list.pop(0)"
               v={`${data.circular_queue.drain.ring_dequeue_ms} ms vs ${data.circular_queue.drain.list_pop0_ms} ms (${data.circular_queue.drain.speedup}×)`} />
          <Row k="overflow: dropped / retained"
               v={`${fmt(data.circular_queue.overflow_policy.dropped)} / ${fmt(data.circular_queue.overflow_policy.retained)}`} />
          <Row k="caveat" v={data.circular_queue.caveat} />
        </BenchCard>

        <BenchCard title="Deque (sliding window)" note={data.deque_trend.note}>
          <Row k="push cost" v={`${data.deque_trend.push_per_call_us} µs per call`} />
          <Row k="rolling max, monotonic deque" v={`${data.deque_trend.rolling_max_monotonic_deque_ms} ms`} />
          <Row k="rolling max, full rescan" v={`${data.deque_trend.rolling_max_full_rescan_ms} ms`} />
          <Row k="speed-up" v={`${data.deque_trend.speedup}× (window=${data.deque_trend.window_size})`} highlight />
        </BenchCard>

        <BenchCard title="Pump scheduler" note={data.scheduler?.note}>
          <Row k="full rebuild, average" v={`${data.scheduler?.avg_ms} ms`} highlight />
          <Row k="min / max" v={`${data.scheduler?.min_ms} / ${data.scheduler?.max_ms} ms`} />
          <Row k="seats filled" v={`${fmt(data.scheduler?.plots_scheduled)} of ${fmt(data.scheduler?.seats)}`} />
          <Row k="per seat" v={`${(data.scheduler?.avg_ms / (data.scheduler?.seats || 1) * 1000).toFixed(1)} µs`} />
        </BenchCard>

        {data.pipeline && (
          <BenchCard title="Full simulation tick" note={data.pipeline.note}>
            <Row k="average tick" v={`${data.pipeline.avg_tick_ms} ms`} highlight />
            <Row k="min / max" v={`${data.pipeline.min_tick_ms} / ${data.pipeline.max_tick_ms} ms`} />
            <Row k="per plot" v={`${data.pipeline.per_plot_us} µs`} />
            <Row k="stages" v={data.pipeline.stages} />
          </BenchCard>
        )}

        {data.priority_board && (
          <BenchCard title="Priority board query" note="heap copy + ordering of the candidate pool">
            <Row k="counting sort path" v={`${data.priority_board.counting.total_ms} ms (sort ${data.priority_board.counting.sort_ms} ms)`} highlight />
            <Row k="heap sort path" v={`${data.priority_board.heap.total_ms} ms (sort ${data.priority_board.heap.sort_ms} ms)`} />
            <Row k="candidates considered" v={fmt(data.priority_board.counting.candidates)} />
            <Row k="rows returned" v={fmt(data.priority_board.limit)} />
          </BenchCard>
        )}
      </div>

      <h3 className="m1-h3">Complexity table for the report</h3>
      <div className="m1-tablewrap">
        <table className="m1-table m1-table--compact">
          <thead>
            <tr><th>Structure</th><th>Operation</th><th>Complexity</th><th>Used for</th></tr>
          </thead>
          <tbody>
            {(data.complexity_table || []).map((r) => (
              <tr key={r.structure + r.operation}>
                <td><strong>{r.structure}</strong></td>
                <td>{r.operation}</td>
                <td className="m1-mono">{r.complexity}</td>
                <td className="m1-muted">{r.used_for}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {data.member2_reference?.length ? (
        <>
          <h3 className="m1-h3">Cross-module comparison points</h3>
          <div className="m1-tablewrap">
            <table className="m1-table m1-table--compact">
              <thead><tr><th>Structure</th><th>Owner</th><th>Complexity</th><th>Note</th></tr></thead>
              <tbody>
                {data.member2_reference.map((r) => (
                  <tr key={r.structure}>
                    <td>{r.structure}</td><td>{r.owner}</td>
                    <td className="m1-mono">{r.complexity}</td>
                    <td className="m1-muted">{r.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}

function BenchCard({ title, note, children }) {
  return (
    <section className="m1-card m1-benchcard">
      <h3>{title}</h3>
      <div className="m1-benchrows">{children}</div>
      {note ? <p className="m1-muted m1-benchcard__note">{note}</p> : null}
    </section>
  );
}

function Row({ k, v, highlight }) {
  return (
    <div className={`m1-benchrow${highlight ? ' m1-benchrow--hl' : ''}`}>
      <span className="m1-benchrow__k">{k}</span>
      <span className="m1-benchrow__v">{v}</span>
    </div>
  );
}
