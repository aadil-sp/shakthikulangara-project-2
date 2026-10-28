// ArUcoNav web app: camera / simulator -> ArUco -> engine -> USB gateway.
import { Engine } from "./engine.js";
import { GatewayLink, serialSupported, F_GUARD, F_FAULT_L, F_FAULT_F, F_FAULT_R } from "./link.js";
import { SimWorld } from "./sim.js";
import { MarkerTracker } from "./vision.js";

const $ = id => document.getElementById(id);
const canvas = $("canvas"), ctx = canvas.getContext("2d", { willReadFrequently: true });
const video = $("video");

// ---------------------------------------------------------------- settings (saved in this browser)
const DEFAULTS = {
  vision: { carMarkerId: 0, goalMarkerIds: [1, 2, 3], markerSizeCm: 5, headingOffsetDeg: 0, mirror: false },
  control: {
    mode: "classic", speed: 0.7, maxPwm: 255, minPwm: 70, arriveCm: 4, brakeCm: 30, pivotDeg: 55, kpTurn: 1.4,
    kdTurn: 0.12, slewPerS: 3, invertThrottle: false, invertSteering: false,
    // Off by default: on a real car these made it move without being asked
    autoPolarity: false, followGoalMarker: false, rlLearnOnline: false,
  },
  obstacle: { enabled: true, warnCm: 35, stopCm: 15, maxEscapes: 0 },
  link: { sendHz: 20, timeoutS: 1, guardCm: 12 },
  lastCamera: "sim",
};
// v2: earlier saves could hold motor-direction flips made by the auto-detector
const STORE = "aruconav-settings-v2";
function loadSettings() {
  const cfg = structuredClone(DEFAULTS);
  try {
    const saved = JSON.parse(localStorage.getItem(STORE) || "{}");
    for (const k of Object.keys(cfg)) {
      if (typeof cfg[k] === "object" && saved[k] && typeof saved[k] === "object") {
        for (const f of Object.keys(cfg[k])) {
          if (Array.isArray(cfg[k][f]) ? Array.isArray(saved[k][f]) : typeof saved[k][f] === typeof cfg[k][f]) cfg[k][f] = saved[k][f];
        }
      } else if (typeof saved[k] === typeof cfg[k]) cfg[k] = saved[k];
    }
  } catch (_) {}
  return cfg;
}
const cfg = loadSettings();
let saveTimer = null;
const save = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => { try { localStorage.setItem(STORE, JSON.stringify(cfg)); } catch (_) {} }, 300); };

// ---------------------------------------------------------------- state
let policy = null;
try { policy = (await (await fetch("data/policy.json")).json()).q; } catch (_) {}
if (!policy) policy = Array.from({ length: 384 }, () => new Array(9).fill(0));
const engine = new Engine(cfg, policy);
const tracker = new MarkerTracker();
const sim = new SimWorld(1280, 720);
const link = new GatewayLink(log);
let source = "sim";             // "sim" | camera deviceId | "file"
let stream = null;
let lastSend = 0, lastPanel = 0, lastFrame = performance.now();
let loopFps = 0, fpsN = 0, fpsT = performance.now();
let out = null;
const keys = new Set();

function log(msg) {
  const el = $("log");
  const line = document.createElement("div");
  line.textContent = `${new Date().toLocaleTimeString([], { hour12: false })}  ${msg}`;
  el.appendChild(line);
  while (el.childNodes.length > 300) el.removeChild(el.firstChild);
  el.scrollTop = el.scrollHeight;
}

// ---------------------------------------------------------------- cameras
async function listCameras(ask) {
  const sel = $("camSelect");
  const keep = sel.value;
  if (ask && !stream) {
    // Device names are only shown after the user allows the camera once
    try { const s = await navigator.mediaDevices.getUserMedia({ video: true }); s.getTracks().forEach(t => t.stop()); }
    catch (e) { log(`Camera not allowed: ${e.message}. Allow it in the address bar's camera icon, then press ⟳.`); }
  }
  let devices = [];
  try { devices = (await navigator.mediaDevices.enumerateDevices()).filter(d => d.kind === "videoinput"); } catch (_) {}
  sel.innerHTML = "";
  sel.add(new Option("Simulator (virtual camera)", "sim"));
  // Before the site is allowed to use the camera, browsers hide device IDs and names
  if (devices.length && devices.every(d => !d.deviceId)) sel.add(new Option("📷 Use a camera (asks permission)", "ask"));
  else devices.forEach((d, i) => sel.add(new Option(`📷 ${d.label || `Camera ${i + 1}`}`, d.deviceId)));
  sel.add(new Option("Video or photo file…", "file"));
  if (!devices.length && ask) log("No cameras found. Plug one in or allow camera access, then press ⟳.");
  else if (ask) log(`Found ${devices.length} camera(s)`);
  sel.value = [...sel.options].some(o => o.value === keep) ? keep : source === "sim" ? "sim" : sel.value;
}

function stopStream() {
  if (stream) stream.getTracks().forEach(t => t.stop());
  stream = null;
  video.srcObject = null;
  if (video.src) { URL.revokeObjectURL(video.src); video.removeAttribute("src"); }
}

async function openSource(value) {
  if (value === "file") return pickFile();
  if (value === "ask") {
    await listCameras(true);
    const first = [...$("camSelect").options].find(o => !["sim", "file", "ask"].includes(o.value));
    if (!first) { $("camSelect").value = source; return; }
    $("camSelect").value = first.value;
    value = first.value;
  }
  stopStream();
  engine.localizer.reset();
  if (value === "sim") {
    source = "sim";
    canvas.width = sim.width; canvas.height = sim.height;
    log("Using the simulator camera and simulated car");
  } else {
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { deviceId: { exact: value }, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
      });
    } catch (e) {
      log(`Could not open that camera: ${e.message}`);
      $("camSelect").value = source;
      return;
    }
    video.srcObject = stream;
    await video.play();
    source = value;
    const label = stream.getVideoTracks()[0].label;
    log(`Opened camera ${label} (${video.videoWidth}×${video.videoHeight})`);
    sizeCanvasToVideo();
  }
  cfg.lastCamera = source === "file" ? "sim" : source;
  save();
  updateModeUi();
}

function pickFile() {
  const inp = document.createElement("input");
  inp.type = "file"; inp.accept = "video/*,image/*";
  inp.onchange = async () => {
    const f = inp.files[0];
    if (!f) { $("camSelect").value = source; return; }
    stopStream();
    engine.localizer.reset();
    if (f.type.startsWith("image/")) {
      const img = new Image();
      img.src = URL.createObjectURL(f);
      await img.decode();
      fileImage = img;
      canvas.width = Math.min(1280, img.naturalWidth);
      canvas.height = Math.round(canvas.width * img.naturalHeight / img.naturalWidth);
    } else {
      fileImage = null;
      video.src = URL.createObjectURL(f);
      video.loop = true;
      await video.play();
      sizeCanvasToVideo();
    }
    source = "file";
    log(`Playing file ${f.name}`);
    updateModeUi();
  };
  inp.click();
}
let fileImage = null;

function sizeCanvasToVideo() {
  const w = video.videoWidth || 1280, h = video.videoHeight || 720;
  const scale = Math.min(1, 1280 / w);      // detection cost grows with pixels
  canvas.width = Math.round(w * scale); canvas.height = Math.round(h * scale);
}

// ---------------------------------------------------------------- link
async function connectGateway(anyPort) {
  if (!serialSupported()) return;
  if (link.open) {
    await link.close();
    log("Gateway disconnected");
    updateModeUi();
    return;
  }
  try {
    await link.choose(anyPort);
    await link.setGuard(cfg.link.guardCm);
    if (source === "sim") log("Gateway connected. Pick your real camera above to drive the real car.");
  } catch (e) {
    if (e.name === "NotFoundError") log("No gateway chosen. Plug in the ESP32-C3 gateway and try again (Shift+click the button to list every USB port).");
    else log(`Could not open the gateway: ${e.message}`);
  }
  updateModeUi();
}

// ---------------------------------------------------------------- main loop
function frame(now) {
  requestAnimationFrame(frame);
  const t = now / 1000;
  const dt = Math.min(0.1, (now - lastFrame) / 1000);
  lastFrame = now;
  engine.manual = manualCommand();

  let markers = {}, sonar = null;
  if (source === "sim") {
    sim.car.step(dt);
    sim.draw(ctx);
    markers = sim.markers();
    sonar = sim.car.sonar();
  } else {
    const src = fileImage || video;
    if (!fileImage && video.readyState < 2) { drawWaiting(); return; }
    ctx.save();
    if (cfg.vision.mirror) { ctx.translate(canvas.width, 0); ctx.scale(-1, 1); }
    ctx.drawImage(src, 0, 0, canvas.width, canvas.height);
    ctx.restore();
    markers = tracker.detect(ctx.getImageData(0, 0, canvas.width, canvas.height));
    const tele = link.fresh(cfg.link.timeoutS);
    sonar = tele ? tele.sonar : null;
  }

  out = engine.process(markers, t, sonar);
  while (engine.events.length) log(engine.events.shift());

  if (source === "sim") sim.car.command(out.pwm[0], out.pwm[1]);
  else if (link.open && now - lastSend >= 1000 / cfg.link.sendHz) { lastSend = now; link.send(out.pwm[0], out.pwm[1]); }

  drawOverlays(out, sonar);
  fpsN++;
  if (now - fpsT >= 1000) { loopFps = (fpsN * 1000) / (now - fpsT); fpsN = 0; fpsT = now; }
  if (now - lastPanel > 100) { lastPanel = now; updatePanel(out); }
}

function drawWaiting() {
  ctx.fillStyle = "#0b0f14"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  setBanner("Waiting for camera…", true);
}

function setBanner(text, warn) {
  const b = $("banner");
  b.textContent = text;
  b.classList.toggle("warn", !!warn);
}

// ---------------------------------------------------------------- overlays
function drawOverlays(o, sonar) {
  const lw = Math.max(2, canvas.width / 500);
  ctx.lineWidth = lw;
  // detected markers
  for (const m of Object.values(o.markers)) {
    const isCar = m.id === cfg.vision.carMarkerId;
    ctx.strokeStyle = isCar ? "#22d3ee" : "#4ade80";
    if (m.corners) {
      ctx.beginPath(); m.corners.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y))); ctx.closePath(); ctx.stroke();
    }
    ctx.fillStyle = ctx.strokeStyle;
    ctx.font = `bold ${Math.round(canvas.width / 70)}px system-ui`;
    ctx.fillText(`ID ${m.id}`, m.x + m.side * 0.7, m.y - m.side * 0.7);
  }
  // trail
  if (engine.trail.length > 1) {
    ctx.strokeStyle = "rgba(34, 211, 238, 0.55)";
    ctx.beginPath(); engine.trail.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.stroke();
  }
  // waypoints and target
  ctx.fillStyle = "#facc15"; ctx.strokeStyle = "#facc15";
  let prev = o.pose ? [o.pose.x, o.pose.y] : null;
  engine.waypoints.forEach(([x, y], i) => {
    if (prev) { ctx.setLineDash([8, 6]); ctx.beginPath(); ctx.moveTo(prev[0], prev[1]); ctx.lineTo(x, y); ctx.stroke(); ctx.setLineDash([]); }
    ctx.beginPath(); ctx.arc(x, y, lw * 4, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#000"; ctx.font = `bold ${lw * 5}px system-ui`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText(String(i + 1), x, y + 1); ctx.textAlign = "start"; ctx.textBaseline = "alphabetic"; ctx.fillStyle = "#facc15";
    prev = [x, y];
  });
  if (o.target && !engine.waypoints.length) {
    ctx.strokeStyle = "#4ade80"; ctx.beginPath(); ctx.arc(o.target[0], o.target[1], lw * 9, 0, Math.PI * 2); ctx.stroke();
  }
  // car pose + sonar fans
  if (o.pose) {
    const { x, y, theta } = o.pose, L = 40 * (canvas.width / 1280);
    ctx.strokeStyle = "#f472b6"; ctx.lineWidth = lw * 1.5;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(theta) * L, y + Math.sin(theta) * L); ctx.stroke();
    ctx.lineWidth = lw;
    if (sonar && cfg.obstacle.enabled) {
      const ppc = engine.localizer.pxPerCm || 6;
      [-40, 0, 40].forEach((deg, i) => {
        const d = Math.min(sonar[i], 150), a = theta + (deg * Math.PI) / 180;
        ctx.strokeStyle = sonar[i] < cfg.obstacle.stopCm ? "rgba(239,68,68,0.9)" : sonar[i] < cfg.obstacle.warnCm ? "rgba(245,158,11,0.8)" : "rgba(34,197,94,0.35)";
        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + Math.cos(a) * d * ppc, y + Math.sin(a) * d * ppc); ctx.stroke();
      });
    }
  }
  const warn = engine.estop || /lost|not moving|stop/i.test(o.status);
  setBanner(o.status || "", warn);
}

// ---------------------------------------------------------------- panel
const TELE_ROWS = [["pose", "Position"], ["heading", "Heading"], ["speed", "Speed"], ["target", "To target"],
  ["status", "Doing"], ["fps", "Camera / loop"], ["radio", "Radio"]];
const BAR_ROWS = [["pwmL", "Left motor", "var(--motor)"], ["pwmR", "Right motor", "var(--motor)"],
  ["sL", "Sonar left", "var(--sonar)"], ["sF", "Sonar front", "var(--sonar)"], ["sR", "Sonar right", "var(--sonar)"]];
function buildPanel() {
  $("tele").innerHTML = TELE_ROWS.map(([k, n]) => `<dt>${n}</dt><dd id="t_${k}">—</dd>`).join("");
  $("bars").innerHTML = BAR_ROWS.map(([k, n, c]) =>
    `<span>${n}</span><span class="bar"><i id="b_${k}" style="background:${c}"></i></span><span class="val" id="v_${k}">—</span>`).join("");
}

function updatePanel(o) {
  const ppc = engine.localizer.pxPerCm || 6, set = (k, v) => ($(`t_${k}`).textContent = v);
  if (o.pose) {
    set("pose", `x ${(o.pose.x / ppc).toFixed(1)} cm   y ${(o.pose.y / ppc).toFixed(1)} cm`);
    set("heading", `${((o.pose.theta * 180) / Math.PI).toFixed(1)}°   turning ${((o.pose.omega * 180) / Math.PI).toFixed(0)}°/s`);
    set("speed", `${(Math.abs(o.pose.v) / ppc).toFixed(1)} cm/s`);
  } else ["pose", "heading", "speed"].forEach(k => set(k, "car marker not visible"));
  set("target", o.target ? `${o.distCm.toFixed(1)} cm, ${((o.headingErr * 180) / Math.PI).toFixed(0)}°` : "no target");
  set("status", o.status + (o.action ? ` (${o.action})` : ""));
  set("fps", `${loopFps.toFixed(0)} fps`);

  const tele = source === "sim" ? null : link.fresh(cfg.link.timeoutS);
  let radio = "—";
  if (tele && tele.carRssi !== null) {
    radio = `car ${tele.carRssi} dBm · gw ${tele.gwRssi} dBm`;
    if (tele.rtt) radio += ` · ${tele.rtt.toFixed(0)} ms`;
    if (link.status) radio += ` · loss ${link.status.loss}%`;
    if (tele.battery > 0) radio += ` · battery ${tele.battery.toFixed(1)} V`;
    if (tele.flags & F_GUARD) radio += " · GUARD STOP";
    const faults = [[F_FAULT_L, "left"], [F_FAULT_F, "front"], [F_FAULT_R, "right"]].filter(([b]) => tele.flags & b).map(([, n]) => n);
    if (faults.length) radio += ` · sonar fault: ${faults.join(", ")}`;
  } else if (tele) radio = "car linked (v1 firmware)";
  set("radio", source === "sim" ? "simulator" : radio);

  const bar = (k, frac, text, color) => {
    const b = $(`b_${k}`); b.style.width = `${Math.round(Math.min(1, Math.max(0, frac)) * 100)}%`;
    if (color) b.style.background = color;
    $(`v_${k}`).textContent = text;
  };
  bar("pwmL", Math.abs(o.pwm[0]) / 255, `${o.pwm[0] >= 0 ? "+" : ""}${o.pwm[0]}`);
  bar("pwmR", Math.abs(o.pwm[1]) / 255, `${o.pwm[1] >= 0 ? "+" : ""}${o.pwm[1]}`);
  const sonar = source === "sim" ? sim.car.sonar() : tele ? tele.sonar : null;
  [["sL", 0], ["sF", 1], ["sR", 2]].forEach(([k, i]) => {
    if (!sonar) return bar(k, 0, "—");
    const d = sonar[i];
    const color = d < cfg.obstacle.stopCm ? "var(--bad)" : d < cfg.obstacle.warnCm ? "var(--warn)" : "var(--sonar)";
    bar(k, Math.min(d, 150) / 150, `${d.toFixed(0)} cm`, color);
  });

  // link pill
  const pill = $("pill");
  if (source === "sim") { pill.textContent = "SIMULATOR"; pill.className = "pill"; }
  else if (link.open) {
    const ok = !!tele;
    pill.textContent = ok ? "CAR LINKED" : "NO CAR SIGNAL";
    pill.className = `pill ${ok ? "ok" : "bad"}`;
  } else { pill.textContent = "VISION ONLY"; pill.className = "pill idle"; }
  $("invT").checked = cfg.control.invertThrottle;
  $("invS").checked = cfg.control.invertSteering;
}

function updateModeUi() {
  const isSim = source === "sim";
  $("simBox").hidden = !isSim;
  $("simHint").hidden = !isSim;
  const btn = $("connectBtn");
  btn.textContent = link.open ? "Disconnect gateway" : "Connect gateway (USB)";
  btn.classList.toggle("connected", link.open);
  $("beepBtn").disabled = !link.open;
}

// ---------------------------------------------------------------- input
function canvasPoint(e) {
  const r = canvas.getBoundingClientRect();
  return [((e.clientX - r.left) / r.width) * canvas.width, ((e.clientY - r.top) / r.height) * canvas.height];
}

function moveSimGoal(e) {
  const [x, y] = canvasPoint(e);
  sim.setGoalPx(x, y); engine.waypoints = []; engine.newTarget();
}
canvas.addEventListener("click", e => {
  if (source === "sim" && (e.ctrlKey || e.metaKey)) return moveSimGoal(e);
  const [x, y] = canvasPoint(e);
  engine.addWaypoint(x, y, e.shiftKey);
});
canvas.addEventListener("contextmenu", e => {
  e.preventDefault();
  // On a Mac, Ctrl+click arrives as a right-click
  if (source === "sim" && e.ctrlKey && e.button === 0) return moveSimGoal(e);
  engine.clearPath();
});

function manualCommand() {
  const v = (keys.has("w") ? 1 : 0) - (keys.has("s") ? 1 : 0);
  const w = (keys.has("d") ? 1 : 0) - (keys.has("a") ? 1 : 0);
  return v || w ? [0.8 * v, 0.7 * w] : null;
}

const typing = e => ["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName) && e.target.type !== "checkbox" && e.target.type !== "range";
window.addEventListener("keydown", e => {
  if (typing(e) || e.metaKey || e.ctrlKey || e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === " ") { e.preventDefault(); toggleEstop(); }
  else if (k === "c") engine.clearPath();
  else if (k === "f") document.fullscreenElement ? document.exitFullscreen() : $("view").requestFullscreen?.().catch(() => {});
  else if ("wasd".includes(k) && k.length === 1) { keys.add(k); e.preventDefault(); }
});
window.addEventListener("keyup", e => keys.delete(e.key.toLowerCase()));
window.addEventListener("blur", () => keys.clear());

function toggleEstop() {
  engine.setEstop(!engine.estop);
  $("estop").classList.toggle("active", engine.estop);
  $("estop").firstChild.textContent = engine.estop ? "RELEASE STOP " : "EMERGENCY STOP ";
  log(engine.estop ? "Emergency stop ON" : "Emergency stop released");
}

// ---------------------------------------------------------------- controls
function bindCheck(id, obj, key) {
  const el = $(id);
  el.checked = obj[key];
  el.addEventListener("change", () => { obj[key] = el.checked; save(); });
}

function setup() {
  buildPanel();
  bindCheck("mirror", cfg.vision, "mirror");
  bindCheck("followGoal", cfg.control, "followGoalMarker");
  bindCheck("obstacles", cfg.obstacle, "enabled");
  bindCheck("autoPol", cfg.control, "autoPolarity");
  bindCheck("invT", cfg.control, "invertThrottle");
  bindCheck("invS", cfg.control, "invertSteering");
  bindCheck("rlLearn", cfg.control, "rlLearnOnline");

  $("brain").value = cfg.control.mode;
  $("brain").onchange = e => { cfg.control.mode = e.target.value; engine.newTarget(); save(); };
  const speed = $("speed"), speedVal = $("speedVal");
  speed.value = cfg.control.speed; speedVal.textContent = `${Math.round(cfg.control.speed * 100)}%`;
  speed.oninput = () => { cfg.control.speed = +speed.value; speedVal.textContent = `${Math.round(cfg.control.speed * 100)}%`; save(); };
  const guard = $("guard");
  guard.value = cfg.link.guardCm;
  guard.onchange = () => { cfg.link.guardCm = Math.max(0, Math.min(100, +guard.value || 0)); guard.value = cfg.link.guardCm; link.setGuard(cfg.link.guardCm); save(); };

  $("camSelect").onchange = e => openSource(e.target.value);
  $("camRefresh").onclick = () => listCameras(true);
  $("connectBtn").onclick = e => connectGateway(e.shiftKey);
  $("beepBtn").onclick = () => link.beep();
  $("estop").onclick = toggleEstop;
  $("clearBtn").onclick = () => engine.clearPath();
  $("flipBtn").onclick = () => {
    cfg.vision.headingOffsetDeg = cfg.vision.headingOffsetDeg ? 0 : 180;
    engine.localizer.reset(); save();
    log(`Car marker heading ${cfg.vision.headingOffsetDeg ? "flipped 180°" : "back to normal"}`);
  };
  $("obsBtn").onclick = () => sim.randomObstacles(3);
  $("obsClear").onclick = () => sim.clearObstacles();
  $("carReset").onclick = () => { sim.car.reset(30 + Math.random() * 140, 20 + Math.random() * 70, Math.random() * 6.28 - 3.14); engine.localizer.reset(); };

  if (!serialSupported()) {
    $("connectBtn").disabled = true;
    const n = $("serialNote");
    n.textContent = "This browser can't talk to USB devices. Open this page in Chrome or Edge to drive the real car. The camera and simulator work here.";
    n.className = "note warn";
  } else {
    $("serialNote").textContent = "Plug the ESP32-C3 gateway into this laptop, then connect. Chrome remembers it next time.";
    link.reconnect().then(ok => { if (ok) { log("Reconnected to the gateway allowed earlier"); link.setGuard(cfg.link.guardCm); updateModeUi(); } }).catch(() => {});
    navigator.serial.addEventListener("disconnect", () => { log("Gateway unplugged"); link.close().then(updateModeUi); });
  }
  if (!navigator.mediaDevices?.getUserMedia) log("This browser has no camera access here. Use https:// in Chrome, Edge or Firefox.");

  log("ArUcoNav ready. Click on the picture to send the car there. Shift+click adds waypoints, right-click clears.");
  updateModeUi();
  listCameras(false).then(async () => {
    if (cfg.lastCamera !== "sim" && [...$("camSelect").options].some(o => o.value === cfg.lastCamera)) {
      $("camSelect").value = cfg.lastCamera;
      await openSource(cfg.lastCamera);
    } else await openSource("sim");
  });
  requestAnimationFrame(frame);
}

window.addEventListener("beforeunload", () => { if (link.open) link.send(0, 0); });
window.aruconav = { engine, sim, link, cfg };   // for debugging from the browser console
// A hidden tab stops running the control loop: stop the car right away
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    keys.clear();
    if (link.open) link.send(0, 0);
    if (source !== "sim" && (engine.waypoints.length || engine.goalMem)) { engine.clearPath(); log("Page hidden - car stopped and path cleared"); }
  }
});
setup();
