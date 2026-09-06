// NOTE: no static import of PoseLandmarker/FilesetResolver anymore.
let PoseLandmarker, FilesetResolver;

const video = document.getElementById("webcam");
const canvas = document.getElementById("overlay");
const ctx = canvas.getContext("2d");
const statusEl = document.getElementById("status");
const rakahDisplay = document.getElementById("rakah-display");
const startBtn = document.getElementById("start-btn");
const endBtn = document.getElementById("end-btn");
const optionsList = document.getElementById("prayer-options");
const currentPrayerInfo = document.getElementById("current-prayer-info");

// Sanity check: if any element is missing, fail loudly instead of silently.
[video, canvas, statusEl, rakahDisplay, startBtn, endBtn, optionsList, currentPrayerInfo].forEach((el, i) => {
  if (!el) console.error(`prayer-check.js: expected element #${i} not found in DOM`);
});

const LINE_FRACTION = 0.75; // bottom 25% of the frame

// Prayers not driven by the adhan schedule. `rakahs: null` means open-ended
// (just show a running counter, no "out of X").
const PRAYER_OPTIONS = [
  { name: "Sunnah before Fajr", rakahs: 2 },
  { name: "Sunnah before Dhuhr", rakahs: 4 },
  { name: "Sunnah after Dhuhr", rakahs: 2 },
  { name: "Sunnah after Maghrib", rakahs: 2 },
  { name: "Sunnah after Isha", rakahs: 2 },
  { name: "Witr", rakahs: 3 },
  { name: "Jummuah", rakahs: 2 },
  { name: "Eid", rakahs: 2 },
  { name: "Tahajjud", rakahs: null },
  { name: "Qiyam al Layl", rakahs: null },
  { name: "Eclipse (Kusuf)", rakahs: null }
];

let selectedPrayer = null;   // { name, rakahs }
let poseLandmarker = null;
let stream = null;
let running = false;
let animationId = null;
let lastVideoTime = -1;

let crossingCount = 0;       // number of times head has gone below the line
let headBelowLine = false;   // current transition state
let rakahCount = 0;

/* ---------------- Open camera on page load ---------------- */

document.addEventListener("DOMContentLoaded", async () => {
  renderPrayerOptions();
  loadCurrentPrayer();

  if (!isSecureContextOk()) {
    statusEl.textContent = "Camera access requires HTTPS or localhost.";
    return;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    statusEl.textContent = "This browser doesn't support camera access.";
    return;
  }

  try {
    statusEl.textContent = "Starting camera…";
    await startWebcam();
    await ensurePoseLandmarker();
    statusEl.textContent = "Put the line on waist level. Select a prayer to begin.";

    previewLoop(); // start drawing line + nose dot immediately, continuously
  } catch (err) {
    console.error("Camera setup failed:", err);
    statusEl.textContent = "Error starting camera: " + err.message;
  }
});

function isSecureContextOk() {
  return window.isSecureContext || location.hostname === "localhost" || location.hostname === "127.0.0.1";
}


/* ---------------- Prayer selection UI ---------------- */

function renderPrayerOptions() {
  optionsList.innerHTML = "";
  PRAYER_OPTIONS.forEach((option) => {
    const li = document.createElement("li");
    li.textContent = option.rakahs
      ? `${option.name} (${option.rakahs} rakah)`
      : `${option.name} (no fixed count)`;
    li.addEventListener("click", () => selectPrayer(option, li));
    optionsList.appendChild(li);
  });
}

function clearSelectionHighlight() {
  document.querySelectorAll("#prayer-options li").forEach(el => el.classList.remove("selected"));
  currentPrayerInfo.classList.remove("selected");
}

function selectPrayer(option, el) {
  if (running) return; // don't allow switching mid-prayer
  selectedPrayer = option;
  clearSelectionHighlight();
  if (el) el.classList.add("selected");
  statusEl.textContent = `Selected: ${option.name}. Press Start when ready.`;
  updateRakahDisplay();
  startBtn.disabled = false;
}

/* ---------------- Current fard prayer (adhan API) ---------------- */

async function loadCurrentPrayer() {
  try {
    let lat = null, lng = null;
    if (navigator.geolocation) {
      await new Promise((resolve) => {
        navigator.geolocation.getCurrentPosition(
          (pos) => { lat = pos.coords.latitude; lng = pos.coords.longitude; resolve(); },
          () => resolve(), // permission denied / unavailable -> fall back to server default
          { timeout: 4000 }
        );
      });
    }

    const url = new URL("/api/current-prayer", window.location.origin);
    if (lat !== null) url.searchParams.set("lat", lat);
    if (lng !== null) url.searchParams.set("lng", lng);

    const res = await fetch(url);
    const data = await res.json();

    currentPrayerInfo.innerHTML = `
      <strong>${data.name}</strong><br>
      ${data.time}<br>
      ${data.rakahs} rakah (Fard)
    `;
    currentPrayerInfo.addEventListener("click", () =>
      selectPrayer({ name: data.name, rakahs: data.rakahs }, currentPrayerInfo)
    );
  } catch (err) {
    currentPrayerInfo.textContent = "Couldn't load prayer time.";
    console.error(err);
  }
}

/* ---------------- Rakah display ---------------- */

function updateRakahDisplay() {
  if (selectedPrayer && selectedPrayer.rakahs) {
    rakahDisplay.textContent = `Rakah: ${rakahCount} / ${selectedPrayer.rakahs}`;
  } else {
    rakahDisplay.textContent = `Rakah: ${rakahCount}`;
  }
}

/* ---------------- MediaPipe setup ---------------- */

async function ensurePoseLandmarker() {
  if (poseLandmarker) return;

  if (!PoseLandmarker || !FilesetResolver) {
    statusEl.textContent = "Loading pose detection library…";
    try {
      const mod = await import("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14");
      PoseLandmarker = mod.PoseLandmarker;
      FilesetResolver = mod.FilesetResolver;
    } catch (err) {
      console.error("Failed to load MediaPipe tasks-vision from CDN:", err);
      throw new Error("Could not load pose detection library. Check your internet connection or ad blocker.");
    }
  }

  const vision = await FilesetResolver.forVisionTasks(
    "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14/wasm"
  );
  poseLandmarker = await PoseLandmarker.createFromOptions(vision, {
    baseOptions: {
      modelAssetPath:
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
      delegate: "GPU"
    },
    runningMode: "VIDEO",
    numPoses: 1
  });
}

async function startWebcam() {
  stream = await navigator.mediaDevices.getUserMedia({ video: true });
  video.srcObject = stream;
  return new Promise((resolve) => {
    video.onloadedmetadata = () => {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      resolve();
    };
  });
}


function drawLine() {
  const lineY = canvas.height * LINE_FRACTION;
  ctx.strokeStyle = headBelowLine ? "red" : "lime";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(0, lineY);
  ctx.lineTo(canvas.width, lineY);
  ctx.stroke();
}

function drawNose(x, y) {
  ctx.fillStyle = headBelowLine ? "red" : "yellow";
  ctx.beginPath();
  ctx.arc(x, y, 8, 0, 2 * Math.PI);
  ctx.fill();
}

let praying = false; // true only between Start and End

function previewLoop() {
  if (video.currentTime !== lastVideoTime) {
    lastVideoTime = video.currentTime;
    const result = poseLandmarker.detectForVideo(video, performance.now());

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    drawLine();

    if (result.landmarks && result.landmarks.length > 0) {
      const nose = result.landmarks[0][0]; // landmark 0 = nose
      const noseX = nose.x * canvas.width;
      const noseY = nose.y * canvas.height;
      drawNose(noseX, noseY);

      const lineY = canvas.height * LINE_FRACTION;
      const isBelow = noseY > lineY;

      if (isBelow && !headBelowLine) {
        headBelowLine = true;
        if (praying) {
          crossingCount++;
          rakahCount = Math.floor(crossingCount / 2);
          updateRakahDisplay();
        }
      } else if (!isBelow && headBelowLine) {
        headBelowLine = false;
      }
    }
  }

  animationId = requestAnimationFrame(previewLoop);
}

/* ---------------- Start / End prayer ---------------- */

startBtn.addEventListener("click", () => {
  if (!selectedPrayer) {
    alert("Please select a prayer first.");
    return;
  }
  if (!poseLandmarker) {
    statusEl.textContent = "Camera isn't ready yet — please wait a moment and try again.";
    return;
  }

  crossingCount = 0;
  rakahCount = 0;
  headBelowLine = false;
  updateRakahDisplay();

  praying = true;

  // Hide the camera view — only the rakah count shows while praying
  document.querySelector(".video-wrap").style.display = "none";

  startBtn.disabled = true;
  endBtn.disabled = false;
  statusEl.textContent = `Praying: ${selectedPrayer.name}`;

  document.querySelector(".left-panel").style.display = "none";
  document.querySelector(".right-panel").style.display = "none";
  document.querySelector(".rakah-display").classList.add("BIG");
});

endBtn.addEventListener("click", async () => {
  praying = false;

  // Show the camera view again (line + nose dot preview resumes)
  document.querySelector(".video-wrap").style.display = "block";

  endBtn.disabled = true;
  statusEl.textContent = "Saving…";

  try {
    const res = await fetch("/api/prayer/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prayer_name: selectedPrayer.name,
        rakahs_completed: rakahCount,
        rakahs_required: selectedPrayer.rakahs
      })
    });
    const data = await res.json();
    statusEl.textContent = data.ok
      ? `Saved! You prayed ${rakahCount} rakah of ${selectedPrayer.name}.`
      : "Error saving prayer log.";
  } catch (err) {
    console.error(err);
    statusEl.textContent = "Error saving prayer log.";
  }

  startBtn.disabled = false;
  document.querySelector(".left-panel").style.display = "";
  document.querySelector(".right-panel").style.display = "";
  document.querySelector(".rakah-display").classList.remove("BIG");
});

/* ---------------- Init ---------------- */

renderPrayerOptions();
loadCurrentPrayer();