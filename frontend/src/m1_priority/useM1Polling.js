/**
 * KJS-AGR-01 | Member 1
 * useM1Polling.js -- one polling subscription for the whole module.
 *
 * Why one and not one per panel: three panels polling independently triples the
 * request rate and lets the panels disagree about the tick they are showing.
 * Everything reads from this single snapshot, so the board, timeline and alerts
 * are always consistent with each other.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { getState } from './m1Api';

export function useM1Polling(intervalMs = 2000, { scheduleRows = 288, alerts = 60 } = {}) {
  const [state, setState] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [paused, setPaused] = useState(false);
  const timer = useRef(null);
  const inFlight = useRef(false);

  const fetchOnce = useCallback(async () => {
    if (inFlight.current) return null;
    inFlight.current = true;
    try {
      const data = await getState(scheduleRows, alerts);
      setState(data);
      setError(null);
      setLastUpdated(new Date());
      return data;
    } catch (err) {
      setError(err.message || String(err));
      return null;
    } finally {
      inFlight.current = false;
      setLoading(false);
    }
  }, [scheduleRows, alerts]);

  useEffect(() => {
    fetchOnce();
    if (paused) return undefined;
    timer.current = setInterval(fetchOnce, intervalMs);
    return () => clearInterval(timer.current);
  }, [fetchOnce, intervalMs, paused]);

  return {
    state, error, loading, lastUpdated, paused,
    setPaused, refresh: fetchOnce,
  };
}

export default useM1Polling;
