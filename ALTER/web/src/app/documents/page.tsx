"use client";

import { ChangeEvent, useRef, useState } from "react";
import ModuleShell, { muted, panel, primary } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Parsed = { filename: string; kind: string; sha256: string; bytes: number; text: string; truncated: boolean; redacted: boolean; metadata: Record<string, unknown>; saved: boolean; document_id?: string };

function toBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error);
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.readAsDataURL(file);
  });
}

export default function DocumentsPage() {
  const input = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<Parsed | null>(null);
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]; if (!file) return;
    setBusy(true); setResult(null); setError(""); setProgress("Перевіряю файл…");
    try {
      if (file.size > 4_000_000) throw new Error("Зараз ліміт парсера — 4 MB на файл.");
      if (file.type.startsWith("image/")) {
        setProgress("OCR запускається локально у браузері…");
        const Tesseract = await import("tesseract.js");
        let recognized;
        try { recognized = await Tesseract.recognize(file, "ukr+eng", { logger: (m) => m.status && setProgress(`${m.status}${typeof m.progress === 'number' ? ` ${Math.round(m.progress * 100)}%` : ''}`) }); }
        catch { recognized = await Tesseract.recognize(file, "eng"); }
        const text = recognized.data.text.trim();
        const id = `ocr:${Date.now()}`;
        await core("/memory", { method: "PUT", body: JSON.stringify({ namespace: "documents", key: id, value: { id, filename: file.name, kind: "image-ocr", text, engine: "tesseract.js", created_at: new Date().toISOString() } }) });
        setResult({ filename: file.name, kind: "image-ocr", sha256: "client-side", bytes: file.size, text, truncated: false, redacted: false, metadata: { parser: "tesseract.js", language: "ukr+eng fallback eng" }, saved: true, document_id: id });
      } else {
        setProgress("Парсю у захищеному Core…");
        const content_base64 = await toBase64(file);
        const parsed = await core<Parsed>("/documents/extract", { method: "POST", body: JSON.stringify({ filename: file.name, content_base64, kind: "auto", save_to_knowledge: !file.name.toLowerCase().endsWith('.zip') }) });
        setResult(parsed);
      }
      setProgress("");
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося обробити файл"); setProgress(""); }
    finally { setBusy(false); event.target.value = ""; }
  }

  return (
    <ModuleShell title="Документи та OCR" eyebrow="PDF · DOCX · XLSX · CSV · ZIP · IMAGE OCR" action={<button onClick={() => input.current?.click()} disabled={busy} style={primary}>+ Файл</button>}>
      <input ref={input} type="file" hidden onChange={onFile} accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.json,.zip,image/*" />
      <section style={{ ...panel, display: "grid", gap: 7 }}><strong>Реальна обробка документів</strong><div style={muted}>PDF з текстовим шаром, DOCX, XLSX, CSV і текст обробляє Core. ZIP лише інспектується — нічого з архіву не запускається. Фото проходять OCR локально у браузері через Tesseract.js.</div></section>
      {progress && <section style={{ ...panel, marginTop: 12, color: "#c9c2ff" }}>{progress}</section>}
      {error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}
      {result && <section style={{ ...panel, marginTop: 12, display: "grid", gap: 8 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{result.filename}</strong><span style={badge}>{result.kind}</span></div><div style={muted}>{Math.ceil(result.bytes / 1024)} KB · {result.saved ? "збережено в Knowledge" : "не збережено"} · {result.redacted ? "секретні фрагменти приховано" : "без redaction"}</div><pre style={preview}>{result.text || "Текст не знайдено."}</pre><details><summary style={{ color: "#b8b2d8" }}>Метадані</summary><pre style={preview}>{JSON.stringify(result.metadata, null, 2)}</pre></details></section>}
    </ModuleShell>
  );
}
const badge: React.CSSProperties = { border: "1px solid rgba(143,126,255,.25)", borderRadius: 999, padding: "5px 8px", color: "#c9c2ff", fontSize: 10 };
const preview: React.CSSProperties = { whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: "56dvh", overflow: "auto", margin: 0, padding: 12, borderRadius: 12, background: "rgba(0,0,0,.2)", color: "rgba(255,255,255,.75)", font: "inherit", fontSize: 12, lineHeight: 1.5 };
