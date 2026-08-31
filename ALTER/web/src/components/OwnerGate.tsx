"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { KeyRound, Lock, ShieldCheck, Users } from "lucide-react";

const ACCESS_INPUT_ID = "alter-access-key";
const ACCESS_ERROR_ID = "alter-access-error";

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
    const credential = token.trim();
    if (busy) return;
    if (!credential) {
      setError(mode === "owner" ? "Введіть ключ доступу власника." : "Введіть одноразовий код запрошення.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const response = await fetch(mode === "owner" ? "/api/auth/login" : "/api/auth/member-login", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(mode === "owner" ? { token: credential } : { code: credential }),
      });
      if (!response.ok) {
        setError(mode === "owner" ? "Неправильний ключ доступу власника." : "Код запрошення недійсний, прострочений або вже використаний.");
        return;
      }
      setToken("");
      setState("ready");
    } catch {
      setError("Не вдалося створити захищену сесію. Спробуйте ще раз.");
    } finally {
      setBusy(false);
    }
  }

  if (state === "ready") return <>{children}</>;

  const empty = token.trim().length === 0;
  const inputLabel = mode === "owner" ? "Ключ доступу власника" : "Одноразовий код запрошення";

  return (
    <main style={{ minHeight: "100svh", display: "grid", placeItems: "center", padding: 20, background: "#050608", color: "#f6f7fb" }}>
      <section aria-labelledby="alter-access-title" style={{ width: "min(100%, 430px)", border: "1px solid rgba(255,255,255,.1)", borderRadius: 24, padding: "clamp(18px,5vw,22px)", background: "linear-gradient(145deg,rgba(26,29,38,.96),rgba(13,15,20,.96))", boxShadow: "0 24px 80px rgba(0,0,0,.55)" }}>
        <div aria-hidden="true" style={{ width: 54, height: 54, borderRadius: 17, display: "grid", placeItems: "center", border: "1px solid rgba(118,102,255,.35)", background: "rgba(118,102,255,.1)", marginBottom: 16 }}><ShieldCheck size={25} /></div>
        <div style={{ letterSpacing: ".2em", fontSize: 22, marginBottom: 5 }}>ALTER</div>
        <h1 id="alter-access-title" style={{ margin: "0 0 8px", fontSize: 28 }}>Захищений доступ</h1>
        <p style={{ margin: "0 0 16px", color: "#9ba0ad", lineHeight: 1.5 }}>Власник має повний контроль. Запрошені учасники входять одноразовим кодом і отримують обмежені права відповідно до ролі Operator або Viewer.</p>
        <div role="group" aria-label="Тип входу" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 14 }}>
          <button aria-pressed={mode === "owner"} type="button" onClick={() => { setMode("owner"); setError(""); setToken(""); }} style={{ ...tab, ...(mode === "owner" ? active : {}) }}><KeyRound size={15} aria-hidden="true" /> Власник</button>
          <button aria-pressed={mode === "member"} type="button" onClick={() => { setMode("member"); setError(""); setToken(""); }} style={{ ...tab, ...(mode === "member" ? active : {}) }}><Users size={15} aria-hidden="true" /> Учасник</button>
        </div>
        {state === "checking" ? <div role="status" aria-live="polite" style={{ color: "#9ba0ad" }}>Перевірка сесії…</div> : (
          <form onSubmit={login} noValidate style={{ display: "grid", gap: 10 }}>
            <label htmlFor={ACCESS_INPUT_ID} style={{ fontSize: 12, color: "#9ba0ad" }}>{inputLabel}</label>
            <div style={{ display: "flex", gap: 8, alignItems: "center", border: `1px solid ${error ? "rgba(237,119,114,.55)" : "rgba(255,255,255,.1)"}`, borderRadius: 13, padding: "0 12px", background: "rgba(255,255,255,.035)" }}>
              <Lock size={16} aria-hidden="true" />
              <input
                id={ACCESS_INPUT_ID}
                name={mode === "owner" ? "owner-access-key" : "invitation-code"}
                type="password"
                autoComplete={mode === "owner" ? "current-password" : "one-time-code"}
                autoCapitalize="none"
                spellCheck={false}
                value={token}
                onChange={(event) => { setToken(event.target.value); if (error) setError(""); }}
                placeholder={mode === "owner" ? "Введіть ключ" : "alt_…"}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? ACCESS_ERROR_ID : undefined}
                required
                autoFocus
                style={{ flex: 1, minWidth: 0, padding: "12px 0", border: 0, outline: 0, background: "transparent", color: "inherit" }}
              />
            </div>
            {error && <div id={ACCESS_ERROR_ID} role="alert" aria-live="assertive" style={{ color: "#ed7772", fontSize: 12 }}>{error}</div>}
            <button
              type="submit"
              disabled={busy || empty}
              aria-disabled={busy || empty}
              style={{ minHeight: 44, border: 0, borderRadius: 13, background: "linear-gradient(145deg,#6657ee,#806dfc)", color: "white", fontWeight: 650, cursor: busy || empty ? "not-allowed" : "pointer", opacity: busy || empty ? .55 : 1 }}
            >
              {busy ? "Перевіряю…" : "Увійти в ALTER"}
            </button>
          </form>
        )}
      </section>
    </main>
  );
}

const tab: React.CSSProperties = { minHeight: 44, borderRadius: 12, border: "1px solid rgba(255,255,255,.08)", background: "rgba(255,255,255,.025)", color: "#a8adba", display: "flex", alignItems: "center", justifyContent: "center", gap: 6, cursor: "pointer" };
const active: React.CSSProperties = { borderColor: "rgba(118,102,255,.35)", background: "rgba(118,102,255,.1)", color: "#ddd8ff" };
