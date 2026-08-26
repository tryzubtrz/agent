"use client";

import { useEffect, useState } from "react";
import ModuleShell, { muted, panel } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Entry = { id: string; name: string; kind: string; status: string; risk: string; permissions: string[]; rollback: string };
type Market = { entries: Entry[]; policy: string; arbitrary_remote_install: boolean; excluded_now: string[] };

export default function MarketPage() {
  const [data, setData] = useState<Market | null>(null); const [error, setError] = useState("");
  useEffect(() => { core<Market>("/market").then(setData).catch((err) => setError(err instanceof Error ? err.message : "Не вдалося відкрити Market")); }, []);
  return <ModuleShell title="Market" eyebrow="VERIFIED SKILLS · MODELS · CONNECTORS">
    <section style={{ ...panel, marginBottom: 12 }}><strong>Безпечний каталог ALTER</strong><p style={muted}>Market не встановлює випадковий код з інтернету. Для кожного модуля видно стан, permissions, risk і rollback. Довільний remote install вимкнено.</p></section>
    {error && <section style={{ ...panel, color: "#ffaaa7" }}>{error}</section>}
    <section style={{ display: "grid", gap: 9 }}>{data?.entries.map((entry) => <article key={entry.id} style={panel}><div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{entry.name}</strong><span style={badge}>{entry.status}</span></div><div style={{ ...muted, marginTop: 6 }}>{entry.kind} · risk: {entry.risk} · rollback: {entry.rollback}</div><div style={{ ...muted, marginTop: 4 }}>Permissions: {entry.permissions.join(', ') || 'none'}</div></article>)}</section>
    {data && <section style={{ ...panel, marginTop: 12 }}><div style={muted}>Policy: {data.policy}</div><div style={muted}>Відкладено за твоїм рішенням: {data.excluded_now.join(', ')}</div></section>}
  </ModuleShell>;
}
const badge: React.CSSProperties = { border: "1px solid rgba(143,126,255,.25)", borderRadius: 999, padding: "5px 8px", color: "#c9c2ff", fontSize: 10 };
