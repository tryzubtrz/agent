"use client";

import Link from "next/link";
import { Menu, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Session = { authenticated: boolean; role: "owner" | "operator" | "viewer"; capabilities: string[] };
type Tool = { href: string; label: string; detail: string; ownerOnly?: boolean; capability?: string };

const tools: Tool[] = [
  { href: "/chat", label: "ALTER", detail: "Дружній AI-чат", capability: "conversation" },
  { href: "/voice", label: "Голос", detail: "Диктування + озвучення", capability: "conversation" },
  { href: "/tasks", label: "Задачі", detail: "Inspector, pause/resume/retry/cancel", capability: "tasks.read" },
  { href: "/documents", label: "Документи", detail: "PDF · DOCX · XLSX · OCR", capability: "documents" },
  { href: "/files", label: "Файли", detail: "Текстові файли та нотатки", capability: "documents" },
  { href: "/knowledge", label: "Knowledge", detail: "Пошук по памʼяті й документах", capability: "knowledge" },
  { href: "/automations", label: "Автоматизації", detail: "Розклад і Run now", capability: "automations" },
  { href: "/notifications", label: "Сповіщення", detail: "In-app центр подій", capability: "notifications.read" },
  { href: "/calendar", label: "Календар", detail: "Локальні події ALTER", capability: "calendar.read" },
  { href: "/contacts", label: "Контакти", detail: "Локальна адресна книга", capability: "contacts.read" },
  { href: "/models", label: "Моделі", detail: "Cloud + local model registry", capability: "models.read" },
  { href: "/media", label: "Media", detail: "Image/video generation provider", ownerOnly: true },
  { href: "/market", label: "Market", detail: "Перевірений каталог ринкових джерел", capability: "models.read" },
  { href: "/memory", label: "Памʼять", detail: "Перегляд і керування записами", capability: "memory.read" },
  { href: "/gateway", label: "Конектори", detail: "Health і capabilities", capability: "connectors.read" },
  { href: "/vault", label: "Vault", detail: "Encrypted secrets + rotation", ownerOnly: true },
  { href: "/people", label: "Люди", detail: "RBAC та запрошення", ownerOnly: true },
  { href: "/settings", label: "Налаштування", detail: "Мова, autonomy, privacy", ownerOnly: true },
  { href: "/status", label: "System Status", detail: "Що реально працює", capability: "connectors.read" },
];

export default function ToolLauncher() {
  const [open, setOpen] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  useEffect(() => { fetch("/api/auth/session", { cache: "no-store" }).then((r) => r.ok ? r.json() : null).then(setSession).catch(() => setSession(null)); }, []);

  const visible = useMemo(() => {
    if (!session) return [];
    if (session.role === "owner") return tools;
    const caps = new Set(session.capabilities || []);
    return tools.filter((tool) => !tool.ownerOnly && (!tool.capability || caps.has(tool.capability) || caps.has(tool.capability.replace(".read", ""))));
  }, [session]);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} aria-label="Відкрити всі модулі ALTER" style={launcher}><Menu size={20} /><span>Модулі</span></button>
      {open && <div style={overlay} onClick={() => setOpen(false)}>
        <section style={sheet} onClick={(event) => event.stopPropagation()}>
          <div style={head}><div><strong style={{ fontSize: 18 }}>ALTER · модулі</strong><div style={muted}>{session?.role === "owner" ? "Owner — повний доступ" : `${session?.role || "member"} — доступ за RBAC`}</div></div><button type="button" onClick={() => setOpen(false)} style={close}><X size={18} /></button></div>
          <div style={grid}>{visible.map((tool) => <Link key={tool.href} href={tool.href} onClick={() => setOpen(false)} style={item}><strong>{tool.label}</strong><span style={muted}>{tool.detail}</span></Link>)}</div>
          <div style={footer}>Android, керування ПК, Telegram, Gmail і TikTok навмисно не показуються — вони відкладені.</div>
        </section>
      </div>}
    </>
  );
}

const launcher: React.CSSProperties = { position: "fixed", zIndex: 70, right: 14, bottom: "calc(14px + env(safe-area-inset-bottom))", minHeight: 42, borderRadius: 999, padding: "0 14px", border: "1px solid rgba(143,126,255,.35)", background: "rgba(16,17,23,.92)", backdropFilter: "blur(18px)", color: "#ddd8ff", display: "flex", alignItems: "center", gap: 7, boxShadow: "0 12px 36px rgba(0,0,0,.35)", fontWeight: 700 };
const overlay: React.CSSProperties = { position: "fixed", inset: 0, zIndex: 100, background: "rgba(0,0,0,.7)", backdropFilter: "blur(10px)", display: "flex", alignItems: "flex-end", justifyContent: "center", padding: 10 };
const sheet: React.CSSProperties = { width: "min(760px,100%)", maxHeight: "85dvh", overflow: "auto", border: "1px solid rgba(255,255,255,.12)", background: "#0b0c10", borderRadius: 24, padding: 15, color: "#f4f2ff" };
const head: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 12 };
const close: React.CSSProperties = { width: 38, height: 38, display: "grid", placeItems: "center", borderRadius: 12, border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.04)", color: "#fff" };
const grid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(145px,1fr))", gap: 8 };
const item: React.CSSProperties = { minHeight: 76, border: "1px solid rgba(255,255,255,.09)", background: "rgba(255,255,255,.035)", borderRadius: 15, padding: 11, color: "inherit", textDecoration: "none", display: "grid", alignContent: "center", gap: 4 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.5)", fontSize: 11, lineHeight: 1.4 };
const footer: React.CSSProperties = { color: "rgba(255,255,255,.4)", fontSize: 10, lineHeight: 1.45, marginTop: 12, padding: "0 3px" };
