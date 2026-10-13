import { useState, useCallback } from "react";
import "./App.css";
import RunCollection from "./screens/RunCollection.jsx";
import Overview from "./screens/Overview.jsx";
import VoiceAssistantModal from "./components/VoiceAssistantModal.jsx";
import { useRunTracker } from "./useRunTracker.js";

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
  const [voiceAgentOn, setVoiceAgentOn] = useState(false);
  const { startRun } = useRunTracker();

  const handleVoiceRunStarted = useCallback(async (city, categories) => {
    await startRun(city, categories);
    setActiveScreen("overview");
  }, [startRun]);

  const toggleVoiceAgent = useCallback(() => {
    setVoiceAgentOn((prev) => !prev);
  }, []);

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
        {/* Top bar with voice agent toggle */}
        <div className="top-bar">
          <div className="top-bar-spacer" />
          <button
            className={`voice-toggle-btn ${voiceAgentOn ? "active" : ""}`}
            onClick={toggleVoiceAgent}
            title={voiceAgentOn ? "Turn off voice agent" : "Turn on voice agent"}
          >
            <div className="voice-toggle-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            </div>
            <span className="voice-toggle-label">
              {voiceAgentOn ? "Voice Agent ON" : "Voice Agent"}
            </span>
            <div className={`voice-toggle-switch ${voiceAgentOn ? "on" : ""}`}>
              <div className="voice-toggle-knob" />
            </div>
          </button>
        </div>

        {activeScreen === "run" ? <RunCollection /> : <Overview />}
      </main>

      {/* Voice Agent — rendered when toggle is ON */}
      <VoiceAssistantModal
        isActive={voiceAgentOn}
        onDeactivate={() => setVoiceAgentOn(false)}
        onRunStarted={handleVoiceRunStarted}
      />
    </div>
  );
}
