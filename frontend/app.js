const state = { socket: null, lastSeq: 0, taskId: "", terminal: false };

const $ = (id) => document.getElementById(id);

function wsUrl(taskId) {
  const configured = new URLSearchParams(location.search).get("api");
  const base = configured || `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
  const url = new URL("/v1/events/ws", base);
  if (taskId) url.searchParams.set("task_id", taskId);
  if (state.lastSeq) url.searchParams.set("after", String(state.lastSeq));
  return url.toString();
}

function setConnection(online, detail = "") {
  const el = $("connection");
  el.className = `status ${online ? "online" : "offline"}`;
  el.textContent = online ? "● Live" : `● Offline${detail ? ` — ${detail}` : ""}`;
}

function setTaskStatus(event) {
  const status = $("taskStatus");
  if (!status) return;
  const type = event.type.toLowerCase();
  status.className = `task-status ${event.payload?.terminal ? "terminal" : "running"}`;
  if (type.includes("failed")) status.textContent = "Failed";
  else if (type.includes("completed")) status.textContent = "Completed";
  else if (type.includes("approval")) status.textContent = "Waiting for approval";
  else if (type.includes("verification")) status.textContent = "Verifying";
  else if (type.includes("action")) status.textContent = "Working";
  else status.textContent = "Running";
}

function addEvent(event) {
  const seq = Number(event.seq || 0);
  if (seq <= state.lastSeq) return;
  state.lastSeq = seq;
  if (event.task_id) state.taskId = event.task_id;
  setTaskStatus(event);

  const item = document.createElement("article");
  item.className = `event ${event.type.replace(/[^a-z0-9_-]/gi, "-")}`;
  const time = new Date((event.ts || Date.now() / 1000) * 1000).toLocaleTimeString();
  const payload = event.payload || {};
  const detail = payload.detail || payload.message || payload.reason || payload.error || payload.tool || payload.status || "";
  item.innerHTML = `<div class="event-meta"><span>#${seq} · ${escapeHtml(event.type)}</span><time>${time}</time></div><strong>${escapeHtml(labelFor(event.type))}</strong>${detail ? `<p>${escapeHtml(String(detail))}</p>` : ""}`;
  $("timeline").prepend(item);
  while ($("timeline").children.length > 100) $("timeline").lastChild.remove();

  if ((event.type === "task.started" || event.type === "TASK_STARTED") && payload.goal) $("taskGoal").textContent = payload.goal;
  if (payload.voice_text) showCommentary(payload.voice_text);
  if (payload.terminal) showResult(payload.message || payload.reply || (event.type.toLowerCase().includes("completed") ? "Ho gaya bhai." : "Kaam complete nahi ho paya."), !event.type.toLowerCase().includes("failed"));
}

function showCommentary(text) {
  const el = $("commentary");
  if (el && text) el.textContent = text;
}

function showResult(text, success) {
  const el = $("result");
  if (!el) return;
  el.className = `result ${success ? "success" : "failure"}`;
  el.textContent = text;
}

function labelFor(type) {
  return type.replaceAll(".", " → ").replaceAll("_", " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function connect() {
  if (state.socket) state.socket.close();
  state.terminal = false;
  state.lastSeq = 0;
  state.taskId = $("taskId").value.trim();
  $("timeline").replaceChildren();
  showResult("Waiting for TOM…", true);
  const taskId = state.taskId;
  state.socket = new WebSocket(wsUrl(taskId));
  state.socket.onopen = () => setConnection(true);
  state.socket.onmessage = (message) => {
    try { addEvent(JSON.parse(message.data)); } catch { /* malformed event is ignored, connection remains alive */ }
  };
  state.socket.onerror = () => setConnection(false, "stream error");
  state.socket.onclose = () => setConnection(false);
}

$("connect").addEventListener("click", connect);
$("taskId").addEventListener("keydown", (event) => { if (event.key === "Enter") connect(); });
