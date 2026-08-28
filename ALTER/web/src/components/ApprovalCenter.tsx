"use client";

import { Check, ShieldAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

type PendingApproval = {
  task_id: string;
  objective: string;
  status: string;
  blocker: string | null;
  action_digest: string;
  action: { category?: string; operation?: string; risk?: string; parameters?: Record<string, unknown> };
  updated_at: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers || {}) }, cache: "no-store" });
  if (!response.ok) throw new Error((await response.text()) || `Request failed with ${response.status}`);
  return response.json() as Promise<T>;
}

export default function ApprovalCenter() {
  const [isOwner, setIsOwner] = useState<boolean | null>(null);
  const [items, setItems] = useState<PendingApproval[]>([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try { setItems(await request<PendingApproval[]>("/approvals")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити схвалення"); }
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/auth/session", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((session) => { if (!cancelled) setIsOwner(session?.role === "owner"); })
      .catch(() => { if (!cancelled) setIsOwner(false); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (isOwner !== true) return;
    let disposed = false;
    let timer: number | undefined;

    async function poll() {
      await refresh();
      if (!disposed) timer = window.setTimeout(() => void poll(), 15000);
    }

    void poll();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [isOwner, refresh]);

  async function decide(item: PendingApproval, decision: "approve" | "reject") {
    setBusy(item.task_id);
    try { await request(`/approvals/${item.task_id}/${decision}`, { method: "POST", body: JSON.stringify({ action_digest: item.action_digest }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося зберегти рішення"); }
    finally { setBusy(null); }
  }

  if (isOwner !== true) return null;
  if (!open && items.length === 0) return null;

  return (
    <>
      <button type="button" onClick={() => setOpen((value) => !value)} aria-label="Відкрити центр схвалень" style={floating}>
        <ShieldAlert size={17} /> {items.length} {items.length === 1 ? "схвалення" : "схвалень"}
      </button>
      {open && <div role="dialog" aria-modal="true" aria-label="Центр схвалень ALTER" style={overlay} onClick={() => setOpen(false)}>
        <section onClick={(event) => event.stopPropagation()} style={sheet}>
          <div style={heading}><div><strong style={{ fontSize: 18 }}>Потрібне твоє рішення</strong><div style={muted}>ALTER не виконає ризикову дію без точного owner-схвалення.</div></div><button type="button" onClick={() => setOpen(false)} aria-label="Закрити" style={iconButtonStyle}><X size={18} /></button></div>
          {error && <div style={{ marginBottom: 12, color: "#ff9a96", fontSize: 13 }}>{error}</div>}
          {items.length === 0 && <div style={{ color: "rgba(255,255,255,.6)", padding: "18px 2px" }}>Немає дій, що чекають схвалення.</div>}
          <div style={{ display: "grid", gap: 12 }}>{items.map((item) => <article key={item.task_id} style={card}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}><div><div style={{ color: "#a89cff", fontSize: 11, textTransform: "uppercase", letterSpacing: ".08em" }}>{item.action.risk || "approval"}</div><strong style={{ display: "block", marginTop: 5 }}>{item.objective}</strong></div><span style={{ color: "#ffd28b", fontSize: 12 }}>{item.action.category || "action"}</span></div>
            <div style={{ marginTop: 10, color: "rgba(255,255,255,.7)", fontSize: 13, lineHeight: 1.5 }}>Дія: <b style={{ color: "#fff" }}>{item.action.operation || "—"}</b>{item.blocker ? <div style={{ marginTop: 4 }}>Причина: {item.blocker}</div> : null}</div>
            {item.action.parameters && Object.keys(item.action.parameters).length > 0 && <pre style={pre}>{JSON.stringify(item.action.parameters, null, 2)}</pre>}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}><button type="button" disabled={busy === item.task_id} onClick={() => void decide(item, "reject")} style={{ ...decisionButtonStyle, borderColor: "rgba(255,102,102,.35)", color: "#ffaaa7" }}><X size={16} /> Відхилити</button><button type="button" disabled={busy === item.task_id} onClick={() => void decide(item, "approve")} style={{ ...decisionButtonStyle, borderColor: "rgba(93,224,154,.35)", color: "#9af0bd" }}><Check size={16} /> Схвалити</button></div>
          </article>)}</div>
        </section>
      </div>}
    </>
  );
}

const floating: React.CSSProperties = { position: "fixed", right: 18, bottom: 92, zIndex: 80, display: "flex", alignItems: "center", gap: 8, border: "1px solid rgba(255,184,77,.45)", borderRadius: 999, padding: "10px 13px", background: "rgba(24,19,10,.92)", color: "#ffd28b", boxShadow: "0 14px 40px rgba(0,0,0,.35)", backdropFilter: "blur(18px)", fontWeight: 700 };
const overlay: React.CSSProperties = { position: "fixed", inset: 0, zIndex: 79, background: "rgba(0,0,0,.58)", backdropFilter: "blur(10px)", display: "flex", alignItems: "flex-end", justifyContent: "center", padding: 12 };
const sheet: React.CSSProperties = { width: "min(680px, 100%)", maxHeight: "78vh", overflow: "auto", borderRadius: 24, border: "1px solid rgba(255,255,255,.12)", background: "rgba(10,11,15,.97)", boxShadow: "0 30px 90px rgba(0,0,0,.55)", padding: 16, color: "#f5f3ff" };
const heading: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 14 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 12, marginTop: 4 };
const card: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", borderRadius: 18, padding: 14, background: "rgba(255,255,255,.035)" };
const pre: React.CSSProperties = { margin: "10px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word", fontSize: 11, color: "rgba(255,255,255,.55)", background: "rgba(0,0,0,.2)", borderRadius: 12, padding: 10 };
const iconButtonStyle: React.CSSProperties = { width: 38, height: 38, display: "grid", placeItems: "center", border: "1px solid rgba(255,255,255,.1)", borderRadius: 12, background: "rgba(255,255,255,.04)", color: "#fff" };
const decisionButtonStyle: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "center", gap: 7, minHeight: 42, border: "1px solid rgba(255,255,255,.12)", borderRadius: 13, background: "rgba(255,255,255,.04)", fontWeight: 700 };

