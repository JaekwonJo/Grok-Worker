(function () {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const logStep = async (message) => {
    try {
      await chrome.runtime.sendMessage({
        type: "grok-extension:log",
        payload: { message }
      });
    } catch (_) {}
  };

  void chrome.runtime.sendMessage({
    type: "grok-extension:set-zoom",
    payload: { zoomFactor: 0.8 }
  }).catch(() => {});

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
    if (!item) {
      throw new Error("실행 항목이 없습니다.");
    }

    await logStep(`${item.tag} 준비 시작`);
    await waitForImagineReady();
    await logStep(`${item.tag} 입력창 확인 완료`);
    await chrome.runtime.sendMessage({
      type: "grok-extension:set-zoom",
      payload: { zoomFactor: Number(settings.zoomFactor || 0.8) }
    }).catch(() => {});
    await focusComposer();
    await clearComposer();
    await logStep(`${item.tag} 입력창 초기화 완료`);
    if (Array.isArray(item.referenceNames) && item.referenceNames.length) {
      await logStep(`${item.tag} 레퍼런스 선택 시작 | ${item.referenceNames.join(", ")}`);
      await selectExistingReferenceImages(item.referenceNames);
      await focusComposer();
      await logStep(`${item.tag} 레퍼런스 선택 완료`);
    }

    await typePrompt(item.renderedPrompt, settings);
    await logStep(`${item.tag} 프롬프트 입력 완료`);
    const submit = findSubmitButton();
    if (!submit) {
      throw new Error("전송 화살표 버튼을 찾지 못했습니다.");
    }
    await logStep(`${item.tag} 전송 버튼 클릭`);
    submit.click();

    await waitForGenerationToSettle();
    await logStep(`${item.tag} 결과 생성 감지`);
    const opened = await openLatestResult();
    if (!opened) {
      throw new Error("결과 이미지를 열지 못했습니다.");
    }
    await logStep(`${item.tag} 결과 상세 열기 완료`);
    const fileName = `${item.tag}.png`;
    await chrome.runtime.sendMessage({
      type: "grok-extension:prepare-download-name",
      payload: {
        fileName,
        subfolder: settings.saveSubfolder || "Grok"
      }
    });
    const downloadButton = await waitForDownloadButton();
    await logStep(`${item.tag} 다운로드 버튼 클릭`);
    downloadButton.click();
    await sleep(1200);
    await logStep(`${item.tag} 다운로드 요청 완료`);
    return { savedAs: fileName };
  }

  async function waitForImagineReady(timeoutMs = 30000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      if (findComposerInput()) {
        return;
      }
      if (isLoginRequiredPage()) {
        throw new Error("로그인이 필요하거나 로그인 상태를 확인하지 못했습니다.");
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

  async function selectExistingReferenceImages(referenceNames) {
    const targets = [...new Set((referenceNames || []).map((name) => String(name || "").trim()).filter(Boolean))];
    if (!targets.length) {
      return;
    }
    const plusButton = findPlusButton();
    if (!plusButton) {
      throw new Error("이미지 추가 + 버튼을 찾지 못했습니다.");
    }
    plusButton.click();
    await sleep(500);

    const searchInput = await waitForAssetSearchInput();
    for (const alias of targets) {
      await selectSingleExistingReference(searchInput, alias);
    }
    await closeReferencePanel();
    await sleep(250);
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

  async function waitForAssetSearchInput(timeoutMs = 6000) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const input = findAssetSearchInput();
      if (input) {
        return input;
      }
      await sleep(250);
    }
    throw new Error("레퍼런스 검색창을 찾지 못했습니다.");
  }

  function findAssetSearchInput() {
    const inputs = [...document.querySelectorAll("input, textarea, [contenteditable='true'], [role='textbox']")];
    const vh = window.innerHeight || 900;
    let best = null;
    let bestScore = -1;
    for (const node of inputs) {
      if (!isVisible(node)) {
        continue;
      }
      const rect = node.getBoundingClientRect();
      const text = ((node.getAttribute?.("placeholder") || "") + " " + (node.getAttribute?.("aria-label") || "") + " " + (node.innerText || "")).trim();
      let score = 0;
      if (/검색|search|asset/i.test(text)) {
        score += 1200;
      }
      if (rect.top < vh * 0.7) {
        score += 120;
      }
      if (rect.width > 180) {
        score += 60;
      }
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return bestScore >= 1000 ? best : null;
  }

  async function selectSingleExistingReference(searchInput, alias) {
    const searchTerms = uniqueStrings([`@${alias}`, alias]);
    let selected = false;
    for (const term of searchTerms) {
      await setInputValue(searchInput, term);
      await sleep(500);
      const card = findReferenceCard(alias);
      if (card) {
        await logStep(`레퍼런스 선택 | ${alias}`);
        card.click();
        selected = true;
        await sleep(350);
        break;
      }
    }
    await setInputValue(searchInput, "");
    await sleep(180);
    if (!selected) {
      throw new Error(`미리 올린 레퍼런스 이미지 '${alias}'를 찾지 못했습니다.`);
    }
  }

  function findReferenceCard(alias) {
    const wanted = String(alias || "").trim().toLowerCase();
    const withAt = `@${wanted}`;
    const candidates = [...document.querySelectorAll("button, [role='button'], div")];
    const vh = window.innerHeight || 900;
    let best = null;
    let bestScore = -1;
    for (const node of candidates) {
      if (!isVisible(node)) {
        continue;
      }
      const rect = node.getBoundingClientRect();
      if (rect.width < 40 || rect.height < 40 || rect.top > vh * 0.85) {
        continue;
      }
      const text = (node.innerText || "").trim().toLowerCase();
      if (!text || (!text.includes(wanted) && !text.includes(withAt))) {
        continue;
      }
      let score = 0;
      if (rect.width >= 80 && rect.height >= 60) {
        score += 200;
      }
      if (rect.left < window.innerWidth * 0.7) {
        score += 80;
      }
      if (text.includes(withAt)) {
        score += 500;
      } else if (text.includes(wanted)) {
        score += 300;
      }
      if (score > bestScore) {
        best = node;
        bestScore = score;
      }
    }
    return best;
  }

  async function closeReferencePanel() {
    const composer = findComposerInput();
    if (composer) {
      composer.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      composer.focus();
      await sleep(200);
      return;
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keyup", { key: "Escape", bubbles: true }));
  }

  async function setInputValue(target, value) {
    target.focus();
    if ("value" in target) {
      target.value = value;
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.dispatchEvent(new Event("change", { bubbles: true }));
      return;
    }
    target.textContent = value;
    target.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: value }));
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
      if ((text === "" || aria === "") && rect.width <= 48 && rect.height <= 48) {
        score += 260;
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

  function uniqueStrings(values) {
    return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
  }

  function isLoginRequiredPage() {
    const text = document.body?.innerText || "";
    return /로그인|가입하기|login|sign up|sign in/i.test(text) && !findComposerInput();
  }
})();
