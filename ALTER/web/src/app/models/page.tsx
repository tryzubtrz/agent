"use client";

import Link from "next/link";
import { Brain, CheckCircle2, Route, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Model = {
  id: string;
  provider: string;
  display_name: string;
  capabilities: string[];
  configured: boolean;
  credential_configured: boolean;
  action: string;
  side_effects: boolean;
  policy_boundary: string;
};

type Routed = { selected: string; provider: string; purpose: string; mode: string; reason: string };

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error((await response.text()) || `Core returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default function ModelsPage() {
  const [models, setModels] = useState<Model[]>([]);
  const [purpose, setPurpose] = useState("reasoning");
  const [mode, setMode] = useState("normal");
  const [routed, setRouted] = useState<Routed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try { setModels(await core<Model[]>("/models")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити registry"); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function testRoute() {
    setBusy(true); setRouted(null);
    try {
      const result = await core<Routed>("/models/route", { method: "POST", body: JSON.stringify({ purpose, mode }) });
      setRouted(result); setError(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Немає доступної моделі"); }
    finally { setBusy(false); }
  }

  return (
    <main style={shell}>
      <header style={header}><Link href="/" style={back}>← ALTER</Link><div><div style={eyebrow}>MODEL ROUTER · LIVE</div><h1 style={title}>Моделі</h1></div><Brain size={25} /></header>

      <section style={panel}>
        <strong>Чесний production registry</strong>
        <p style={muted}>ALTER показує лише реально підключені провайдери. Демонстраційних назв моделей тут немає.</p>
      </section>

      {error && <section style={errorBox}>{error}</section>}

      <section style={{ display: "grid", gap: 10, marginTop: 12 }}>
        {models.map((model) => (
          <article key={model.id} style={panel}>
            <div style={{ display: "grid", gridTemplateColumns: "42px 1fr auto", gap: 10, alignItems: "center" }}>
              <div style={icon}><Brain size={20} /></div>
              <div><strong>{model.display_name}</strong><div style={muted}>{model.provider} · {model.action}</div></div>
              <span style={{ ...badge, ...(model.configured ? good : missing) }}>{model.configured ? <><CheckCircle2 size={12} /> Ready</> : <><XCircle size={12} /> Waiting</>}</span>
            </div>
            <div style={chips}>{model.capabilities.map((cap) => <span key={cap} style={chip}>{cap}</span>)}</div>
            <div style={{ ...muted, marginTop: 10 }}>Side effects: {model.side_effects ? "можливі" : "ні"} · Boundary: {model.policy_boundary}</div>
          </article>
        ))}
      </section>

      <section style={{ ...panel, marginTop: 14, display: "grid", gap: 10 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Route size={18} /><strong>Перевірити маршрутизацію</strong></div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <select value={purpose} onChange={(e) => setPurpose(e.target.value)} style={field}>
            <option value="chat">chat</option><option value="reasoning">reasoning</option><option value="planning">planning</option><option value="summarization">summarization</option><option value="coding">coding</option>
          </select>
          <select value={mode} onChange={(e) => setMode(e.target.value)} style={field}>
            <option value="quick">quick</option><option value="normal">normal</option><option value="deep">deep</option><option value="plan">plan</option>
          </select>
        </div>
        <button type="button" onClick={() => void testRoute()} disabled={busy} style={primary}>Вибрати модель</button>
        {routed && <div style={result}><strong>{routed.selected}</strong><div style={muted}>{routed.reason}</div></div>}
      </section>
    </main>
  );
}

const shell: React.CSSProperties = { minHeight: "100dvh", maxWidth: 760, margin: "0 auto", padding: "max(18px, env(safe-area-inset-top)) 14px calc(30px + env(safe-area-inset-bottom))", color: "#f4f2ff" };
const header: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", marginBottom: 14 };
const back: React.CSSProperties = { color: "#b8b2d8", textDecoration: "none", fontWeight: 700 };
const title: React.CSSProperties = { margin: "2px 0 0", fontSize: 26 };
const eyebrow: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const panel: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.035)", borderRadius: 18, padding: 14 };
const errorBox: React.CSSProperties = { ...panel, borderColor: "rgba(255,100,100,.35)", color: "#ffaaa7", marginTop: 12 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 12, lineHeight: 1.5, margin: "4px 0 0" };
const icon: React.CSSProperties = { width: 42, height: 42, display: "grid", placeItems: "center", borderRadius: 13, background: "rgba(118,102,255,.1)", color: "#aaa1ff" };
const badge: React.CSSProperties = { borderRadius: 999, padding: "6px 9px", fontSize: 11, display: "inline-flex", gap: 5, alignItems: "center", whiteSpace: "nowrap" };
const good: React.CSSProperties = { color: "#9af0bd", border: "1px solid rgba(93,224,154,.25)", background: "rgba(93,224,154,.08)" };
const missing: React.CSSProperties = { color: "#ffd28b", border: "1px solid rgba(255,184,77,.25)", background: "rgba(255,184,77,.08)" };
const chips: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 };
const chip: React.CSSProperties = { borderRadius: 999, padding: "5px 8px", background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.08)", color: "rgba(255,255,255,.7)", fontSize: 11 };
const field: React.CSSProperties = { width: "100%", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: "11px 12px", outline: "none" };
const primary: React.CSSProperties = { minHeight: 42, border: "1px solid rgba(143,126,255,.35)", background: "rgba(111,91,255,.15)", color: "#d9d3ff", borderRadius: 12, fontWeight: 700 };
const result: React.CSSProperties = { padding: 12, borderRadius: 13, border: "1px solid rgba(93,224,154,.2)", background: "rgba(93,224,154,.05)" };
