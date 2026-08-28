"use client";

import Link from "next/link";
import {
  Activity,
  Bot,
  Brain,
  Database,
  FileText,
  Folder,
  KeyRound,
  Link2,
  ListChecks,
  MemoryStick,
  MessageCircle,
  Settings,
  ShieldCheck,
  Users,
} from "lucide-react";
import { type ComponentType, useEffect, useMemo, useState } from "react";
import { core, formatDate } from "@/lib/core-client";

type Icon = ComponentType<{ size?: number; strokeWidth?: number }>;
type Health = { service: string; status: string; version: string; storage: string };
type AgentStatus = { configured: boolean; provider: string };
type Task = {
  id: string;
  objective: string;
  status: string;
  current_step?: string | null;
  blocker?: string | null;
  updated_at: string;
};
type ConnectorState = { connector_key: string; status: string };
type Message = { role: "user" | "agent"; text: string; created_at?: string | null };
type Conversation = { messages: Message[]; count: number; persistent: boolean };
type Session = { authenticated: boolean; role: "owner" | "operator" | "viewer"; capabilities: string[] };
type ModuleLink = { href: string; label: string; detail: string; icon: Icon; ownerOnly?: boolean };

const modules: ModuleLink[] = [
  { href: "/chat", label: "ALTER", detail: "Єдина постійна розмова з памʼяттю", icon: MessageCircle },
  { href: "/tasks", label: "Задачі", detail: "Планування, контроль і перевірка", icon: ListChecks },
  { href: "/memory", label: "Памʼять", detail: "Профіль, факти й довготривалі записи", icon: MemoryStick },
  { href: "/knowledge", label: "Knowledge", detail: "Пошук по памʼяті та документах", icon: Brain },
  { href: "/documents", label: "Документи", detail: "PDF, DOCX, XLSX та OCR", icon: FileText },
  { href: "/files", label: "Файли", detail: "Файлові записи та нотатки", icon: Folder },
  { href: "/models", label: "Моделі", detail: "Cloud і local model registry", icon: Bot },
  { href: "/gateway", label: "Конектори", detail: "Реальний стан і capabilities", icon: Link2 },
  { href: "/rules", label: "Правила", detail: "Policy Engine та approvals", icon: ShieldCheck },
  { href: "/vault", label: "Vault", detail: "Зашифровані секрети та aliases", icon: KeyRound, ownerOnly: true },
  { href: "/people", label: "Люди", detail: "RBAC, ролі та запрошення", icon: Users, ownerOnly: true },
  { href: "/settings", label: "Налаштування", detail: "Autonomy, privacy та поведінка", icon: Settings, ownerOnly: true },
  { href: "/status", label: "System Status", detail: "Що реально працює зараз", icon: Activity },
];

const terminalStatuses = new Set(["done", "failed", "cancelled"]);

export default function HomePage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [connectors, setConnectors] = useState<ConnectorState[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [warnings, setWarnings] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const [healthResult, agentResult, tasksResult, connectorsResult, conversationResult, sessionResult] = await Promise.allSettled([
        core<Health>("/health"),
        core<AgentStatus>("/agent/status"),
        core<Task[]>("/tasks?limit=50"),
        core<ConnectorState[]>("/connectors"),
        core<Conversation>("/conversation?limit=6"),
        fetch("/api/auth/session", { cache: "no-store" }).then(async (response) => response.ok ? response.json() as Promise<Session> : null),
      ]);
      if (cancelled) return;

      if (healthResult.status === "fulfilled") setHealth(healthResult.value);
      if (agentResult.status === "fulfilled") setAgent(agentResult.value);
      if (tasksResult.status === "fulfilled") setTasks(tasksResult.value);
      if (connectorsResult.status === "fulfilled") setConnectors(connectorsResult.value);
      if (conversationResult.status === "fulfilled") setConversation(conversationResult.value);
      if (sessionResult.status === "fulfilled" && sessionResult.value) setSession(sessionResult.value);

      const failed: string[] = [];
      if (healthResult.status === "rejected") failed.push("Core health");
      if (agentResult.status === "rejected") failed.push("AI status");
      if (tasksResult.status === "rejected") failed.push("Tasks");
      if (connectorsResult.status === "rejected") failed.push("Connectors");
      if (conversationResult.status === "rejected") failed.push("Conversation");
      setWarnings(failed);
      setLoading(false);
    }
    void load();
    return () => { cancelled = true; };
  }, []);

  const currentTask = useMemo(() => {
    return [...tasks]
      .filter((task) => !terminalStatuses.has(task.status))
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())[0] ?? null;
  }, [tasks]);

  const connectedCount = useMemo(
    () => connectors.filter((connector) => connector.status === "connected").length,
    [connectors],
  );

  const latestAgentMessage = useMemo(
    () => [...(conversation?.messages ?? [])].reverse().find((message) => message.role === "agent") ?? null,
    [conversation],
  );

  const visibleModules = useMemo(
    () => modules.filter((module) => !module.ownerOnly || session?.role === "owner"),
    [session],
  );

  return (
    <main style={shell}>
      <header style={header}>
        <div>
          <div style={eyebrow}>ALTER · CONTROL PLANE</div>
          <h1 style={title}>Головна</h1>
        </div>
        <Link href="/status" style={statusLink}><Activity size={17} /> Статус</Link>
      </header>

      <section style={statusGrid}>
        <Status label="Core" value={health?.status === "ok" ? "online" : loading ? "checking" : "offline"} good={health?.status === "ok"} />
        <Status label="Storage" value={health?.storage ?? "—"} good={health?.storage === "postgres"} />
        <Status label="AI" value={agent?.configured ? "connected" : loading ? "checking" : "waiting"} good={Boolean(agent?.configured)} />
        <Status label="Connectors" value={`${connectedCount} connected`} good={connectedCount > 0} />
      </section>

      {warnings.length > 0 && (
        <section style={warningBox}>
          Частина модулів недоступна: {warnings.join(", ")}. Решта dashboard продовжує працювати.
        </section>
      )}

      <section style={{ ...panel, ...hero }}>
        <div style={heroIcon}><MessageCircle size={24} /></div>
        <div style={{ minWidth: 0 }}>
          <div style={eyebrow}>ЄДИНА РОЗМОВА · POSTGRES MEMORY</div>
          <h2 style={sectionTitle}>Поговорити з ALTER</h2>
          <p style={description}>
            {latestAgentMessage
              ? latestAgentMessage.text
              : "Чат зберігає історію, використовує памʼять і knowledge context. Тут більше немає окремого дубльованого чату."}
          </p>
        </div>
        <Link href="/chat" style={primaryAction}>Відкрити чат</Link>
      </section>

      <section style={{ ...panel, marginTop: 12 }}>
        <div style={sectionHead}>
          <div>
            <div style={eyebrow}>ПОТОЧНА ЗАДАЧА · LIVE CORE STATE</div>
            <h2 style={sectionTitle}>{currentTask?.objective ?? "Немає активної задачі"}</h2>
          </div>
          <Link href="/tasks" style={secondaryAction}>Усі задачі</Link>
        </div>
        {currentTask ? (
          <div style={taskMeta}>
            <span><b>Статус:</b> {currentTask.status}</span>
            <span><b>Крок:</b> {currentTask.current_step || "—"}</span>
            <span><b>Оновлено:</b> {formatDate(currentTask.updated_at)}</span>
            {currentTask.blocker && <span style={{ color: "#ffd28b" }}><b>Блокер:</b> {currentTask.blocker}</span>}
            <Link href={`/tasks/${currentTask.id}`} style={primaryAction}>Відкрити Task Inspector</Link>
          </div>
        ) : (
          <div style={taskMeta}>
            <span style={description}>Створи задачу — ALTER одразу спробує сформувати перевірений план.</span>
            <Link href="/tasks" style={primaryAction}>Створити задачу</Link>
          </div>
        )}
      </section>

      <section style={{ marginTop: 16 }}>
        <div style={sectionHead}><div><div style={eyebrow}>МОДУЛІ</div><h2 style={sectionTitle}>Одна функція — одна сторінка</h2></div></div>
        <div style={moduleGrid}>
          {visibleModules.map(({ href, label, detail, icon: Icon }) => (
            <Link key={href} href={href} style={moduleCard}>
              <div style={moduleIcon}><Icon size={19} /></div>
              <strong>{label}</strong>
              <span style={description}>{detail}</span>
            </Link>
          ))}
        </div>
      </section>

      <footer style={footer}>
        Browser/Android control залишаються відкладеними. Інші модулі показуються тільки там, де вже існує реальна реалізація.
      </footer>
    </main>
  );
}

function Status({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div style={statusCard}>
      <span style={statusLabel}>{label}</span>
      <strong style={{ color: good ? "#9af0bd" : "#ffd28b" }}>{value}</strong>
    </div>
  );
}

const shell: React.CSSProperties = { minHeight: "100dvh", maxWidth: 900, margin: "0 auto", padding: "max(18px, env(safe-area-inset-top)) 14px calc(86px + env(safe-area-inset-bottom))", color: "#f4f2ff" };
const header: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 14 };
const eyebrow: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const title: React.CSSProperties = { margin: "2px 0 0", fontSize: 30 };
const sectionTitle: React.CSSProperties = { margin: "3px 0 0", fontSize: 20 };
const description: React.CSSProperties = { color: "rgba(255,255,255,.58)", fontSize: 12, lineHeight: 1.5, margin: "6px 0 0", whiteSpace: "pre-wrap" };
const panel: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.035)", borderRadius: 20, padding: 14 };
const hero: React.CSSProperties = { display: "grid", gridTemplateColumns: "50px minmax(0,1fr) auto", gap: 12, alignItems: "center" };
const heroIcon: React.CSSProperties = { width: 50, height: 50, display: "grid", placeItems: "center", borderRadius: 16, color: "#c6bfff", background: "rgba(118,102,255,.12)", border: "1px solid rgba(143,126,255,.24)" };
const statusGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(4,minmax(0,1fr))", gap: 8, marginBottom: 12 };
const statusCard: React.CSSProperties = { minWidth: 0, border: "1px solid rgba(255,255,255,.08)", background: "rgba(255,255,255,.025)", borderRadius: 15, padding: 10, display: "grid", gap: 4 };
const statusLabel: React.CSSProperties = { color: "rgba(255,255,255,.42)", fontSize: 9, textTransform: "uppercase", letterSpacing: ".08em" };
const statusLink: React.CSSProperties = { display: "flex", alignItems: "center", gap: 6, minHeight: 40, padding: "0 12px", borderRadius: 12, border: "1px solid rgba(255,255,255,.1)", color: "#d8d4eb", textDecoration: "none", fontWeight: 700, fontSize: 12 };
const primaryAction: React.CSSProperties = { display: "inline-flex", alignItems: "center", justifyContent: "center", minHeight: 40, padding: "0 12px", borderRadius: 12, border: "1px solid rgba(143,126,255,.35)", background: "rgba(111,91,255,.14)", color: "#ddd8ff", textDecoration: "none", fontWeight: 750, fontSize: 12, whiteSpace: "nowrap" };
const secondaryAction: React.CSSProperties = { ...primaryAction, background: "rgba(255,255,255,.035)", borderColor: "rgba(255,255,255,.1)", color: "#c8c4d8" };
const warningBox: React.CSSProperties = { ...panel, marginBottom: 12, borderColor: "rgba(255,184,77,.25)", color: "#ffd28b", fontSize: 12, lineHeight: 1.45 };
const sectionHead: React.CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 };
const taskMeta: React.CSSProperties = { display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, color: "rgba(255,255,255,.6)", fontSize: 12, marginTop: 12 };
const moduleGrid: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 9, marginTop: 10 };
const moduleCard: React.CSSProperties = { minHeight: 118, border: "1px solid rgba(255,255,255,.09)", background: "rgba(255,255,255,.03)", borderRadius: 17, padding: 13, color: "inherit", textDecoration: "none", display: "grid", alignContent: "start", gap: 6 };
const moduleIcon: React.CSSProperties = { width: 36, height: 36, display: "grid", placeItems: "center", borderRadius: 11, color: "#bdb5ff", background: "rgba(118,102,255,.1)" };
const footer: React.CSSProperties = { color: "rgba(255,255,255,.35)", fontSize: 10, lineHeight: 1.45, padding: "18px 3px 0" };
