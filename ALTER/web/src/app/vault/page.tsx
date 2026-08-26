"use client";

import Link from "next/link";
import { CheckCircle2, KeyRound, RotateCw, ShieldCheck, XCircle } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Alias = { alias: string; purpose: string; configured: boolean; source: string; owner_writable?: boolean; value_exposed: boolean };
type Health = { status: string; aliases: number; configured: number; raw_secret_exposure: boolean; owner_rotation?: boolean };

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers || {}) }, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Core returned ${response.status}`);
  return response.json() as Promise<T>;
}

export default function VaultPage() {
  const [aliases, setAliases] = useState<Alias[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [selected, setSelected] = useState("botpress_runtime");
  const [secret, setSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [a, h] = await Promise.all([core<Alias[]>("/vault/aliases"), core<Health>("/vault/health")]);
      setAliases(a); setHealth(h); setError(null);
      const writable = a.find((item) => item.owner_writable);
      if (writable && !a.some((item) => item.alias === `vault:${selected}` && item.owner_writable)) setSelected(writable.alias.replace("vault:", ""));
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити Vault"); }
  }, [selected]);

  useEffect(() => { void refresh(); }, [refresh]);
  const writableAliases = useMemo(() => aliases.filter((item) => item.owner_writable), [aliases]);

  async function save(event: FormEvent) {
    event.preventDefault(); if (!secret.trim() || busy) return;
    setBusy(true); setError(null); setNotice("");
    try {
      await core(`/vault/secrets/${encodeURIComponent(selected)}`, { method: "PUT", body: JSON.stringify({ value: secret }) });
      setSecret(""); setNotice("Секрет зашифровано й збережено. Значення не повернулося у браузер."); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося зберегти secret"); }
    finally { setBusy(false); }
  }

  return (
    <main style={shell}>
      <header style={header}><Link href="/" style={back}>← ALTER</Link><div><div style={eyebrow}>VAULT · SECRET FIREWALL</div><h1 style={title}>Сховище</h1></div><ShieldCheck size={25} /></header>

      <section style={hero}><KeyRound size={26} /><div><strong>Секрети ніколи не показуються після збереження</strong><p style={muted}>Password-поле → HTTPS → server-side BFF → Core → AES-256-GCM Vault у Neon. Моделі бачать лише `vault:*` alias, а не raw value.</p></div></section>
      {error && <section style={errorBox}>{error}</section>}
      {notice && <section style={successBox}>{notice}</section>}

      <div style={stats}><div style={stat}><strong>{health?.configured ?? "—"}</strong><span style={muted}>налаштовано</span></div><div style={stat}><strong>{health?.aliases ?? "—"}</strong><span style={muted}>aliases</span></div><div style={stat}><strong>{health?.raw_secret_exposure === false ? "0" : "—"}</strong><span style={muted}>raw exposed</span></div></div>

      {writableAliases.length > 0 && <form onSubmit={save} style={{ ...panel, marginTop: 14, display: "grid", gap: 9 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><RotateCw size={17} /><strong>Додати / замінити runtime secret</strong></div>
        <select value={selected} onChange={(e) => setSelected(e.target.value)} style={field}>{writableAliases.map((item) => <option key={item.alias} value={item.alias.replace("vault:", "")}>{item.alias} — {item.purpose}</option>)}</select>
        <input type="password" autoComplete="new-password" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="Встав ключ тут — не в чат" style={field} />
        <button disabled={busy || secret.trim().length < 8} style={primary}>{busy ? "Шифрую…" : "Зашифрувати у Vault"}</button>
        <div style={muted}>Core/database/owner-auth aliases керуються тільки серверним environment і навмисно не редагуються з UI.</div>
      </form>}

      <section style={{ display: "grid", gap: 10, marginTop: 14 }}>{aliases.map((item) => <article key={item.alias} style={panel}><div style={{ display: "grid", gridTemplateColumns: "40px 1fr auto", gap: 10, alignItems: "center" }}><div style={icon}>{item.configured ? <CheckCircle2 size={20} /> : <XCircle size={20} />}</div><div><strong>{item.alias}</strong><div style={muted}>{item.purpose} · {item.source}{item.owner_writable ? " · owner-rotatable" : " · server-managed"}</div></div><span style={{ ...badge, ...(item.configured ? good : missing) }}>{item.configured ? "Готово" : "Не задано"}</span></div></article>)}</section>

      <section style={{ ...panel, marginTop: 14 }}><strong>Безпека</strong><p style={muted}>Запис secret створює audit event лише з alias і часом ротації. Значення не логуються, не повертаються API і не передаються Botpress/іншим моделям.</p></section>
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
const successBox: React.CSSProperties = { ...panel, borderColor: "rgba(93,224,154,.25)", color: "#9af0bd", marginTop: 12 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.57)", fontSize: 12, lineHeight: 1.5, margin: "5px 0 0" };
const stats: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 8, marginTop: 12 };
const stat: React.CSSProperties = { ...panel, display: "grid", gap: 3, textAlign: "center" };
const icon: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", borderRadius: 12, background: "rgba(118,102,255,.1)", color: "#aaa1ff" };
const badge: React.CSSProperties = { borderRadius: 999, padding: "6px 9px", fontSize: 11, whiteSpace: "nowrap" };
const good: React.CSSProperties = { color: "#9af0bd", background: "rgba(93,224,154,.08)", border: "1px solid rgba(93,224,154,.25)" };
const missing: React.CSSProperties = { color: "#ffd28b", background: "rgba(255,184,77,.08)", border: "1px solid rgba(255,184,77,.25)" };
const field: React.CSSProperties = { width: "100%", boxSizing: "border-box", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: "11px 12px", outline: "none" };
const primary: React.CSSProperties = { minHeight: 42, border: "1px solid rgba(143,126,255,.35)", background: "rgba(111,91,255,.15)", color: "#d9d3ff", borderRadius: 12, fontWeight: 700 };
