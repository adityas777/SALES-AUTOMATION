/**
 * Robust browser audio recorder that produces clean WAV files.
 *
 * Strategy: Use the browser's native MediaRecorder (which always works)
 * to capture audio, then decode it via OfflineAudioContext to get raw PCM,
 * downsample to 16 kHz mono, and encode as a proper WAV file.
 *
 * This avoids the ScriptProcessorNode pitfalls (deprecated, drops frames,
 * browsers ignore sampleRate constraints) while producing audio that
 * Gnani STT and Groq Whisper both accept.
 */

// ── WAV encoder ────────────────────────────────────────────────

function writeString(view, offset, str) {
  for (let i = 0; i < str.length; i++) {
    view.setUint8(offset + i, str.charCodeAt(i));
  }
}

function float32ToInt16(samples) {
  const buf = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    buf[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return buf;
}

function encodeWAV(pcm16, sampleRate) {
  const numSamples = pcm16.length;
  const byteRate = sampleRate * 2; // 16-bit mono
  const buffer = new ArrayBuffer(44 + numSamples * 2);
  const view = new DataView(buffer);

  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + numSamples * 2, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);   // PCM
  view.setUint16(22, 1, true);   // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, 2, true);   // block align
  view.setUint16(34, 16, true);  // bits per sample

  writeString(view, 36, "data");
  view.setUint32(40, numSamples * 2, true);

  // Copy int16 PCM data
  const dst = new Int16Array(buffer, 44);
  dst.set(pcm16);

  return new Blob([buffer], { type: "audio/wav" });
}

// ── Downsampler ────────────────────────────────────────────────

function downsample(channelData, fromRate, toRate) {
  if (fromRate === toRate) return channelData;
  const ratio = fromRate / toRate;
  const newLen = Math.round(channelData.length / ratio);
  const result = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    const srcIdx = i * ratio;
    const lo = Math.floor(srcIdx);
    const hi = Math.min(lo + 1, channelData.length - 1);
    const frac = srcIdx - lo;
    result[i] = channelData[lo] * (1 - frac) + channelData[hi] * frac;
  }
  return result;
}

// ── Public recorder class ──────────────────────────────────────

const TARGET_SAMPLE_RATE = 16000;

export class WavAudioRecorder {
  constructor() {
    this._stream = null;
    this._mediaRecorder = null;
    this._chunks = [];
    this._analyser = null;
    this._analyserCtx = null;
    this._rafId = null;
    this._onAudioLevel = null;
    this._onSilence = null;
    this._silenceTimer = null;
  }

  /**
   * Start recording.
   * @param {function} onAudioLevel - Callback (0-100) ~60 fps for waveform visualizer
   * @param {function} [onSilence] - Callback triggered when user stops speaking (silence after speech)
   * @param {object} [options] - VAD options
   */
  async start(onAudioLevel, onSilence, options = {}) {
    this._onAudioLevel = onAudioLevel;
    this._onSilence = onSilence;
    this._vadOptions = {
      silenceThreshold: options.silenceThreshold ?? 6,    // 0-100 scale
      speechThreshold: options.speechThreshold ?? 10,     // 0-100 scale
      silenceDurationMs: options.silenceDurationMs ?? 1600,// 1.6s of silence after speech
      minSpeechDurationMs: options.minSpeechDurationMs ?? 600, // 0.6s min speech required
    };

    this._stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    // ── Set up a live analyser for the waveform bars & VAD ──
    try {
      const ActxClass = window.AudioContext || window.webkitAudioContext;
      this._analyserCtx = new ActxClass();
      this._analyser = this._analyserCtx.createAnalyser();
      this._analyser.fftSize = 256;
      const src = this._analyserCtx.createMediaStreamSource(this._stream);
      src.connect(this._analyser);
      this._pumpLevel();
    } catch (_) {
      /* visualizer is optional */
    }

    // ── Record with MediaRecorder (browser picks best codec) ──
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
      ? "audio/webm"
      : "";

    this._mediaRecorder = new MediaRecorder(
      this._stream,
      mimeType ? { mimeType } : undefined
    );
    this._chunks = [];

    this._mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) this._chunks.push(e.data);
    };

    // Request data every 250 ms so we don't lose the last chunk
    this._mediaRecorder.start(250);
  }

  /**
   * Stop recording and return a clean 16 kHz mono WAV Blob.
   */
  async stop() {
    // Stop the analyser loop
    if (this._rafId) cancelAnimationFrame(this._rafId);
    this._rafId = null;
    if (this._analyserCtx) {
      this._analyserCtx.close().catch(() => {});
      this._analyserCtx = null;
      this._analyser = null;
    }

    // Stop MediaRecorder
    await new Promise((resolve) => {
      if (!this._mediaRecorder || this._mediaRecorder.state === "inactive") {
        resolve();
        return;
      }
      this._mediaRecorder.onstop = resolve;
      this._mediaRecorder.stop();
    });

    // Stop mic stream
    if (this._stream) {
      this._stream.getTracks().forEach((t) => t.stop());
      this._stream = null;
    }

    // Combine chunks into a single blob
    const recBlob = new Blob(this._chunks, {
      type: this._mediaRecorder?.mimeType || "audio/webm",
    });
    this._mediaRecorder = null;
    this._chunks = [];

    if (recBlob.size < 100) return recBlob; // nothing meaningful recorded

    // ── Decode the browser recording into raw PCM ──
    const arrayBuf = await recBlob.arrayBuffer();
    const ActxClass = window.AudioContext || window.webkitAudioContext;
    const tempCtx = new ActxClass();
    let decoded;
    try {
      decoded = await tempCtx.decodeAudioData(arrayBuf);
    } catch (err) {
      console.error("Failed to decode recorded audio:", err);
      await tempCtx.close().catch(() => {});
      // Return original blob as fallback — backend Whisper can handle webm
      return recBlob;
    }
    await tempCtx.close().catch(() => {});

    // ── Downsample to 16 kHz mono and encode to WAV ──
    const rawPcm = decoded.getChannelData(0); // mono channel
    const nativeSR = decoded.sampleRate;

    const pcm16k = downsample(rawPcm, nativeSR, TARGET_SAMPLE_RATE);
    const int16 = float32ToInt16(pcm16k);
    return encodeWAV(int16, TARGET_SAMPLE_RATE);
  }

  // ── Internal: pump audio level & perform Voice Activity Detection (VAD) ──
  _pumpLevel() {
    if (!this._analyser || !this._onAudioLevel) return;
    const buf = new Uint8Array(this._analyser.frequencyBinCount);

    const { silenceThreshold = 6, speechThreshold = 10, silenceDurationMs = 1600, minSpeechDurationMs = 600 } =
      this._vadOptions || {};

    let speechDetected = false;
    let speechStartTime = null;
    let silenceStartTime = null;
    let triggeredSilence = false;

    const tick = () => {
      if (!this._analyser) return;
      this._analyser.getByteFrequencyData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i];
      const avg = sum / buf.length;
      const level = Math.min(100, Math.round((avg / 128) * 100));

      this._onAudioLevel(level);

      // Voice Activity Detection (VAD)
      if (this._onSilence && !triggeredSilence) {
        const now = Date.now();

        if (level >= speechThreshold) {
          if (!speechStartTime) speechStartTime = now;
          if (now - speechStartTime >= minSpeechDurationMs) {
            speechDetected = true;
          }
          silenceStartTime = null; // reset silence counter while speaking
        } else if (level < silenceThreshold) {
          if (speechDetected) {
            if (!silenceStartTime) {
              silenceStartTime = now;
            } else if (now - silenceStartTime >= silenceDurationMs) {
              triggeredSilence = true;
              this._onSilence();
            }
          }
        }
      }

      this._rafId = requestAnimationFrame(tick);
    };
    tick();
  }
}
