// Practice mode: timer, audio recording with playback, live transcription
// (where the browser supports it), and optional AI feedback.
(function () {
  "use strict";

  const root = document.getElementById("practice");
  if (!root) return;

  const $ = (id) => document.getElementById(id);
  const answerBox = $("answer-box");
  const form = $("rate-form");
  const csrf = form.querySelector("input[name=csrfmiddlewaretoken]").value;
  const OVERTIME_SECONDS = ["behavioral", "project"].includes(root.dataset.category) ? 120 : null;

  // ---------------------------------------------------------------- timer
  const display = $("timer-display");
  const toggleBtn = $("timer-toggle");
  let elapsed = 0;
  let ticker = null;

  function render() {
    const m = Math.floor(elapsed / 60);
    const s = String(elapsed % 60).padStart(2, "0");
    display.textContent = `${m}:${s}`;
    display.classList.toggle("is-over", OVERTIME_SECONDS !== null && elapsed > OVERTIME_SECONDS);
  }
  function startTimer() {
    if (ticker) return;
    ticker = setInterval(() => { elapsed += 1; render(); }, 1000);
    toggleBtn.textContent = "Pause";
    display.classList.add("is-running");
  }
  function stopTimer() {
    clearInterval(ticker);
    ticker = null;
    toggleBtn.textContent = elapsed ? "Resume" : "Start timer";
    display.classList.remove("is-running");
  }
  toggleBtn.addEventListener("click", () => (ticker ? stopTimer() : startTimer()));
  $("timer-reset").addEventListener("click", () => { stopTimer(); elapsed = 0; render(); toggleBtn.textContent = "Start timer"; });

  // ---------------------------------------------------------------- recording
  const recBtn = $("record-toggle");
  const recLabel = recBtn.querySelector(".label");
  const recStatus = $("record-status");
  const playback = $("playback");
  let recorder = null;
  let chunks = [];
  let audioUrl = null;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let keepListening = false;

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = "en-US";
    recognition.addEventListener("result", (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          const text = event.results[i][0].transcript.trim();
          if (text) answerBox.value = (answerBox.value ? answerBox.value.trimEnd() + " " : "") + text;
        }
      }
    });
    // Chrome stops listening after silence; restart while we're still recording.
    recognition.addEventListener("end", () => { if (keepListening) { try { recognition.start(); } catch (_) {} } });
  }

  if (!navigator.mediaDevices || !window.MediaRecorder) {
    recBtn.disabled = true;
    recStatus.textContent = "Recording isn't supported in this browser.";
  }

  async function startRecording() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      recStatus.textContent = "Microphone access was blocked. Allow it in your browser to record.";
      return;
    }
    chunks = [];
    recorder = new MediaRecorder(stream);
    recorder.addEventListener("dataavailable", (e) => { if (e.data.size) chunks.push(e.data); });
    recorder.addEventListener("stop", () => {
      stream.getTracks().forEach((t) => t.stop());
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      audioUrl = URL.createObjectURL(new Blob(chunks, { type: recorder.mimeType || "audio/webm" }));
      playback.src = audioUrl;
      playback.hidden = false;
      recStatus.textContent = "Play it back below. Recordings aren't saved.";
    });
    recorder.start();
    if (recognition) { keepListening = true; try { recognition.start(); } catch (_) {} }
    recBtn.classList.add("is-recording");
    recLabel.textContent = "Stop recording";
    recStatus.textContent = recognition ? "Recording and transcribing…" : "Recording…";
    startTimer();
  }

  function stopRecording() {
    if (recorder && recorder.state !== "inactive") recorder.stop();
    if (recognition) { keepListening = false; recognition.stop(); }
    recBtn.classList.remove("is-recording");
    recLabel.textContent = "Record again";
    stopTimer();
  }

  recBtn.addEventListener("click", () => {
    if (recorder && recorder.state === "recording") stopRecording();
    else startRecording();
  });

  // ---------------------------------------------------------------- AI feedback
  const aiBtn = $("ai-feedback-btn");
  if (aiBtn) {
    const aiStatus = $("ai-status");
    const aiBox = $("ai-feedback");
    aiBtn.addEventListener("click", async () => {
      aiBtn.disabled = true;
      aiStatus.textContent = "Thinking…";
      const body = new FormData();
      body.append("answer", answerBox.value);
      try {
        const res = await fetch(root.dataset.feedbackUrl, {
          method: "POST",
          headers: { "X-CSRFToken": csrf },
          body,
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Something went wrong.");
        aiBox.textContent = data.feedback;
        aiBox.hidden = false;
        $("id_ai_feedback").value = data.feedback;
        aiStatus.textContent = "";
      } catch (err) {
        aiStatus.textContent = err.message;
      } finally {
        aiBtn.disabled = false;
      }
    });
  }

  // ---------------------------------------------------------------- save
  form.addEventListener("submit", () => {
    if (recorder && recorder.state === "recording") stopRecording();
    $("id_duration_seconds").value = elapsed > 0 ? String(elapsed) : "";
    $("id_answer_text").value = answerBox.value;
  });

  render();
})();
