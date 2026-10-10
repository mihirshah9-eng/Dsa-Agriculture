/**
 * KJS-AGR-01 | Member 1
 * PriorityBoard.jsx -- the Live Priority Board.
 *
 * Reads the candidate pool from the INDEXED MAX-HEAP and orders it with the
 * selected sorting algorithm.  Counting sort is the default because stress
 * scores are integers in [0, 1000] -> O(n + k) instead of O(n log n).
 * The UI shows the measured sort time so the choice is visible, not asserted.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { getPlots, getPlotTrend } from './m1Api';
import { ScoreBar, Sparkline, StatusPill, TrendArrow, fmt, STATUS_COLORS } from './ui';

const ALGOS = [
  { id: 'counting', label: 'Counting sort', note: 'O(n + k) · default' },
  { id: 'heap', label: 'Heap sort', note: 'O(n log n) · fallback' },
  { id: 'insertion', label: 'Insertion sort', note: 'O(n + inv) · near-sorted' },
  { id: 'bubble', label: 'Bubble sort', note: 'O(n²) · baseline only' },
];

const VILLAGES = ['', 'Kadugodi', 'Hosakere', 'Bidalur', 'Yelahanka', 'Doddaballapur', 'Nelamangala', 'Anekal', 'Kanakapura'];
const CROPS = ['', 'Paddy', 'Sugarcane', 'Tomato', 'Maize', 'Onion', 'Groundnut', 'Ragi', 'Cotton'];
const STATUSES = ['', 'CRITICAL', 'HIGH', 'MODERATE', 'OK'];

export default function PriorityBoard({ tick }) {
  const [algo, setAlgo] = useState('counting');
  const [village, setVillage] = useState('');
  const [crop, setCrop] = useState('');
  const [status, setStatus] = useState('');
  const [limit, setLimit] = useState(60);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [selected, setSelected] = useState(null);

  const load = useCallback(async () => {
    try {
      const payload = await getPlots({ limit, algorithm: algo, village, crop, status });
      setData(payload);
      setErr(null);
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }, [limit, algo, village, crop, status]);

  useEffect(() => { load(); }, [load, tick]);

  const rows = data?.rows || [];

  return (
    <div className="m1-page">
      <div className="m1-page__head">
        <div>
          <h2 className="m1-page__title">Live Priority Board</h2>
          <p className="m1-page__sub">
            Candidates pulled from the indexed max-heap, then ordered by the selected sort.
            Highest water-stress score first.
          </p>
        </div>
        <div className="m1-pagetools">
          <label className="m1-field">
            <span>Ordering</span>
            <select value={algo} onChange={(e) => setAlgo(e.target.value)}>
              {ALGOS.map((a) => <option key={a.id} value={a.id}>{a.label} — {a.note}</option>)}
            </select>
          </label>
          <label className="m1-field">
            <span>Rows</span>
            <select value={limit} onChange={(e) => setLimit(Number(e.target.value))}>
              {[25, 60, 120, 250].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="m1-filters">
        <label className="m1-field"><span>Village</span>
          <select value={village} onChange={(e) => setVillage(e.target.value)}>
            {VILLAGES.map((v) => <option key={v || 'all'} value={v}>{v || 'All villages'}</option>)}
          </select>
        </label>
        <label className="m1-field"><span>Crop</span>
          <select value={crop} onChange={(e) => setCrop(e.target.value)}>
            {CROPS.map((c) => <option key={c || 'all'} value={c}>{c || 'All crops'}</option>)}
          </select>
        </label>
        <label className="m1-field"><span>Status</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s || 'all'} value={s}>{s || 'Any status'}</option>)}
          </select>
        </label>
        <div className="m1-sortmeta">
          {data ? (
            <>
              <strong>{fmt(data.candidates)}</strong> candidates · sorted in{' '}
              <strong>{data.sort_ms} ms</strong> · round trip {data.total_ms} ms
            </>
          ) : 'loading…'}
        </div>
      </div>

      {err && <div className="m1-banner m1-banner--error">API error: {err}</div>}

      <div className="m1-tablewrap">
        <table className="m1-table">
          <thead>
            <tr>
              <th>#</th><th>Plot</th><th>Village</th><th>Crop</th>
              <th>Stress score</th><th>Status</th><th>Moisture</th><th>Temp</th>
              <th>Trend</th><th>Pump</th><th>Slot</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.plot_id}
                  className={`m1-row${selected === r.plot_id ? ' m1-row--sel' : ''}${r.emergency ? ' m1-row--emergency' : ''}`}
                  onClick={() => setSelected(r.plot_id === selected ? null : r.plot_id)}>
                <td className="m1-td-rank">{r.rank}</td>
                <td className="m1-td-id">{r.plot_id}{r.emergency ? <span className="m1-emg" title="below emergency moisture line">EMG</span> : null}</td>
                <td>{r.village}</td>
                <td>{r.crop}</td>
                <td style={{ minWidth: 140 }}><ScoreBar score={r.stress_score} status={r.status} /></td>
                <td><StatusPill status={r.status} small /></td>
                <td>{r.moisture.toFixed(1)}%</td>
                <td>{r.temperature.toFixed(0)}°</td>
                <td><TrendArrow delta={Math.round(r.trend)} /></td>
                <td className="m1-td-pump">{r.pump_id || '—'}</td>
                <td className="m1-td-slot">{r.scheduled_slot === null || r.scheduled_slot === undefined ? '—' : `S${r.scheduled_slot}`}</td>
              </tr>
            ))}
            {!rows.length && !loading && (
              <tr><td colSpan={11} className="m1-empty">No plots match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {selected ? <PlotDetail plotId={selected} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}

/** Drill-down: deque sliding window, sparkline, and the score breakdown. */
function PlotDetail({ plotId, onClose }) {
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let alive = true;
    getPlotTrend(plotId)
      .then((d) => { if (alive) setDetail(d); })
      .catch((e) => { if (alive) setErr(e.message); });
    return () => { alive = false; };
  }, [plotId]);

  return (
    <div className="m1-detail">
      <div className="m1-detail__head">
        <h3>Plot {plotId} — drying trend &amp; score breakdown</h3>
        <button className="m1-btn m1-btn--ghost" onClick={onClose}>close</button>
      </div>
      {err && <div className="m1-banner m1-banner--error">{err}</div>}
      {!detail && !err && <div className="m1-muted">loading…</div>}
      {detail ? (
        <div className="m1-detail__grid">
          <div>
            <div className="m1-detail__meta">
              <StatusPill status={detail.status} />
              <span>{detail.village} · {detail.crop}</span>
              <span>moisture {detail.moisture?.toFixed(1)}%</span>
              <span>score {detail.stress_score}</span>
            </div>
            <Sparkline points={detail.window} color={STATUS_COLORS[detail.status] || '#4c6ef5'}
                       label={`stress score over the last ${detail.window?.length} ticks`} />
            <div className="m1-dequeStats">
              <span>sliding window (deque) <strong>{detail.window?.join(' → ')}</strong></span>
              <span>rolling max <strong>{detail.rolling_max}</strong> · min <strong>{detail.rolling_min}</strong></span>
              <span>mean <strong>{detail.mean}</strong> · delta <strong>{detail.delta > 0 ? '+' : ''}{detail.delta}</strong></span>
            </div>
          </div>
          <div>
            <div className="m1-breakdown">
              {Object.entries(detail.explain?.terms || {}).map(([key, t]) => (
                <div className="m1-breakdown__row" key={key}>
                  <span className="m1-breakdown__name">{key}</span>
                  <span className="m1-breakdown__val">{t.value}{key === 'temperature' ? '°C' : key === 'rainfall' ? ' mm' : '%'}</span>
                  <div className="m1-breakdown__track">
                    <div className="m1-breakdown__fill" style={{ width: `${(t.points / 450) * 100}%` }} />
                  </div>
                  <span className="m1-breakdown__pts">{t.points} / {t.weight}</span>
                </div>
              ))}
              <div className="m1-breakdown__total">
                subtotal {detail.explain?.subtotal} × crop coefficient {detail.explain?.crop_coefficient} ={' '}
                <strong>{detail.explain?.score}</strong>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
