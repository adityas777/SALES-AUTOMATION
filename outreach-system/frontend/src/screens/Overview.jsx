import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useRunTracker } from "../useRunTracker.js";
import LiveFeedPanel from "../components/LiveFeedPanel.jsx";
import "./Overview.css";

const FUNNEL_STAGES = [
  { key: "queued", label: "Queued" },
  { key: "contacted", label: "Contacted" },
  { key: "follow_up", label: "Follow-up" },
  { key: "responded", label: "Responded" },
];

const ICONS = {
  calendar: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <rect x="3" y="5" width="18" height="16" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3 10H21" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 3V7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M16 3V7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M8 14l2.5 2.5L16 11" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  chat: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path
        d="M4 12a8 8 0 1 1 3.2 6.4L4 20l1.1-3.5A7.96 7.96 0 0 1 4 12Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  ),
  star: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path
        d="M12 3.5l2.6 5.5 6 .7-4.4 4.1 1.2 6-5.4-3-5.4 3 1.2-6-4.4-4.1 6-.7L12 3.5Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinejoin="round"
      />
    </svg>
  ),
  alert: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
      <path
        d="M10.3 4.2 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M12 10v4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="12" cy="17.2" r="0.9" fill="currentColor" />
    </svg>
  ),
};

function formatTimestamp(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export default function Overview() {
  const [stats, setStats] = useState(null);
  const [queue, setQueue] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [resolvingId, setResolvingId] = useState(null);
  const { runId, status: runStatus, feed, isRunning, stopRun } = useRunTracker();

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [statsRes, queueRes] = await Promise.all([
        api.getStats(),
        api.getHandoffQueue(),
      ]);
      setStats(statsRes);
      setQueue(queueRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleResolve(businessId) {
    setResolvingId(businessId);
    setQueue((prev) => prev.filter((row) => row.business_id !== businessId));
    try {
      await api.resolveHandoff(businessId);
    } catch (err) {
      setError(`Failed to resolve: ${err.message}`);
      load();
    } finally {
      setResolvingId(null);
    }
  }

  const funnelTotal = stats
    ? FUNNEL_STAGES.reduce((sum, s) => sum + (stats.funnel[s.key] || 0), 0)
    : 0;

  return (
    <div>
      <div className="page-header page-header-row">
        <div>
          <h1>Overview</h1>
          <p>What needs your attention right now.</p>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={loading}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && <div className="banner banner-danger">{error}</div>}

      {runId && (
        <LiveFeedPanel status={runStatus} feed={feed} isRunning={isRunning} onStop={stopRun} />
      )}

      {stats && (
        <>
          <div className="metric-grid">
            <div className="metric-card">
              <div className="metric-icon metric-icon-info">{ICONS.calendar}</div>
              <div className="metric-value">{stats.contacted_today}</div>
              <div className="metric-label">Contacted today</div>
            </div>
            <div className="metric-card">
              <div className="metric-icon metric-icon-primary">{ICONS.chat}</div>
              <div className="metric-value">{Math.round(stats.reply_rate * 100)}%</div>
              <div className="metric-label">Reply rate</div>
            </div>
            <div className="metric-card metric-card-success">
              <div className="metric-icon metric-icon-success">{ICONS.star}</div>
              <div className="metric-value">{stats.interested_count}</div>
              <div className="metric-label">Interested</div>
            </div>
            <div className="metric-card metric-card-warning">
              <div className="metric-icon metric-icon-warning">{ICONS.alert}</div>
              <div className="metric-value">{stats.needs_human_count}</div>
              <div className="metric-label">Needs human</div>
            </div>
          </div>

          <div className="funnel-card">
            <div className="funnel-title">Pipeline funnel</div>
            <div className="funnel-bar">
              {FUNNEL_STAGES.map((stage) => {
                const count = stats.funnel[stage.key] || 0;
                const pct = funnelTotal ? (count / funnelTotal) * 100 : 0;
                return (
                  <div
                    key={stage.key}
                    className={`funnel-segment funnel-${stage.key}`}
                    style={{ width: `${pct}%` }}
                    title={`${stage.label}: ${count}`}
                  />
                );
              })}
            </div>
            <div className="funnel-legend">
              {FUNNEL_STAGES.map((stage) => (
                <div key={stage.key} className="funnel-legend-item">
                  <span className={`funnel-dot funnel-${stage.key}`} />
                  {stage.label}: {stats.funnel[stage.key] || 0}
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="queue-section">
        <h2 className="section-title">Needs your attention ({queue.length})</h2>
        {queue.length === 0 && !loading && (
          <div className="empty-state">Nothing needs attention right now.</div>
        )}
        <div className="queue-list">
          {queue.map((row) => (
            <div key={row.business_id} className="queue-row">
              <div className="queue-row-main">
                <div className="queue-row-title">
                  <strong>{row.name}</strong>
                  <span className="badge badge-category">{row.category}</span>
                  <span className="badge badge-reason">{row.reason}</span>
                </div>
                <div className="queue-row-sub">{row.city}</div>
                {row.last_message && (
                  <div className="queue-row-message">"{row.last_message.slice(0, 160)}"</div>
                )}
                <div className="queue-row-timestamp">{formatTimestamp(row.timestamp)}</div>
              </div>
              <button
                className="btn btn-outline"
                onClick={() => handleResolve(row.business_id)}
                disabled={resolvingId === row.business_id}
              >
                Mark resolved
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
