/* LeRobot Dataset Curator - frontend */

let DS = null;          // /api/dataset 応答
let project = null;     // curation {episodes: {"5": {decision, trim, reviewed}}}
let currentEp = -1;
let signals = null;     // 現在エピソードの state/action
let playing = false;
let filteredIndices = [];
let statusFilter = "all";
let taskFilter = "__all__";
let helpVisible = false;

const $ = (id) => document.getElementById(id);
const videos = {};      // feature -> video element
let spans = {};         // feature -> {url, from_ts, to_ts}

const fps = () => DS ? DS.fps : 30;
const curEpData = () => DS.episodes[currentEp];

/* ================= curation accessors ================= */

function epEntry(i, create = false) {
  const k = String(i);
  if (!project.episodes[k]) {
    if (!create) return null;
    project.episodes[k] = {};
  }
  return project.episodes[k];
}
function isDeleted(i) { return epEntry(i)?.decision === "delete"; }
function trimOf(i) {
  const t = epEntry(i)?.trim;
  return Array.isArray(t) && t.length === 2 ? t : null;
}
function isReviewed(i) { return !!epEntry(i)?.reviewed; }

function setDeleted(i, del) {
  const e = epEntry(i, true);
  if (del) e.decision = "delete";
  else delete e.decision;
  scheduleSave();
}
function setTrim(i, t) {
  const e = epEntry(i, true);
  if (t === null) delete e.trim;
  else e.trim = t;
  scheduleSave();
}

/* ================= boot ================= */

async function boot() {
  const [ds, proj] = await Promise.all([
    fetch("/api/dataset").then(r => r.json()),
    fetch("/api/project").then(r => r.json()),
  ]);
  DS = ds;
  project = proj;
  if (!project.episodes) project.episodes = {};

  $("dataset-title").textContent = `${DS.repo_id} — ${DS.episodes.length} エピソード / ${DS.fps} fps`;

  buildPlayers();
  buildTaskFilter();
  renderList();
  initTimeline();
  initKeys();
  initApplyDialog();

  if (DS.episodes.length > 0) openEpisode(0);
}

function buildPlayers() {
  const wrap = $("players");
  wrap.innerHTML = "";
  for (const key of DS.video_keys) {
    const div = document.createElement("div");
    div.className = "player";
    const v = document.createElement("video");
    v.muted = true;
    v.playsInline = true;
    v.preload = "metadata";
    div.appendChild(v);
    const label = document.createElement("label");
    label.textContent = key.split(".").pop();
    div.appendChild(label);
    wrap.appendChild(div);
    videos[key] = v;
  }
}

/* ================= episode list ================= */

function buildTaskFilter() {
  const sel = $("task-filter");
  const tasks = [...new Set(DS.episodes.flatMap(e => e.tasks))];
  sel.innerHTML = "";
  const optAll = document.createElement("option");
  optAll.value = "__all__";
  optAll.textContent = `すべてのタスク (${DS.episodes.length})`;
  sel.appendChild(optAll);
  for (const t of tasks) {
    const o = document.createElement("option");
    o.value = t;
    const n = DS.episodes.filter(e => e.tasks.includes(t)).length;
    o.textContent = `${t} (${n})`;
    sel.appendChild(o);
  }
  sel.onchange = () => { taskFilter = sel.value; renderList(); };
}

$("status-filter").addEventListener("click", (ev) => {
  const b = ev.target.closest("button");
  if (!b) return;
  statusFilter = b.dataset.f;
  for (const x of $("status-filter").children) x.classList.toggle("active", x === b);
  renderList();
});

function matchesFilter(i) {
  const ep = DS.episodes[i];
  if (taskFilter !== "__all__" && !ep.tasks.includes(taskFilter)) return false;
  switch (statusFilter) {
    case "unreviewed": return !isReviewed(i);
    case "reviewed": return isReviewed(i);
    case "trim": return !!trimOf(i) && !isDeleted(i);
    case "delete": return isDeleted(i);
    default: return true;
  }
}

function renderList() {
  const ul = $("episode-list");
  ul.innerHTML = "";
  filteredIndices = [];
  DS.episodes.forEach((ep) => {
    const i = ep.index;
    if (!matchesFilter(i)) return;
    filteredIndices.push(i);

    const li = document.createElement("li");
    li.dataset.ep = i;
    if (i === currentEp) li.classList.add("current");

    const dot = document.createElement("span");
    dot.className = "reviewed-dot" + (isReviewed(i) ? " on" : "");
    dot.title = "確認済み";

    const num = document.createElement("span");
    num.className = "ep-num";
    num.textContent = `#${i}`;

    const badge = document.createElement("span");
    if (isDeleted(i)) { badge.className = "badge delete"; badge.textContent = "削除"; }
    else if (trimOf(i)) { badge.className = "badge trim"; badge.textContent = `トリム ${trimOf(i)[0]}–${trimOf(i)[1]}`; }
    else { badge.className = "badge keep"; badge.textContent = "保持"; }

    const len = document.createElement("span");
    len.className = "ep-len";
    len.textContent = `${ep.length}f`;

    li.append(dot, num, badge, len);
    li.onclick = () => openEpisode(i);
    ul.appendChild(li);
  });

  const nDel = DS.episodes.filter((_, i) => isDeleted(_.index)).length;
  const nTrim = DS.episodes.filter((_, i) => trimOf(_.index) && !isDeleted(_.index)).length;
  const nRev = DS.episodes.filter((_, i) => isReviewed(_.index)).length;
  $("sidebar-summary").innerHTML =
    `確認済み ${nRev} / ${DS.episodes.length} ・ トリム ${nTrim} ・ 削除 ${nDel}<br>` +
    `表示中 ${filteredIndices.length} エピソード`;
}

/* ================= episode open / playback ================= */

async function openEpisode(i) {
  if (i < 0 || i >= DS.episodes.length) return;
  currentEp = i;
  const ep = curEpData();

  $("ep-title").textContent = `エピソード #${i} — ${ep.length} フレーム (${(ep.length / fps()).toFixed(1)} 秒)`;
  $("ep-task").textContent = ep.tasks.join(" / ");
  if (ep.avail < ep.length) {
    $("ep-warning").hidden = false;
    $("ep-warning").textContent = `⚠ このエピソードの動画はデータより ${ep.length - ep.avail} フレーム短いため、末尾は近似表示になり適用時に切り詰めます`;
  } else {
    $("ep-warning").hidden = true;
  }

  spans = {};
  for (const [key, v] of Object.entries(ep.videos)) {
    spans[key] = v;
    const el = videos[key];
    const url = v.url;
    if (!el.src.endsWith(url)) { el.src = url; el.load(); }
  }

  const e = epEntry(i, true);
  e.reviewed = true;
  scheduleSave();

  // シグナル取得 (非同期)
  signals = null;
  fetch(`/api/episode/${i}/signals`).then(r => r.json()).then(s => {
    if (currentEp === i) { signals = s; drawTimeline(); }
  });

  // イン点があればそこへ、なければ先頭へ
  const t = trimOf(i);
  const startFrame = t ? t[0] : 0;
  seekTo(startFrame);
  updateDeleteUI();
  renderList();
  updateReadouts();
  startTick();
}

function frameOf(key) {
  const el = videos[key];
  const sp = spans[key];
  if (!el || !sp || !isFinite(el.currentTime)) return 0;
  const f = Math.round((el.currentTime - sp.from_ts) * fps());
  return Math.max(0, Math.min(curEpData().length - 1, f));
}
function masterKey() { return DS.video_keys[0]; }
function currentFrame() { return frameOf(masterKey()); }

function seekTo(frame) {
  const ep = curEpData();
  frame = Math.max(0, Math.min(ep.length - 1, frame));
  for (const key of DS.video_keys) {
    const sp = spans[key];
    if (!sp) continue;
    const t = sp.from_ts + frame / fps();
    const capped = Math.min(t, Math.max(sp.from_ts, sp.to_ts - 0.5 / fps()));
    const clamped = Math.max(sp.from_ts, capped);
    const el = videos[key];
    if (el.readyState < 1) {
      // メタデータ読み込み前はシークが効かないためロード後に適用
      el.addEventListener("loadedmetadata", () => { el.currentTime = clamped; }, { once: true });
    } else {
      el.currentTime = clamped;
    }
  }
  updateReadouts();
  drawTimeline();
}

async function play() {
  playing = true;
  $("btn-play").textContent = "⏸";
  try { await videos[masterKey()].play(); } catch (_) {}
  for (const key of DS.video_keys.slice(1)) { try { await videos[key].play(); } catch (_) {} }
}
function pause() {
  playing = false;
  $("btn-play").textContent = "▶";
  for (const key of DS.video_keys) videos[key].pause();
}
function togglePlay() { playing ? pause() : play(); }

/* rAF ループ: スレーブ同期・上限停止・UI更新 (単一ループ) */
let tickStarted = false;
function startTick() {
  if (tickStarted) return;
  tickStarted = true;
  requestAnimationFrame(tick);
}
function tick() {
  if (currentEp < 0) return;
  const ep = curEpData();
  const mk = masterKey();
  const master = videos[mk];
  const sp = spans[mk];

  if (playing && master && sp) {
    const endT = sp.to_ts;
    if (master.currentTime >= endT - 1 / (2 * fps())) {
      pause();
      seekTo(ep.length - 1);
    }
    // スレーブ同期
    for (const key of DS.video_keys.slice(1)) {
      const sl = videos[key];
      const ssp = spans[key];
      if (!sl || !ssp) continue;
      const target = ssp.from_ts + (master.currentTime - sp.from_ts);
      if (Math.abs(sl.currentTime - target) > 0.04) sl.currentTime = Math.max(ssp.from_ts, target);
    }
    updateReadouts();
    drawTimeline();
  }
  requestAnimationFrame(tick);
}

function updateReadouts() {
  if (currentEp < 0) return;
  const ep = curEpData();
  const f = currentFrame();
  $("frame-readout").textContent = `フレーム ${f} / ${ep.length - 1}  (${(f / fps()).toFixed(2)}s)`;
  const t = trimOf(currentEp);
  $("trim-readout").textContent = t
    ? `⟦ トリム ${t[0]} … ${t[1]} ⟧ (${t[1] - t[0]}f)`
    : "トリムなし (全体)";
}

function updateDeleteUI() {
  const del = currentEp >= 0 && isDeleted(currentEp);
  $("delete-ribbon").hidden = !del;
  $("btn-delete").classList.toggle("active-toggle", del);
}

/* ================= trim / delete actions ================= */

function setIn() {
  if (currentEp < 0) return;
  const t = trimOf(currentEp) ? [...trimOf(currentEp)] : [0, curEpData().length];
  t[0] = currentFrame();
  if (t[0] >= t[1]) t[1] = Math.min(curEpData().length, t[0] + 1);
  setTrim(currentEp, t);
  afterMarkChange();
}
function setOut() {
  if (currentEp < 0) return;
  const t = trimOf(currentEp) ? [...trimOf(currentEp)] : [0, curEpData().length];
  t[1] = Math.max(1, currentFrame() + 1);
  if (t[1] <= t[0]) t[0] = Math.max(0, t[1] - 1);
  setTrim(currentEp, t);
  afterMarkChange();
}
function clearTrim() {
  if (currentEp < 0) return;
  setTrim(currentEp, null);
  afterMarkChange();
}
function toggleDelete() {
  if (currentEp < 0) return;
  setDeleted(currentEp, !isDeleted(currentEp));
  updateDeleteUI();
  renderList();
}
function afterMarkChange() {
  updateReadouts();
  drawTimeline();
  renderList();
}

function gotoPrevEpisode() {
  const pos = filteredIndices.indexOf(currentEp);
  const prev = filteredIndices[Math.max(0, pos - 1)];
  if (prev !== undefined && prev !== currentEp) openEpisode(prev);
}
function gotoNextEpisode() {
  const pos = filteredIndices.indexOf(currentEp);
  if (pos === -1) { if (filteredIndices.length) openEpisode(filteredIndices[0]); return; }
  const next = filteredIndices[Math.min(filteredIndices.length - 1, pos + 1)];
  if (next !== currentEp) openEpisode(next);
  const li = document.querySelector(`#episode-list li.current`);
  if (li) li.scrollIntoView({ block: "nearest" });
}

/* ================= keyboard ================= */

function initKeys() {
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
    if ($("apply-dialog").open) return;
    const k = e.key;
    let handled = true;
    switch (k) {
      case " ": togglePlay(); break;
      case "ArrowLeft":
        pause();
        seekTo(currentFrame() - (e.shiftKey ? fps() : 1)); break;
      case "ArrowRight":
        pause();
        seekTo(currentFrame() + (e.shiftKey ? fps() : 1)); break;
      case "j": case "J": pause(); seekTo(currentFrame() - fps()); break;
      case "l": case "L": pause(); seekTo(currentFrame() + fps()); break;
      case "k": case "K": pause(); break;
      case "i": case "I": setIn(); break;
      case "o": case "O": setOut(); break;
      case "x": case "X": clearTrim(); break;
      case "d": case "D": toggleDelete(); break;
      case "ArrowUp": gotoPrevEpisode(); break;
      case "ArrowDown": gotoNextEpisode(); break;
      case "PageUp": gotoPrevEpisode(); break;
      case "PageDown": gotoNextEpisode(); break;
      case "Home": {
        const t = trimOf(currentEp);
        seekTo(t ? t[0] : 0); break;
      }
      case "End": {
        const t = trimOf(currentEp);
        seekTo((t ? t[1] : curEpData().length) - 1); break;
      }
      case "?": helpVisible = !helpVisible; $("shortcuts-help").hidden = !helpVisible; break;
      case "Escape": helpVisible = false; $("shortcuts-help").hidden = true; break;
      default: handled = false;
    }
    if (handled) e.preventDefault();
  });
}

/* ================= timeline canvas ================= */

const TL_RULER_H = 18;
let tl = null;   // canvas 2d context

function initTimeline() {
  const c = $("timeline");
  tl = c.getContext("2d");
  new ResizeObserver(() => drawTimeline()).observe(c);

  let dragMode = null; // 'in' | 'out' | 'scrub' | null
  let moved = false;

  const frameAtX = (x) => {
    const r = c.getBoundingClientRect();
    const w = r.width - 2; // 左右1pxマージン
    const ep = curEpData();
    return Math.max(0, Math.min(ep.length - 1, Math.round(((x - 1) / w) * ep.length)));
  };
  const xOfFrame = (f) => {
    const r = c.getBoundingClientRect();
    const w = r.width - 2;
    const ep = curEpData();
    return 1 + (f / ep.length) * w;
  };
  const hitTest = (x) => {
    const t = trimOf(currentEp);
    if (t) {
      if (Math.abs(x - xOfFrame(t[0])) < 7) return "in";
      if (Math.abs(x - xOfFrame(t[1] - 1)) < 7) return "out";
    }
    return null;
  };

  c.addEventListener("pointerdown", (e) => {
    if (currentEp < 0) return;
    c.setPointerCapture(e.pointerId);
    moved = false;
    const x = e.offsetX;
    dragMode = hitTest(x) || "scrub";
    if (dragMode === "scrub") { pause(); seekTo(frameAtX(x)); }
  });
  c.addEventListener("pointermove", (e) => {
    if (currentEp < 0) return;
    const x = e.offsetX;
    if (!dragMode) { c.style.cursor = hitTest(x) ? "ew-resize" : "crosshair"; return; }
    moved = true;
    const f = frameAtX(x);
    if (dragMode === "scrub") seekTo(f);
    else if (dragMode === "in") {
      const t = [...trimOf(currentEp)];
      t[0] = Math.max(0, Math.min(f, t[1] - 1));
      setTrim(currentEp, t); afterMarkChange();
    } else if (dragMode === "out") {
      const t = [...trimOf(currentEp)];
      t[1] = Math.max(t[0] + 1, Math.min(f + 1, curEpData().length));
      setTrim(currentEp, t); afterMarkChange();
    }
  });
  const up = (e) => {
    if (dragMode === "scrub" && !moved) { /* クリックのみ → 既にseek済み */ }
    dragMode = null;
  };
  c.addEventListener("pointerup", up);
  c.addEventListener("pointercancel", up);
}

function drawTimeline() {
  const c = $("timeline");
  if (!tl || !DS || currentEp < 0) return;
  const ep = curEpData();
  const dpr = window.devicePixelRatio || 1;
  const W = c.clientWidth, H = c.clientHeight;
  if (c.width !== W * dpr || c.height !== H * dpr) { c.width = W * dpr; c.height = H * dpr; }
  const g = tl;
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);

  const m = 1; // 左右マージン
  const plotW = W - 2 * m;
  const plotH = H - TL_RULER_H;
  const xOf = (f) => m + (f / ep.length) * plotW;

  /* トリム除外領域 */
  const t = trimOf(currentEp);
  if (t) {
    g.fillStyle = "rgba(229, 83, 75, 0.13)";
    g.fillRect(m, 0, xOf(t[0]) - m, H);
    g.fillRect(xOf(t[1]), 0, m + plotW - xOf(t[1]), H);
  }
  if (isDeleted(currentEp)) {
    g.fillStyle = "rgba(229, 83, 75, 0.18)";
    g.fillRect(m, 0, plotW, H);
  }

  /* 信号カーブ */
  if (signals && signals.state && signals.state.length) {
    const n = signals.state.length;
    const drawSeries = (series, color, width, alpha) => {
      g.strokeStyle = color;
      g.globalAlpha = alpha;
      g.lineWidth = width;
      for (let ch = 0; ch < series[0].length; ch++) {
        let mn = Infinity, mx = -Infinity;
        for (const row of series) { mn = Math.min(mn, row[ch]); mx = Math.max(mx, row[ch]); }
        const range = mx - mn || 1;
        g.beginPath();
        for (let i = 0; i < n; i++) {
          const x = m + (i / ep.length) * plotW;
          const y = TL_RULER_H + plotH - ((series[i][ch] - mn) / range) * (plotH - 6) - 3;
          i === 0 ? g.moveTo(x, y) : g.lineTo(x, y);
        }
        g.stroke();
      }
      g.globalAlpha = 1;
    };
    drawSeries(signals.state, "#58a6ff", 1, 0.45);
    drawSeries(signals.action, "#d29922", 1, 0.35);
    // グリッパー (最終チャネル) を強調
    if (signals.state[0].length >= 6) {
      drawSeries(signals.state.map(r => [r[5]]), "#79c0ff", 2, 0.95);
      drawSeries(signals.action.map(r => [r[5]]), "#ffa657", 1.5, 0.8);
    }
  }

  /* ルーラー */
  g.fillStyle = "#1a1e22";
  g.fillRect(0, 0, W, TL_RULER_H);
  g.strokeStyle = "#30363d";
  g.beginPath(); g.moveTo(0, TL_RULER_H - 0.5); g.lineTo(W, TL_RULER_H - 0.5); g.stroke();
  g.fillStyle = "#8b949e";
  g.font = "10px monospace";
  g.textBaseline = "middle";
  const totalSec = ep.length / fps();
  const pxPerSec = plotW / totalSec;
  const secStep = pxPerSec >= 45 ? 1 : pxPerSec >= 9 ? 5 : Math.max(5, Math.round(totalSec / 12));
  for (let s = 0; s <= totalSec; s += secStep) {
    const x = xOf(Math.round(s * fps()));
    g.strokeStyle = "#444c56";
    g.beginPath(); g.moveTo(x, TL_RULER_H - 6); g.lineTo(x, TL_RULER_H - 1); g.stroke();
    g.fillText(`${s}s`, x + 2, 7);
  }

  /* 動画利用可能範囲の境界 */
  if (ep.avail < ep.length) {
    const x = xOf(ep.avail);
    g.strokeStyle = "rgba(212, 167, 44, 0.8)";
    g.setLineDash([4, 3]);
    g.beginPath(); g.moveTo(x, TL_RULER_H); g.lineTo(x, H); g.stroke();
    g.setLineDash([]);
  }

  /* イン/アウトマーカー */
  if (t) {
    const marker = (x, label, color) => {
      g.strokeStyle = color;
      g.lineWidth = 2;
      g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke();
      g.fillStyle = color;
      g.beginPath();
      g.moveTo(x - 5, 0); g.lineTo(x + 5, 0); g.lineTo(x, 9); g.closePath(); g.fill();
      g.font = "bold 10px monospace";
      g.fillText(label, x + 4, H - 6);
    };
    marker(xOf(t[0]), `I ${t[0]}`, "#4da6ff");
    marker(xOf(t[1] - 1), `O ${t[1]}`, "#4da6ff");
  }

  /* 再生ヘッド */
  const px = xOf(currentFrame());
  g.strokeStyle = "#ffffff";
  g.lineWidth = 1.5;
  g.beginPath(); g.moveTo(px, 0); g.lineTo(px, H); g.stroke();
  g.fillStyle = "#ffffff";
  g.beginPath();
  g.moveTo(px - 6, 0); g.lineTo(px + 6, 0); g.lineTo(px, 8); g.closePath(); g.fill();
}

/* ================= autosave ================= */

let saveTimer = null;
let saveSeq = 0;
function scheduleSave() {
  $("save-status").textContent = "保存中...";
  $("save-status").className = "saving";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(doSave, 800);
}
async function doSave() {
  const seq = ++saveSeq;
  try {
    const res = await fetch("/api/project", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(project),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (seq === saveSeq) {
      $("save-status").textContent = `保存済み ${new Date().toLocaleTimeString()}`;
      $("save-status").className = "";
    }
  } catch (e) {
    $("save-status").textContent = `保存エラー: ${e.message}`;
    $("save-status").className = "error";
  }
}

/* ================= apply dialog ================= */

function computeSummary() {
  let keep = 0, trimN = 0, del = 0, framesBefore = 0, framesAfter = 0;
  for (const ep of DS.episodes) {
    const i = ep.index;
    framesBefore += ep.length;
    const effLen = Math.min(ep.length, ep.avail);
    if (isDeleted(i)) { del++; continue; }
    const t = trimOf(i);
    if (t) {
      trimN++;
      const s = Math.max(0, t[0]);
      const e2 = Math.min(t[1], effLen);
      framesAfter += Math.max(0, e2 - s);
    } else {
      keep++;
      framesAfter += effLen;
    }
  }
  return { keep, trimN, del, framesBefore, framesAfter };
}

function initApplyDialog() {
  const dlg = $("apply-dialog");
  $("btn-apply").onclick = () => {
    const s = computeSummary();
    $("apply-summary").innerHTML =
      `保持 (無編集): <b>${s.keep}</b> ・ トリム: <b>${s.trimN}</b> ・ 削除: <b>${s.del}</b> エピソード<br>` +
      `フレーム数: ${s.framesBefore} → <b>${s.framesAfter}</b> (${(100 * s.framesAfter / s.framesBefore).toFixed(1)}%)<br>` +
      `<span style="color:var(--dim)">元データセットは変更されません。新しいデータセットとして書き出します。</span>`;
    $("apply-repo-id").value = `${DS.repo_id}_curated`;
    $("apply-root").value = "";
    $("apply-root").placeholder = "(空欄で自動: <元データセット名>_curated)";
    $("apply-log").hidden = true;
    $("apply-result").hidden = true;
    $("apply-start").disabled = false;
    $("apply-overwrite").checked = false;
    dlg.showModal();
  };
  $("apply-close").onclick = () => dlg.close();
  $("apply-start").onclick = async () => {
    $("apply-start").disabled = true;
    $("apply-log").hidden = false;
    const logEl = $("apply-log");
    logEl.textContent = "未保存の編集を保存中...\n";
    clearTimeout(saveTimer);
    await doSave(); // 適用はディスク上の curation.json を読むため、保留中の保存を反映
    logEl.textContent = "開始...\n";
    try {
      const res = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_repo_id: $("apply-repo-id").value.trim() || null,
          output_root: $("apply-root").value.trim() || null,
          overwrite: $("apply-overwrite").checked,
        }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || `HTTP ${res.status}`);
      }
      // ステータスポーリング
      while (true) {
        await new Promise(r => setTimeout(r, 1000));
        const st = await fetch("/api/apply/status").then(r => r.json());
        logEl.textContent = st.log.join("\n") + "\n";
        logEl.scrollTop = logEl.scrollHeight;
        if (!st.running) {
          if (st.error) {
            logEl.textContent += `\n✖ 失敗: ${st.error}`;
          } else if (st.result) {
            $("apply-result").hidden = false;
            $("apply-result").innerHTML =
              `✅ 完了: <b>${st.result.total_episodes}</b> エピソード / <b>${st.result.total_frames}</b> フレーム<br>` +
              `出力: <code>${st.result.output_root}</code><br>` +
              `学習コマンド例:<br><code>lerobot-train --dataset.repo-id=${st.result.output_repo_id} --dataset.root=${st.result.output_root} ...</code>`;
          }
          break;
        }
      }
    } catch (e) {
      logEl.textContent += `\n✖ エラー: ${e.message}`;
    }
    $("apply-start").disabled = false;
  };
}

/* ================= transport buttons ================= */

function initButtons() {
  $("btn-play").onclick = togglePlay;
  $("btn-frame-back").onclick = () => { pause(); seekTo(currentFrame() - 1); };
  $("btn-frame-fwd").onclick = () => { pause(); seekTo(currentFrame() + 1); };
  $("btn-prev-ep").onclick = gotoPrevEpisode;
  $("btn-next-ep").onclick = gotoNextEpisode;
  $("btn-in").onclick = setIn;
  $("btn-out").onclick = setOut;
  $("btn-clear-trim").onclick = clearTrim;
  $("btn-delete").onclick = toggleDelete;
  $("btn-help").onclick = () => { helpVisible = !helpVisible; $("shortcuts-help").hidden = !helpVisible; };
}

initButtons();
boot();
