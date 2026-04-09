const BLOCK_SEPARATOR = "|||";
const HEADER_RE = /^\s*0*([1-9][0-9]*)\s*:\s*(.*)\s*$/;
const REF_RE = /@([A-Za-z0-9_-]+)/g;

function normalizeBody(body) {
  return String(body || "")
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+$/, ""))
    .join("\n")
    .trim();
}

function buildTag(number, prefix = "S", padWidth = 3) {
  return `${prefix}${String(number).padStart(Math.max(3, padWidth), "0")}`;
}

export function parsePromptBlocks(rawText, options = {}) {
  const prefix = options.prefix || "S";
  const padWidth = Number(options.padWidth || 3);
  const chunks = String(rawText || "")
    .split(BLOCK_SEPARATOR)
    .map((part) => part.trim())
    .filter(Boolean);

  const items = [];
  for (const chunk of chunks) {
    const lines = chunk.split(/\r?\n/);
    const firstLine = String(lines[0] || "").trim();
    let number = null;
    let body = "";

    const inline = HEADER_RE.exec(firstLine);
    if (inline) {
      number = Number(inline[1]);
      const inlineBody = String(inline[2] || "").trim();
      const restBody = lines.slice(1).join("\n").trim();
      body = normalizeBody([inlineBody, restBody].filter(Boolean).join("\n"));
    } else {
      const onlyHeader = /^\s*0*([1-9][0-9]*)\s*:\s*$/.exec(firstLine);
      if (!onlyHeader) {
        continue;
      }
      number = Number(onlyHeader[1]);
      body = normalizeBody(lines.slice(1).join("\n"));
    }
    if (!number || !body) {
      continue;
    }

    const tag = buildTag(number, prefix, padWidth);
    const referenceNames = [];
    let match;
    while ((match = REF_RE.exec(body)) !== null) {
      referenceNames.push(match[1]);
    }
    REF_RE.lastIndex = 0;

    items.push({
      number,
      tag,
      body,
      raw: chunk,
      referenceNames,
      renderedPrompt: `${tag} Prompt : ${body}`,
      cleanedBody: body.replace(REF_RE, "$1")
    });
  }

  items.sort((a, b) => a.number - b.number);
  return items;
}

export function parseManualNumbers(raw) {
  const wanted = new Set();
  for (const part of String(raw || "").replace(/\s+/g, "").split(",")) {
    if (!part) {
      continue;
    }
    if (part.includes("-")) {
      const [left, right] = part.split("-", 2);
      const lo = Number(left);
      const hi = Number(right);
      if (Number.isFinite(lo) && Number.isFinite(hi) && lo > 0 && hi > 0) {
        const start = Math.min(lo, hi);
        const end = Math.max(lo, hi);
        for (let value = start; value <= end; value += 1) {
          wanted.add(value);
        }
      }
      continue;
    }
    const value = Number(part);
    if (Number.isFinite(value) && value > 0) {
      wanted.add(value);
    }
  }
  return [...wanted].sort((a, b) => a - b);
}

export function filterPromptBlocks(items, settings) {
  const mode = settings.numberMode || "range";
  if (mode === "manual") {
    const wanted = new Set(parseManualNumbers(settings.manualNumbers || ""));
    return items.filter((item) => wanted.has(item.number));
  }
  const start = Number(settings.startNumber || 1);
  const end = Number(settings.endNumber || start || 1);
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  return items.filter((item) => item.number >= lo && item.number <= hi);
}

export function summarizeSelection(items) {
  if (!items.length) {
    return "선택된 작업 없음";
  }
  const preview = items.slice(0, 8).map((item) => item.tag).join(", ");
  if (items.length > 8) {
    return `${items.length}개 선택: ${preview} 외 ${items.length - 8}개`;
  }
  return `${items.length}개 선택: ${preview}`;
}

export function compressNumbers(numbers, prefix = "S") {
  const unique = [...new Set(numbers.map((value) => Number(value)).filter((value) => Number.isFinite(value) && value > 0))].sort((a, b) => a - b);
  if (!unique.length) {
    return "";
  }
  const parts = [];
  let start = unique[0];
  let prev = unique[0];
  for (const value of unique.slice(1)) {
    if (value === prev + 1) {
      prev = value;
      continue;
    }
    parts.push(formatRange(start, prev, prefix));
    start = prev = value;
  }
  parts.push(formatRange(start, prev, prefix));
  return parts.join(",");
}

function formatRange(start, end, prefix) {
  const left = `${prefix}${String(start).padStart(3, "0")}`;
  const right = `${prefix}${String(end).padStart(3, "0")}`;
  return start === end ? left : `${left}-${right}`;
}
