const chatScroll = document.getElementById("chatScroll");
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
const stepTemplate = document.getElementById("stepTemplate");

let currentThreadId = localStorage.getItem("assistant_thread_id") || null;
let pendingAttachment = null; // {path, filename}
let isStreaming = false;

// ---------------------------------------------------------------------------
// Thread sidebar
// ---------------------------------------------------------------------------
async function loadThreads() {
  const res = await fetch("/api/threads");
  const threads = await res.json();
  threadListEl.innerHTML = "";
  threads.forEach((t) => {
    const item = document.createElement("div");
    item.className = "thread-item" + (t.id === currentThreadId ? " active" : "");
    item.innerHTML = `<span class="thread-title">${escapeHtml(t.title || "নতুন কথোপকথন")}</span><span class="del" title="মুছুন">✕</span>`;
    item.querySelector(".thread-title").addEventListener("click", () => selectThread(t.id));
    item.querySelector(".del").addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/threads/${t.id}`, { method: "DELETE" });
      if (t.id === currentThreadId) {
        currentThreadId = null;
        localStorage.removeItem("assistant_thread_id");
        messagesEl.innerHTML = "";
        emptyState.style.display = "block";
      }
      loadThreads();
    });
    threadListEl.appendChild(item);
  });
}

async function selectThread(threadId) {
  currentThreadId = threadId;
  localStorage.setItem("assistant_thread_id", threadId);
  await loadThreads();
  await loadHistory();
}

newChatBtn.addEventListener("click", async () => {
  const res = await fetch("/api/threads", { method: "POST" });
  const data = await res.json();
  await selectThread(data.thread_id);
  messagesEl.innerHTML = "";
  emptyState.style.display = "block";
});

// ---------------------------------------------------------------------------
// History reload (survives page refresh)
// ---------------------------------------------------------------------------
async function loadHistory() {
  if (!currentThreadId) return;
  const res = await fetch(`/api/history?thread_id=${encodeURIComponent(currentThreadId)}`);
  const data = await res.json();
  messagesEl.innerHTML = "";
  if (!data.turns || data.turns.length === 0) {
    emptyState.style.display = "block";
    return;
  }
  emptyState.style.display = "none";
  data.turns.forEach((turn) => {
    if (turn.role === "user") {
      renderUserMessage(turn.text);
    } else {
      const { row, stepsWrap, bubble } = renderAssistantSkeleton();
      (turn.steps || []).forEach((s) => {
        const stepEl = createStepEl(s.type === "agent_start" ? "agent" : "tool", s.agent, s.tool, s.input);
        stepsWrap.appendChild(stepEl);
        markStepDone(stepEl, s.output !== undefined ? s.output : "");
      });
      bubble.textContent = turn.text || "";
      if (!turn.text) row.querySelector(".bubble-wrap").style.display = (turn.steps && turn.steps.length) ? "block" : "none";
    }
  });
  scrollToBottom();
}

// ---------------------------------------------------------------------------
// Rendering helpers
// ---------------------------------------------------------------------------
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function scrollToBottom() {
  chatScroll.scrollTop = chatScroll.scrollHeight;
}

function renderUserMessage(text) {
  emptyState.style.display = "none";
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `<div class="bubble"></div>`;
  row.querySelector(".bubble").textContent = text;
  messagesEl.appendChild(row);
  scrollToBottom();
  return row;
}

function renderAssistantSkeleton() {
  emptyState.style.display = "none";
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  row.innerHTML = `
    <div class="bubble-wrap">
      <div class="steps"></div>
      <div class="bubble" style="display:none;"></div>
    </div>`;
  messagesEl.appendChild(row);
  scrollToBottom();
  return {
    row,
    stepsWrap: row.querySelector(".steps"),
    bubble: row.querySelector(".bubble"),
  };
}

const AGENT_LABELS = {
  git_hub_agent: "GitHub Manager Agent",
  git_lab_agent: "GitLab Manager Agent",
  facebook_agent: "Facebook Manager Agent",
  youtube_agent: "YouTube Manager Agent",
};

function createStepEl(kind, agent, tool, input) {
  const node = stepTemplate.content.firstElementChild.cloneNode(true);
  const icon = node.querySelector(".step-icon");
  const label = node.querySelector(".step-label");
  const detail = node.querySelector(".step-detail");

  if (kind === "agent") {
    icon.textContent = "🤖";
    label.textContent = `${AGENT_LABELS[agent] || agent} কে কাজ দেওয়া হচ্ছে`;
  } else {
    icon.textContent = "🔧";
    label.textContent = `${tool || "tool"} চালানো হচ্ছে` + (agent ? ` — ${AGENT_LABELS[agent] || agent}` : "");
  }
  if (input) {
    detail.textContent = `▶ ইনপুট:\n${input}`;
  }

  node.querySelector(".step-head").addEventListener("click", () => {
    detail.style.display = detail.style.display === "none" ? "block" : "none";
  });
  return node;
}

function markStepDone(stepEl, output) {
  stepEl.classList.add("done");
  stepEl.querySelector(".step-status").textContent = "সম্পন্ন";
  if (output) {
    const detail = stepEl.querySelector(".step-detail");
    detail.textContent += `\n\n▶ ফলাফল:\n${output}`;
  }
}

// ---------------------------------------------------------------------------
// Attachment handling
// ---------------------------------------------------------------------------
attachBtn.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch("/api/upload", { method: "POST", body: formData });
  const data = await res.json();
  pendingAttachment = data;
  attachmentName.textContent = `📎 ${data.filename}`;
  attachmentChip.style.display = "flex";
  fileInput.value = "";
});

removeAttachment.addEventListener("click", () => {
  pendingAttachment = null;
  attachmentChip.style.display = "none";
});

// ---------------------------------------------------------------------------
// Sending messages + streaming Manus-style action timeline
// ---------------------------------------------------------------------------
textInput.addEventListener("input", () => {
  textInput.style.height = "auto";
  textInput.style.height = Math.min(textInput.scrollHeight, 160) + "px";
});

textInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener("click", sendMessage);

async function ensureThread() {
  if (currentThreadId) return currentThreadId;
  const res = await fetch("/api/threads", { method: "POST" });
  const data = await res.json();
  currentThreadId = data.thread_id;
  localStorage.setItem("assistant_thread_id", currentThreadId);
  return currentThreadId;
}

async function sendMessage() {
  const text = textInput.value.trim();
  if (!text || isStreaming) return;

  await ensureThread();

  renderUserMessage(text);
  textInput.value = "";
  textInput.style.height = "auto";

  const { stepsWrap, bubble } = renderAssistantSkeleton();
  bubble.style.display = "block";

  const attachment = pendingAttachment;
  pendingAttachment = null;
  attachmentChip.style.display = "none";

  const formData = new FormData();
  formData.append("thread_id", currentThreadId);
  formData.append("text", text);
  if (attachment) formData.append("attachment_path", attachment.path);

  isStreaming = true;
  sendBtn.disabled = true;

  const activeSteps = {}; // tool/agent key -> step element

  try {
    const res = await fetch("/api/chat", { method: "POST", body: formData });
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
        let evt;
        try {
          evt = JSON.parse(line);
        } catch {
          continue;
        }
        handleEvent(evt, stepsWrap, bubble, activeSteps);
        scrollToBottom();
      }
    }
  } catch (err) {
    bubble.textContent = "⚠️ একটি সমস্যা হয়েছে: " + err.message;
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    loadThreads();
  }
}

function handleEvent(evt, stepsWrap, bubble, activeSteps) {
  if (evt.type === "agent_start") {
    const key = "agent:" + evt.agent;
    if (!activeSteps[key]) {
      const stepEl = createStepEl("agent", evt.agent, null, null);
      stepsWrap.appendChild(stepEl);
      activeSteps[key] = stepEl;
      markStepDone(stepEl, "");
    }
  } else if (evt.type === "tool_start") {
    const key = "tool:" + evt.tool + ":" + (evt.input || "");
    const stepEl = createStepEl("tool", evt.agent, evt.tool, evt.input);
    stepsWrap.appendChild(stepEl);
    activeSteps[key] = stepEl;
  } else if (evt.type === "tool_end") {
    const key = "tool:" + evt.tool + ":";
    // find the most recent matching not-yet-done step for this tool
    const steps = stepsWrap.querySelectorAll(".step:not(.done)");
    let target = null;
    steps.forEach((s) => {
      if (s.querySelector(".step-label").textContent.includes(evt.tool)) target = s;
    });
    if (target) markStepDone(target, evt.output);
  } else if (evt.type === "token") {
    bubble.textContent += evt.text;
  } else if (evt.type === "error") {
    bubble.textContent += "\n⚠️ " + evt.message;
  } else if (evt.type === "done") {
    // finalize any steps still marked in-progress
    stepsWrap.querySelectorAll(".step:not(.done)").forEach((s) => markStepDone(s, ""));
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
(async function init() {
  await loadThreads();
  if (currentThreadId) {
    await loadHistory();
  }
})();
