import { compressNumbers, filterPromptBlocks, parsePromptBlocks, summarizeSelection } from "./lib/prompt-parser.js";
import { deleteReferenceImage, listReferenceImages, putReferenceImage } from "./lib/ref-db.js";

const SETTINGS_KEY = "grokWorkerExtensionSettings";
const RUN_STATE_KEY = "grokWorkerExtensionRunState";

const els = {};

document.addEventListener("DOMContentLoaded", async () => {
  bindElements();
  bindEvents();
  await loadSettings();
  await renderReferences();
  await refreshRunState();
  chrome.storage.onChanged.addListener(handleStorageChanged);
});

function bindElements() {
  for (const id of [
    "runBadge",
    "saveSubfolderInput",
    "typingSpeedInput",
    "typingSpeedValue",
    "zoomFactorSelect",
    "humanLikeTypingInput",
    "referenceUploadInput",
    "referenceList",
    "startNumberInput",
    "endNumberInput",
    "manualNumbersInput",
    "promptTextInput",
    "promptFileInput",
    "startBtn",
    "stopBtn",
    "saveSettingsBtn",
    "summaryBar",
    "queueList",
    "copyFailedBtn",
    "logList"
  ]) {
    els[id] = document.getElementById(id);
  }
}

function bindEvents() {
  els.typingSpeedInput.addEventListener("input", () => {
    els.typingSpeedValue.textContent = Number(els.typingSpeedInput.value).toFixed(1);
    void saveSettings();
  });
  els.saveSubfolderInput.addEventListener("change", () => void saveSettings());
  els.humanLikeTypingInput.addEventListener("change", () => void saveSettings());
  els.zoomFactorSelect.addEventListener("change", () => void saveSettings());
  document.querySelectorAll("input[name='numberMode']").forEach((node) => {
    node.addEventListener("change", () => void saveSettings());
  });
  els.startNumberInput.addEventListener("change", () => void saveSettings());
  els.endNumberInput.addEventListener("change", () => void saveSettings());
  els.manualNumbersInput.addEventListener("change", () => void saveSettings());
  els.promptTextInput.addEventListener("change", () => void saveSettings());
  els.saveSettingsBtn.addEventListener("click", () => void saveSettings(true));
  els.referenceUploadInput.addEventListener("change", (event) => void handleReferenceUpload(event));
  els.promptFileInput.addEventListener("change", (event) => void handlePromptFileUpload(event));
  els.startBtn.addEventListener("click", () => void startRun());
  els.stopBtn.addEventListener("click", () => void stopRun());
  els.copyFailedBtn.addEventListener("click", () => void copyFailedNumbers());
}

async function loadSettings() {
  const stored = await chrome.storage.local.get([SETTINGS_KEY]);
  const settings = {
    saveSubfolder: "Grok",
    promptText: "",
    numberMode: "range",
    startNumber: 1,
    endNumber: 1,
    manualNumbers: "",
    zoomFactor: 0.8,
    typingSpeed: 1,
    humanLikeTyping: true,
    ...(stored[SETTINGS_KEY] || {})
  };
  els.saveSubfolderInput.value = settings.saveSubfolder || "Grok";
  els.typingSpeedInput.value = String(settings.typingSpeed || 1);
  els.typingSpeedValue.textContent = Number(settings.typingSpeed || 1).toFixed(1);
  els.zoomFactorSelect.value = String(settings.zoomFactor || 0.8);
  els.humanLikeTypingInput.checked = Boolean(settings.humanLikeTyping);
  document.querySelector(`input[name='numberMode'][value='${settings.numberMode || "range"}']`).checked = true;
  els.startNumberInput.value = String(settings.startNumber || 1);
  els.endNumberInput.value = String(settings.endNumber || 1);
  els.manualNumbersInput.value = settings.manualNumbers || "";
  els.promptTextInput.value = settings.promptText || "";
}

function currentSettings() {
  const modeNode = document.querySelector("input[name='numberMode']:checked");
  return {
    saveSubfolder: els.saveSubfolderInput.value.trim() || "Grok",
    promptText: els.promptTextInput.value,
    numberMode: modeNode?.value || "range",
    startNumber: Number(els.startNumberInput.value || 1),
    endNumber: Number(els.endNumberInput.value || 1),
    manualNumbers: els.manualNumbersInput.value.trim(),
    zoomFactor: Number(els.zoomFactorSelect.value || 0.8),
    typingSpeed: Number(els.typingSpeedInput.value || 1),
    humanLikeTyping: Boolean(els.humanLikeTypingInput.checked)
  };
}

async function saveSettings(showToast = false) {
  await chrome.storage.local.set({
    [SETTINGS_KEY]: currentSettings()
  });
  if (showToast) {
    els.runBadge.textContent = "저장됨";
    els.runBadge.className = "badge idle";
    window.setTimeout(() => {
      els.runBadge.textContent = "준비 완료";
    }, 1500);
  }
}

async function handleReferenceUpload(event) {
  const files = [...(event.target.files || [])];
  if (!files.length) {
    return;
  }
  for (const file of files) {
    const dataUrl = await readFileAsDataUrl(file);
    const alias = inferAliasFromFile(file.name);
    await putReferenceImage({
      alias,
      fileName: file.name,
      mimeType: file.type,
      dataUrl
    });
  }
  event.target.value = "";
  await renderReferences();
}

async function renderReferences() {
  const refs = await listReferenceImages();
  els.referenceList.innerHTML = "";
  if (!refs.length) {
    els.referenceList.innerHTML = `<div class="queue-card pending"><strong>아직 이미지가 없습니다</strong><p>위의 '이미지 추가'로 캐릭터 이미지를 넣어주세요.</p></div>`;
    return;
  }
  for (const ref of refs) {
    const card = document.createElement("div");
    card.className = "ref-card";
    card.innerHTML = `
      <img src="${ref.dataUrl}" alt="${escapeHtml(ref.alias)}" />
      <input class="ref-alias" type="text" value="${escapeHtml(ref.alias)}" />
      <div class="ref-actions">
        <button class="mini-btn save-alias">이름 저장</button>
        <button class="mini-btn delete-ref">삭제</button>
      </div>
    `;
    card.querySelector(".save-alias").addEventListener("click", async () => {
      const nextAlias = card.querySelector(".ref-alias").value.trim();
      if (!nextAlias) {
        return;
      }
      await putReferenceImage({
        ...ref,
        alias: nextAlias
      });
      await renderReferences();
    });
    card.querySelector(".delete-ref").addEventListener("click", async () => {
      await deleteReferenceImage(ref.id);
      await renderReferences();
    });
    els.referenceList.appendChild(card);
  }
}

async function handlePromptFileUpload(event) {
  const file = event.target.files?.[0];
  if (!file) {
    return;
  }
  const text = await file.text();
  els.promptTextInput.value = text;
  event.target.value = "";
  await saveSettings();
}

async function startRun() {
  const settings = currentSettings();
  const parsed = parsePromptBlocks(settings.promptText || "");
  const items = filterPromptBlocks(parsed, settings);
  if (!items.length) {
    els.runBadge.textContent = "프롬프트 없음";
    return;
  }
  await saveSettings();
  els.runBadge.textContent = "실행 중";
  els.runBadge.className = "badge running";
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const response = await chrome.runtime.sendMessage({
    type: "grok-extension:start-run",
    payload: {
      tabId: tab?.id,
      settings,
      items
    }
  });
  if (!response?.ok) {
    els.runBadge.textContent = "실패";
    alert(response?.error || "실행을 시작하지 못했습니다.");
    return;
  }
  await refreshRunState();
}

async function stopRun() {
  await chrome.runtime.sendMessage({ type: "grok-extension:stop-run" });
  await refreshRunState();
}

async function refreshRunState() {
  const stored = await chrome.storage.local.get([RUN_STATE_KEY]);
  renderRunState(stored[RUN_STATE_KEY] || {
    running: false,
    currentTag: "",
    progressCurrent: 0,
    progressTotal: 0,
    successCount: 0,
    failedCount: 0,
    failedNumbers: [],
    queue: [],
    logs: []
  });
}

function renderRunState(state) {
  els.runBadge.textContent = state.running ? (state.currentTag ? `${state.currentTag} 실행 중` : "실행 중") : "준비 완료";
  els.runBadge.className = `badge ${state.running ? "running" : "idle"}`;
  els.summaryBar.textContent = `활성 ${state.running ? 1 : 0}개 | 완료 ${state.successCount || 0} | 실패 ${state.failedCount || 0} | 대기 ${Math.max(0, (state.progressTotal || 0) - (state.progressCurrent || 0) - (state.running ? 1 : 0))}`;
  els.queueList.innerHTML = "";
  const queue = Array.isArray(state.queue) ? state.queue : [];
  const logs = Array.isArray(state.logs) ? state.logs : [];
  if (!queue.length) {
    els.queueList.innerHTML = `<div class="queue-card pending"><strong>대기열 없음</strong><p>프롬프트를 넣고 시작을 누르면 여기 보입니다.</p></div>`;
  } else {
    for (const row of queue) {
      const card = document.createElement("div");
      card.className = `queue-card ${row.status || "pending"}`;
      card.innerHTML = `<strong>${escapeHtml(row.tag || String(row.number))}</strong><p>${escapeHtml(row.message || statusLabel(row.status))}</p>`;
      els.queueList.appendChild(card);
    }
  }

  els.logList.innerHTML = "";
  if (!logs.length) {
    els.logList.innerHTML = `<div class="queue-card pending"><strong>로그 없음</strong><p>실행을 시작하면 단계별 로그가 여기에 보입니다.</p></div>`;
    return;
  }
  for (const row of logs.slice().reverse()) {
    const item = document.createElement("div");
    item.className = "log-row";
    item.innerHTML = `<span class="time">${escapeHtml(row.time || "")}</span><span class="msg">${escapeHtml(row.message || "")}</span>`;
    els.logList.appendChild(item);
  }
}

async function copyFailedNumbers() {
  const stored = await chrome.storage.local.get([RUN_STATE_KEY]);
  const state = stored[RUN_STATE_KEY];
  const text = compressNumbers((state?.failedNumbers || []), "S");
  if (!text) {
    return;
  }
  await navigator.clipboard.writeText(text);
  els.runBadge.textContent = "복사됨";
  window.setTimeout(() => {
    els.runBadge.textContent = state?.running ? "실행 중" : "준비 완료";
  }, 1500);
}

function handleStorageChanged(changes, areaName) {
  if (areaName !== "local") {
    return;
  }
  if (changes[RUN_STATE_KEY]) {
    renderRunState(changes[RUN_STATE_KEY].newValue || {});
  }
}

function statusLabel(status) {
  switch (status) {
    case "running":
      return "실행 중";
    case "success":
      return "성공";
    case "failed":
      return "실패";
    default:
      return "대기 중";
  }
}

function inferAliasFromFile(name) {
  return String(name || "").replace(/\.[^.]+$/, "").trim() || "S999";
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
