const DB_NAME = "grok-worker-extension";
const DB_VERSION = 1;
const STORE_NAME = "reference-images";

function openDb() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "id" });
        store.createIndex("by_alias", "aliasLower", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function withStore(mode, callback) {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    let result;
    try {
      result = callback(store, tx);
    } catch (error) {
      reject(error);
      return;
    }
    tx.oncomplete = () => resolve(result);
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

export async function listReferenceImages() {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const store = tx.objectStore(STORE_NAME);
    const request = store.getAll();
    request.onsuccess = () => {
      const items = (request.result || []).sort((a, b) => {
        const left = String(a.alias || "").localeCompare(String(b.alias || ""), "ko");
        if (left !== 0) {
          return left;
        }
        return Number(a.createdAt || 0) - Number(b.createdAt || 0);
      });
      resolve(items);
    };
    request.onerror = () => reject(request.error);
  });
}

export async function getReferenceByAlias(alias) {
  const aliasLower = String(alias || "").trim().toLowerCase();
  if (!aliasLower) {
    return null;
  }
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const index = tx.objectStore(STORE_NAME).index("by_alias");
    const request = index.get(aliasLower);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

export async function putReferenceImage(item) {
  const payload = {
    id: item.id || crypto.randomUUID(),
    alias: String(item.alias || "").trim(),
    aliasLower: String(item.alias || "").trim().toLowerCase(),
    fileName: String(item.fileName || "").trim(),
    mimeType: String(item.mimeType || "image/png"),
    dataUrl: String(item.dataUrl || ""),
    createdAt: Number(item.createdAt || Date.now())
  };
  await withStore("readwrite", (store) => store.put(payload));
  return payload;
}

export async function deleteReferenceImage(id) {
  await withStore("readwrite", (store) => store.delete(id));
}
