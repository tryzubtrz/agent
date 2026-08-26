"use client";

import Link from "next/link";
import { CheckCircle2, KeyRound, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type Alias = { alias: string; purpose: string; configured: boolean; source: string; value_exposed: boolean };
type Health = { status: string; aliases: number; configured: number; raw_secret_exposure: boolean };

async function core<T>(path: string): Promise<T> {
  const response = await fetch(`/api/core${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Core returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default function VaultPage() {
  const [aliases, setAliases] = useState<Alias[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [a, h] = await Promise.all([core<Alias[]>("/vault/aliases"), core<Health>("/vault/health")]);
      setAliases(a); setHealth(h); setError(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити Vault"); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return (
    <main style={shell}>
      <header style={header}><Link href="/" style={back}>← ALTER</Link><div><div style={eyebrow}>VAULT · SECRET FIREWALL</div><h1 style={title}>Сховище</h1></div><ShieldCheck size={25} /></header>

      <section style={hero}>
        <KeyRound size={26} />
        <div><strong>Секрети ніколи не показуються в цьому інтерфейсі</strong><p style={muted}>ALTER бачить лише alias і факт налаштування. Raw API keys, паролі та database URL не повертаються через API.</p></div>
      </section>

      {error && <section style={errorBox}>{error}</section>}

      <div style={stats}>
        <div style={stat}><strong>{health?.configured ?? "—"}</strong><span style={muted}>налаштовано</span></div>
        <div style={stat}><strong>{health?.aliases ?? "—"}</strong><span style={muted}>aliases</span></div>
        <div style={stat}><strong>{health?.raw_secret_exposure === false ? "0" : "—"}</strong><span style={muted}>raw exposed</span></div>
      </div>

      <section style={{ display: "grid", gap: 10, marginTop: 14 }}>
        {aliases.map((item) => (
          <article key={item.alias} style={panel}>
            <div style={{ display: "grid", gridTemplateColumns: "40px 1fr auto", gap: 10, alignItems: "center" }}>
              <div style={icon}>{item.configured ? <CheckCircle2 size={20} /> : <XCircle size={20} />}</div>
              <div><strong>{item.alias}</strong><div style={muted}>{item.purpose} · {item.source}</div></div>
              <span style={{ ...badge, ...(item.configured ? good : missing) }}>{item.configured ? "Готово" : "Не задано"}</span>
            </div>
          </article>
        ))}
      </section>

      <section style={{ ...panel, marginTop: 14 }}>
        <strong>Що це вже дає</strong>
        <p style={muted}>Моделі й UI можуть посилатися на `vault:*` aliases, не отримуючи самих секретів. Наступний рівень — rotation/versioning і окремі scoped credentials для кожного connector.</p>
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
const hero: React.CSSProperties = { ...panel, display: "grid", gridTemplateColumns: "32px 1fr", gap: 12, alignItems: "start" };
const errorBox: React.CSSProperties = { ...panel, borderColor: "rgba(255,100,100,.35)", color: "#ffaaa7", marginTop: 12 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.57)", fontSize: 12, lineHeight: 1.5, margin: "5px 0 0" };
const stats: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 12 };
const stat: React.CSSProperties = { ...panel, display: "grid", gap: 3, textAlign: "center" };
const icon: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", borderRadius: 12, background: "rgba(118,102,255,.1)", color: "#aaa1ff" };
const badge: React.CSSProperties = { borderRadius: 999, padding: "6px 9px", fontSize: 11, whiteSpace: "nowrap" };
const good: React.CSSProperties = { color: "#9af0bd", background: "rgba(93,224,154,.08)", border: "1px solid rgba(93,224,154,.25)" };
const missing: React.CSSProperties = { color: "#ffd28b", background: "rgba(255,184,77,.08)", border: "1px solid rgba(255,184,77,.25)" };
