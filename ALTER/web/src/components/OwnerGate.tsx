"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { KeyRound, Lock, ShieldCheck, Users } from "lucide-react";

export default function OwnerGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"checking" | "locked" | "ready">("checking");
  const [mode, setMode] = useState<"owner" | "member">("owner");
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/auth/session", { cache: "no-store" })
      .then((response) => setState(response.ok ? "ready" : "locked"))
      .catch(() => setState("locked"));
  }, []);

  async function login(event: FormEvent) {
    event.preventDefault();
    if (!token.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(mode === "owner" ? "/api/auth/login" : "/api/auth/member-login", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(mode === "owner" ? { token } : { code: token }),
      });
      if (!response.ok) { setError(mode === "owner" ? "Неправильний owner access key." : "Код запрошення недійсний, прострочений або вже використаний."); return; }
      setToken(""); setState("ready");
    } catch { setError("Не вдалося створити захищену сесію."); }
    finally { setBusy(false); }
  }

  if (state === "ready") return <>{children}</>;

  return (
    <main style={{ minHeight: "100svh", display: "grid", placeItems: "center", padding: 20, background: "#050608", color: "#f6f7fb" }}>
      <section style={{ width: "min(100%, 430px)", border: "1px solid rgba(255,255,255,.1)", borderRadius: 24, padding: 22, background: "linear-gradient(145deg,rgba(26,29,38,.96),rgba(13,15,20,.96))", boxShadow: "0 24px 80px rgba(0,0,0,.55)" }}>
        <div style={{ width: 54, height: 54, borderRadius: 17, display: "grid", placeItems: "center", border: "1px solid rgba(118,102,255,.35)", background: "rgba(118,102,255,.1)", marginBottom: 16 }}><ShieldCheck size={25} /></div>
        <div style={{ letterSpacing: ".2em", fontSize: 22, marginBottom: 5 }}>ALTER</div>
        <h1 style={{ margin: "0 0 8px", fontSize: 28 }}>Захищений доступ</h1>
        <p style={{ margin: "0 0 16px", color: "#9ba0ad", lineHeight: 1.5 }}>Owner має повний контроль. Operator/Viewer входять тільки одноразовим кодом запрошення і отримують обмежену RBAC-сесію.</p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          <button type="button" onClick={() => { setMode("owner"); setError(""); setToken(""); }} style={{ ...tab, ...(mode === "owner" ? active : {}) }}><KeyRound size={15} /> Owner</button>
          <button type="button" onClick={() => { setMode("member"); setError(""); setToken(""); }} style={{ ...tab, ...(mode === "member" ? active : {}) }}><Users size={15} /> Member</button>
        </div>
        {state === "checking" ? <div style={{ color: "#9ba0ad" }}>Перевірка сесії…</div> : (
          <form onSubmit={login} style={{ display: "grid", gap: 10 }}>
            <label style={{ fontSize: 12, color: "#9ba0ad" }}>{mode === "owner" ? "Owner access key" : "Одноразовий код запрошення"}</label>
            <div style={{ display: "flex", gap: 8, alignItems: "center", border: "1px solid rgba(255,255,255,.1)", borderRadius: 13, padding: "0 12px", background: "rgba(255,255,255,.035)" }}>
              <Lock size={16} /><input type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} placeholder={mode === "owner" ? "Вставте ключ" : "alt_…"} style={{ flex: 1, minWidth: 0, padding: "12px 0", border: 0, outline: 0, background: "transparent", color: "inherit" }} />
            </div>
            {error && <div style={{ color: "#ed7772", fontSize: 12 }}>{error}</div>}
            <button disabled={busy} style={{ minHeight: 44, border: 0, borderRadius: 13, background: "linear-gradient(145deg,#6657ee,#806dfc)", color: "white", fontWeight: 650 }}>{busy ? "Перевіряю…" : "Увійти в ALTER"}</button>
          </form>
        )}
      </section>
    </main>
  );
}

const tab: React.CSSProperties = { minHeight: 40, borderRadius: 12, border: "1px solid rgba(255,255,255,.08)", background: "rgba(255,255,255,.025)", color: "#a8adba", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 };
const active: React.CSSProperties = { borderColor: "rgba(118,102,255,.35)", background: "rgba(118,102,255,.1)", color: "#ddd8ff" };
