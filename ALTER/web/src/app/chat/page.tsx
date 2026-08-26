"use client";

import Link from "next/link";
import { Bot, Brain, Eraser, Send, ShieldCheck, Sparkles } from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

type Message = {
  role: "user" | "agent";
  text: string;
  created_at?: string | null;
  redacted?: boolean;
};

type Conversation = { messages: Message[]; count: number; persistent: boolean };
type AgentStatus = {
  provider: string;
  configured: boolean;
  bot_id_configured: boolean;
  credential_configured: boolean;
  action: string;
  side_effect_boundary: string;
};
type ResponsePayload = {
  provider: string;
  user: Message;
  agent: Message;
  persistent: boolean;
  side_effects_performed: false;
  boundary: string;
};

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = "";
    try {
      const payload = await response.json();
      detail = typeof payload?.detail === "string" ? payload.detail : "";
    } catch {
      detail = await response.text().catch(() => "");
    }
    throw new Error(detail || `ALTER Core returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function ChatPage() {
  const endRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"normal" | "deep">("normal");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [conversation, agent] = await Promise.all([
        core<Conversation>("/conversation"),
        core<AgentStatus>("/agent/status"),
      ]);
      setMessages(conversation.messages);
      setStatus(agent);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося відкрити чат");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, busy]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = text.trim();
    if (!value || busy || !status?.configured) return;
    setBusy(true);
    setText("");
    setError(null);

    const optimistic: Message = { role: "user", text: value, created_at: new Date().toISOString() };
    setMessages((items) => [...items, optimistic]);

    try {
      const result = await core<ResponsePayload>("/conversation/respond", {
        method: "POST",
        body: JSON.stringify({ text: value, mode }),
      });
      setMessages((items) => [...items.slice(0, -1), result.user, result.agent]);
    } catch (err) {
      setMessages((items) => items.slice(0, -1));
      setText(value);
      setError(err instanceof Error ? err.message : "ALTER не зміг відповісти");
    } finally {
      setBusy(false);
    }
  }

  async function clearHistory() {
    if (busy || messages.length === 0) return;
    setBusy(true);
    try {
      await core<{ cleared: boolean }>("/conversation/clear", { method: "POST", body: "{}" });
      setMessages([]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося очистити історію");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={shell}>
      <header style={header}>
        <Link href="/" style={back}>← ALTER</Link>
        <div style={{ minWidth: 0 }}>
          <div style={eyebrow}>LIVE CONVERSATION</div>
          <h1 style={title}>Поговоримо</h1>
        </div>
        <button type="button" onClick={() => void clearHistory()} disabled={busy || messages.length === 0} style={iconButton} aria-label="Очистити історію"><Eraser size={18} /></button>
      </header>

      <section style={{ ...statusCard, ...(status?.configured ? readyBorder : waitingBorder) }}>
        <div style={agentOrb}><Bot size={22} /></div>
        <div style={{ minWidth: 0 }}>
          <strong>{status?.configured ? "ALTER готовий до розмови" : "ALTER майже готовий"}</strong>
          <p style={muted}>
            {status?.configured
              ? "Розмова зберігається в твоїй приватній памʼяті. Я можу говорити звичайно, а не тільки приймати задачі."
              : "Дружній AI вже задеплоєний у Botpress, але Core ще чекає один runtime credential. Історія чату вже працює; фальшиву AI-відповідь ALTER не показує."}
          </p>
        </div>
        <span style={{ ...badge, ...(status?.configured ? good : waiting) }}>{status?.configured ? "ONLINE" : "WAITING"}</span>
      </section>

      <div style={securityLine}><ShieldCheck size={14} /> Схожі на паролі/API keys/token значення редагуються до збереження.</div>
      {error && <section style={errorBox}>{error}</section>}

      <section style={chatPanel}>
        {loading && <div style={empty}>Завантажую нашу історію…</div>}
        {!loading && messages.length === 0 && (
          <div style={empty}>
            <Sparkles size={24} />
            <strong style={{ color: "#f5f3ff" }}>Можеш писати як звичайно</strong>
            <span>Поговорити, щось спитати, пожартувати або подумати вголос — не кожне повідомлення буде ставати задачею.</span>
          </div>
        )}

        {messages.map((message, index) => (
          <article key={`${message.created_at || index}-${index}`} style={{ ...bubble, ...(message.role === "user" ? userBubble : agentBubble) }}>
            <div style={messageMeta}>
              <span>{message.role === "user" ? "Ти" : "ALTER"}</span>
              <span>{formatTime(message.created_at)}</span>
            </div>
            <div style={messageText}>{message.text}</div>
            {message.redacted && <div style={redactedNote}>Секретне значення було приховано перед збереженням.</div>}
          </article>
        ))}

        {busy && <article style={{ ...bubble, ...agentBubble }}><div style={messageMeta}>ALTER</div><div style={typing}>думає<span>…</span></div></article>}
        <div ref={endRef} />
      </section>

      <form onSubmit={submit} style={composer}>
        <textarea
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={status?.configured ? "Напиши щось ALTER…" : "Чат активується після runtime credential"}
          disabled={busy || !status?.configured}
          rows={2}
          style={textarea}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
        />
        <div style={composerBottom}>
          <div style={modeWrap}>
            <Brain size={14} />
            <button type="button" onClick={() => setMode("normal")} style={{ ...modeButton, ...(mode === "normal" ? modeActive : {}) }}>Звичайно</button>
            <button type="button" onClick={() => setMode("deep")} style={{ ...modeButton, ...(mode === "deep" ? modeActive : {}) }}>Глибше</button>
          </div>
          <button type="submit" disabled={busy || !status?.configured || !text.trim()} style={sendButton}><Send size={17} /></button>
        </div>
      </form>
    </main>
  );
}

function formatTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
}

const shell: React.CSSProperties = { minHeight: "100dvh", maxWidth: 760, margin: "0 auto", padding: "max(18px, env(safe-area-inset-top)) 14px calc(25px + env(safe-area-inset-bottom))", color: "#f4f2ff", display: "flex", flexDirection: "column" };
const header: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", marginBottom: 12 };
const back: React.CSSProperties = { color: "#b8b2d8", textDecoration: "none", fontWeight: 700 };
const eyebrow: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const title: React.CSSProperties = { margin: "2px 0 0", fontSize: 26 };
const iconButton: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", border: "1px solid rgba(255,255,255,.1)", borderRadius: 13, background: "rgba(255,255,255,.04)", color: "#dcd8ef" };
const statusCard: React.CSSProperties = { display: "grid", gridTemplateColumns: "46px 1fr auto", gap: 11, alignItems: "center", border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.035)", borderRadius: 18, padding: 13 };
const readyBorder: React.CSSProperties = { borderColor: "rgba(93,224,154,.22)" };
const waitingBorder: React.CSSProperties = { borderColor: "rgba(255,184,77,.22)" };
const agentOrb: React.CSSProperties = { width: 46, height: 46, borderRadius: 15, display: "grid", placeItems: "center", color: "#bbb4ff", background: "radial-gradient(circle at 35% 25%, rgba(147,128,255,.36), rgba(81,62,190,.11))", border: "1px solid rgba(147,128,255,.3)" };
const muted: React.CSSProperties = { margin: "4px 0 0", color: "rgba(255,255,255,.57)", fontSize: 12, lineHeight: 1.45 };
const badge: React.CSSProperties = { borderRadius: 999, padding: "6px 8px", fontSize: 9, letterSpacing: ".08em", whiteSpace: "nowrap" };
const good: React.CSSProperties = { color: "#9af0bd", border: "1px solid rgba(93,224,154,.25)", background: "rgba(93,224,154,.08)" };
const waiting: React.CSSProperties = { color: "#ffd28b", border: "1px solid rgba(255,184,77,.25)", background: "rgba(255,184,77,.08)" };
const securityLine: React.CSSProperties = { display: "flex", gap: 6, alignItems: "center", color: "rgba(255,255,255,.45)", fontSize: 10, padding: "9px 4px" };
const errorBox: React.CSSProperties = { border: "1px solid rgba(255,100,100,.3)", background: "rgba(255,100,100,.055)", color: "#ffaaa7", borderRadius: 14, padding: 11, marginBottom: 10, fontSize: 12 };
const chatPanel: React.CSSProperties = { flex: 1, minHeight: 340, display: "flex", flexDirection: "column", gap: 9, padding: "8px 0 14px", overflow: "auto" };
const empty: React.CSSProperties = { margin: "auto", maxWidth: 370, textAlign: "center", display: "grid", placeItems: "center", gap: 8, color: "rgba(255,255,255,.48)", fontSize: 13, lineHeight: 1.5, padding: 30 };
const bubble: React.CSSProperties = { maxWidth: "88%", borderRadius: 18, padding: "11px 13px", border: "1px solid rgba(255,255,255,.08)" };
const userBubble: React.CSSProperties = { alignSelf: "flex-end", background: "rgba(118,102,255,.13)", borderColor: "rgba(138,123,255,.2)", borderBottomRightRadius: 6 };
const agentBubble: React.CSSProperties = { alignSelf: "flex-start", background: "rgba(255,255,255,.035)", borderBottomLeftRadius: 6 };
const messageMeta: React.CSSProperties = { display: "flex", justifyContent: "space-between", gap: 12, color: "rgba(255,255,255,.38)", fontSize: 9, marginBottom: 5, textTransform: "uppercase", letterSpacing: ".07em" };
const messageText: React.CSSProperties = { whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.5, fontSize: 14 };
const redactedNote: React.CSSProperties = { marginTop: 7, color: "#ffd28b", fontSize: 10 };
const typing: React.CSSProperties = { color: "rgba(255,255,255,.62)", fontSize: 13 };
const composer: React.CSSProperties = { position: "sticky", bottom: 0, border: "1px solid rgba(255,255,255,.1)", background: "rgba(10,11,15,.94)", backdropFilter: "blur(20px)", borderRadius: 19, padding: 10, boxShadow: "0 -10px 35px rgba(0,0,0,.18)" };
const textarea: React.CSSProperties = { width: "100%", border: 0, outline: 0, resize: "none", background: "transparent", color: "#fff", fontFamily: "inherit", fontSize: 14, lineHeight: 1.45, minHeight: 48 };
const composerBottom: React.CSSProperties = { display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" };
const modeWrap: React.CSSProperties = { display: "flex", gap: 5, alignItems: "center", color: "rgba(255,255,255,.42)" };
const modeButton: React.CSSProperties = { border: "1px solid transparent", background: "transparent", color: "rgba(255,255,255,.45)", borderRadius: 999, padding: "5px 8px", fontSize: 10 };
const modeActive: React.CSSProperties = { borderColor: "rgba(139,124,255,.25)", background: "rgba(118,102,255,.09)", color: "#cfc9ff" };
const sendButton: React.CSSProperties = { width: 42, height: 42, display: "grid", placeItems: "center", borderRadius: 14, border: "1px solid rgba(139,124,255,.35)", background: "rgba(118,102,255,.18)", color: "#e2deff" };
