"use client";

import Link from "next/link";
import { Copy, Crown, ShieldCheck, UserMinus, UserPlus, Users } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { core } from "@/lib/core-client";

type Member = { id: string; label: string; role: "operator" | "viewer"; capabilities: string[]; active: boolean; created_at: string; last_login_at?: string };
type Invite = { id: string; label: string; role: "operator" | "viewer"; capabilities: string[]; expires_at: string; redeemed_at?: string | null; revoked?: boolean };
type CreatedInvite = Invite & { code: string; code_shown_once: boolean };

export default function PeoplePage() {
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [label, setLabel] = useState("");
  const [role, setRole] = useState<"operator" | "viewer">("viewer");
  const [created, setCreated] = useState<CreatedInvite | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [memberRows, inviteRows] = await Promise.all([core<Member[]>("/access/members"), core<Invite[]>("/access/invites")]);
      setMembers(memberRows); setInvites(inviteRows); setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити RBAC"); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function createInvite(event: FormEvent) {
    event.preventDefault(); if (!label.trim() || busy) return;
    setBusy(true); setCreated(null);
    try {
      const result = await core<CreatedInvite>("/access/invites", { method: "POST", body: JSON.stringify({ label: label.trim(), role, expires_hours: 72, capabilities: [] }) });
      setCreated(result); setLabel(""); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося створити запрошення"); }
    finally { setBusy(false); }
  }

  async function deactivate(member: Member) {
    setBusy(true);
    try { await core(`/access/members/${member.id}/deactivate`, { method: "POST", body: "{}" }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося деактивувати доступ"); }
    finally { setBusy(false); }
  }

  return (
    <main style={shell}>
      <header style={header}><Link href="/" style={back}>← ALTER</Link><div><div style={eyebrow}>PEOPLE · RBAC · LIVE</div><h1 style={title}>Люди</h1></div><Users size={25} /></header>

      <section style={ownerCard}><div style={icon}><Crown size={21} /></div><div><strong>Owner</strong><div style={muted}>Повний контроль workspace, approvals, policies та Vault.</div></div><span style={good}>ACTIVE</span></section>

      <form onSubmit={createInvite} style={{ ...panel, marginTop: 12, display: "grid", gap: 9 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><UserPlus size={18} /><strong>Створити одноразове запрошення</strong></div>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Імʼя або опис людини" style={field} />
        <select value={role} onChange={(e) => setRole(e.target.value as "operator" | "viewer")} style={field}><option value="viewer">Viewer — тільки читання</option><option value="operator">Operator — задачі та робочі модулі</option></select>
        <button disabled={busy || !label.trim()} style={primary}><ShieldCheck size={16} /> Створити код на 72 години</button>
        <div style={muted}>Код показується лише один раз. У базі зберігається тільки SHA-256 hash. Після першого входу invite погашається.</div>
      </form>

      {created && <section style={{ ...panel, marginTop: 12, borderColor: "rgba(93,224,154,.25)" }}><strong>Код готовий — скопіюй зараз</strong><div style={code}>{created.code}</div><button type="button" style={primary} onClick={() => void navigator.clipboard?.writeText(created.code)}><Copy size={15} /> Скопіювати</button><div style={muted}>Role: {created.role} · expires {new Date(created.expires_at).toLocaleString("uk-UA")}</div></section>}
      {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}

      <section style={{ display: "grid", gap: 10, marginTop: 14 }}>
        <strong>Учасники</strong>
        {members.length === 0 && <div style={empty}>Ще немає активованих Partner/Guest-сесій.</div>}
        {members.map((member) => <article key={member.id} style={panel}><div style={row}><div><strong>{member.label}</strong><div style={muted}>{member.role} · {member.capabilities.join(" · ")}</div></div><span style={member.active ? good : waiting}>{member.active ? "ACTIVE" : "OFF"}</span></div>{member.active && <button type="button" onClick={() => void deactivate(member)} disabled={busy} style={danger}><UserMinus size={15} /> Деактивувати</button>}</article>)}
      </section>

      <section style={{ display: "grid", gap: 10, marginTop: 14 }}>
        <strong>Запрошення</strong>
        {invites.length === 0 && <div style={empty}>Запрошень ще немає.</div>}
        {invites.map((invite) => <article key={invite.id} style={panel}><div style={row}><div><strong>{invite.label}</strong><div style={muted}>{invite.role} · до {new Date(invite.expires_at).toLocaleString("uk-UA")}</div></div><span style={invite.redeemed_at ? good : waiting}>{invite.redeemed_at ? "USED" : "OPEN"}</span></div></article>)}
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
const ownerCard: React.CSSProperties = { ...panel, display: "grid", gridTemplateColumns: "42px 1fr auto", gap: 10, alignItems: "center", borderColor: "rgba(93,224,154,.2)" };
const icon: React.CSSProperties = { width: 42, height: 42, display: "grid", placeItems: "center", borderRadius: 13, background: "rgba(93,224,154,.08)", color: "#9af0bd" };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 12, lineHeight: 1.5, marginTop: 4 };
const row: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 };
const good: React.CSSProperties = { color: "#9af0bd", border: "1px solid rgba(93,224,154,.25)", background: "rgba(93,224,154,.08)", borderRadius: 999, padding: "6px 9px", fontSize: 10 };
const waiting: React.CSSProperties = { color: "#ffd28b", border: "1px solid rgba(255,184,77,.25)", background: "rgba(255,184,77,.08)", borderRadius: 999, padding: "6px 9px", fontSize: 10 };
const field: React.CSSProperties = { width: "100%", boxSizing: "border-box", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: "11px 12px", outline: "none" };
const primary: React.CSSProperties = { minHeight: 40, border: "1px solid rgba(143,126,255,.35)", background: "rgba(111,91,255,.15)", color: "#d9d3ff", borderRadius: 12, padding: "0 12px", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 7, fontWeight: 700 };
const danger: React.CSSProperties = { marginTop: 10, minHeight: 36, border: "1px solid rgba(255,100,100,.25)", background: "rgba(255,100,100,.06)", color: "#ffaaa7", borderRadius: 11, padding: "0 10px", display: "inline-flex", alignItems: "center", gap: 6 };
const code: React.CSSProperties = { margin: "10px 0", padding: 12, borderRadius: 12, background: "rgba(0,0,0,.25)", wordBreak: "break-all", fontFamily: "monospace", fontSize: 12 };
const empty: React.CSSProperties = { ...panel, color: "rgba(255,255,255,.5)" };
