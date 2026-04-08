(function () {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || message.type !== "grok-extension:run-item") {
      return false;
    }
    runItem(message.payload)
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error?.message || String(error) }));
    return true;
  });

  async function runItem(payload) {
    const item = payload?.item;
    const settings = payload?.settings || {};
    const references = Array.isArray(payload?.references) ? payload.references : [];
    if (!item) {
      throw new Error("실행 항목이 없습니다.");
    }

    await waitForImagineReady();
    await focusComposer();
    await clearComposer();

    if (references.length) {
      await attachReferenceImages(references);
    }

    await typePrompt(item.renderedPrompt, settings);
    const submit = findSubmitButton();
    if (!submit) {
      throw new Error("전송 화살표 버튼을 찾지 못했습니다.");
    }
    submit.click();

    await waitForGenerationToSettle();
    const opened = await openLatestResult();
    if (!opened) {
      throw new Error("결과 이미지를 열지 못했습니다.");
    }
    const fileName = `${item.tag}.png`;
    await chrome.runtime.sendMessage({
      type: "grok-extension:prepare-download-name",
      payload: {
        fileName,
        subfolder: settings.saveSubfolder || "Grok"
      }
    });
    const downloadButton = await waitForDownloadButton();
    downloadButton.click();
    await sleep(1200);
    return { savedAs: fileName };
  }

  async function waitForImagineReady(timeoutMs = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (findComposerInput()) {
        return;
      }
      await sleep(400);
    }
    throw new Error("Grok 입력창을 찾지 못했습니다.");
  }

  function findComposerInput() {
    const candidates = [...document.querySelectorAll("textarea, [contenteditable='true'], [role='textbox']")];
    const vh = window.innerHeight || 900;
    let best = null;
    let bestScore = -1;
    for (const node of candidates) {
      if (!isVisible(node)) {
        continue;
      }
      const rect = node.getBoundingClientRect();
      if (!rect.width || !rect.height) {
        continue;
      }
      let score = 0;
      if (rect.top > vh * 0.55) {
        score += 1000;
      }
      score += Math.min(rect.width, 900);
      if (rect.height >= 32) {
        score += 60;
      }
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return best;
  }

  async function focusComposer() {
    const input = findComposerInput();
    if (!input) {
      throw new Error("입력창을 찾지 못했습니다.");
    }
    input.focus();
    input.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    await sleep(120);
  }

  async function clearComposer() {
    const input = findComposerInput();
    if (!input) {
      throw new Error("입력창을 찾지 못했습니다.");
    }
    input.focus();
    document.execCommand("selectAll");
    document.execCommand("delete");
    if ("value" in input) {
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      input.textContent = "";
      input.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward", data: null }));
    }
    await sleep(180);
  }

  async function attachReferenceImages(references) {
    const plusButton = findPlusButton();
    if (!plusButton) {
      throw new Error("이미지 추가 + 버튼을 찾지 못했습니다.");
    }
    plusButton.click();
    await sleep(400);

    let fileInput = findFileInput();
    if (!fileInput) {
      await sleep(600);
      fileInput = findFileInput();
    }
    if (!fileInput) {
      throw new Error("이미지 업로드 입력칸을 찾지 못했습니다.");
    }

    const files = await Promise.all(
      references.map(async (ref) => {
        const blob = await (await fetch(ref.dataUrl)).blob();
        return new File([blob], ref.fileName || `${ref.alias}.png`, { type: ref.mimeType || blob.type || "image/png" });
      })
    );
    const transfer = new DataTransfer();
    for (const file of files) {
      transfer.items.add(file);
    }
    fileInput.files = transfer.files;
    fileInput.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(1800);
  }

  function findPlusButton() {
    const candidates = [...document.querySelectorAll("button, [role='button']")];
    const vw = window.innerWidth || 1400;
    const vh = window.innerHeight || 900;
    let best = null;
    let bestScore = -1;
    for (const node of candidates) {
      if (!isVisible(node)) {
        continue;
      }
      const rect = node.getBoundingClientRect();
      const text = (node.innerText || "").trim();
      const aria = (node.getAttribute("aria-label") || "").trim();
      let score = 0;
      if (rect.top > vh * 0.55) {
        score += 600;
      }
      if (rect.left < vw * 0.2) {
        score += 300;
      }
      if (Math.abs(rect.width - rect.height) < 18) {
        score += 120;
      }
      if (text === "+" || aria === "+") {
        score += 700;
      }
      if (/추가|add|plus/i.test(text) || /추가|add|plus/i.test(aria)) {
        score += 300;
      }
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return best;
  }

  function findFileInput() {
    const inputs = [...document.querySelectorAll("input[type='file']")];
    if (!inputs.length) {
      return null;
    }
    return inputs[inputs.length - 1];
  }

  async function typePrompt(text, settings) {
    const input = findComposerInput();
    if (!input) {
      throw new Error("입력창을 찾지 못했습니다.");
    }
    input.focus();
    const typingSpeed = Number(settings.typingSpeed || 1);
    const delay = Math.max(12, Math.round(34 / Math.max(0.5, typingSpeed)));
    const humanLike = Boolean(settings.humanLikeTyping);
    for (const ch of String(text || "")) {
      insertText(input, ch);
      await sleep(humanLike ? delay + Math.floor(Math.random() * 30) : delay);
    }
  }

  function insertText(target, text) {
    if ("value" in target) {
      const start = target.selectionStart ?? target.value.length;
      const end = target.selectionEnd ?? target.value.length;
      const before = target.value.slice(0, start);
      const after = target.value.slice(end);
      target.value = `${before}${text}${after}`;
      const next = start + text.length;
      target.selectionStart = next;
      target.selectionEnd = next;
      target.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      target.textContent = `${target.textContent || ""}${text}`;
    } else {
      selection.deleteFromDocument();
      selection.getRangeAt(0).insertNode(document.createTextNode(text));
      selection.collapseToEnd();
    }
    target.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
  }

  function findSubmitButton() {
    const nodes = [...document.querySelectorAll("button, [role='button']")];
    const vw = window.innerWidth || 1400;
    const vh = window.innerHeight || 900;
    let best = null;
    let bestScore = -1;
    for (const node of nodes) {
      if (!isVisible(node)) {
        continue;
      }
      const rect = node.getBoundingClientRect();
      const text = (node.innerText || "").trim();
      const aria = (node.getAttribute("aria-label") || "").trim();
      let score = 0;
      if (rect.top > vh * 0.55) {
        score += 900;
      }
      if (rect.left > vw * 0.75) {
        score += 700;
      }
      if (Math.abs(rect.width - rect.height) < 20) {
        score += 180;
      }
      if (/전송|send|submit|arrow/i.test(text) || /전송|send|submit|arrow/i.test(aria)) {
        score += 1000;
      }
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return best;
  }

  async function waitForGenerationToSettle(timeoutMs = 180000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const button = locateDownloadButton();
      if (button) {
        return;
      }
      await sleep(2000);
    }
    throw new Error("결과 생성이 너무 오래 걸립니다.");
  }

  async function openLatestResult() {
    const already = locateDownloadButton();
    if (already) {
      return true;
    }
    const nodes = [...document.querySelectorAll("img, video, button, [role='button']")];
    const vh = window.innerHeight || 900;
    let best = null;
    let bestScore = -1;
    for (const node of nodes) {
      if (!isVisible(node)) {
        continue;
      }
      const rect = node.getBoundingClientRect();
      if (rect.top > vh * 0.8) {
        continue;
      }
      const area = rect.width * rect.height;
      let score = area;
      if (rect.top < vh * 0.45) {
        score += 200000;
      }
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    if (!best) {
      return false;
    }
    best.click();
    await sleep(1000);
    return Boolean(locateDownloadButton());
  }

  function locateDownloadButton() {
    const nodes = [...document.querySelectorAll("button, [role='button']")];
    for (const node of nodes) {
      if (!isVisible(node)) {
        continue;
      }
      const text = (node.innerText || "").trim();
      const aria = (node.getAttribute("aria-label") || "").trim();
      if (/다운로드|download/i.test(text) || /다운로드|download/i.test(aria)) {
        return node;
      }
    }
    return null;
  }

  async function waitForDownloadButton(timeoutMs = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const button = locateDownloadButton();
      if (button) {
        return button;
      }
      await sleep(700);
    }
    throw new Error("다운로드 버튼을 찾지 못했습니다.");
  }

  function isVisible(node) {
    if (!node || !(node instanceof Element)) {
      return false;
    }
    const style = window.getComputedStyle(node);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity || 1) <= 0.05) {
      return false;
    }
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }
})();
