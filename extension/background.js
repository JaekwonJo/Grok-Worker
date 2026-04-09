const SETTINGS_KEY = "grokWorkerExtensionSettings";
const RUN_STATE_KEY = "grokWorkerExtensionRunState";

let currentSession = null;
let pendingDownload = null;
const zoomStateByTab = new Map();

chrome.runtime.onInstalled.addListener(async () => {
  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  } catch (error) {
    console.warn("sidePanel init failed", error);
  }
  const stored = await chrome.storage.local.get([SETTINGS_KEY, RUN_STATE_KEY]);
  if (!stored[SETTINGS_KEY]) {
    await chrome.storage.local.set({
      [SETTINGS_KEY]: defaultSettings()
    });
  }
  if (!stored[RUN_STATE_KEY]) {
    await chrome.storage.local.set({
      [RUN_STATE_KEY]: emptyRunState()
    });
  }
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || typeof message !== "object") {
    return false;
  }
  if (message.type === "grok-extension:start-run") {
    startRun(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
  if (message.type === "grok-extension:stop-run") {
    stopRun().then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
  if (message.type === "grok-extension:prepare-download-name") {
    pendingDownload = {
      fileName: message.payload?.fileName || "",
      subfolder: message.payload?.subfolder || "",
      createdAt: Date.now()
    };
    sendResponse({ ok: true });
    return false;
  }
  if (message.type === "grok-extension:set-zoom") {
    setTabZoom(message.payload, sender)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
  if (message.type === "grok-extension:restore-zoom") {
    restoreTabZoom(message.payload, sender)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  }
  if (message.type === "grok-extension:get-run-state") {
    chrome.storage.local.get([RUN_STATE_KEY]).then((stored) => {
      sendResponse({ ok: true, state: stored[RUN_STATE_KEY] || emptyRunState() });
    });
    return true;
  }
  return false;
});

chrome.downloads.onDeterminingFilename.addListener((item, suggest) => {
  if (!pendingDownload) {
    suggest();
    return;
  }
  const ageMs = Date.now() - Number(pendingDownload.createdAt || 0);
  if (ageMs > 30000) {
    pendingDownload = null;
    suggest();
    return;
  }
  const targetName = sanitizeRelativePath(
    `${pendingDownload.subfolder ? `${pendingDownload.subfolder}/` : ""}${pendingDownload.fileName}`
  );
  pendingDownload = null;
  if (!targetName) {
    suggest();
    return;
  }
  suggest({ filename: targetName, conflictAction: "uniquify" });
});

async function startRun(payload) {
  if (currentSession?.running) {
    throw new Error("이미 실행 중입니다.");
  }
  const tabId = await resolveTargetTab(payload?.tabId);
  const settings = payload?.settings || defaultSettings();
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) {
    throw new Error("실행할 프롬프트가 없습니다.");
  }

  currentSession = {
    running: true,
    stopRequested: false,
    tabId,
    settings,
    items
  };

  await ensureZoomForRun(tabId, settings);

  const initialState = {
    running: true,
    currentTag: "",
    progressCurrent: 0,
    progressTotal: items.length,
    successCount: 0,
    failedCount: 0,
    failedNumbers: [],
    queue: items.map((item) => ({
      number: item.number,
      tag: item.tag,
      status: "pending",
      message: ""
    }))
  };
  await setRunState(initialState);

  for (let index = 0; index < items.length; index += 1) {
    if (!currentSession || currentSession.stopRequested) {
      break;
    }
    const item = items[index];
    await patchRunState((state) => {
      state.currentTag = item.tag;
      state.progressCurrent = index;
      const row = state.queue.find((entry) => entry.number === item.number);
      if (row) {
        row.status = "running";
        row.message = `${item.tag} 실행 중`;
      }
      return state;
    });

    try {
      const response = await chrome.tabs.sendMessage(tabId, {
        type: "grok-extension:run-item",
        payload: {
          item,
          settings
        }
      });
      if (!response?.ok) {
        throw new Error(response?.error || "알 수 없는 실행 오류");
      }
      await patchRunState((state) => {
        state.progressCurrent = index + 1;
        state.successCount += 1;
        const row = state.queue.find((entry) => entry.number === item.number);
        if (row) {
          row.status = "success";
          row.message = response.result?.savedAs ? `저장: ${response.result.savedAs}` : "성공";
        }
        return state;
      });
    } catch (error) {
      await patchRunState((state) => {
        state.progressCurrent = index + 1;
        state.failedCount += 1;
        state.failedNumbers.push(item.number);
        const row = state.queue.find((entry) => entry.number === item.number);
        if (row) {
          row.status = "failed";
          row.message = error?.message || String(error);
        }
        return state;
      });
    }
  }

  await patchRunState((state) => {
    state.running = false;
    state.currentTag = "";
    return state;
  });
  currentSession = null;
  return { ok: true };
}

async function stopRun() {
  if (currentSession) {
    currentSession.stopRequested = true;
    await restoreZoomForTab(currentSession.tabId);
  }
  await patchRunState((state) => {
    state.running = false;
    state.currentTag = "";
    return state;
  });
}

async function resolveTargetTab(explicitTabId) {
  if (Number.isInteger(explicitTabId)) {
    return explicitTabId;
  }
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const active = tabs.find((tab) => /^https:\/\/grok\.com\//.test(tab.url || ""));
  if (!active?.id) {
    throw new Error("현재 창의 활성 탭이 grok.com 페이지가 아닙니다.");
  }
  return active.id;
}

function defaultSettings() {
  return {
    saveSubfolder: "Grok",
    promptText: "",
    numberMode: "range",
    startNumber: 1,
    endNumber: 1,
    manualNumbers: "",
    typingSpeed: 1,
    humanLikeTyping: true
  };
}

function emptyRunState() {
  return {
    running: false,
    currentTag: "",
    progressCurrent: 0,
    progressTotal: 0,
    successCount: 0,
    failedCount: 0,
    failedNumbers: [],
    queue: []
  };
}

async function setRunState(state) {
  await chrome.storage.local.set({
    [RUN_STATE_KEY]: state
  });
}

async function ensureZoomForRun(tabId, settings) {
  const zoomFactor = Number(settings.zoomFactor || 0.8);
  if (!tabId || !Number.isFinite(zoomFactor) || zoomFactor <= 0) {
    return;
  }
  try {
    if (!zoomStateByTab.has(tabId)) {
      const currentZoom = await chrome.tabs.getZoom(tabId);
      zoomStateByTab.set(tabId, currentZoom);
    }
    await chrome.tabs.setZoom(tabId, zoomFactor);
  } catch (error) {
    console.warn("setZoom failed", error);
  }
}

async function setTabZoom(payload, sender) {
  const tabId = Number(payload?.tabId || sender?.tab?.id || 0);
  const zoomFactor = Number(payload?.zoomFactor || 0.8);
  if (!tabId) {
    throw new Error("탭 ID가 없습니다.");
  }
  if (!Number.isFinite(zoomFactor) || zoomFactor <= 0) {
    throw new Error("잘못된 줌 값입니다.");
  }
  if (!zoomStateByTab.has(tabId)) {
    const currentZoom = await chrome.tabs.getZoom(tabId);
    zoomStateByTab.set(tabId, currentZoom);
  }
  await chrome.tabs.setZoom(tabId, zoomFactor);
  return { tabId, zoomFactor };
}

async function restoreTabZoom(payload, sender) {
  const tabId = Number(payload?.tabId || sender?.tab?.id || 0);
  if (!tabId) {
    throw new Error("탭 ID가 없습니다.");
  }
  await restoreZoomForTab(tabId);
  return { tabId };
}

async function restoreZoomForTab(tabId) {
  if (!zoomStateByTab.has(tabId)) {
    return;
  }
  const previous = zoomStateByTab.get(tabId);
  zoomStateByTab.delete(tabId);
  try {
    await chrome.tabs.setZoom(tabId, previous);
  } catch (error) {
    console.warn("restore zoom failed", error);
  }
}

async function patchRunState(mutator) {
  const stored = await chrome.storage.local.get([RUN_STATE_KEY]);
  const state = structuredClone(stored[RUN_STATE_KEY] || emptyRunState());
  const next = mutator(state) || state;
  await setRunState(next);
}

function sanitizeRelativePath(raw) {
  return String(raw || "")
    .replace(/^[\\/]+/, "")
    .replace(/[<>:"|?*\u0000-\u001F]/g, "_")
    .replace(/\\/g, "/")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean)
    .join("/");
}
