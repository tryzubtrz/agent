"use client";

import Link from "next/link";
import { Activity, Bot, CheckCircle2, CircleDashed, Database, RefreshCw, ShieldCheck, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type ComponentStatus = {
  key: string;
  label: string;
  status: "ready" | "waiting" | "degraded" | string;
  detail: string;
};
type SystemStatus = {
  overall: string;
  storage: string;
  tasks: { total: number; active: number; awaiting_approval: number };
  agent: { provider: string; configured: boolean; credential_configured: boolean; bot_id_configured: boolean; action: string };
  connectors: { total: number; by_status: Record<string, number> };
  vault: { aliases_known: number; configured: number; raw_secret_exposure: boolean };
  components: ComponentStatus[];
};

async function core<T>(path: string): Promise<T> {
  const response = await fetch(`/api/core${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Core returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default function StatusPage() {
  const [data, setData] = useState<SystemStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      setData(await core<SystemStatus>("/system/status"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося прочитати статус системи");
    } finally { setBusy(false); }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const ready = data?.components.filter((item) => item.status === "ready").length ?? 0;
  const waiting = data?.components.filter((item) => item.status === "waiting").length ?? 0;

  return (
    <main style={shell}>
      <header style={header}>
        <Link href="/" style={back}>← ALTER</Link>
        <div><div style={eyebrow}>SYSTEM · LIVE</div><h1 style={title}>Стан системи</h1></div>
        <button type="button" onClick={() => void refresh()} disabled={busy} style={iconButton} aria-label="Оновити"><RefreshCw size={18} /></button>
      </header>

      <section style={hero}>
        <div style={pulse}><Activity size={24} /></div>
        <div><strong>ALTER працює на реальних даних</strong><p style={muted}>Ця сторінка читає Core напряму. Тут немає намальованих “online” статусів.</p></div>
        <span style={{ ...badge, ...(data?.overall === "ready" ? good : warn) }}>{data?.overall?.toUpperCase() || "CHECKING"}</span>
      </section>

      {error && <section style={errorBox}>{error}</section>}

      <div style={stats}>
        <Stat value={ready} label="ready" />
        <Stat value={waiting} label="waiting" />
        <Stat value={data?.tasks.active ?? "—"} label="активних задач" />
        <Stat value={data?.tasks.awaiting_approval ?? "—"} label="схвалень" />
      </div>

      <section style={{ display: "grid", gap: 9, marginTop: 14 }}>
        {data?.components.map((item) => <ComponentRow key={item.key} item={item} />)}
      </section>

      <section style={{ ...panel, marginTop: 14 }}>
        <div style={{ display: "grid", gridTemplateColumns: "24px 1fr", gap: 9 }}><Bot size={18} /><div><strong>AI specialist</strong><div style={muted}>{data?.agent.configured ? `${data.agent.provider} · ${data.agent.action} · ready` : "Botpress задеплоєний; Core чекає runtime credential"}</div></div></div>
        <div style={divider} />
        <div style={{ display: "grid", gridTemplateColumns: "24px 1fr", gap: 9 }}><Database size={18} /><div><strong>Storage</strong><div style={muted}>{data?.storage || "—"} · Vault aliases {data ? `${data.vault.configured}/${data.vault.aliases_known}` : "—"} · raw secrets exposed: {data?.vault.raw_secret_exposure === false ? "0" : "—"}</div></div></div>
      </section>

      <section style={links}>
        <Link href="/chat" style={linkCard}>Живий чат</Link>
        <Link href="/files" style={linkCard}>Файли</Link>
        <Link href="/vault" style={linkCard}>Vault</Link>
        <Link href="/models" style={linkCard}>Моделі</Link>
      </section>
    </main>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return <div style={stat}><strong style={{ fontSize: 20 }}>{value}</strong><span style={muted}>{label}</span></div>;
}

function ComponentRow({ item }: { item: ComponentStatus }) {
  const Icon = item.status === "ready" ? CheckCircle2 : item.status === "waiting" ? CircleDashed : TriangleAlert;
  const tone = item.status === "ready" ? "#9af0bd" : item.status === "waiting" ? "#ffd28b" : "#ffaaa7";
  return (
    <article style={panel}>
      <div style={{ display: "grid", gridTemplateColumns: "40px 1fr auto", gap: 10, alignItems: "center" }}>
        <div style={{ ...componentIcon, color: tone }}><Icon size={19} /></div>
        <div><strong>{item.label}</strong><div style={muted}>{item.detail}</div></div>
        <span style={{ color: tone, fontSize: 10, textTransform: "uppercase" }}>{item.status}</span>
      </div>
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
const hero: React.CSSProperties = { ...panel, display: "grid", gridTemplateColumns: "46px 1fr auto", gap: 11, alignItems: "center", borderColor: "rgba(93,224,154,.18)" };
const pulse: React.CSSProperties = { width: 46, height: 46, display: "grid", placeItems: "center", borderRadius: 15, color: "#9af0bd", background: "rgba(93,224,154,.07)", border: "1px solid rgba(93,224,154,.18)" };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 11, lineHeight: 1.45, margin: "4px 0 0" };
const badge: React.CSSProperties = { borderRadius: 999, padding: "6px 8px", fontSize: 9, letterSpacing: ".07em" };
const good: React.CSSProperties = { color: "#9af0bd", border: "1px solid rgba(93,224,154,.25)", background: "rgba(93,224,154,.08)" };
const warn: React.CSSProperties = { color: "#ffd28b", border: "1px solid rgba(255,184,77,.25)", background: "rgba(255,184,77,.08)" };
const errorBox: React.CSSProperties = { ...panel, marginTop: 10, borderColor: "rgba(255,100,100,.3)", color: "#ffaaa7" };
const stats: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 7, marginTop: 10 };
const stat: React.CSSProperties = { ...panel, display: "grid", gap: 1, textAlign: "center", padding: 10 };
const componentIcon: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", borderRadius: 12, background: "rgba(255,255,255,.035)" };
const divider: React.CSSProperties = { height: 1, background: "rgba(255,255,255,.07)", margin: "12px 0" };
const links: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 };
const linkCard: React.CSSProperties = { ...panel, textDecoration: "none", color: "#d9d4ff", textAlign: "center", fontWeight: 700 };
