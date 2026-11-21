const liveFeed = document.getElementById("liveFeed");
const viewportEmpty = document.getElementById("viewportEmpty");
const modelPill = document.getElementById("modelPill");
const jobPill = document.getElementById("jobPill");
const clock = document.getElementById("clock");
const alertBanner = document.getElementById("alertBanner");
const alertCopy = document.getElementById("alertCopy");
const frameChip = document.getElementById("frameChip");
const uploadForm = document.getElementById("uploadForm");
const videoFile = document.getElementById("videoFile");
const fileLabel = document.getElementById("fileLabel");
const dropzone = document.getElementById("dropzone");
const runBtn = document.getElementById("runBtn");
const sendEmail = document.getElementById("sendEmail");
const eventLog = document.getElementById("eventLog");

let streaming = false;
let lastAccident = false;

function setPill(el, text, dotClass) {
  el.querySelector("span:last-child").textContent = text;
  el.querySelector(".dot").className = "dot " + (dotClass || "");
}

function log(message) {
  const item = document.createElement("li");
  item.textContent = `${new Date().toLocaleTimeString()}  ${message}`;
  eventLog.prepend(item);
}

function tickClock() {
  clock.textContent = new Date().toLocaleTimeString();
}
setInterval(tickClock, 1000);
tickClock();

videoFile.addEventListener("change", () => {
  if (videoFile.files[0]) {
    fileLabel.textContent = videoFile.files[0].name;
    runBtn.disabled = false;
  }
});

["dragenter", "dragover"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("drag");
  });
});
["dragleave", "drop"].forEach((evt) => {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("drag");
  });
});
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) {
    videoFile.files = e.dataTransfer.files;
    fileLabel.textContent = file.name;
    runBtn.disabled = false;
  }
});

document.querySelectorAll("[data-sample]").forEach((btn) => {
  btn.addEventListener("click", () => startJob({ sample: btn.dataset.sample }));
});

uploadForm.addEventListener("submit", (e) => {
  e.preventDefault();
  if (!videoFile.files[0]) return;
  const data = new FormData();
  data.append("video", videoFile.files[0]);
  data.append("send_email", sendEmail.checked ? "1" : "0");
  startJob(data);
});

async function startJob(payload) {
  runBtn.disabled = true;
  lastAccident = false;
  alertBanner.classList.add("hidden");
  log("Detection job started.");
  try {
    let res;
    if (payload instanceof FormData) {
      res = await fetch("/api/detect", { method: "POST", body: payload });
    } else {
      res = await fetch("/api/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sample: payload.sample,
          send_email: sendEmail.checked,
        }),
      });
    }
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || "Failed to start detection");
    startStream();
  } catch (err) {
    log(err.message);
    runBtn.disabled = false;
  }
}

function startStream() {
  liveFeed.src = "/stream?" + Date.now();
  liveFeed.classList.add("active");
  viewportEmpty.classList.add("hidden");
  streaming = true;
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    const s = await res.json();
    setPill(modelPill, s.model_ready ? "YOLO ready" : "Loading YOLO", s.model_ready ? "ok" : "");
    runBtn.disabled = !s.model_ready || s.running || !videoFile.files[0];

    const jobLabel = s.running ? "Detecting" : s.accident_detected ? "Accident" : s.completed ? "Complete" : "Standby";
    const jobDot = s.accident_detected ? "alert" : s.running ? "ok" : "idle";
    setPill(jobPill, jobLabel, jobDot);

    document.getElementById("mVehicles").textContent = s.vehicles;
    document.getElementById("mCollisions").textContent = s.collision_count;
    document.getElementById("mSpeed").textContent = Number(s.max_speed || 0).toFixed(1);
    frameChip.textContent = "Frame " + s.frame;

    const sev = document.getElementById("mSeverity");
    const text = s.severity || "—";
    sev.textContent = text.split(":")[0].replace(" SEVERITY", "") || "—";
    sev.className = "sev";
    if (/HIGH/.test(text)) sev.classList.add("high");
    else if (/MEDIUM/.test(text)) sev.classList.add("medium");
    else if (/LOW/.test(text)) sev.classList.add("low");

    if (s.weather) {
      document.getElementById("weatherValue").textContent = `${s.weather}, ${Number(s.temperature).toFixed(1)}°C`;
    }
    document.getElementById("eventsValue").textContent = (s.vehicle_events || []).join(", ") || "Simulated CAN bus idle";

    if (s.police) {
      document.getElementById("policeName").textContent = s.police.name;
      document.getElementById("policeDist").textContent = s.police.distance_km != null ? `${s.police.distance_km.toFixed(2)} km away` : "";
    }
    if (s.hospital) {
      document.getElementById("hospitalName").textContent = s.hospital.name;
      document.getElementById("hospitalDist").textContent = s.hospital.distance_km != null ? `${s.hospital.distance_km.toFixed(2)} km away` : "";
    }

    if (s.accident_detected && !lastAccident) {
      lastAccident = true;
      alertBanner.classList.remove("hidden");
      alertCopy.textContent = s.severity || "Collision confirmed. Dispatch nearest units.";
      log("Accident detected. Emergency context assembled.");
    }
    if (s.completed && !s.running) {
      runBtn.disabled = !s.model_ready;
      if (s.error) log(s.error);
    }
  } catch (err) {
    /* keep polling */
  }
}
setInterval(pollStatus, 700);
pollStatus();
