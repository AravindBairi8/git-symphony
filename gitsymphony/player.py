"""Export a Score as a self-contained HTML page that plays and visualises it."""

from __future__ import annotations

import html
import json

from .composer import Score

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · git-symphony</title>
<style>
  :root { --bg:#0e1117; --panel:#161b22; --fg:#e6edf3; --muted:#8b949e; --line:#30363d; --accent:#f78166; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; }
  header { padding:20px 24px 8px; display:flex; flex-wrap:wrap; gap:12px 24px; align-items:baseline; }
  h1 { margin:0; font-size:22px; }
  .meta { color:var(--muted); }
  #roll { display:block; width:100%; height:min(60vh, 520px); background:var(--panel); border-block:1px solid var(--line); cursor:pointer; }
  .bar { display:flex; gap:16px; align-items:center; padding:14px 24px; flex-wrap:wrap; }
  button { background:var(--accent); color:#0e1117; border:0; border-radius:6px; padding:8px 18px; font-weight:600; font-size:15px; cursor:pointer; }
  #time { font-variant-numeric: tabular-nums; color:var(--muted); }
  #cue { padding:0 24px 12px; min-height:3em; font-family:ui-monospace, monospace; }
  #cue .sha { color:var(--accent); }
  #cue .who { color:var(--muted); }
  #legend { display:flex; flex-wrap:wrap; gap:8px 18px; padding:0 24px 24px; color:var(--muted); }
  #legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta" id="info"></span>
</header>
<canvas id="roll" title="Click to jump"></canvas>
<div class="bar"><button id="play">Play</button><span id="time">0:00</span></div>
<div id="cue"></div>
<div id="legend"></div>
<script>
const SCORE = __SCORE__;
const COLORS = ["#f78166","#7ee787","#79c0ff","#d2a8ff","#ffa657","#ff7b72","#a5d6ff","#e3b341"];
const WAVES = ["triangle","sine","square","sine","triangle"];
const spb = 60 / SCORE.tempo;
const notes = SCORE.notes.slice().sort((a, b) => a.start - b.start);
const endBeat = Math.max(...notes.map(n => n.start + n.duration)) + 2;
const tonal = notes.filter(n => n.part !== "drums");
const lo = Math.min(...tonal.map(n => n.pitch)) - 2, hi = Math.max(...tonal.map(n => n.pitch)) + 2;
const fmt = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

document.getElementById("info").textContent =
  `${SCORE.cues.length} commits · ${SCORE.voices.length} voices · ${SCORE.key} ${SCORE.scale} · ${SCORE.tempo} bpm · ${fmt(endBeat * spb)}`;
document.getElementById("legend").innerHTML = SCORE.voices.map((v, i) =>
  `<span><i style="background:${COLORS[i % COLORS.length]}"></i>${v.replace(/[<&]/g, c => c === "<" ? "&lt;" : "&amp;")}</span>`).join("");

const canvas = document.getElementById("roll"), ctx = canvas.getContext("2d");
const PX = 40; // pixels per beat
let ac = null, master = null, noise = null, playing = false, t0 = 0, offset = 0, next = 0, timer = null;

function beatNow() { return playing ? (ac.currentTime - t0) / spb : offset; }

function draw() {
  const dpr = devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== w * dpr) { canvas.width = w * dpr; canvas.height = h * dpr; }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const now = beatNow(), headX = w * 0.3, x0 = now * PX - headX;
  const y = p => h - 12 - (p - lo) / (hi - lo) * (h - 36);
  for (const n of notes) {
    const x = n.start * PX - x0;
    if (x > w || x + n.duration * PX < 0) continue;
    const active = now >= n.start && now <= n.start + n.duration;
    ctx.globalAlpha = active ? 1 : 0.55;
    if (n.part === "drums") {
      ctx.fillStyle = "#8b949e";
      ctx.fillRect(x, h - 6, 3, 6);
      continue;
    }
    ctx.fillStyle = n.part === "bass" ? "#484f58" : COLORS[n.voice % COLORS.length];
    ctx.fillRect(x, y(n.pitch) - 4, Math.max(3, n.duration * PX - 2), n.part === "chord" ? 6 : 8);
  }
  ctx.globalAlpha = 1;
  ctx.fillStyle = "#e6edf3";
  ctx.fillRect(headX, 0, 1, h);
  document.getElementById("time").textContent = `${fmt(now * spb)} / ${fmt(endBeat * spb)}`;
  let cue = null;
  for (const c of SCORE.cues) { if (c.beat <= now) cue = c; else break; }
  const el = document.getElementById("cue");
  el.innerHTML = "";
  if (cue) {
    for (const [cls, text] of [["sha", cue.sha + " "], ["who", cue.author + "  "], ["", cue.subject]]) {
      const s = document.createElement("span"); s.className = cls; s.textContent = text; el.appendChild(s);
    }
  }
  if (playing && now > endBeat) stop();
  requestAnimationFrame(draw);
}

function voice(n, when) {
  const dur = n.duration * spb, amp = n.velocity / 127;
  if (n.part === "drums") {
    const src = ac.createBufferSource(), g = ac.createGain();
    if (n.pitch === 36) {
      const o = ac.createOscillator();
      o.frequency.setValueAtTime(150, when); o.frequency.exponentialRampToValueAtTime(50, when + 0.15);
      g.gain.setValueAtTime(amp * 0.8, when); g.gain.exponentialRampToValueAtTime(0.001, when + 0.35);
      o.connect(g).connect(master); o.start(when); o.stop(when + 0.4); return;
    }
    const len = n.pitch === 42 ? 0.06 : 1.4;
    const hp = ac.createBiquadFilter(); hp.type = "highpass"; hp.frequency.value = 6000;
    src.buffer = noise;
    g.gain.setValueAtTime(amp * (n.pitch === 42 ? 0.3 : 0.15), when);
    g.gain.exponentialRampToValueAtTime(0.001, when + len);
    src.connect(hp).connect(g).connect(master); src.start(when); src.stop(when + len); return;
  }
  const o = ac.createOscillator(), g = ac.createGain();
  o.type = n.part === "bass" ? "sine" : WAVES[n.voice % WAVES.length];
  o.frequency.value = 440 * Math.pow(2, (n.pitch - 69) / 12);
  const peak = amp * (n.part === "chord" ? 0.08 : n.part === "bass" ? 0.25 : 0.15) * (o.type === "square" ? 0.4 : 1);
  const rel = n.part === "chord" ? 0.6 : 0.25;
  g.gain.setValueAtTime(0, when);
  g.gain.linearRampToValueAtTime(peak, when + 0.01);
  g.gain.setTargetAtTime(peak * 0.6, when + 0.02, 0.1);
  g.gain.setTargetAtTime(0, when + dur, rel / 3);
  let out = g;
  if (n.part !== "bass") {
    const p = ac.createStereoPanner(); p.pan.value = ((n.voice * 0.618) % 1) * 1.4 - 0.7; g.connect(p); out = p;
  }
  o.connect(g); out.connect(master);
  o.start(when); o.stop(when + dur + rel * 2);
}

function schedule() {
  const horizon = (ac.currentTime - t0 + 0.25) / spb;
  while (next < notes.length && notes[next].start < horizon) {
    const n = notes[next++];
    if (n.start >= offset) voice(n, t0 + n.start * spb);
  }
}

function start() {
  if (!ac) {
    ac = new AudioContext();
    master = ac.createGain(); master.gain.value = 0.8; master.connect(ac.destination);
    noise = ac.createBuffer(1, ac.sampleRate * 1.5, ac.sampleRate);
    const d = noise.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  if (offset >= endBeat) offset = 0;
  master.gain.cancelScheduledValues(ac.currentTime); master.gain.setValueAtTime(0.8, ac.currentTime);
  t0 = ac.currentTime + 0.05 - offset * spb;
  next = notes.findIndex(n => n.start >= offset); if (next < 0) next = notes.length;
  playing = true; timer = setInterval(schedule, 50); schedule();
  document.getElementById("play").textContent = "Pause";
}

function stop() {
  offset = beatNow(); playing = false; clearInterval(timer);
  master.gain.setTargetAtTime(0, ac.currentTime, 0.02);
  const old = master; master = ac.createGain(); master.gain.value = 0.8; master.connect(ac.destination);
  setTimeout(() => old.disconnect(), 300);
  document.getElementById("play").textContent = "Play";
}

document.getElementById("play").onclick = () => playing ? stop() : start();
canvas.onclick = e => {
  const r = canvas.getBoundingClientRect();
  const target = Math.max(0, beatNow() + (e.clientX - r.left - r.width * 0.3) / PX);
  const was = playing; if (was) stop(); offset = target; if (was) start();
};
draw();
</script>
</body>
</html>
"""


def to_html(score: Score) -> str:
    data = json.dumps(score.to_dict(), separators=(",", ":")).replace("</", "<\\/")
    title = html.escape(score.title or "git-symphony")
    return TEMPLATE.replace("__TITLE__", title).replace("__SCORE__", data)


def write_html(score: Score, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(to_html(score))
