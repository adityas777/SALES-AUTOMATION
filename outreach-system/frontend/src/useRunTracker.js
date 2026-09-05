import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const POLL_MS = 2000;

// Shared by both screens so either one can discover + display a run that's
// already active on the server (started from this screen, the other screen,
// or a different browser tab entirely) - the run itself lives server-side,
// this hook is just a display/control layer on top of it. Losing the poll
// (tab closed, screen switched) never stops the underlying run; re-opening
// either screen picks it back up via GET /api/active-runs.
export function useRunTracker() {
  const [runId, setRunId] = useState(null);
  const [status, setStatus] = useState(null);
  const [feed, setFeed] = useState([]);
  const [checkingActive, setCheckingActive] = useState(true);
  const pollRef = useRef(null);
  const mountedRef = useRef(true);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const pollOnce = useCallback(
    async (id) => {
      try {
        const [statusRes, feedRes] = await Promise.all([
          api.getRunStatus(id),
          api.getRunFeed(id),
        ]);
        if (!mountedRef.current) return;
        setStatus(statusRes);
        setFeed(feedRes);
        if (statusRes.status !== "running") {
          stopPolling();
        }
      } catch {
        if (!mountedRef.current) return;
        stopPolling();
      }
    },
    [stopPolling]
  );

  const track = useCallback(
    (id) => {
      setRunId(id);
      stopPolling();
      pollOnce(id);
      pollRef.current = setInterval(() => pollOnce(id), POLL_MS);
    },
    [pollOnce, stopPolling]
  );

  useEffect(() => {
    mountedRef.current = true;
    api
      .getActiveRuns()
      .then((runs) => {
        if (!mountedRef.current) return;
        if (runs.length > 0) track(runs[0].run_id);
      })
      .catch(() => {})
      .finally(() => {
        if (mountedRef.current) setCheckingActive(false);
      });

    return () => {
      mountedRef.current = false;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function startRun(city, categories) {
    const { run_id } = await api.runCollection(city, categories);
    track(run_id);
  }

  async function stopRun() {
    if (!runId) return;
    await api.stopRun(runId);
    pollOnce(runId);
  }

  return {
    runId,
    status,
    feed,
    isRunning: status?.status === "running",
    checkingActive,
    startRun,
    stopRun,
  };
}
