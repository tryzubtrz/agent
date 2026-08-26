"use client";

import Link from "next/link";
import { CheckCircle2, CircleDashed, Link2, RefreshCw, Send, ShieldCheck, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Connector = {
  key: string;
  label: string;
  status: "connected" | "available" | "not_configured" | "degraded" | string;
  capabilities: string[];
  credential_source: string;
  write_boundary: string;
};

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) throw new Error((await response.text()) || `Core returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default function GatewayPage() {
  const [items, setItems] = useState<Connector[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    try { setItems(await core<Connector[]>("/gateway/connectors")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити gateway"); }
    finally { setBusy(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function testPostHog() {
    setBusy(true); setMessage(null); setError(null);
    try {
      await core("/gateway/posthog/capture", {
        method: "POST",
        body: JSON.stringify({ event: "alter_connector_test", properties: { source: "gateway_ui" } }),
      });
      setMessage("PostHog прийняв тестову production-подію.");
    } catch (err) { setError(err instanceof Error ? err.message : "Тест PostHog не пройшов"); }
    finally { setBusy(false); }
  }

  return (
    <main style={shell}>
      <header style={header}>
        <Link href="/" style={back}>← ALTER</Link>
        <div><div style={eyebrow}>CONNECTOR GATEWAY</div><h1 style={title}>Конектори</h1></div>
        <button type="button" onClick={() => void refresh()} disabled={busy} style={iconButton}><RefreshCw size={18} /></button>
      </header>

      <section style={hero}>
        <ShieldCheck size={23} />
        <div><strong>Fail-closed gateway</strong><p style={muted}>ALTER не успадковує доступи ChatGPT. Кожен production connector має власний scoped credential і чітку межу дій.</p></div>
      </section>

      {message && <section style={successBox}>{message}</section>}
      {error && <section style={errorBox}>{error}</section>}

      <section style={{ display: "grid", gap: 10, marginTop: 12 }}>
        {items.map((item) => <ConnectorCard key={item.key} item={item} />)}
      </section>

      <section style={{ ...panel, marginTop: 14, display: "grid", gap: 10 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Send size={17} /><strong>Production smoke test</strong></div>
        <p style={muted}>Тест надсилає тільки технічну подію `alter_connector_test`, без тексту чату, файлів, памʼяті або секретів.</p>
        <button type="button" onClick={() => void testPostHog()} disabled={busy} style={primary}>Перевірити PostHog</button>
      </section>
    </main>
  );
}

function ConnectorCard({ item }: { item: Connector }) {
  const Icon = item.status === "connected" ? CheckCircle2 : item.status === "degraded" ? TriangleAlert : CircleDashed;
  const tone = item.status === "connected" ? "#9af0bd" : item.status === "degraded" ? "#ffaaa7" : "#ffd28b";
  return (
    <article style={panel}>
      <div style={{ display: "grid", gridTemplateColumns: "42px 1fr auto", gap: 10, alignItems: "center" }}>
        <div style={{ ...connectorIcon, color: tone }}><Icon size={20} /></div>
        <div><strong>{item.label}</strong><div style={muted}>{item.credential_source}</div></div>
        <span style={{ color: tone, fontSize: 10, textTransform: "uppercase" }}>{item.status.replaceAll("_", " ")}</span>
      </div>
      <div style={chips}>{item.capabilities.map((cap) => <span key={cap} style={chip}>{cap}</span>)}</div>
      <div style={{ ...muted, marginTop: 9 }}>Boundary: {item.write_boundary}</div>
    </article>
  );
}

const shell: React.CSSProperties = { minHeight: "100dvh", maxWidth: 760, margin: "0 auto", padding: "max(18px, env(safe-area-inset-top)) 14px calc(30px + env(safe-area-inset-bottom))", color: "#f4f2ff" };
const header: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", marginBottom: 14 };
const back: React.CSSProperties = { color: "#b8b2d8", textDecoration: "none", fontWeight: 700 };
const eyebrow: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const title: React.CSSProperties = { margin: "2px 0 0", fontSize: 26 };
const iconButton: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", border: "1px solid rgba(255,255,255,.1)", borderRadius: 13, background: "rgba(255,255,255,.04)", color: "#dcd8ef" };
const panel: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.035)", borderRadius: 18, padding: 13 };
const hero: React.CSSProperties = { ...panel, display: "grid", gridTemplateColumns: "28px 1fr", gap: 10, alignItems: "start" };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 11, lineHeight: 1.45, margin: "4px 0 0" };
const successBox: React.CSSProperties = { ...panel, marginTop: 10, color: "#9af0bd", borderColor: "rgba(93,224,154,.25)" };
const errorBox: React.CSSProperties = { ...panel, marginTop: 10, color: "#ffaaa7", borderColor: "rgba(255,100,100,.3)" };
const connectorIcon: React.CSSProperties = { width: 42, height: 42, display: "grid", placeItems: "center", borderRadius: 13, background: "rgba(255,255,255,.035)" };
const chips: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 11 };
const chip: React.CSSProperties = { borderRadius: 999, padding: "5px 8px", border: "1px solid rgba(255,255,255,.08)", background: "rgba(255,255,255,.03)", color: "rgba(255,255,255,.66)", fontSize: 10 };
const primary: React.CSSProperties = { minHeight: 42, border: "1px solid rgba(139,124,255,.3)", background: "rgba(118,102,255,.13)", color: "#d9d4ff", borderRadius: 13, fontWeight: 700 };
