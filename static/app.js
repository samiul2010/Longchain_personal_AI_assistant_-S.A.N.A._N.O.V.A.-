const messagesEl = document.getElementById("messages");
const emptyState = document.getElementById("emptyState");
const threadListEl = document.getElementById("threadList");
const textInput = document.getElementById("textInput");
const sendBtn = document.getElementById("sendBtn");
const attachBtn = document.getElementById("attachBtn");
const fileInput = document.getElementById("fileInput");
const attachmentChip = document.getElementById("attachmentChip");
const attachmentName = document.getElementById("attachmentName");
const removeAttachment = document.getElementById("removeAttachment");
const newChatBtn = document.getElementById("newChatBtn");
const clearChatBtn = document.getElementById("clearChatBtn");
const themeToggle = document.getElementById("themeToggle");
const themeIcon = themeToggle?.querySelector(".theme-icon");
const themeColorMeta = document.getElementById("themeColorMeta");
const suggestionCards = document.querySelectorAll(".suggestion-card");
const stepTemplate = document.getElementById("stepTemplate");
const appEl = document.querySelector(".app");
const menuBtn = document.getElementById("menuBtn");
const closeSidebarBtn = document.getElementById("closeSidebarBtn");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const chatScroll = document.getElementById("chatScroll");

let currentThreadId = localStorage.getItem("assistant_thread_id") || null;
let pendingAttachment = null;
let isStreaming = false;
let activeTranscript = [];

const CACHE_PREFIX = "assistant_transcript_";
const AGENT_LABELS = {
  git_hub_agent: "GitHub Manager Agent",
  git_lab_agent: "GitLab Manager Agent",
  facebook_agent: "Facebook Manager Agent",
  youtube_agent: "YouTube Manager Agent",
};

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  document.body.dataset.theme = nextTheme;
  if (themeIcon) themeIcon.textContent = nextTheme === "dark" ? "☀" : "☾";
  if (themeToggle) {
    themeToggle.title = nextTheme === "dark" ? "Switch to light mode" : "Switch to dark mode";
    themeToggle.setAttribute("aria-label", themeToggle.title);
  }
  if (themeColorMeta) themeColorMeta.content = nextTheme === "dark" ? "#17181c" : "#ffffff";
}
function initTheme() {
  const saved = localStorage.getItem("assistant_theme");
  const systemDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  applyTheme(saved || (systemDark ? "dark" : "light"));
}
initTheme();
themeToggle?.addEventListener("click", () => {
  const next = document.body.dataset.theme === "dark" ? "light" : "dark";
  localStorage.setItem("assistant_theme", next);
  applyTheme(next);
});

function cacheKey(threadId) { return `${CACHE_PREFIX}${threadId}`; }
function readCachedTurns(threadId) {
  if (!threadId) return [];
  try {
    const value = JSON.parse(localStorage.getItem(cacheKey(threadId)) || "[]");
    return Array.isArray(value) ? value : [];
  } catch { return []; }
}
function saveCachedTurns(turns) {
  if (!currentThreadId) return;
  try { localStorage.setItem(cacheKey(currentThreadId), JSON.stringify(turns.slice(-80))); } catch (err) { console.warn("Transcript cache unavailable", err); }
}
function normalizeTurns(turns) {
  return (Array.isArray(turns) ? turns : []).filter((turn) =>
    turn && (turn.role === "user" || turn.role === "assistant")
  ).map((turn) => ({
    role: turn.role,
    text: typeof turn.text === "string" ? turn.text : String(turn.text || ""),
    steps: Array.isArray(turn.steps) ? turn.steps : [],
  }));
}

function openSidebar() { appEl.classList.add("sidebar-open"); sidebarBackdrop.classList.add("visible"); }
function closeSidebar() { appEl.classList.remove("sidebar-open"); sidebarBackdrop.classList.remove("visible"); }
menuBtn.addEventListener("click", openSidebar);
closeSidebarBtn.addEventListener("click", closeSidebar);
sidebarBackdrop.addEventListener("click", closeSidebar);

async function loadThreads() {
  try {
    const res = await fetch("/api/threads", { cache: "no-store" });
    if (!res.ok) throw new Error("threads request failed");
    const threads = await res.json();
    threadListEl.innerHTML = "";
    if (!threads.length) {
      threadListEl.innerHTML = '<div class="thread-empty">No conversations yet</div>';
      return;
    }
    threads.forEach((t) => {
      const item = document.createElement("div");
      item.className = "thread-item" + (t.id === currentThreadId ? " active" : "");
      const title = document.createElement("span");
      title.className = "thread-title";
      title.textContent = t.title || "New conversation";
      const del = document.createElement("span");
      del.className = "del";
      del.title = "Delete";
      del.textContent = "×";
      item.append(title, del);
      title.addEventListener("click", () => selectThread(t.id));
      del.addEventListener("click", async (e) => {
        e.stopPropagation();
        await fetch(`/api/threads/${encodeURIComponent(t.id)}`, { method: "DELETE" });
        localStorage.removeItem(cacheKey(t.id));
        if (t.id === currentThreadId) {
          currentThreadId = null;
          localStorage.removeItem("assistant_thread_id");
          activeTranscript = [];
          clearRenderedChat();
        }
        await loadThreads();
      });
      threadListEl.appendChild(item);
    });
  } catch (err) { console.warn("Unable to load threads", err); }
}

async function selectThread(threadId) {
  currentThreadId = threadId;
  localStorage.setItem("assistant_thread_id", threadId);
  activeTranscript = readCachedTurns(threadId);
  renderTurns(activeTranscript);
  await loadThreads();
  await loadHistory();
  closeSidebar();
}

async function createNewChat() {
  const res = await fetch("/api/threads", { method: "POST" });
  const data = await res.json();
  currentThreadId = data.thread_id;
  localStorage.setItem("assistant_thread_id", currentThreadId);
  activeTranscript = [];
  clearRenderedChat();
  await loadThreads();
  closeSidebar();
  textInput.focus();
}
newChatBtn.addEventListener("click", createNewChat);
clearChatBtn.addEventListener("click", createNewChat);

function clearRenderedChat() {
  messagesEl.replaceChildren();
  emptyState.style.display = "block";
}

async function loadHistory() {
  if (!currentThreadId) { clearRenderedChat(); return; }
  try {
    const res = await fetch(`/api/history?thread_id=${encodeURIComponent(currentThreadId)}`, { cache: "no-store" });
    const data = res.ok ? await res.json() : { turns: [] };
    const serverTurns = normalizeTurns(data.turns);
    // The browser cache is a deliberate fallback: a refresh must not blank the
    // conversation while the graph/checkpointer is still being restored.
    const serverHasAnswer = serverTurns.some((turn) => turn.role === "assistant" && turn.text.trim());
    if (serverHasAnswer) {
      activeTranscript = serverTurns;
      saveCachedTurns(activeTranscript);
    } else if (!activeTranscript.length) {
      activeTranscript = readCachedTurns(currentThreadId);
    }
    renderTurns(activeTranscript);
  } catch (err) {
    activeTranscript = activeTranscript.length ? activeTranscript : readCachedTurns(currentThreadId);
    renderTurns(activeTranscript);
    console.warn("Unable to load history", err);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str ?? "");
  return div.innerHTML;
}
function scrollToBottom() { requestAnimationFrame(() => { chatScroll.scrollTop = chatScroll.scrollHeight; }); }

function renderTurns(turns) {
  messagesEl.replaceChildren();
  const safeTurns = normalizeTurns(turns);
  emptyState.style.display = safeTurns.length ? "none" : "block";
  safeTurns.forEach((turn) => {
    if (turn.role === "user") renderUserMessage(turn.text, false);
    else renderAssistantMessage(turn, false);
  });
  scrollToBottom();
}
function renderUserMessage(text, shouldScroll = true) {
  emptyState.style.display = "none";
  const row = document.createElement("div");
  row.className = "msg-row user";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  if (shouldScroll) scrollToBottom();
  return row;
}
function renderAssistantMessage(turn, shouldScroll = true) {
  const { row, stepsWrap, bubble } = renderAssistantSkeleton();
  (turn.steps || []).forEach((step) => {
    if (step.type === "report") {
      renderReportStep(stepsWrap, step.agent, step.output || "");
      return;
    }
    const stepEl = createStepEl(step.type === "agent_start" ? "agent" : "tool", step.agent, step.tool, step.input);
    stepsWrap.appendChild(stepEl);
    markStepDone(stepEl, step.output !== undefined && step.output !== null ? step.output : "");
  });
  const activityPanel = row.querySelector(".activity-panel");
  if (turn.steps?.length) {
    activityPanel?.removeAttribute("hidden");
    const status = activityPanel.querySelector(".activity-status");
    if (status) status.textContent = "Complete";
  } else activityPanel?.setAttribute("hidden", "");
  setAssistantContent(bubble, turn.text || "");
  bubble.classList.remove("is-typing");
  row.querySelector(".typing-cursor")?.remove();
  if (!turn.text && !(turn.steps || []).length) row.remove();
  if (shouldScroll) scrollToBottom();
  return { row, stepsWrap, bubble };
}
function renderAssistantSkeleton() {
  emptyState.style.display = "none";
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.innerHTML = `<div class="bubble-wrap"><div class="assistant-label"><span class="assistant-mini-avatar">✦</span><span>Chief Personal Assistant</span></div><div class="activity-panel"><button class="activity-summary" type="button"><span class="activity-glyph">✦</span><span class="activity-label">Thinking</span><span class="activity-status">Working</span><span class="activity-chevron">⌄</span></button><div class="steps" hidden></div></div><div class="assistant-copy bubble is-typing"></div><span class="typing-cursor" aria-hidden="true"></span></div>`;
  const activity = row.querySelector(".activity-panel");
  activity.querySelector(".activity-summary").addEventListener("click", () => {
    const isHidden = activity.querySelector(".steps").hasAttribute("hidden");
    const steps = activity.querySelector(".steps");
    if (isHidden) { steps.removeAttribute("hidden"); activity.classList.add("open"); }
    else { steps.setAttribute("hidden", ""); activity.classList.remove("open"); }
  });
  messagesEl.appendChild(row);
  scrollToBottom();
  return { row, stepsWrap: row.querySelector(".steps"), bubble: row.querySelector(".bubble") };
}

function inlineMarkdown(value) {
  let html = escapeHtml(value);
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
  return html;
}
function renderAssistantMarkdown(text) {
  const source = String(text || "").replace(/\r\n/g, "\n");
  if (!source.trim()) return "";
  const blocks = source.split(/```/);
  let html = "";
  blocks.forEach((block, index) => {
    if (index % 2 === 1) {
      html += `<pre class="code-block"><code>${escapeHtml(block.replace(/^\w+\n/, ""))}</code></pre>`;
      return;
    }
    const lines = block.split("\n");
    let listType = null;
    let listItems = [];
    const flushList = () => {
      if (!listItems.length) return;
      html += `<${listType}>${listItems.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</${listType}>`;
      listType = null; listItems = [];
    };
    let paragraph = [];
    const flushParagraph = () => { if (paragraph.join(" ").trim()) html += `<p>${inlineMarkdown(paragraph.join(" "))}</p>`; paragraph = []; };
    lines.forEach((line) => {
      const trimmed = line.trim();
      const heading = trimmed.match(/^(#{1,3})\s+(.+)$/);
      const bullet = trimmed.match(/^[-*+]\s+(.+)$/);
      const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/);
      if (heading) { flushList(); flushParagraph(); html += `<h${heading[1].length}>${inlineMarkdown(heading[2])}</h${heading[1].length}>`; }
      else if (bullet || ordered) { flushParagraph(); const type = bullet ? "ul" : "ol"; if (listType && listType !== type) flushList(); listType = type; listItems.push((bullet || ordered)[1]); }
      else if (/^>\s?/.test(trimmed)) { flushList(); flushParagraph(); html += `<blockquote>${inlineMarkdown(trimmed.replace(/^>\s?/, ""))}</blockquote>`; }
      else if (!trimmed) { flushList(); flushParagraph(); }
      else { flushList(); paragraph.push(trimmed); }
    });
    flushList(); flushParagraph();
  });
  return html;
}
function setAssistantContent(bubble, text) {
  bubble.innerHTML = renderAssistantMarkdown(text);
}

function createStepEl(kind, agent, tool, input) {
  const node = stepTemplate.content.firstElementChild.cloneNode(true);
  const icon = node.querySelector(".step-icon");
  const label = node.querySelector(".step-label");
  const detail = node.querySelector(".step-detail");
  if (kind === "agent") {
    icon.textContent = "✦";
    label.textContent = `Delegating to ${AGENT_LABELS[agent] || agent || "specialist agent"}`;
  } else if (kind === "report") {
    icon.textContent = "▤";
    label.textContent = `${AGENT_LABELS[agent] || agent || "Specialist agent"} reported back`;
  } else {
    icon.textContent = "⌁";
    label.textContent = `Running ${tool || "tool"}` + (agent ? ` — ${AGENT_LABELS[agent] || agent}` : "");
  }
  if (input) detail.textContent = `Input:\n${input}`;
  node.querySelector(".step-head").addEventListener("click", () => {
    const isHidden = detail.hasAttribute("hidden");
    if (isHidden) { detail.removeAttribute("hidden"); node.classList.add("open"); }
    else { detail.setAttribute("hidden", ""); node.classList.remove("open"); }
  });
  return node;
}
function markStepDone(stepEl, output) {
  stepEl.classList.add("done");
  stepEl.querySelector(".step-status").textContent = "Done";
  if (output) {
    const detail = stepEl.querySelector(".step-detail");
    detail.textContent += `${detail.textContent ? "\n\n" : ""}Output:\n${output}`;
  }
}
function renderReportStep(stepsWrap, agent, text) {
  const stepEl = createStepEl("report", agent, null, null);
  stepsWrap.appendChild(stepEl);
  const detail = stepEl.querySelector(".step-detail");
  detail.textContent = text || "";
  // Auto-expanded: this is the sub-agent's actual answer, not just
  // telemetry, so it shouldn't be hidden behind an extra click.
  detail.removeAttribute("hidden");
  stepEl.classList.add("done", "open");
  stepEl.querySelector(".step-status").textContent = "Done";
  return stepEl;
}

suggestionCards.forEach((card) => card.addEventListener("click", () => {
  textInput.value = card.dataset.prompt || "";
  resizeComposer();
  textInput.focus();
}));

attachBtn.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  try {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Unable to upload the file");
    pendingAttachment = data;
    attachmentName.textContent = data.filename;
    attachmentChip.hidden = false;
  } catch (err) { alert(err.message); }
  fileInput.value = "";
});
removeAttachment.addEventListener("click", () => { pendingAttachment = null; attachmentChip.hidden = true; });

function resizeComposer() {
  textInput.style.height = "auto";
  textInput.style.height = Math.min(textInput.scrollHeight, 150) + "px";
}
textInput.addEventListener("input", resizeComposer);
textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
sendBtn.addEventListener("click", sendMessage);

async function ensureThread() {
  if (currentThreadId) return currentThreadId;
  const res = await fetch("/api/threads", { method: "POST" });
  const data = await res.json();
  currentThreadId = data.thread_id;
  localStorage.setItem("assistant_thread_id", currentThreadId);
  activeTranscript = [];
  return currentThreadId;
}

async function sendMessage() {
  const text = textInput.value.trim();
  if (!text || isStreaming) return;
  await ensureThread();
  const attachment = pendingAttachment;
  pendingAttachment = null;
  attachmentChip.hidden = true;
  textInput.value = "";
  resizeComposer();

  const userTurn = { role: "user", text };
  activeTranscript = [...activeTranscript, userTurn];
  saveCachedTurns(activeTranscript);
  renderUserMessage(text);
  const { row, stepsWrap, bubble } = renderAssistantSkeleton();
  const assistantTurn = { role: "assistant", text: "", steps: [] };
  activeTranscript.push(assistantTurn);
  saveCachedTurns(activeTranscript);

  const formData = new FormData();
  formData.append("thread_id", currentThreadId);
  formData.append("text", text);
  if (attachment) formData.append("attachment_path", attachment.path);
  isStreaming = true;
  sendBtn.disabled = true;

  const activeSteps = {};
  try {
    const res = await fetch("/api/chat", { method: "POST", body: formData });
    if (!res.ok || !res.body) throw new Error("The server could not respond");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        try { handleEvent(JSON.parse(line), stepsWrap, bubble, activeSteps, assistantTurn); }
        catch (err) { console.warn("Invalid stream event", err); }
        scrollToBottom();
      }
    }
    if (buffer.trim()) {
      try { handleEvent(JSON.parse(buffer), stepsWrap, bubble, activeSteps, assistantTurn); } catch { /* incomplete tail */ }
    }
  } catch (err) {
    assistantTurn.text = `Something went wrong: ${err.message}`;
    setAssistantContent(bubble, assistantTurn.text);
    bubble.classList.remove("is-typing");
  } finally {
    row.querySelector(".typing-cursor")?.remove();
    bubble.classList.remove("is-typing");
    const activityStatus = row.querySelector(".activity-status");
    if (activityStatus) activityStatus.textContent = "Complete";
    isStreaming = false;
    sendBtn.disabled = false;
    saveCachedTurns(activeTranscript);
    await syncHistoryAfterChat();
    loadThreads();
  }
}

async function syncHistoryAfterChat() {
  try {
    const res = await fetch(`/api/history?thread_id=${encodeURIComponent(currentThreadId)}`, { cache: "no-store" });
    const data = res.ok ? await res.json() : { turns: [] };
    const serverTurns = normalizeTurns(data.turns);
    // Only replace the live transcript when the server actually returned a
    // complete conversation. Otherwise the just-finished answer stays visible.
    if (serverTurns.some((turn) => turn.role === "assistant" && turn.text.trim())) {
      activeTranscript = serverTurns;
      saveCachedTurns(activeTranscript);
      renderTurns(activeTranscript);
    }
  } catch (err) { console.warn("History sync deferred", err); }
}

function handleEvent(evt, stepsWrap, bubble, activeSteps, assistantTurn) {
  if (evt.type === "heartbeat") return;
  if (evt.type === "agent_start") {
    const key = "agent:" + evt.agent;
    if (!activeSteps[key]) {
      const stepEl = createStepEl("agent", evt.agent, null, null);
      stepsWrap.appendChild(stepEl);
      activeSteps[key] = stepEl;
      assistantTurn.steps.push({ type: "agent_start", agent: evt.agent, output: "" });
      const activityPanel = stepsWrap.closest(".activity-panel");
      activityPanel?.removeAttribute("hidden");
      stepsWrap.removeAttribute("hidden");
      activityPanel?.classList.add("open");
      markStepDone(stepEl, "");
    }
  } else if (evt.type === "tool_start") {
    const key = "tool:" + evt.tool + ":" + (evt.input || "");
    const stepEl = createStepEl("tool", evt.agent, evt.tool, evt.input);
    stepsWrap.closest(".activity-panel")?.removeAttribute("hidden");
    stepsWrap.removeAttribute("hidden");
    stepsWrap.closest(".activity-panel")?.classList.add("open");
    stepsWrap.appendChild(stepEl);
    activeSteps[key] = stepEl;
    assistantTurn.steps.push({ type: "tool", agent: evt.agent, tool: evt.tool, input: evt.input || "", output: null });
  } else if (evt.type === "tool_end") {
    const steps = stepsWrap.querySelectorAll(".step:not(.done)");
    let target = null;
    steps.forEach((step) => { if (step.querySelector(".step-label").textContent.includes(evt.tool)) target = step; });
    if (target) markStepDone(target, evt.output);
    for (let i = assistantTurn.steps.length - 1; i >= 0; i--) {
      if (assistantTurn.steps[i].tool === evt.tool && assistantTurn.steps[i].output == null) { assistantTurn.steps[i].output = evt.output || ""; break; }
    }
  } else if (evt.type === "sub_agent_report") {
    renderReportStep(stepsWrap, evt.agent, evt.text || "");
    assistantTurn.steps.push({ type: "report", agent: evt.agent, output: evt.text || "" });
    const activityPanel = stepsWrap.closest(".activity-panel");
    activityPanel?.removeAttribute("hidden");
    stepsWrap.removeAttribute("hidden");
    activityPanel?.classList.add("open");
  } else if (evt.type === "token") {
    assistantTurn.text += evt.text;
    setAssistantContent(bubble, assistantTurn.text);
  } else if (evt.type === "final_answer") {
    assistantTurn.text = evt.text || "";
    setAssistantContent(bubble, assistantTurn.text);
  } else if (evt.type === "error") {
    assistantTurn.text += `${assistantTurn.text ? "\n" : ""}Warning: ${evt.message}`;
    setAssistantContent(bubble, assistantTurn.text);
  } else if (evt.type === "done") {
    stepsWrap.querySelectorAll(".step:not(.done)").forEach((step) => markStepDone(step, ""));
  }
  // Cache during streaming too, so a tab refresh during a slow response is
  // still able to recover the latest visible state.
  saveCachedTurns(activeTranscript);
}

(async function init() {
  await loadThreads();
  if (currentThreadId) {
    activeTranscript = readCachedTurns(currentThreadId);
    renderTurns(activeTranscript);
    await loadHistory();
  }
})();
