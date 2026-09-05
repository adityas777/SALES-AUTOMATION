import { useEffect, useState } from "react";
import "./LiveFeedPanel.css";

function elapsedLabel(startedAt) {
  const start = new Date(startedAt).getTime();
  const secs = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const m = Math.floor(secs / 60)
    .toString()
    .padStart(2, "0");
  const s = (secs % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

const STATUS_LABEL = {
  running: "Collecting",
  stopped: "Stopped",
  completed: "Completed",
  failed: "Failed",
};

// This is the "what is the system actually fetching right now" view - each
// row appears the moment a business is written to Airtable, so it's a real
// feed of server activity, not a simulated progress bar.
export default function LiveFeedPanel({ status, feed, isRunning, onStop }) {
  const [, forceTick] = useState(0);

  useEffect(() => {
    if (!isRunning) return;
    const t = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [isRunning]);

  if (!status) return null;

  const categoryLabel = status.categories?.length
    ? status.categories.join(", ")
    : "all categories";

  return (
    <div className={"feed-panel " + (isRunning ? "feed-panel-running" : "")}>
      <div className="feed-header">
        <div className="feed-header-title">
          {isRunning && <span className="spinner" />}
          <strong>{STATUS_LABEL[status.status] || status.status}:</strong>
          <span>
            {categoryLabel} in {status.city}
          </span>
        </div>
        <div className="feed-header-metrics">
          {isRunning && <span>Elapsed: {elapsedLabel(status.started_at)}</span>}
          <span>Found: {status.businesses_found}</span>
          <span>New: {status.new_businesses}</span>
          {isRunning && (
            <button className="btn btn-outline" onClick={onStop}>
              Stop
            </button>
          )}
        </div>
      </div>

      <div className="feed-list">
        {feed.length === 0 && (
          <div className="feed-empty">Waiting for the first result...</div>
        )}
        {feed.map((row, i) => (
          <div key={i} className="feed-row">
            <span className="feed-row-name">{row.name}</span>
            <span className="badge badge-category">{row.category}</span>
            <span className="feed-row-address">{row.address}</span>
            {row.phone && <span className="feed-row-phone">{row.phone}</span>}
            {row.website && (
              <a
                className="feed-row-website"
                href={row.website}
                target="_blank"
                rel="noreferrer"
              >
                website
              </a>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
