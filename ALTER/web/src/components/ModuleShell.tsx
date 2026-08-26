"use client";

import Link from "next/link";
import { type ReactNode } from "react";

export default function ModuleShell({ title, eyebrow, children, action }: { title: string; eyebrow: string; children: ReactNode; action?: ReactNode }) {
  return (
    <main style={shell}>
      <header style={header}>
        <Link href="/" style={back}>← ALTER</Link>
        <div style={{ minWidth: 0 }}><div style={eyebrowStyle}>{eyebrow}</div><h1 style={titleStyle}>{title}</h1></div>
        <div>{action}</div>
      </header>
      {children}
    </main>
  );
}

export const panel: React.CSSProperties = {
  border: "1px solid rgba(255,255,255,.1)",
  background: "rgba(255,255,255,.035)",
  borderRadius: 18,
  padding: 14,
};

export const field: React.CSSProperties = {
  width: "100%",
  border: "1px solid rgba(255,255,255,.1)",
  background: "rgba(0,0,0,.2)",
  color: "#fff",
  borderRadius: 12,
  padding: "11px 12px",
  outline: "none",
  font: "inherit",
};

export const primary: React.CSSProperties = {
  minHeight: 42,
  border: "1px solid rgba(143,126,255,.35)",
  background: "rgba(111,91,255,.15)",
  color: "#d9d3ff",
  borderRadius: 12,
  padding: "0 13px",
  fontWeight: 700,
};

export const danger: React.CSSProperties = {
  ...primary,
  borderColor: "rgba(255,100,100,.28)",
  background: "rgba(255,100,100,.06)",
  color: "#ffaaa7",
};

export const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 12, lineHeight: 1.5 };
export const good: React.CSSProperties = { color: "#9af0bd" };
export const warn: React.CSSProperties = { color: "#ffd28b" };

const shell: React.CSSProperties = {
  minHeight: "100dvh",
  maxWidth: 800,
  margin: "0 auto",
  padding: "max(18px, env(safe-area-inset-top)) 14px calc(34px + env(safe-area-inset-bottom))",
  color: "#f4f2ff",
};
const header: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", marginBottom: 14 };
const back: React.CSSProperties = { color: "#b8b2d8", textDecoration: "none", fontWeight: 700 };
const eyebrowStyle: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const titleStyle: React.CSSProperties = { margin: "2px 0 0", fontSize: 27 };
