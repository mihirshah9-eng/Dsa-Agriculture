/**
 * KJS-AGR-01 | Member 1
 * PumpScheduleTimeline.jsx -- which plot runs on which pump, in which slot.
 *
 * The 12 slots are exactly the two electricity windows the brief specifies:
 *   05:00-08:00 and 14:00-17:00, six 30-minute slots each.
 * One plot per pump per slot; seats are dealt in strict score order, so the
 * most stressed plot in the whole farm gets the first seat of the morning window.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { getSchedule } from './m1Api';
import { StatusPill, fmt } from './ui';

export default function PumpScheduleTimeline({ state }) {
  const [onlyEmergency, setOnlyEmergency] = useState(false);
  const [schedule, setSchedule] = useState(null);
  const summary = schedule?.summary || state?.schedule?.summary || {};
  const slots = schedule?.slots || [];
  const rows = schedule?.rows || [];
  const currentSlot = state?.slot?.in_window ? state.slot.slot_index : null;

  // Own slower poll: the 12-slot grid is a bigger payload than the hot state
  // poll, and the timeline does not need 2-second resolution.
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await getSchedule(40);
        if (alive) setSchedule(data);
      } catch { /* the hot poll's error banner already covers this */ }
    };
    load();
    const id = setInterval(load, 4000);
    return () => { alive = false; clearInterval(id); };
  }, []);   // mount-only: the interval drives the cadence, the hot poll must not force refetches

  const windows = useMemo(() => {
    const grouped = {};
    slots.forEach((s) => {
      grouped[s.window] = grouped[s.window] || { key: s.window, label: s.window_label, slots: [] };
      grouped[s.window].slots.push(s);
    });
    return Object.values(grouped);
  }, [slots]);

  if (!state) return <div className="m1-muted">loading schedule…</div>;

  const reserved = summary.seats_idle_reserved || 0;

  return (
    <div className="m1-page">
      <div className="m1-page__head">
        <div>
          <h2 className="m1-page__title">Pump Scheduler Timeline</h2>
          <p className="m1-page__sub">
            {fmt(summary.pumps_active)} of {summary.pumps_fleet} pumps active ·
            {' '}{fmt(summary.seats_total)} seats this cycle ·
            {' '}{fmt(summary.runtime_minutes_per_plot)} min per plot ·
            {' '}rebuild cost ~{fmt(summary.rebuild_ms ?? '—')}
          </p>
        </div>
        <label className="m1-toggle">
          <input type="checkbox" checked={onlyEmergency} onChange={(e) => setOnlyEmergency(e.target.checked)} />
          <span>Only emergency plots</span>
        </label>
      </div>

      <div className="m1-badges">
        <span className="m1-chip m1-chip--ok">{fmt(summary.seats_filled)} seats filled</span>
        <span className="m1-chip">{fmt(summary.emergency_seats_used)} to emergencies</span>
        <span className="m1-chip">{fmt(summary.normal_seat_cap)} seats open to normal plots</span>
        {reserved > 0 && <span className="m1-chip m1-chip--warn">{fmt(reserved)} held in reserve</span>}
        <span className="m1-chip">{fmt(summary.unserved_high_priority)} stressed plots still waiting</span>
        {summary.power_cut && <span className="m1-chip m1-chip--err">power cut — evening window shed</span>}
      </div>

      {windows.map((w) => (
        <div className="m1-window" key={w.key}>
          <div className="m1-window__head">
            <h3>{w.label}</h3>
            <span className="m1-muted">
              {w.slots[0]?.slot_label?.split('-')[0]} – {w.slots[w.slots.length - 1]?.slot_label?.split('-')[1]}
              {' · '}{w.slots.reduce((a, s) => a + s.assignments.length, 0)} plots ·
              {' '}{w.slots.reduce((a, s) => a + (s.active_pumps || 0), 0)} seats
            </span>
          </div>
          <div className="m1-slots">
            {w.slots.map((s) => {
              const rows = onlyEmergency ? s.assignments.filter((r) => r.emergency) : s.assignments;
              const shed = (s.active_pumps || 0) === 0;
              return (
                <div className={`m1-slot${shed ? ' m1-slot--shed' : ''}${currentSlot === s.slot_index ? ' m1-slot--now' : ''}`}
                     key={s.slot_index}>
                  <div className="m1-slot__head">
                    <span className="m1-slot__time">{s.slot_label}</span>
                    <span className="m1-slot__count">
                      {shed ? 'shed' : `${rows.length}/${s.active_pumps}`}
                    </span>
                  </div>
                  <div className="m1-slot__body">
                    {rows.map((r) => (
                      <div className={`m1-job${r.emergency ? ' m1-job--emg' : ''}`} key={`${r.slot_index}-${r.pump_id}-${r.plot_id}`}
                           title={r.reason}>
                        <span className="m1-job__pump">{r.pump_id.replace('PUMP-', 'P')}</span>
                        <span className="m1-job__plot">#{r.plot_id}</span>
                        <span className="m1-job__score">{r.stress_score}</span>
                      </div>
                    ))}
                    {!rows.length && !shed && <div className="m1-slot__empty">no assignment</div>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="m1-legend">
        <span><i className="m1-dot m1-dot--emg" /> emergency (below moisture line)</span>
        <span><i className="m1-dot m1-dot--norm" /> normal priority</span>
        <span><i className="m1-dot m1-dot--now" /> current slot</span>
        <span><i className="m1-dot m1-dot--shed" /> shed by power cut</span>
        <span className="m1-muted">hover a job to read its priority reason</span>
      </div>

      <h3 className="m1-h3">Top of the run list</h3>
      <div className="m1-tablewrap">
        <table className="m1-table m1-table--compact">
          <thead>
            <tr><th>Rank</th><th>Slot</th><th>Pump</th><th>Plot</th><th>Village</th><th>Crop</th><th>Score</th><th>Status</th><th>Why this plot</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.slot_index}-${r.plot_id}`} className={r.emergency ? 'm1-row--emergency' : ''}>
                <td className="m1-td-rank">{r.priority_rank}</td>
                <td>{r.slot_label}</td>
                <td className="m1-td-pump">{r.pump_id}</td>
                <td className="m1-td-id">{r.plot_id}</td>
                <td>{r.village}</td>
                <td>{r.crop}</td>
                <td>{r.stress_score}</td>
                <td><StatusPill status={r.status} small /></td>
                <td className="m1-muted m1-why">{r.reason?.replace(/^R\d+: /, '')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
