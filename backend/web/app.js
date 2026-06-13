const SCENES = {
  drive: "开车", commute: "上下班", work: "工作",
  rediscover: "听腻了 · 翻旧歌",
};
const $ = (s) => document.querySelector(s);
const tokenEl = $("#token");
tokenEl.value = localStorage.getItem("echo_token") || "";
tokenEl.addEventListener("change", () => localStorage.setItem("echo_token", tokenEl.value));

function headers() { return { "X-Echo-Token": tokenEl.value, "Content-Type": "application/json" }; }
function show(id) {
  for (const s of ["home", "queue", "alerts"]) $("#" + s).hidden = (s !== id);
}

document.querySelectorAll(".scene").forEach((b) =>
  b.addEventListener("click", () => openQueue(b.dataset.scene)));
document.querySelectorAll(".back").forEach((b) =>
  b.addEventListener("click", () => show(b.dataset.target)));
$("#alertsBtn").addEventListener("click", openAlerts);

async function openQueue(scene) {
  $("#queueTitle").textContent = SCENES[scene] || scene;
  show("queue");
  const list = $("#queueList");
  list.innerHTML = "加载中…";
  const r = await fetch(`/api/queue?scene=${encodeURIComponent(scene)}`, { headers: headers() });
  if (!r.ok) { list.innerHTML = "出错了（token?）"; return; }
  const { queue } = await r.json();
  list.innerHTML = "";
  queue.forEach((t) => list.appendChild(renderRow(t, scene)));
}

function renderRow(t, scene) {
  const li = document.createElement("li");
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div class="meta"><div class="title">${t.title}</div>
    <div class="sub">${t.artist || ""}</div></div>
    <a class="play" target="_blank" href="${t.yt_music_url}">播放 ▶</a>`;
  const fb = document.createElement("div"); fb.className = "fb";
  const actions = [["finish", "听完了"], ["skip", "不想听"], ["too_noisy", "太吵"], ["manual_pick", "正中"]];
  actions.forEach(([action, label]) => {
    const b = document.createElement("button");
    b.textContent = label;
    b.addEventListener("click", () => sendFeedback(t, scene, action, b));
    fb.appendChild(b);
  });
  li.appendChild(row); li.appendChild(fb);
  return li;
}

async function sendFeedback(t, scene, action, btn) {
  btn.disabled = true;
  await fetch("/api/feedback", { method: "POST", headers: headers(),
    body: JSON.stringify({ youtube_video_id: t.youtube_video_id, scene, action,
      listened_seconds: action === "finish" ? t.duration_seconds : 0,
      duration_seconds: t.duration_seconds }) });
  btn.textContent = "✓";
}

async function openAlerts() {
  show("alerts");
  const list = $("#alertList");
  list.innerHTML = "加载中…";
  const r = await fetch("/api/alerts", { headers: headers() });
  if (!r.ok) { list.innerHTML = "出错了（token?）"; return; }
  const alerts = await r.json();
  list.innerHTML = alerts.length ? "" : "<li>没有消失的歌 🎉</li>";
  alerts.forEach((a) => {
    const li = document.createElement("li"); li.className = "row";
    const cands = JSON.parse(a.candidate || "[]");
    const candTxt = cands.map((c) => c.title).join(" / ") || "无候选";
    li.innerHTML = `<div class="meta"><div class="title">${a.title_at_time}</div>
      <div class="sub">候选: ${candTxt}</div></div>`;
    list.appendChild(li);
  });
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
