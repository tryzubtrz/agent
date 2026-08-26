"use client";

import Link from "next/link";
import { FilePlus2, FileText, Search, Trash2, Upload, X } from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type MemoryItem = {
  id?: string;
  namespace: string;
  key: string;
  value: unknown;
  updated_at?: string;
};

type StoredFile = {
  name: string;
  type: string;
  size: number;
  content: string;
  createdAt: string;
  updatedAt?: string;
  deleted?: boolean;
};

type FileEntry = MemoryItem & { value: StoredFile };

const MAX_BYTES = 200_000;
const ACCEPT = ".txt,.md,.json,.csv,.log,.xml,.yaml,.yml,text/*,application/json";

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error((await response.text()) || `Core returned ${response.status}`);
  return response.json() as Promise<T>;
}

function asFile(item: MemoryItem): FileEntry | null {
  if (item.namespace !== "files" || typeof item.value !== "object" || !item.value) return null;
  const value = item.value as Partial<StoredFile>;
  if (typeof value.name !== "string" || typeof value.content !== "string") return null;
  return { ...item, value: { name: value.name, type: value.type || "text/plain", size: Number(value.size || 0), content: value.content, createdAt: value.createdAt || "", updatedAt: value.updatedAt, deleted: Boolean(value.deleted) } };
}

export default function FilesPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<FileEntry[]>([]);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<FileEntry | null>(null);
  const [noteName, setNoteName] = useState("");
  const [noteContent, setNoteContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const raw = await core<MemoryItem[]>("/memory?namespace=files&limit=250");
      setItems(raw.map(asFile).filter((item): item is FileEntry => Boolean(item)).filter((item) => !item.value.deleted));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося завантажити файли");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((item) => item.value.name.toLowerCase().includes(needle) || item.value.content.toLowerCase().includes(needle));
  }, [items, query]);

  async function saveFile(name: string, type: string, content: string, key?: string) {
    const encodedSize = new TextEncoder().encode(content).length;
    if (encodedSize > MAX_BYTES) throw new Error("Файл завеликий для Files v1. Ліміт зараз 200 KB тексту.");
    const cleanName = name.trim() || "Нотатка.txt";
    const memoryKey = key || `file:${Date.now()}:${cleanName.replace(/[^\p{L}\p{N}._-]+/gu, "_").slice(0, 90)}`;
    const previous = items.find((item) => item.key === memoryKey)?.value;
    await core<MemoryItem>("/memory", {
      method: "PUT",
      body: JSON.stringify({
        namespace: "files",
        key: memoryKey,
        value: {
          name: cleanName,
          type: type || "text/plain",
          size: encodedSize,
          content,
          createdAt: previous?.createdAt || new Date().toISOString(),
          updatedAt: new Date().toISOString(),
          deleted: false,
        },
      }),
    });
    await refresh();
  }

  async function onUpload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    setBusy(true);
    try {
      for (const file of files) {
        if (file.size > MAX_BYTES) throw new Error(`${file.name}: більше 200 KB. Великі файли підключимо через object storage пізніше.`);
        const text = await file.text();
        await saveFile(file.name, file.type || "text/plain", text);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося завантажити файл");
    } finally {
      setBusy(false);
      event.target.value = "";
    }
  }

  async function createNote(event: FormEvent) {
    event.preventDefault();
    if (!noteContent.trim()) return;
    setBusy(true);
    try {
      const name = noteName.trim() || `Нотатка ${new Date().toLocaleDateString("uk-UA")}.md`;
      await saveFile(name, "text/markdown", noteContent);
      setNoteName("");
      setNoteContent("");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося зберегти нотатку");
    } finally { setBusy(false); }
  }

  async function remove(item: FileEntry) {
    setBusy(true);
    try {
      await core<MemoryItem>("/memory", {
        method: "PUT",
        body: JSON.stringify({ namespace: "files", key: item.key, value: { ...item.value, deleted: true, updatedAt: new Date().toISOString() } }),
      });
      if (selected?.key === item.key) setSelected(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося видалити файл");
    } finally { setBusy(false); }
  }

  return (
    <main style={shell}>
      <header style={header}>
        <Link href="/" style={back}>← ALTER</Link>
        <div><div style={eyebrow}>FILES · POSTGRES</div><h1 style={title}>Файли</h1></div>
        <button type="button" style={primary} onClick={() => inputRef.current?.click()} disabled={busy}><Upload size={16} /> Завантажити</button>
        <input ref={inputRef} type="file" multiple accept={ACCEPT} onChange={onUpload} hidden />
      </header>

      <section style={notice}>Files v1 зберігає невеликі текстові файли прямо в Neon Postgres. Ліміт — 200 KB на файл; великі фото/PDF/відео підключимо через object storage окремо.</section>
      {error && <section style={errorBox}>{error}</section>}

      <div style={searchWrap}><Search size={17} /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Пошук по назві або тексту…" style={searchInput} /></div>

      <form onSubmit={createNote} style={panel}>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}><FilePlus2 size={18} /><strong>Нова нотатка</strong></div>
        <input value={noteName} onChange={(e) => setNoteName(e.target.value)} placeholder="Назва (необовʼязково)" style={field} />
        <textarea value={noteContent} onChange={(e) => setNoteContent(e.target.value)} placeholder="Напиши текст…" rows={5} style={{ ...field, resize: "vertical" }} />
        <button disabled={busy || !noteContent.trim()} style={primary}>Зберегти</button>
      </form>

      <section style={{ display: "grid", gap: 10, marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between" }}><strong>Збережено</strong><span style={muted}>{filtered.length}</span></div>
        {filtered.length === 0 && <div style={empty}>Поки немає файлів.</div>}
        {filtered.map((item) => (
          <article key={item.key} style={panel}>
            <button type="button" onClick={() => setSelected(item)} style={fileOpen}>
              <FileText size={19} />
              <span style={{ textAlign: "left", minWidth: 0 }}><strong style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis" }}>{item.value.name}</strong><small style={muted}>{Math.ceil(item.value.size / 1024)} KB · {item.value.type}</small></span>
            </button>
            <button type="button" aria-label="Видалити" onClick={() => void remove(item)} disabled={busy} style={danger}><Trash2 size={16} /></button>
          </article>
        ))}
      </section>

      {selected && (
        <div style={overlay} onClick={() => setSelected(null)}>
          <section style={modal} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{selected.value.name}</strong><button type="button" style={icon} onClick={() => setSelected(null)}><X size={17} /></button></div>
            <pre style={preview}>{selected.value.content}</pre>
            <button type="button" style={primary} onClick={() => void navigator.clipboard?.writeText(selected.value.content)}>Скопіювати текст</button>
          </section>
        </div>
      )}
    </main>
  );
}

const shell: React.CSSProperties = { minHeight: "100dvh", maxWidth: 760, margin: "0 auto", padding: "max(18px, env(safe-area-inset-top)) 14px calc(30px + env(safe-area-inset-bottom))", color: "#f4f2ff" };
const header: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", marginBottom: 14 };
const title: React.CSSProperties = { margin: "2px 0 0", fontSize: 26 };
const eyebrow: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const back: React.CSSProperties = { color: "#b8b2d8", textDecoration: "none", fontWeight: 700 };
const panel: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.035)", borderRadius: 18, padding: 14, display: "grid", gap: 10 };
const notice: React.CSSProperties = { ...panel, color: "rgba(255,255,255,.65)", fontSize: 13, lineHeight: 1.5, marginBottom: 12 };
const errorBox: React.CSSProperties = { ...panel, borderColor: "rgba(255,100,100,.35)", color: "#ffaaa7", marginBottom: 12 };
const field: React.CSSProperties = { width: "100%", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: "11px 12px", outline: "none" };
const primary: React.CSSProperties = { border: "1px solid rgba(143,126,255,.35)", background: "rgba(111,91,255,.15)", color: "#d9d3ff", borderRadius: 12, minHeight: 40, padding: "0 12px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, fontWeight: 700 };
const danger: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", borderRadius: 12, border: "1px solid rgba(255,100,100,.25)", color: "#ffaaa7", background: "rgba(255,100,100,.06)" };
const fileOpen: React.CSSProperties = { border: 0, background: "transparent", color: "inherit", display: "grid", gridTemplateColumns: "24px 1fr", gap: 10, alignItems: "center", padding: 0 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.5)", fontSize: 12 };
const empty: React.CSSProperties = { ...panel, color: "rgba(255,255,255,.5)" };
const searchWrap: React.CSSProperties = { ...panel, display: "grid", gridTemplateColumns: "20px 1fr", alignItems: "center", marginBottom: 12 };
const searchInput: React.CSSProperties = { border: 0, outline: 0, background: "transparent", color: "#fff", minWidth: 0 };
const overlay: React.CSSProperties = { position: "fixed", inset: 0, zIndex: 90, background: "rgba(0,0,0,.65)", backdropFilter: "blur(10px)", padding: 12, display: "flex", alignItems: "flex-end", justifyContent: "center" };
const modal: React.CSSProperties = { width: "min(720px,100%)", maxHeight: "80dvh", overflow: "auto", border: "1px solid rgba(255,255,255,.12)", background: "#0b0c10", borderRadius: 22, padding: 16, display: "grid", gap: 12 };
const icon: React.CSSProperties = { width: 38, height: 38, display: "grid", placeItems: "center", border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.04)", color: "#fff", borderRadius: 12 };
const preview: React.CSSProperties = { whiteSpace: "pre-wrap", wordBreak: "break-word", fontFamily: "inherit", lineHeight: 1.55, color: "rgba(255,255,255,.78)", background: "rgba(0,0,0,.22)", borderRadius: 14, padding: 12, maxHeight: "55dvh", overflow: "auto" };
