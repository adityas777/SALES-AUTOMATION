import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { WavAudioRecorder } from "../utils/wavRecorder.js";
import "./VoiceAssistantModal.css";

const LANGUAGES = [
  { code: "en-IN", label: "English (India)", flag: "🇮🇳" },
  { code: "hi-IN", label: "Hindi / Hinglish", flag: "🇮🇳" },
];

function labelize(categoryKey) {
  return (categoryKey || "")
    .split("_")
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : ""))
    .join(" ");
}

/* ─── Animated Orb (Canvas) ─── */
function VoiceOrb({ audioLevel, mode, size = 200 }) {
  const canvasRef = useRef(null);
  const rafRef = useRef(null);
  const smoothLevel = useRef(0);
  const timeRef = useRef(0);
  const audioLevelRef = useRef(audioLevel);
  audioLevelRef.current = audioLevel;

  useEffect(() => {
    const cvs = canvasRef.current;
    if (!cvs) return;
    const ctx = cvs.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    cvs.width = size * dpr;
    cvs.height = size * dpr;
    cvs.style.width = size + "px";
    cvs.style.height = size + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cx = size / 2;
    const cy = size / 2;
    const baseR = size * 0.28;

    function draw() {
      const target = audioLevelRef.current / 100;
      smoothLevel.current += (target - smoothLevel.current) * 0.12;
      const lvl = smoothLevel.current;
      timeRef.current += 0.018;
      const t = timeRef.current;

      ctx.clearRect(0, 0, size, size);

      const isActive = mode === "listening" || mode === "recording";
      const isProcessing = mode === "processing";
      const numRings = isActive ? 5 : 3;

      for (let ring = numRings; ring >= 1; ring--) {
        const ringScale = 1 + ring * 0.12 + lvl * ring * 0.09;
        const alpha = isActive
          ? (0.06 + lvl * 0.04) * (1 - ring / (numRings + 1))
          : 0.03 * (1 - ring / (numRings + 1));

        ctx.beginPath();
        const segments = 120;
        for (let i = 0; i <= segments; i++) {
          const angle = (i / segments) * Math.PI * 2;
          const noiseAmp = isActive ? 6 + lvl * 18 : 2;
          const n1 = Math.sin(angle * 3 + t * 2 + ring) * noiseAmp;
          const n2 = Math.cos(angle * 5 - t * 1.5 + ring * 2) * noiseAmp * 0.6;
          const n3 = Math.sin(angle * 7 + t * 3) * noiseAmp * 0.3;
          const r = baseR * ringScale + n1 + n2 + n3;
          const x = cx + Math.cos(angle) * r;
          const y = cy + Math.sin(angle) * r;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.closePath();
        const hue = 38 + ring * 6;
        ctx.fillStyle = `hsla(${hue}, 85%, 55%, ${alpha})`;
        ctx.fill();
      }

      const coreR = baseR + lvl * 10;
      const grad = ctx.createRadialGradient(
        cx - coreR * 0.25, cy - coreR * 0.25, coreR * 0.1,
        cx, cy, coreR
      );

      if (isProcessing) {
        const pulse = Math.sin(t * 4) * 0.15 + 0.85;
        grad.addColorStop(0, `rgba(244, 217, 127, ${0.95 * pulse})`);
        grad.addColorStop(0.5, `rgba(212, 175, 55, ${0.7 * pulse})`);
        grad.addColorStop(1, `rgba(156, 122, 31, ${0.3 * pulse})`);
      } else if (isActive) {
        grad.addColorStop(0, "rgba(244, 217, 127, 0.95)");
        grad.addColorStop(0.5, "rgba(212, 175, 55, 0.7)");
        grad.addColorStop(1, "rgba(156, 122, 31, 0.25)");
      } else {
        grad.addColorStop(0, "rgba(212, 175, 55, 0.6)");
        grad.addColorStop(0.5, "rgba(156, 122, 31, 0.35)");
        grad.addColorStop(1, "rgba(100, 80, 20, 0.1)");
      }

      ctx.beginPath();
      const coreSegments = 180;
      for (let i = 0; i <= coreSegments; i++) {
        const angle = (i / coreSegments) * Math.PI * 2;
        const noiseAmp = isActive ? 3 + lvl * 12 : 1.5;
        const n = Math.sin(angle * 4 + t * 2.5) * noiseAmp
               + Math.cos(angle * 6 - t * 1.8) * noiseAmp * 0.5
               + Math.sin(angle * 9 + t * 3.5) * noiseAmp * 0.3;
        const r = coreR + n;
        const x = cx + Math.cos(angle) * r;
        const y = cy + Math.sin(angle) * r;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();

      if (isActive || isProcessing) {
        const numParticles = isActive ? 40 + Math.floor(lvl * 40) : 20;
        for (let i = 0; i < numParticles; i++) {
          const angle = (i / numParticles) * Math.PI * 2 + t * 0.3;
          const dist = coreR + 10 + Math.sin(angle * 3 + t + i) * (8 + lvl * 15);
          const px = cx + Math.cos(angle) * dist;
          const py = cy + Math.sin(angle) * dist;
          const sz = 1 + Math.random() * 1.5;
          ctx.beginPath();
          ctx.arc(px, py, sz, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(244, 217, 127, ${0.3 + lvl * 0.5})`;
          ctx.fill();
        }
      }

      const hlGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 0.4);
      hlGrad.addColorStop(0, `rgba(255, 245, 210, ${isActive ? 0.35 + lvl * 0.2 : 0.15})`);
      hlGrad.addColorStop(1, "rgba(255, 245, 210, 0)");
      ctx.beginPath();
      ctx.arc(cx, cy, coreR * 0.4, 0, Math.PI * 2);
      ctx.fillStyle = hlGrad;
      ctx.fill();

      rafRef.current = requestAnimationFrame(draw);
    }

    draw();
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [mode, size]);

  return <canvas ref={canvasRef} className="voice-orb-canvas" />;
}

/* ─── Main Voice Agent ─── */
/*
  Agent modes:
  - "greeting"   : Just activated, says hello, starts listening
  - "listening"  : Actively recording user speech
  - "processing" : Transcribing + parsing
  - "setup"      : Shows detected city/categories for confirmation
  - "running"    : Automation started, mini mode, can answer updates
  - "responding" : Agent speaking a response (mini panel)
  - "idle"       : Toggled on but not doing anything special
*/
export default function VoiceAssistantModal({ isActive, onDeactivate, onRunStarted }) {
  const [lang, setLang] = useState("en-IN");
  const [mode, setMode] = useState("idle");
  const [audioLevel, setAudioLevel] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const [transcript, setTranscript] = useState("");
  const [parsedCity, setParsedCity] = useState("");
  const [parsedCategories, setParsedCategories] = useState([]);
  const [spokenResponse, setSpokenResponse] = useState("");
  const [allCategories, setAllCategories] = useState([]);
  const [knownCities, setKnownCities] = useState([]);

  // For the mini update panel
  const [summaryText, setSummaryText] = useState("");
  const [showSetupModal, setShowSetupModal] = useState(false);

  const wavRecorderRef = useRef(null);
  const currentAudioRef = useRef(null);
  const parsedCityRef = useRef(parsedCity);
  parsedCityRef.current = parsedCity;
  const parsedCategoriesRef = useRef(parsedCategories);
  parsedCategoriesRef.current = parsedCategories;
  const modeRef = useRef(mode);
  modeRef.current = mode;
  const showSetupModalRef = useRef(showSetupModal);
  showSetupModalRef.current = showSetupModal;
  const pendingConfirmRef = useRef(false);

  // Load categories on mount
  useEffect(() => {
    Promise.all([api.getCategories(), api.getLocations()])
      .then(([cats, locs]) => {
        setAllCategories(cats || []);
        setKnownCities(locs || []);
      })
      .catch(() => {});
  }, []);

  // Handle activation / deactivation
  useEffect(() => {
    if (isActive && mode === "idle") {
      greet();
    }
    if (!isActive) {
      cleanup();
      setMode("idle");
      setShowSetupModal(false);
      pendingConfirmRef.current = false;
      setErrorMessage("");
      setSummaryText("");
    }
  }, [isActive]);

  function greet() {
    setMode("greeting");
    setStatusText("How can I help you?");
    setErrorMessage("");
    setTranscript("");
    setParsedCity("");
    setParsedCategories([]);
    setSummaryText("");
    speak("How can I help you? Tell me the city and business type to get started.", () => {
      startListening();
    });
  }

  const isSpeakingRef = useRef(false);
  const echoTimeoutRef = useRef(null);

  function speak(text, onEnd) {
    setSpokenResponse(text);
    isSpeakingRef.current = true;

    // Stop microphone if currently recording while TTS speaks
    if (wavRecorderRef.current) {
      wavRecorderRef.current.stop().catch(() => {});
      wavRecorderRef.current = null;
    }

    const safeOnEnd = () => {
      // 800ms echo suppression buffer so microphone doesn't pick up speaker sound/room tail
      if (echoTimeoutRef.current) clearTimeout(echoTimeoutRef.current);
      echoTimeoutRef.current = setTimeout(() => {
        isSpeakingRef.current = false;
        onEnd?.();
      }, 800);
    };

    // Use browser speech synthesis as it's instant (no API delay)
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = lang === "hi-IN" ? "hi-IN" : "en-IN";
      utterance.rate = 1.05;
      utterance.onend = safeOnEnd;
      utterance.onerror = safeOnEnd;
      window.speechSynthesis.speak(utterance);
    } else {
      setTimeout(safeOnEnd, 1500);
    }
  }

  async function startListening() {
    // DO NOT open mic if agent is currently speaking or in echo buffer
    if (isSpeakingRef.current) return;

    setErrorMessage("");
    try {
      if (wavRecorderRef.current) {
        await wavRecorderRef.current.stop().catch(() => {});
      }
      const recorder = new WavAudioRecorder();
      wavRecorderRef.current = recorder;
      await recorder.start(
        (level) => setAudioLevel(level),
        () => {
          // Silence detected after speaking — auto stop recording!
          stopListening();
        }
      );
      setMode("listening");
      setStatusText("Listening...");
    } catch (err) {
      console.error("Mic error:", err);
      setErrorMessage("Microphone access denied.");
      setMode("idle");
    }
  }

  async function stopListening() {
    if (!wavRecorderRef.current) return;
    setAudioLevel(0);

    try {
      const wavBlob = await wavRecorderRef.current.stop();
      wavRecorderRef.current = null;
      if (wavBlob && wavBlob.size > 100) {
        await processAudio(wavBlob);
      } else {
        // Nothing captured, keep listening
        setStatusText("Didn't catch that. Try again.");
        setTimeout(() => startListening(), 1500);
      }
    } catch (err) {
      console.error("Stop error:", err);
      setMode("idle");
    }
  }

  async function processAudio(audioBlob) {
    setMode("processing");
    setStatusText("Processing...");

    const currentState = showSetupModalRef.current || modeRef.current === "setup"
      ? "CONFIRMING"
      : modeRef.current === "running"
      ? "RUNNING"
      : "IDLE";

    try {
      const data = await api.processVoiceAudio(
        audioBlob,
        lang,
        currentState,
        parsedCityRef.current || "",
        parsedCategoriesRef.current || []
      );
      setTranscript(data.transcript || "");
      handleIntent(data);
    } catch (err) {
      console.error("Voice processing error:", err);
      setErrorMessage(err.message || "Failed to process audio.");
      setStatusText("Something went wrong. Try again.");
      setTimeout(() => startListening(), 2000);
    }
  }

  const CONFIRM_REGEX = /\b(yes|yeah|yep|yup|ok|okay|sure|confirm|go\s*ahead|start|launch|sounds?\s*(good|great|perfect|nice|fine)|looks?\s*(good|great|perfect)|go\s*for\s*it|let'?s\s*go|do\s*it|proceed|theek\s*hai|thik\s*hai|haan|han|ha|chalo|shuru\s*karo|sahi\s*hai|bilkul|karo)\b/i;
  const STATUS_REGEX = /\b(updates?|status|progress|how'?s\s*it|what'?s\s*happening|tell\s*me|give\s*me|show\s*me|summary|report|kitna\s*hua|kya\s*update)\b/i;
  const IGNORE_PATTERNS = /^\s*(thank\s*you|thanks|thanking\s*you|hello|hi|hey|bye|goodbye|okay\s*thanks|thank\s*you\s*so\s*much)\s*$/i;

  function handleIntent(data) {
    const intent = data.intent || "search";
    const rawTranscript = (data.transcript || "").trim();

    // Ignore phantom self-hearing / polite filler utterances
    if (IGNORE_PATTERNS.test(rawTranscript)) {
      setTimeout(() => startListening(), 1000);
      return;
    }

    const isModalOpen = showSetupModalRef.current || modeRef.current === "setup" || pendingConfirmRef.current;
    const isConfirmPhrase = CONFIRM_REGEX.test(rawTranscript);
    const isStatusPhrase = intent === "status_update" || STATUS_REGEX.test(rawTranscript);

    // Status queries: fetch & speak dashboard summary without changing slots or modal state
    if (isStatusPhrase) {
      fetchAndSpeakSummary();
      return;
    }

    // Confirmation when modal is open
    if (isModalOpen && (intent === "confirm" || isConfirmPhrase)) {
      pendingConfirmRef.current = false;
      executeCollection();
      return;
    }

    // Conservative slot update: only update if valid values returned
    if (data.city) setParsedCity(data.city);
    if (data.categories && data.categories.length > 0) setParsedCategories(data.categories);

    switch (intent) {
      case "search":
      case "edit":
        setSpokenResponse(data.spoken_response || "");
        setShowSetupModal(true);
        pendingConfirmRef.current = true;
        setMode("setup");
        setStatusText("Review and confirm");

        const cityName = data.city || parsedCityRef.current || "your location";
        const catList = (data.categories && data.categories.length > 0) ? data.categories : parsedCategoriesRef.current;
        const catNames = catList.map((c) => labelize(c)).join(", ") || "all categories";
        const msg = intent === "edit"
          ? `Updated to ${catNames} in ${cityName}. Shall I start the collection?`
          : `I found ${catNames} in ${cityName}. Shall I start the collection?`;
        speak(msg, () => {
          startListening();
        });
        break;

      case "confirm":
        if (isModalOpen) {
          pendingConfirmRef.current = false;
          executeCollection();
        } else {
          speak("There's nothing to confirm right now. Tell me what city and category you'd like.", () => {
            startListening();
          });
        }
        break;

      case "cancel":
        pendingConfirmRef.current = false;
        setShowSetupModal(false);
        setParsedCity("");
        setParsedCategories([]);
        setMode("idle");
        speak("Alright, cancelled.", () => {
          startListening();
        });
        break;

      case "status_update":
        fetchAndSpeakSummary();
        break;

      default:
        speak("I didn't quite get that. You can tell me a city and business type, or ask for an update.", () => {
          startListening();
        });
        break;
    }
  }

  async function fetchAndSpeakSummary() {
    setMode("responding");
    setStatusText("Fetching update...");

    function onSummaryEnded() {
      if (showSetupModalRef.current) {
        setMode("setup");
        setStatusText("Review and confirm");
      } else {
        setMode("idle");
        setStatusText("Listening for commands...");
      }
      startListening();
    }

    try {
      // Use the shared api module (consistent base URL) with a 25 s timeout.
      // 25 s covers: 12 s Airtable cold cache + ~2 s Groq + network round-trip.
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 25000);

      const hostname = window.location.hostname || "localhost";
      const res = await fetch(`http://${hostname}:8000/api/voice/smart-summary`, {
        signal: controller.signal,
      });
      clearTimeout(timeoutId);

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const text =
        (data.summary || "").trim() ||
        "System is ready. No active runs right now.";

      console.log("[VoiceAgent] smart-summary received:", text);
      setSummaryText(text);
      setStatusText("Speaking update...");
      speak(text, onSummaryEnded);
    } catch (err) {
      console.error("[VoiceAgent] Failed to fetch smart-summary:", err);
      const fallbackText =
        err.name === "AbortError"
          ? "Dashboard is loading, please try again in a moment."
          : "System is live. No collection runs are currently active.";
      setSummaryText(fallbackText);
      speak(fallbackText, onSummaryEnded);
    }
  }

  const executeCollection = useCallback(async () => {
    pendingConfirmRef.current = false;
    const city = (parsedCityRef.current || "").trim();
    if (!city) {
      setErrorMessage("Please specify a city name.");
      speak("I need a city name to start. Which city should I look in?", () => {
        startListening();
      });
      return;
    }

    setShowSetupModal(false);
    setMode("running");
    setStatusText(`Starting collection for ${city}...`);
    speak(`Starting the collection for ${city} now.`);

    try {
      await onRunStarted(city, parsedCategoriesRef.current);
      setStatusText("Collection started! Ask me for updates anytime.");
      // Stay active and listening
      setTimeout(() => startListening(), 3000);
    } catch (err) {
      setErrorMessage(err.message || "Failed to start collection.");
      setMode("setup");
      setShowSetupModal(true);
    }
  }, [onRunStarted]);

  function toggleCategory(catKey) {
    setParsedCategories((prev) =>
      prev.includes(catKey) ? prev.filter((k) => k !== catKey) : [...prev, catKey]
    );
  }

  function cleanup() {
    if (wavRecorderRef.current) {
      wavRecorderRef.current.stop().catch(() => {});
      wavRecorderRef.current = null;
    }
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current = null;
    }
  }

  if (!isActive) return null;

  const isListeningOrRecording = mode === "listening";
  const showMini = !showSetupModal && mode !== "idle";

  return (
    <>
      {/* ── Mini Voice Indicator (always visible when agent is on) ── */}
      <div className={`voice-mini-panel ${showMini ? "expanded" : ""}`}>
        <div
          className="voice-mini-orb-wrap"
          onClick={isListeningOrRecording ? stopListening : startListening}
          role="button"
          tabIndex={0}
          title={isListeningOrRecording ? "Click to stop" : "Click to speak"}
        >
          <VoiceOrb audioLevel={audioLevel} mode={mode} size={80} />
          <div className="voice-mini-icon">
            {mode === "processing" ? (
              <div className="voice-spin-sm" />
            ) : isListeningOrRecording ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              </svg>
            )}
          </div>
        </div>

        <div className="voice-mini-info">
          <span className="voice-mini-status">{statusText}</span>
          {transcript && mode !== "setup" && (
            <span className="voice-mini-transcript">"{transcript}"</span>
          )}
          {summaryText && mode === "responding" && (
            <span className="voice-mini-summary">{summaryText}</span>
          )}
          {errorMessage && (
            <span className="voice-mini-error">{errorMessage}</span>
          )}
        </div>
      </div>

      {/* ── Full Setup Modal (only for city/category confirmation) ── */}
      {showSetupModal && (
        <div className="voice-modal-backdrop" onClick={() => {}}>
          <div className="voice-modal-container" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="voice-modal-header">
              <div className="voice-modal-title">
                <div className="voice-header-orb">
                  <span className="voice-header-orb-inner" />
                </div>
                <div>
                  <h3>Confirm Collection</h3>
                  <p className="voice-modal-subtitle">Review what I heard — say "Sounds good" or edit below</p>
                </div>
              </div>
              <button className="voice-close-btn" onClick={() => { pendingConfirmRef.current = false; setShowSetupModal(false); setMode("idle"); }} title="Close">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>

            {/* Language */}
            <div className="voice-lang-bar">
              <span className="voice-lang-label">Language:</span>
              {LANGUAGES.map((l) => (
                <button
                  key={l.code}
                  className={`voice-lang-chip ${lang === l.code ? "active" : ""}`}
                  onClick={() => setLang(l.code)}
                >
                  <span className="voice-lang-flag">{l.flag}</span> {l.label}
                </button>
              ))}
            </div>

            {/* Orb + listening state */}
            <div className="voice-orb-section">
              <div
                className={`voice-orb-wrapper ${mode}`}
                onClick={isListeningOrRecording ? stopListening : startListening}
                role="button"
                tabIndex={0}
              >
                <VoiceOrb audioLevel={audioLevel} mode={mode} size={160} />
                <div className="voice-orb-icon-overlay">
                  {mode === "processing" ? (
                    <div className="voice-processing-spinner" />
                  ) : isListeningOrRecording ? (
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor">
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    </svg>
                  ) : (
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                      <line x1="12" y1="19" x2="12" y2="23" />
                      <line x1="8" y1="23" x2="16" y2="23" />
                    </svg>
                  )}
                </div>
              </div>
              {isListeningOrRecording && (
                <p className="voice-hint-text">Listening... say "Sounds good" to confirm or "Cancel"</p>
              )}
            </div>

            {/* Transcript */}
            {transcript && (
              <div className="voice-transcript-card">
                <div className="voice-card-label">You said:</div>
                <div className="voice-transcript-text">"{transcript}"</div>
              </div>
            )}

            {errorMessage && <div className="voice-error-banner">{errorMessage}</div>}

            {/* City + Categories */}
            <div className="voice-result-card">
              <div className="voice-entity-group">
                <label className="voice-entity-label">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                    <circle cx="12" cy="10" r="3" />
                  </svg>
                  Target City:
                </label>
                <input
                  type="text"
                  className="voice-city-input"
                  value={parsedCity}
                  onChange={(e) => setParsedCity(e.target.value)}
                  placeholder="e.g. Pune"
                  list="voice-known-cities"
                />
                <datalist id="voice-known-cities">
                  {knownCities.map((c) => <option key={c} value={c} />)}
                </datalist>
              </div>

              <div className="voice-entity-group">
                <label className="voice-entity-label">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                    <line x1="7" y1="7" x2="7.01" y2="7" />
                  </svg>
                  Categories ({parsedCategories.length > 0 ? parsedCategories.length : "All"}):
                </label>
                <div className="voice-categories-grid">
                  {allCategories.map((catKey) => {
                    const isSelected = parsedCategories.includes(catKey);
                    return (
                      <button
                        key={catKey}
                        type="button"
                        className={`voice-cat-tag ${isSelected ? "selected" : ""}`}
                        onClick={() => toggleCategory(catKey)}
                      >
                        {labelize(catKey)} {isSelected && "✓"}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="voice-modal-footer">
              <button className="voice-btn-secondary" onClick={() => { setShowSetupModal(false); setMode("idle"); startListening(); }}>
                🎙 Re-speak
              </button>
              <button
                className="voice-btn-primary"
                onClick={executeCollection}
                disabled={!parsedCity.trim()}
              >
                🚀 Launch Collection
              </button>
              <button className="voice-btn-ghost" onClick={() => { setShowSetupModal(false); setMode("idle"); }}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
