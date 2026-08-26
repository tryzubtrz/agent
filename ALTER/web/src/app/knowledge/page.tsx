"use client";

import { FormEvent, useState } from "react";
import ModuleShell, { field, muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Result = { namespace: string; key: string; score: number; preview: string; updated_at?: string };
type Search = { query: string; engine: string; results: Result[] };

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Search | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function search(event: FormEvent) {
    event.preventDefault(); if (!query.trim()) return; setBusy(true);
    try { setResult(await core<Search>("/knowledge/search", { method: "POST", body: JSON.stringify({ query: query.trim(), namespaces: ["memory","files","conversation","task.meta","documents"], limit: 30 }) })); setError(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Пошук не вдався"); } finally { setBusy(false); }
  }

  return (
    <ModuleShell title="Знання" eyebrow="SEARCH · MEMORY · FILES · DOCUMENTS">
      <section style={{ ...panel, marginBottom: 12 }}><strong>Пошук по твоєму ALTER</strong><p style={muted}>Зараз працює локальний lexical engine без зовнішнього API. BGE-M3 додасть semantic/vector retrieval після появи локального runtime.</p></section>
      <form onSubmit={search} style={{ ...panel, display: "grid", gridTemplateColumns: "1fr auto", gap: 8 }}><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Що знайти?" style={field} /><button disabled={busy || !query.trim()} style={primary}>{busy ? "Шукаю…" : "Знайти"}</button></form>
      {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
      {result && <section style={{ display: "grid", gap: 9, marginTop: 14 }}><div style={muted}>Engine: {result.engine} · знайдено {result.results.length}</div>{result.results.map((item, index) => <article key={`${item.namespace}-${item.key}-${index}`} style={panel}><div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{item.namespace} / {item.key}</strong><span style={muted}>score {item.score}</span></div><pre style={preview}>{item.preview}</pre><div style={muted}>{formatDate(item.updated_at)}</div></article>)}</section>}
    </ModuleShell>
  );
}
const preview: React.CSSProperties = { whiteSpace: "pre-wrap", wordBreak: "break-word", margin: "8px 0", color: "rgba(255,255,255,.72)", font: "inherit", fontSize: 12, lineHeight: 1.5 };
