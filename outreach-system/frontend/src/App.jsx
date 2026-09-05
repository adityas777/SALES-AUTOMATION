import { useState } from "react";
import "./App.css";
import RunCollection from "./screens/RunCollection.jsx";
import Overview from "./screens/Overview.jsx";

const NAV_ITEMS = [
  {
    key: "overview",
    label: "Overview",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="7" height="9" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <rect x="14" y="3" width="7" height="5" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <rect x="14" y="12" width="7" height="9" rx="2" stroke="currentColor" strokeWidth="1.8" />
        <rect x="3" y="16" width="7" height="5" rx="2" stroke="currentColor" strokeWidth="1.8" />
      </svg>
    ),
  },
  {
    key: "run",
    label: "Run collection",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="1.8" />
        <path d="M20 20L16.5 16.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    ),
  },
];

export default function App() {
  const [activeScreen, setActiveScreen] = useState("overview");

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">O</div>
          <div>
            <div className="brand-name">Outreach</div>
            <div className="brand-sub">Automation Console</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.key}
              className={
                "sidebar-link" + (activeScreen === item.key ? " active" : "")
              }
              onClick={() => setActiveScreen(item.key)}
            >
              <span className="sidebar-link-icon">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot" />
          System live
        </div>
      </aside>
      <main className="main-content">
        {activeScreen === "run" ? <RunCollection /> : <Overview />}
      </main>
    </div>
  );
}
