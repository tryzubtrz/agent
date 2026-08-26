"use client";

import Link from "next/link";
import { Crown, LockKeyhole, UserPlus, Users } from "lucide-react";

export default function PeoplePage() {
  return (
    <main style={shell}>
      <header style={header}><Link href="/" style={back}>← ALTER</Link><div><div style={eyebrow}>PEOPLE · ACCESS</div><h1 style={title}>Люди</h1></div><Users size={25} /></header>

      <section style={ownerCard}>
        <div style={icon}><Crown size={21} /></div>
        <div><strong>Owner</strong><div style={muted}>Активний · повний контроль власного workspace</div></div>
        <span style={good}>ACTIVE</span>
      </section>

      <section style={{ ...panel, marginTop: 12 }}>
        <div style={{ display: "flex", gap: 9, alignItems: "center" }}><LockKeyhole size={18} /><strong>Single-owner mode</strong></div>
        <p style={muted}>Зараз ALTER навмисно не видає права Partner/Guest, доки немає production identity + RBAC backend. Це безпечніше, ніж показувати фальшиві ролі.</p>
      </section>

      <section style={{ display: "grid", gap: 10, marginTop: 12 }}>
        <article style={panel}><div style={row}><div><strong>Partner</strong><div style={muted}>Майбутній обмежений доступ до вибраних модулів і задач.</div></div><span style={waiting}>NOT ENABLED</span></div></article>
        <article style={panel}><div style={row}><div><strong>Guest</strong><div style={muted}>За замовчуванням нуль доступу; лише явно видані permissions.</div></div><span style={waiting}>NOT ENABLED</span></div></article>
      </section>

      <button type="button" disabled style={disabled}><UserPlus size={17} /> Запрошення зʼявляться після RBAC backend</button>
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
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 12, lineHeight: 1.5, margin: "4px 0 0" };
const row: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 };
const good: React.CSSProperties = { color: "#9af0bd", border: "1px solid rgba(93,224,154,.25)", background: "rgba(93,224,154,.08)", borderRadius: 999, padding: "6px 9px", fontSize: 10 };
const waiting: React.CSSProperties = { color: "#ffd28b", border: "1px solid rgba(255,184,77,.25)", background: "rgba(255,184,77,.08)", borderRadius: 999, padding: "6px 9px", fontSize: 10, whiteSpace: "nowrap" };
const disabled: React.CSSProperties = { marginTop: 14, width: "100%", minHeight: 44, border: "1px solid rgba(255,255,255,.08)", background: "rgba(255,255,255,.025)", color: "rgba(255,255,255,.35)", borderRadius: 14, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 };
