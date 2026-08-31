"use client";

import {
  AlertTriangle,
  Bell,
  Bot,
  Brain,
  Check,
  ChevronRight,
  CirclePause,
  Clock3,
  Database,
  FileText,
  Folder,
  Globe2,
  KeyRound,
  Link2,
  ListChecks,
  MemoryStick,
  Mic,
  Monitor,
  MoreHorizontal,
  Play,
  Plus,
  RefreshCw,
  Send,
  Settings,
  Shield,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Store,
  Terminal,
  UserRound,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { type ComponentType, type FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import styles from "./cockpit.module.css";

type Screen =
  | "home"
  | "tasks"
  | "rules"
  | "memory"
  | "audit"
  | "connectors"
  | "browser"
  | "android"
  | "models"
  | "vault"
  | "people"
  | "files"
  | "market"
  | "settings";

type Icon = ComponentType<{ size?: number; strokeWidth?: number }>;
type TaskStatus =
  | "intake"
  | "planning"
  | "ready"
  | "executing"
  | "awaiting_approval"
  | "awaiting_login"
  | "awaiting_mfa"
  | "blocked_by_rule"
  | "recovering"
  | "paused"
  | "done"
  | "failed"
  | "cancelled";
type ChatMode = "chat" | "task";
type ReasoningMode = "quick" | "normal" | "deep" | "plan";

type Task = {
  id: string;
  objective: string;
  status: TaskStatus;
  acceptance_criteria: string[];
  current_step: string | null;
  blocker: string | null;
  updated_at: string;
  created_at: string;
};

type PolicyRule = {
  id: string;
  original_text: string;
  category: string;
  effect: "allow" | "deny" | "require_approval";
  enabled: boolean;
  priority: number;
};

type MemoryItem = {
  id?: string;
  namespace: string;
  key: string;
  value: unknown;
  updated_at?: string;
};

type AuditEvent = {
  id: number;
  task_id?: string | null;
  actor_type: string;
  actor_id?: string | null;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

type ConnectorState = {
  id?: string;
  connector_key: string;
  status: "available" | "connected" | "degraded" | "blocked" | "not_configured" | "unavailable";
  capabilities: string[];
  details: Record<string, unknown>;
  checked_at?: string | null;
  updated_at?: string;
};

type Health = { service: string; status: string; version: string; storage: string };
type AgentStatus = {
  provider: string;
  configured: boolean;
  bot_id_configured: boolean;
  credential_configured: boolean;
  action: string;
  side_effect_boundary: string;
};
type Capability = { number: number; key: string; label: string; status: string; evidence: string; next_step?: string };
type CapabilityResponse = { spec_version: string; counts: Record<string, number>; capabilities: Capability[] };
type ModelItem = {
  id: string;
  display_name: string;
  provider: string;
  capabilities: string[];
  configured: boolean;
  source: "cloud" | "local";
  install_state: string;
  requirements?: string;
};
type ModelCatalog = { models: ModelItem[]; configured: number; local_runtime_connected: boolean };
type Module = { id: Screen; label: string; icon: Icon };

type Message = { role: "user" | "agent"; text: string };

const modules: Module[] = [
  { id: "home", label: "ALTER", icon: Bot },
  { id: "files", label: "Файли", icon: Folder },
  { id: "browser", label: "Браузер", icon: Globe2 },
  { id: "settings", label: "Linux", icon: Terminal },
  { id: "android", label: "Android", icon: Smartphone },
  { id: "rules", label: "Правила", icon: Shield },
  { id: "vault", label: "Сховище", icon: KeyRound },
  { id: "models", label: "Моделі", icon: Brain },
  { id: "market", label: "Маркет", icon: Store },
  { id: "tasks", label: "Задачі", icon: ListChecks },
  { id: "connectors", label: "Конектори", icon: Link2 },
  { id: "memory", label: "Памʼять", icon: MemoryStick },
  { id: "people", label: "Люди", icon: Users },
  { id: "settings", label: "Налаштування", icon: Settings },
];

const statusLabel: Record<TaskStatus, string> = {
  intake: "Прийнято",
  planning: "Планує",
  ready: "Готово до виконання",
  executing: "Виконує",
  awaiting_approval: "Чекає на мене",
  awaiting_login: "Потрібен вхід",
  awaiting_mfa: "Потрібна 2FA",
  blocked_by_rule: "Заблоковано",
  recovering: "Відновлюється",
  paused: "Пауза",
  done: "Готово",
  failed: "Помилка",
  cancelled: "Скасовано",
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
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body?.detail || body);
    } catch {
      detail = await response.text();
    }
    throw new Error(detail || `ALTER Core returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function LogoMark({ small = false }: { small?: boolean }) {
  return <span className={small ? styles.logoSmall : styles.logoMark}>A</span>;
}

function StatusPill({ children, tone = "green" }: { children: React.ReactNode; tone?: "green" | "violet" | "amber" | "red" | "muted" }) {
  return <span className={`${styles.statusPill} ${styles[tone]}`}><i />{children}</span>;
}

function formatAgo(value?: string | null) {
  if (!value) return "—";
  const diff = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(diff) || diff < 0) return new Date(value).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" });
  const minutes = Math.max(1, Math.round(diff / 60_000));
  if (minutes < 60) return `${minutes} хв тому`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} год тому`;
  return new Date(value).toLocaleDateString("uk-UA");
}

function taskTone(status: TaskStatus): "green" | "violet" | "amber" | "red" | "muted" {
  if (status === "done") return "green";
  if (["failed", "cancelled", "blocked_by_rule"].includes(status)) return "red";
  if (["awaiting_approval", "awaiting_login", "awaiting_mfa"].includes(status)) return "amber";
  if (["executing", "recovering"].includes(status)) return "violet";
  return "muted";
}

function connectorTone(status: ConnectorState["status"]): "green" | "violet" | "amber" | "red" | "muted" {
  if (status === "connected") return "green";
  if (status === "available") return "violet";
  if (status === "degraded" || status === "not_configured") return "amber";
  return "red";
}

export default function Page() {
  const [screen, setScreen] = useState<Screen>("home");
  const [health, setHealth] = useState<Health | null>(null);
  const [agent, setAgent] = useState<AgentStatus | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [rules, setRules] = useState<PolicyRule[]>([]);
  const [memory, setMemory] = useState<MemoryItem[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [connectors, setConnectors] = useState<ConnectorState[]>([]);
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [models, setModels] = useState<ModelCatalog | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [command, setCommand] = useState("");
  const [chatMode, setChatMode] = useState<ChatMode>("chat");
  const [reasoningMode, setReasoningMode] = useState<ReasoningMode>("normal");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    const requests = await Promise.allSettled([
      core<Health>("/health"),
      core<Task[]>("/tasks"),
      core<PolicyRule[]>("/policies"),
      core<MemoryItem[]>("/memory"),
      core<AuditEvent[]>("/audit?limit=60"),
      core<ConnectorState[]>("/connectors"),
      core<AgentStatus>("/agent/status"),
      core<CapabilityResponse>("/system/capabilities"),
      core<ModelCatalog>("/models/catalog"),
    ]);
    const [h, t, r, m, a, c, ag, cap, model] = requests;
    if (h.status === "fulfilled") setHealth(h.value);
    if (t.status === "fulfilled") setTasks(t.value);
    if (r.status === "fulfilled") setRules(r.value);
    if (m.status === "fulfilled") setMemory(m.value);
    if (a.status === "fulfilled") setAudit(a.value);
    if (c.status === "fulfilled") setConnectors(c.value);
    if (ag.status === "fulfilled") setAgent(ag.value);
    if (cap.status === "fulfilled") setCapabilities(cap.value.capabilities);
    if (model.status === "fulfilled") setModels(model.value);
    const failures = requests.filter((item) => item.status === "rejected");
    setError(failures.length === requests.length ? "ALTER Core зараз недоступний." : "");
    setLoading(false);
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const activeTasks = useMemo(() => tasks.filter((task) => !["done", "failed", "cancelled"].includes(task.status)), [tasks]);
  const currentTask = activeTasks[0] ?? tasks[0] ?? null;
  const connected = useMemo(() => connectors.filter((item) => item.status === "connected").length, [connectors]);
  const browserCapability = capabilities.find((item) => item.key === "browser");
  const androidCapability = capabilities.find((item) => item.key === "android");
  const localModelCapability = capabilities.find((item) => item.key === "model_install");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const objective = command.trim();
    if (!objective || sending) return;
    setSending(true);
    setError("");
    setMessages((items) => [...items, { role: "user", text: objective }]);
    setCommand("");
    try {
      if (chatMode === "chat") {
        const response = await core<{ response: string }>("/agent/think", {
          method: "POST",
          body: JSON.stringify({ objective, context: "ALTER Cockpit mobile session", mode: reasoningMode }),
        });
        setMessages((items) => [...items, { role: "agent", text: response.response }]);
      } else {
        const task = await core<Task>("/tasks", {
          method: "POST",
          body: JSON.stringify({
            objective,
            acceptance_criteria: ["Результат відповідає дорученню та має перевіряльні докази виконання."],
          }),
        });
        let planned = false;
        if (agent?.configured) {
          try {
            await core(`/tasks/${task.id}/plan`, {
              method: "POST",
              body: JSON.stringify({ context: "Створено з Cockpit AUTO flow", mode: reasoningMode === "quick" ? "normal" : reasoningMode }),
            });
            planned = true;
          } catch {
            planned = false;
          }
        }
        setMessages((items) => [...items, {
          role: "agent",
          text: planned
            ? "Задачу створено, план збережено. Вона вже є у Task Inspector."
            : "Задачу створено і збережено. Відкрий Task Inspector для наступного кроку.",
        }]);
        await refresh();
      }
    } catch (err) {
      const text = err instanceof Error ? err.message : "Невідома помилка";
      setMessages((items) => [...items, { role: "agent", text: `Не вдалося виконати запит: ${text}` }]);
    } finally {
      setSending(false);
    }
  }

  async function taskControl(action: "pause" | "resume") {
    if (!currentTask) return;
    try {
      await core(`/tasks/${currentTask.id}/control`, { method: "POST", body: JSON.stringify({ action }) });
      await refresh();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Команда не виконана");
    }
  }

  return (
    <main className={styles.shell}>
      <div className={styles.warmGlowOne} /><div className={styles.warmGlowTwo} />
      <div className={styles.surface}>
        <header className={styles.header}>
          <button className={styles.wordmark} onClick={() => setScreen("home")}>ALTER</button>
          <button className={styles.logoButton} onClick={() => setScreen("home")} aria-label="ALTER"><LogoMark /></button>
          <button className={styles.bell} onClick={() => setScreen("audit")} aria-label="Сповіщення"><Bell size={21} /><i /></button>
        </header>

        {screen !== "home" && (
          <div className={styles.pageHeading}>
            <button onClick={() => setScreen("home")} className={styles.backButton}>‹</button>
            <div><span>ALTER CONTROL PLANE</span><h1>{modules.find((item) => item.id === screen)?.label ?? screen}</h1></div>
          </div>
        )}

        {error && <div className={styles.errorBanner}><AlertTriangle size={17} /> {error}<button onClick={() => void refresh()}><RefreshCw size={16} /></button></div>}
        {notice && <div className={styles.notice} onClick={() => setNotice("")}>{notice}<X size={15} /></div>}

        {screen === "home" && (
          <>
            <div className={styles.statusRow}>
              <StatusPill tone={health?.status === "ok" ? "green" : "amber"}>{health?.status === "ok" ? "Core online" : loading ? "Перевіряю" : "Core offline"}</StatusPill>
              <StatusPill tone={agent?.configured ? "violet" : "amber"}>{agent?.configured ? "AI connected" : "AI waiting"}</StatusPill>
              <span className={styles.microPill}><ListChecks size={14} /> {activeTasks.length} активні задачі</span>
            </div>

            <section className={styles.hero}>
              <div className={styles.heroCopy}>
                <span className={styles.heroKicker}>Зараз</span>
                <h1>{currentTask?.objective ?? "ALTER готовий до нової задачі"}</h1>
                <div className={styles.progress}><span style={{ width: currentTask?.status === "done" ? "100%" : currentTask?.status === "executing" ? "68%" : currentTask ? "34%" : "4%" }} /></div>
                <div className={styles.heroMeta}>
                  <div><Globe2 size={21} /><span><small>Поточний стан</small><b>{currentTask ? statusLabel[currentTask.status] : "Вільний"}</b></span></div>
                  <ChevronRight size={18} />
                  <div><Sparkles size={20} /><span><small>Далі</small><b>{currentTask?.current_step || (currentTask ? "Відкрити Task Inspector" : "Дай доручення нижче")}</b></span></div>
                </div>
              </div>
              <button className={styles.heroOrb} onClick={() => setScreen("tasks")}><Play size={28} fill="currentColor" /></button>
              <div className={styles.heroActions}>
                <button disabled={!currentTask || currentTask.status === "paused"} onClick={() => void taskControl("pause")}><CirclePause size={19} />Пауза</button>
                <Link href={currentTask ? `/tasks/${currentTask.id}` : "/status"}><Monitor size={19} />Live-view</Link>
                <Link className={styles.primaryOutline} href={currentTask ? `/tasks/${currentTask.id}` : "/status"}><Bot size={19} />Взяти керування</Link>
              </div>
              <button className={styles.emergency} disabled={!currentTask || currentTask.status === "paused"} onClick={() => void taskControl("pause")}><Shield size={20} /><span>ЕКСТРЕНА ПАУЗА</span><b>Зупинити поточну задачу ALTER</b></button>
            </section>

            <section className={styles.moduleGrid} aria-label="Модулі ALTER">
              {modules.map(({ id, label, icon: ModuleIcon }, index) => (
                <button key={`${id}-${label}`} onClick={() => setScreen(id)} className={id === "home" ? styles.moduleActive : ""}>
                  <ModuleIcon size={29} strokeWidth={1.45} />
                  <span>{label}</span>
                  {label === "Задачі" && activeTasks.length > 0 && <i>{Math.min(activeTasks.length, 99)}</i>}
                  {index === 0 && <em />}
                </button>
              ))}
            </section>

            <ActivityPanel events={audit} tasks={tasks} onOpen={() => setScreen("audit")} />

            {messages.length > 0 && (
              <section className={styles.chatCard}>
                <div className={styles.chatTabs}><b>Чат</b><span>Останні повідомлення</span></div>
                {messages.slice(-4).map((message, index) => (
                  <div className={styles.message} key={`${message.role}-${index}`}>
                    {message.role === "agent" ? <LogoMark small /> : <span className={styles.avatar}>В</span>}
                    <div><small>{message.role === "agent" ? "ALTER" : "Ви"}</small><p>{message.text}</p></div>
                  </div>
                ))}
              </section>
            )}

            <form className={styles.composer} onSubmit={submit}>
              <button type="button" className={styles.plus} onClick={() => setScreen("files")}><Plus size={24} /></button>
              <div className={styles.inputWrap}>
                <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder={chatMode === "task" ? "Дайте нову задачу або уточнення…" : "Напишіть ALTER…"} disabled={sending} />
                <button type="button" onClick={() => setNotice("Голосовий runtime ще не підключений.")}><Mic size={20} /></button>
              </div>
              <button className={styles.send} disabled={sending || !command.trim()} aria-label="Надіслати"><Send size={18} /></button>
              <div className={styles.composerRow}>
                <button type="button" onClick={() => setNotice("Живий голос буде доступний після підключення voice runtime.")}><Mic size={17} />Говорити</button>
                <button type="button" onClick={() => setNotice("Screen handoff буде активний після підключення Browser/Remote PC runtime.")}><Monitor size={17} />Екран</button>
                <button type="button" className={chatMode === "task" ? styles.modeActive : ""} onClick={() => setChatMode(chatMode === "chat" ? "task" : "chat")}>{chatMode === "task" ? "Задача" : "Розмова"}</button>
                <select value={reasoningMode} onChange={(e) => setReasoningMode(e.target.value as ReasoningMode)} aria-label="Режим ALTER">
                  <option value="quick">FAST</option>
                  <option value="normal">AUTO</option>
                  <option value="deep">DEEP</option>
                  <option value="plan">PLAN</option>
                </select>
              </div>
            </form>
          </>
        )}

        {screen === "tasks" && <TasksScreen tasks={tasks} />}
        {screen === "rules" && <RulesScreen rules={rules} refresh={refresh} />}
        {screen === "memory" && <MemoryScreen memory={memory} />}
        {screen === "audit" && <AuditScreen events={audit} />}
        {screen === "connectors" && <ConnectorsScreen connectors={connectors} />}
        {screen === "browser" && <RuntimeScreen title="Браузер" icon={Globe2} capability={browserCapability} />}
        {screen === "android" && <RuntimeScreen title="Android" icon={Smartphone} capability={androidCapability} />}
        {screen === "models" && <ModelsScreen catalog={models} capability={localModelCapability} />}
        {screen === "vault" && <VaultScreen capabilities={capabilities} />}
        {screen === "people" && <PeopleScreen />}
        {screen === "files" && <FilesScreen capabilities={capabilities} />}
        {screen === "market" && <MarketScreen connectors={connectors} />}
        {screen === "settings" && <SettingsScreen health={health} agent={agent} connected={connected} capabilities={capabilities} refresh={refresh} />}

        {screen !== "home" && (
          <nav className={styles.bottomNav}>
            {[
              ["home", "Головна", Bot],
              ["tasks", "Задачі", ListChecks],
              ["connectors", "Конектори", Link2],
              ["memory", "Памʼять", MemoryStick],
              ["settings", "Налаштування", Settings],
            ].map(([id, label, NavIcon]) => {
              const C = NavIcon as Icon;
              return <button key={id as string} className={screen === id ? styles.navActive : ""} onClick={() => setScreen(id as Screen)}><C size={21} /><span>{label as string}</span></button>;
            })}
          </nav>
        )}
      </div>
    </main>
  );
}

function ActivityPanel({ events, tasks, onOpen }: { events: AuditEvent[]; tasks: Task[]; onOpen: () => void }) {
  const rows = events.slice(0, 4);
  if (rows.length === 0) {
    rows.push(...tasks.slice(0, 4).map((task, index) => ({
      id: -1 - index,
      task_id: task.id,
      actor_type: "ALTER",
      event_type: `task.${task.status}`,
      payload: { objective: task.objective },
      created_at: task.updated_at,
    })));
  }
  return (
    <section className={styles.activity}>
      <div className={styles.sectionTitle}><span>Остання активність</span><button onClick={onOpen}>Переглянути все <ChevronRight size={16} /></button></div>
      {rows.length === 0 && <div className={styles.empty}>Подій ще немає.</div>}
      {rows.map((event) => (
        <button key={event.id} onClick={onOpen} className={styles.activityRow}>
          <span className={styles.activityIcon}><Check size={16} /></span>
          <span><b>{event.event_type.replaceAll("_", " ")}</b><small>{String(event.payload?.objective || event.payload?.provider || event.actor_type || "ALTER")}</small></span>
          <time>{formatAgo(event.created_at)}</time><ChevronRight size={16} />
        </button>
      ))}
    </section>
  );
}

function TasksScreen({ tasks }: { tasks: Task[] }) {
  const columns: Array<{ title: string; statuses: TaskStatus[] }> = [
    { title: "Заплановано", statuses: ["intake", "planning", "ready"] },
    { title: "Виконується", statuses: ["executing", "recovering"] },
    { title: "Чекає на мене", statuses: ["awaiting_approval", "awaiting_login", "awaiting_mfa", "paused"] },
    { title: "Заблоковано", statuses: ["blocked_by_rule", "failed"] },
    { title: "Готово", statuses: ["done", "cancelled"] },
  ];
  return (
    <section className={styles.kanban}>
      {columns.map((column) => {
        const items = tasks.filter((task) => column.statuses.includes(task.status));
        return <div className={styles.kanbanColumn} key={column.title}><header><b>{column.title}</b><span>{items.length}</span></header>{items.length === 0 && <div className={styles.empty}>Порожньо</div>}{items.map((task) => <Link href={`/tasks/${task.id}`} key={task.id} className={styles.taskCard}><strong>{task.objective}</strong><small>{task.current_step || "Без активного кроку"}</small><div><StatusPill tone={taskTone(task.status)}>{statusLabel[task.status]}</StatusPill><span>{formatAgo(task.updated_at)}</span></div></Link>)}</div>;
      })}
    </section>
  );
}

function RulesScreen({ rules, refresh }: { rules: PolicyRule[]; refresh: () => Promise<void> }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  async function addRule(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await core("/policies", { method: "POST", body: JSON.stringify({ original_text: text.trim(), category: "owner_rule", effect: "deny", priority: 100 }) });
      setText("");
      await refresh();
    } finally { setBusy(false); }
  }
  return <div className={styles.stack}><form className={styles.addRule} onSubmit={addRule}><button type="button"><Plus size={22} /></button><input value={text} onChange={(e) => setText(e.target.value)} placeholder="Напишіть правило своїми словами" /><button disabled={busy || !text.trim()}><Sparkles size={18} /></button></form><div className={styles.ruleHeader}><b>Мої правила</b><span>Увімкнено: {rules.filter((item) => item.enabled).length} з {rules.length}</span></div>{rules.map((rule) => <article className={styles.ruleCard} key={rule.id}><span className={`${styles.ruleIcon} ${rule.effect === "deny" ? styles.red : rule.effect === "require_approval" ? styles.amber : styles.green}`}><Shield size={24} /></span><div><strong>{rule.original_text}</strong><small>{rule.category} · priority {rule.priority}</small></div><StatusPill tone={rule.enabled ? "green" : "muted"}>{rule.enabled ? "Активне" : "Вимкнено"}</StatusPill></article>)}<section className={styles.systemRules}><ShieldCheck size={24} /><div><b>Системні межі безпеки</b><p>Незмінні P0-правила діють окремо від ваших правил і не можуть бути вимкнені.</p></div></section></div>;
}

function MemoryScreen({ memory }: { memory: MemoryItem[] }) {
  const groups = [
    ["Профіль", "profile"],
    ["Світ / Проєкти", "world"],
    ["Епізоди", "episode"],
  ];
  return <div className={styles.stack}>{groups.map(([label, key]) => { const items = memory.filter((item) => item.namespace.toLowerCase().includes(key)); return <section className={styles.panel} key={key}><div className={styles.sectionTitle}><span>{label}</span><StatusPill tone="violet">{items.length}</StatusPill></div>{items.slice(0, 8).map((item) => <div className={styles.memoryRow} key={`${item.namespace}:${item.key}`}><MemoryStick size={18} /><span><b>{item.key}</b><small>{typeof item.value === "string" ? item.value : JSON.stringify(item.value)}</small></span></div>)}{items.length === 0 && <div className={styles.empty}>У цьому шарі ще немає записів.</div>}</section>; })}</div>;
}

function AuditScreen({ events }: { events: AuditEvent[] }) {
  return <section className={styles.panel}><div className={styles.sectionTitle}><span>Хронологія</span><StatusPill tone="green">LIVE</StatusPill></div>{events.map((event) => <div className={styles.auditRow} key={event.id}><span className={styles.timelineDot} /><div><b>{event.event_type}</b><small>{event.actor_type} · {formatAgo(event.created_at)}</small></div><MoreHorizontal size={18} /></div>)}{events.length === 0 && <div className={styles.empty}>Журнал порожній.</div>}</section>;
}

function ConnectorsScreen({ connectors }: { connectors: ConnectorState[] }) {
  return <div className={styles.stack}><div className={styles.segment}><button className={styles.segmentActive}>Через сервіс</button><button>API-ключ</button><button>Пристрій</button><button>Маркет</button></div><section className={styles.connectorGrid}>{connectors.map((connector) => <article className={styles.connectorCard} key={connector.connector_key}><span className={styles.connectorLogo}>{connector.connector_key.slice(0, 1).toUpperCase()}</span><div><strong>{connector.connector_key}</strong><StatusPill tone={connectorTone(connector.status)}>{connector.status}</StatusPill></div><small>{connector.capabilities.join(" · ") || "capabilities not reported"}</small></article>)}</section>{connectors.length === 0 && <section className={styles.panel}><div className={styles.empty}>Core не повернув список конекторів.</div></section>}</div>;
}

function RuntimeScreen({ title, icon: RuntimeIcon, capability }: { title: string; icon: Icon; capability?: Capability }) {
  const live = capability?.status === "ready";
  return <div className={styles.stack}><section className={styles.runtimeHero}><div><RuntimeIcon size={30} /><span><b>{title} Runtime</b><small>{capability?.evidence || "Стан executor-а ще не отримано."}</small></span></div><StatusPill tone={live ? "green" : "amber"}>{capability?.status || "unknown"}</StatusPill></section><section className={styles.runtimeCanvas}><div className={styles.runtimeTop}><span>{title === "Браузер" ? "Спільна сесія" : "Віртуальний пристрій"}</span><StatusPill tone={live ? "green" : "muted"}>{live ? "Підключено" : "Не підключено"}</StatusPill></div><div className={styles.runtimePlaceholder}><RuntimeIcon size={54} /><h2>{live ? `${title} доступний` : `${title} executor ще не працює`}</h2><p>{capability?.next_step || "ALTER не показує фальшиву активну сесію. Після підключення runtime тут зʼявиться live-view та контроль."}</p></div></section></div>;
}

function ModelsScreen({ catalog, capability }: { catalog: ModelCatalog | null; capability?: Capability }) {
  return <div className={styles.stack}><div className={styles.segment}><button className={styles.segmentActive}>Доступні</button><button>Довірені</button><button>На перевірці</button><button>Локальні</button><button>API</button></div>{catalog?.models.map((model) => <article className={styles.modelCard} key={model.id}><span className={styles.modelIcon}><Brain size={26} /></span><div className={styles.modelMain}><div><strong>{model.display_name}</strong><StatusPill tone={model.configured ? "green" : model.source === "local" ? "amber" : "muted"}>{model.configured ? "ОНЛАЙН" : model.install_state}</StatusPill></div><div className={styles.chips}>{model.capabilities.map((item) => <span key={item}>{item}</span>)}</div><small>{model.provider} · {model.requirements || model.source}</small></div></article>)}{!catalog && <section className={styles.panel}><div className={styles.empty}>Model catalog не завантажений.</div></section>}<section className={styles.runtimeHero}><Brain size={26} /><div><b>Локальні моделі</b><small>{capability?.evidence || "Потрібен окремий GPU/CPU runtime."}</small></div><StatusPill tone={catalog?.local_runtime_connected ? "green" : "amber"}>{catalog?.local_runtime_connected ? "CONNECTED" : "WAITING"}</StatusPill></section></div>;
}

function VaultScreen({ capabilities }: { capabilities: Capability[] }) {
  const vault = capabilities.find((item) => item.key === "vault");
  return <div className={styles.stack}><section className={styles.runtimeHero}><KeyRound size={28} /><div><b>Secrets Firewall</b><small>{vault?.evidence || "Стан Vault не отримано."}</small></div><StatusPill tone={vault?.status === "ready" ? "green" : "amber"}>{vault?.status || "unknown"}</StatusPill></section><section className={styles.panel}><div className={styles.sectionTitle}><span>Псевдоніми</span><span>Сирі значення приховані</span></div>{["vault:alter_api", "vault:database", "vault:openai_api", "vault:botpress_runtime", "vault:github_connector"].map((alias) => <div className={styles.secretRow} key={alias}><KeyRound size={18} /><span><b>{alias}</b><small>server-side alias</small></span><StatusPill tone="green">hidden</StatusPill></div>)}</section></div>;
}

function PeopleScreen() {
  return <div className={styles.peopleGrid}>{[["Власник", "Ви", "Повний контроль над усіма даними, модулями та налаштуваннями."], ["Партнер", "Не запрошено", "Доступ лише до вибраних модулів та власного ізольованого середовища."], ["Гість", "0 користувачів", "Нульовий доступ за замовчуванням; права надаються явно."]].map(([role, name, copy], index) => <section className={styles.personCard} key={role}><span className={styles.personIcon}><UserRound size={26} /></span><b>{role}</b><small>{copy}</small><StatusPill tone={index === 0 ? "green" : "muted"}>{name}</StatusPill></section>)}</div>;
}

function FilesScreen({ capabilities }: { capabilities: Capability[] }) {
  const files = capabilities.find((item) => item.key === "zip_inspection") || capabilities.find((item) => item.key === "ocr");
  return <div className={styles.stack}><section className={styles.uploadBox}><Folder size={34} /><div><b>Файли ALTER</b><p>Документи та артефакти відображаються лише після фактичного збереження в Core.</p></div><StatusPill tone={files?.status === "ready" ? "green" : "amber"}>{files?.status || "partial"}</StatusPill></section><section className={styles.panel}><div className={styles.fileRow}><FileText size={20} /><span><b>MASTER_SYSTEM_SPEC_V1.md</b><small>Канонічна специфікація в GitHub</small></span><StatusPill tone="green">repo</StatusPill></div></section></div>;
}

function MarketScreen({ connectors }: { connectors: ConnectorState[] }) {
  return <div className={styles.stack}><section className={styles.runtimeHero}><Store size={28} /><div><b>Market Sandbox</b><small>Нові інтеграції проходять permission review, sandbox і approval перед довірою.</small></div><StatusPill tone="amber">PARTIAL</StatusPill></section><section className={styles.panel}><div className={styles.sectionTitle}><span>Доступні зараз</span><span>{connectors.length}</span></div>{connectors.map((connector) => <div className={styles.fileRow} key={connector.connector_key}><Link2 size={19} /><span><b>{connector.connector_key}</b><small>{connector.capabilities.join(" · ") || "Без заявлених capability"}</small></span><StatusPill tone={connectorTone(connector.status)}>{connector.status}</StatusPill></div>)}</section></div>;
}

function SettingsScreen({ health, agent, connected, capabilities, refresh }: { health: Health | null; agent: AgentStatus | null; connected: number; capabilities: Capability[]; refresh: () => Promise<void> }) {
  const ready = capabilities.filter((item) => item.status === "ready").length;
  return <div className={styles.stack}><section className={styles.panel}><div className={styles.sectionTitle}><span>Environment Audit</span><button onClick={() => void refresh()}><RefreshCw size={16} />Оновити</button></div>{[["Core", health?.status || "unknown"], ["Storage", health?.storage || "unknown"], ["AI", agent?.configured ? "connected" : "waiting"], ["Connectors", String(connected)], ["Capabilities ready", `${ready}/${capabilities.length || 30}`]].map(([label, value]) => <div className={styles.settingRow} key={label}><span>{label}</span><b>{value}</b></div>)}</section><section className={styles.panel}><div className={styles.sectionTitle}><span>Linux / Console</span><StatusPill tone="amber">HOST REQUIRED</StatusPill></div><div className={styles.terminal}><code>$ alter audit --live</code><code>core........ {health?.status || "unknown"}</code><code>storage..... {health?.storage || "unknown"}</code><code>agent....... {agent?.configured ? "ready" : "waiting"}</code><code>remote_pc... waiting</code></div></section></div>;
}
