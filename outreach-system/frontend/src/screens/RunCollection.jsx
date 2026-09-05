import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useRunTracker } from "../useRunTracker.js";
import "./RunCollection.css";

function labelize(categoryKey) {
  return categoryKey
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

export default function RunCollection() {
  const [knownCities, setKnownCities] = useState([]);
  const [categories, setCategories] = useState([]);
  const [city, setCity] = useState("");
  const [selectedCategories, setSelectedCategories] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [startError, setStartError] = useState("");

  const { status, isRunning, checkingActive, startRun, stopRun } = useRunTracker();

  useEffect(() => {
    Promise.all([api.getLocations(), api.getCategories()])
      .then(([locs, cats]) => {
        setKnownCities(locs);
        setCategories(cats);
      })
      .catch((err) => setLoadError(err.message));
  }, []);

  function toggleCategory(key) {
    setSelectedCategories((prev) =>
      prev.includes(key) ? prev.filter((c) => c !== key) : [...prev, key]
    );
  }

  async function handleRun() {
    if (!city.trim()) return;
    setStartError("");
    try {
      await startRun(city.trim(), selectedCategories);
    } catch (err) {
      setStartError(err.message);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>Run collection</h1>
        <p>
          Manually trigger a collection run: finds businesses on Google Maps,
          enriches, dedupes, pushes to Airtable, and sends first-touch
          outreach automatically. Once started, this keeps running on the
          server even if you navigate away or close this tab - come back any
          time to check progress, or press Stop to end it early.
        </p>
      </div>

      {loadError && <div className="banner banner-danger">{loadError}</div>}
      {startError && <div className="banner banner-danger">{startError}</div>}

      {checkingActive ? (
        <p className="hint">Checking for an in-progress run...</p>
      ) : isRunning ? (
        <div className="run-status run-status-running">
          <div className="run-status-message">
            <span className="spinner" />A run is already in progress for{" "}
            <strong>{status.city}</strong> - see live progress on the Overview
            screen, or stop it below.
          </div>
          <div className="run-status-metrics">
            <span>Found: {status.businesses_found}</span>
            <span>New: {status.new_businesses}</span>
            <span>Contacted: {status.contacted}</span>
          </div>
          <button className="btn btn-outline" style={{ marginTop: 12 }} onClick={stopRun}>
            Stop
          </button>
        </div>
      ) : (
        <div className="run-form">
          <div className="form-row">
            <label htmlFor="city-input">City</label>
            <input
              id="city-input"
              type="text"
              placeholder="e.g. Bhilai, Chhattisgarh"
              value={city}
              onChange={(e) => setCity(e.target.value)}
              list="known-cities"
            />
            <datalist id="known-cities">
              {knownCities.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
            <p className="hint">
              Any city works - it doesn't need to be pre-configured in
              locations.yaml.
            </p>
          </div>

          <div className="form-row">
            <label>Categories</label>
            <p className="hint">Leave all unchecked to search every category.</p>
            <div className="category-grid">
              {categories.map((cat) => (
                <label key={cat} className="category-checkbox">
                  <input
                    type="checkbox"
                    checked={selectedCategories.includes(cat)}
                    onChange={() => toggleCategory(cat)}
                  />
                  {labelize(cat)}
                </label>
              ))}
            </div>
          </div>

          <button className="btn btn-primary" onClick={handleRun} disabled={!city.trim()}>
            Run collection
          </button>
        </div>
      )}

      {status && !isRunning && (
        <div
          className={
            "run-status " +
            (status.status === "failed" ? "run-status-failed" : "run-status-done")
          }
        >
          <div className="run-status-message">{status.status_message}</div>
          {status.errors?.length > 0 && (
            <ul className="run-errors">
              {status.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
