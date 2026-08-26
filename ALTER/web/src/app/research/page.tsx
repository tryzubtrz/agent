"use client";

import { FormEvent, useState } from "react";
import ModuleShell, { field, muted, panel, primary } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Result = { url: string; content_type: string; text: string; truncated: boolean; redacted: boolean; browser_session: false };

export default function ResearchPage() {
  const [url, setUrl] = useState(""); const [result, setResult] = useState<Result | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function fetchUrl(event: FormEvent) { event.preventDefault(); if (!url.trim()) return; setBusy(true); setResult(null); try { setResult(await core<Result>("/research/fetch", { method: "POST", body: JSON.stringify({ url: url.trim() }) })); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося прочитати URL"); } finally { setBusy(false); } }
  return <ModuleShell title="Дослідження" eyebrow="PUBLIC URL READER · SSRF SAFE">
    <section style={{ ...panel, marginBottom: 12 }}><strong>Читання відкритих веб-джерел</strong><p style={muted}>ALTER може забрати текст із конкретного публічного HTTP/HTTPS URL, очистити HTML, приховати секретоподібні фрагменти та додати результат у твою роботу. Це не live Browser і не пошукова система: приватні IP/localhost заблоковані.</p></section>
    <form onSubmit={fetchUrl} style={{ ...panel, display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.com/article" inputMode="url" style={field}/><button disabled={busy || !url.trim()} style={primary}>{busy ? "Читаю…" : "Прочитати"}</button></form>
    {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
    {result && <section style={{ ...panel, marginTop: 12, display: "grid", gap: 8 }}><strong>{result.url}</strong><div style={muted}>{result.content_type || "unknown"} · {result.truncated ? "скорочено" : "повний ліміт"} · {result.redacted ? "секрети приховано" : "без redaction"}</div><pre style={preview}>{result.text}</pre></section>}
  </ModuleShell>;
}
const preview: React.CSSProperties = { whiteSpace: "pre-wrap", wordBreak: "break-word", maxHeight: "65dvh", overflow: "auto", margin: 0, padding: 12, borderRadius: 12, background: "rgba(0,0,0,.2)", color: "rgba(255,255,255,.75)", font: "inherit", fontSize: 12, lineHeight: 1.5 };
