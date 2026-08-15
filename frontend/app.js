const state = { socket: null, lastSeq: 0 };

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

function addEvent(event) {
  state.lastSeq = Math.max(state.lastSeq, Number(event.seq || 0));
  const item = document.createElement("article");
  item.className = `event ${event.type.replace(/[^a-z0-9_-]/gi, "-")}`;
  const time = new Date((event.ts || Date.now() / 1000) * 1000).toLocaleTimeString();
  const payload = event.payload || {};
  const detail = payload.detail || payload.message || payload.reason || payload.error || payload.tool || payload.status || "";
  item.innerHTML = `<div class="event-meta"><span>${escapeHtml(event.type)}</span><time>${time}</time></div><strong>${escapeHtml(labelFor(event.type))}</strong>${detail ? `<p>${escapeHtml(String(detail))}</p>` : ""}`;
  $("timeline").prepend(item);
  while ($("timeline").children.length > 100) $("timeline").lastChild.remove();

  if (event.type === "task.started" && payload.goal) $("taskGoal").textContent = payload.goal;
}

function labelFor(type) {
  return type
    .replaceAll(".", " → ")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

function escapeHtml(value) {
  return value.replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
}

function connect() {
  if (state.socket) state.socket.close();
  const taskId = $("taskId").value.trim();
  state.socket = new WebSocket(wsUrl(taskId));
  state.socket.onopen = () => setConnection(true);
  state.socket.onmessage = (message) => {
    try { addEvent(JSON.parse(message.data)); } catch { /* ignore malformed UI events */ }
  };
  state.socket.onerror = () => setConnection(false, "stream error");
  state.socket.onclose = () => setConnection(false);
}

$("connect").addEventListener("click", connect);
$("taskId").addEventListener("keydown", (event) => {
  if (event.key === "Enter") connect();
});
