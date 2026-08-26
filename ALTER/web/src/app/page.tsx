"use client";

import {
  AlertTriangle,
  Bell,
  Bot,
  Brain,
  CheckCircle2,
  Database,
  Folder,
  Globe2,
  KeyRound,
  Link2,
  ListChecks,
  MemoryStick,
  Plus,
  Send,
  Shield,
  ShieldCheck,
  Smartphone,
  Users,
  Wifi,
} from "lucide-react";
import { type ComponentType, type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Screen = "home" | "tasks" | "rules" | "memory" | "connectors" | "browser" | "android" | "models" | "vault" | "people" | "files";
type Icon = ComponentType<{ size?: number; strokeWidth?: number }>;
type TaskStatus = "intake" | "planning" | "ready" | "executing" | "awaiting_approval" | "awaiting_login" | "awaiting_mfa" | "blocked_by_rule" | "recovering" | "paused" | "done" | "failed";

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

type Health = { service: string; status: string; version: string; storage: string };

type Module = { id: Screen; label: string; icon: Icon };

const modules: Module[] = [
  { id: "home", label: "ALTER", icon: Bot },
  { id: "tasks", label: "Задачі", icon: ListChecks },
  { id: "memory", label: "Памʼять", icon: MemoryStick },
  { id: "rules", label: "Правила", icon: ShieldCheck },
  { id: "connectors", label: "Конектори", icon: Link2 },
  { id: "files", label: "Файли", icon: Folder },
  { id: "browser", label: "Браузер", icon: Globe2 },
  { id: "models", label: "Моделі", icon: Brain },
  { id: "android", label: "Android", icon: Smartphone },
  { id: "vault", label: "Сховище", icon: KeyRound },
  { id: "people", label: "Люди", icon: Users },
];

const statusLabel: Record<TaskStatus, string> = {
  intake: "Прийнято",
  planning: "Планування",
  ready: "Готова",
  executing: "Виконується",
  awaiting_approval: "Чекає схвалення",
  awaiting_login: "Потрібен вхід",
  awaiting_mfa: "Потрібна 2FA",
  blocked_by_rule: "Заблоковано правилом",
  recovering: "Відновлення",
  paused: "Пауза",
  done: "Готово",
  failed: "Помилка",
};

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `ALTER Core returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function Logo() {
  return <div className="alterLogo" aria-label="ALTER">A</div>;
}

function Header({ title }: { title?: string }) {
  return (
    <header className="appHeader">
      <div className="brandWord">ALTER</div>
      {title ? <div className="screenTitleCompact"><span>{title}</span></div> : <Logo />}
      <button className="iconButton notification" aria-label="Сповіщення"><Bell size={19} /><i /></button>
    </header>
  );
}

function StatusChip({ children, tone = "green" }: { children: React.ReactNode; tone?: "green" | "violet" | "amber" | "red" }) {
  return <span className={`statusChip ${tone}`}><i />{children}</span>;
}

function HonestPlaceholder({ title, icon: Icon, text }: { title: string; icon: Icon; text: string }) {
  return (
    <section className="glassPanel" style={{ borderRadius: 22, padding: 20 }}>
      <div style={{ display: "flex", gap: 13, alignItems: "center" }}>
        <div className="iconButton"><Icon size={20} /></div>
        <div>
          <h2 style={{ margin: 0, fontSize: 22 }}>{title}</h2>
          <p style={{ color: "var(--muted)", margin: "6px 0 0", lineHeight: 1.5 }}>{text}</p>
        </div>
      </div>
      <div style={{ marginTop: 16 }}><StatusChip tone="amber">Ще не підключено до runtime</StatusChip></div>
    </section>
  );
}

export default function Page() {
  const [screen, setScreen] = useState<Screen>("home");
  const [health, setHealth] = useState<Health | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [policies, setPolicies] = useState<PolicyRule[]>([]);
  const [memory, setMemory] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [command, setCommand] = useState("");
  const [sending, setSending] = useState(false);
  const [messages, setMessages] = useState<Array<{ role: "user" | "agent"; text: string }>>([]);

  const refresh = useCallback(async () => {
    try {
      setError(null);
      const [h, t, p, m] = await Promise.all([
        core<Health>("/health"),
        core<Task[]>("/tasks"),
        core<PolicyRule[]>("/policies"),
        core<MemoryItem[]>("/memory"),
      ]);
      setHealth(h);
      setTasks(t);
      setPolicies(p);
      setMemory(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не вдалося зʼєднатися з ALTER Core");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const activeTasks = useMemo(() => tasks.filter((t) => !["done", "failed"].includes(t.status)), [tasks]);
  const currentTask = activeTasks[0] ?? tasks[0] ?? null;

  async function submitCommand(event: FormEvent) {
    event.preventDefault();
    const objective = command.trim();
    if (!objective || sending) return;
    setSending(true);
    setMessages((items) => [...items, { role: "user", text: objective }]);
    setCommand("");
    try {
      const task = await core<Task>("/tasks", {
        method: "POST",
        body: JSON.stringify({ objective, acceptance_criteria: [] }),
      });
      setMessages((items) => [...items, { role: "agent", text: `Задачу записано в Core/Postgres. Статус: ${statusLabel[task.status]}. ID: ${task.id.slice(0, 8)}…` }]);
      await refresh();
    } catch (e) {
      setMessages((items) => [...items, { role: "agent", text: `Не вдалося створити задачу: ${e instanceof Error ? e.message : "невідома помилка"}` }]);
    } finally {
      setSending(false);
    }
  }

  return (
    <main className="appShell">
      <div className="ambient one" /><div className="ambient two" />
      <div className="appSurface">
        <Header title={screen === "home" ? undefined : modules.find((m) => m.id === screen)?.label} />

        <div className="quickModules">
          {modules.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setScreen(id)} style={screen === id ? { borderColor: "var(--line-strong)", color: "#d8d3ff" } : undefined}>
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>

        {error && (
          <section className="glassPanel" style={{ borderRadius: 18, padding: 14, marginBottom: 14, borderColor: "rgba(237,98,95,.4)" }}>
            <div style={{ display: "flex", gap: 10, alignItems: "center" }}><AlertTriangle size={18} /><b>Core недоступний</b></div>
            <p style={{ color: "var(--muted)", marginBottom: 0 }}>{error}</p>
          </section>
        )}

        {screen === "home" && (
          <>
            <div className="statusRow">
              <StatusChip tone={health?.status === "ok" ? "green" : "amber"}>{health?.status === "ok" ? "Core online" : loading ? "Перевірка Core…" : "Core offline"}</StatusChip>
              <span className="microPill"><Database size={13} /> {health?.storage === "postgres" ? "Postgres" : health?.storage ?? "—"}</span>
              <span className="microPill"><ListChecks size={13} /> {activeTasks.length} активних</span>
            </div>

            <section className="focusCard glowBorder">
              <div className="focusTop">
                <div>
                  <div className="eyebrow">ПОТОЧНА ЗАДАЧА · LIVE DATA</div>
                  <h1>{currentTask?.objective ?? "Немає активних задач"}</h1>
                </div>
                <button className="orbPlay" onClick={() => setScreen("tasks")}><ListChecks size={23} /></button>
              </div>
              {currentTask && (
                <>
                  <div className="progressTrack"><span style={{ width: currentTask.status === "done" ? "100%" : currentTask.status === "executing" ? "66%" : "28%" }} /></div>
                  <div className="focusMeta">
                    <b>{statusLabel[currentTask.status]}</b>
                    <span>Крок <strong>{currentTask.current_step ?? "—"}</strong></span>
                    <span>Оновлено <strong>{new Date(currentTask.updated_at).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" })}</strong></span>
                  </div>
                </>
              )}
            </section>

            <section className="chatPanel glassPanel" style={{ marginTop: 16 }}>
              <div className="chatMessage agent"><Logo /><div><small>ALTER · LIVE</small><p>Core підключений до Neon Postgres. Команди нижче створюють справжні задачі, а не локальну імітацію.</p></div></div>
              {messages.map((m, i) => (
                <div className={`chatMessage ${m.role}`} key={`${m.role}-${i}`}>
                  {m.role === "agent" ? <Logo /> : <div className="userAvatar">В</div>}
                  <div><small>{m.role === "agent" ? "ALTER" : "Ви"} · щойно</small><p>{m.text}</p></div>
                </div>
              ))}
            </section>

            <form className="commandComposer" onSubmit={submitCommand}>
              <button type="button" className="plusButton" aria-label="Додати"><Plus size={22} /></button>
              <input value={command} onChange={(e) => setCommand(e.target.value)} placeholder="Створити задачу для ALTER…" disabled={sending} />
              <span />
              <button className="sendButton" disabled={sending} aria-label="Надіслати"><Send size={18} /></button>
              <div className="composerModes"><button type="button">Core</button><button type="button">Postgres</button><button type="button">Policy first</button></div>
            </form>
          </>
        )}

        {screen === "tasks" && <TasksScreen tasks={tasks} refresh={refresh} />}
        {screen === "rules" && <RulesScreen policies={policies} refresh={refresh} />}
        {screen === "memory" && <MemoryScreen memory={memory} refresh={refresh} />}
        {screen === "connectors" && <ConnectorsScreen health={health} />}
        {screen === "browser" && <HonestPlaceholder title="Браузер" icon={Globe2} text="UI готовий, але remote Playwright/Browser executor ще не підʼєднаний. ALTER не буде показувати фальшиву активну сесію." />}
        {screen === "android" && <HonestPlaceholder title="Android" icon={Smartphone} text="Ізольований Android executor ще не запущений. Входи, 2FA та CAPTCHA мають залишатися під вашим ручним контролем." />}
        {screen === "models" && <HonestPlaceholder title="Моделі" icon={Brain} text="Model Router ще не має production registry. Демонстраційні VideoGen/CodeCraft/VisionPro прибрані як неіснуючі runtime-моделі." />}
        {screen === "vault" && <HonestPlaceholder title="Сховище" icon={KeyRound} text="Vercel secrets уже захищають Core-токен, але окремий ALTER Vault з alias/rotation/audit ще не реалізований." />}
        {screen === "people" && <HonestPlaceholder title="Люди" icon={Users} text="Production RBAC та запрошення Partner/Guest ще не реалізовані. Поточний Core працює в single-owner режимі." />}
        {screen === "files" && <HonestPlaceholder title="Файли" icon={Folder} text="Файлове сховище та індексація ще не підʼєднані до Core. Тут не показуються вигадані файли." />}

        <nav className="bottomNav" aria-label="Основна навігація">
          {[
            ["home", "ALTER", Bot],
            ["tasks", "Задачі", ListChecks],
            ["connectors", "Конектори", Link2],
            ["memory", "Памʼять", MemoryStick],
            ["rules", "Правила", Shield],
          ].map(([id, label, Icon]) => {
            const C = Icon as Icon;
            return <button key={id as string} className={screen === id ? "active" : ""} onClick={() => setScreen(id as Screen)}><C size={20} /><span>{label as string}</span></button>;
          })}
        </nav>
      </div>
    </main>
  );
}

function TasksScreen({ tasks, refresh }: { tasks: Task[]; refresh: () => Promise<void> }) {
  const [busy, setBusy] = useState<string | null>(null);
  async function transition(task: Task, action: "ready" | "complete") {
    setBusy(task.id);
    try {
      await core<Task>(`/tasks/${task.id}/${action}`, { method: "POST", body: "{}" });
      await refresh();
    } finally { setBusy(null); }
  }
  return (
    <section className="glassPanel" style={{ borderRadius: 22, padding: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}><div><b>Реальні задачі</b><div style={{ color: "var(--muted)", fontSize: 12 }}>Джерело: Core / Postgres</div></div><StatusChip>{tasks.length}</StatusChip></div>
      <div style={{ display: "grid", gap: 10 }}>
        {tasks.length === 0 && <p style={{ color: "var(--muted)" }}>Ще немає задач. Створи першу на головному екрані.</p>}
        {tasks.map((task) => (
          <article key={task.id} className="ruleCard" style={{ borderRadius: 16, padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><strong>{task.objective}</strong><StatusChip tone={task.status === "failed" || task.status === "blocked_by_rule" ? "red" : task.status === "awaiting_approval" ? "amber" : "green"}>{statusLabel[task.status]}</StatusChip></div>
            <div style={{ color: "var(--muted)", marginTop: 8, fontSize: 12 }}>Крок: {task.current_step ?? "—"}{task.blocker ? ` · ${task.blocker}` : ""}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              {task.status === "planning" && <button className="wideAction" disabled={busy === task.id} onClick={() => void transition(task, "ready")}>Позначити Ready</button>}
              {!["done", "failed"].includes(task.status) && <button className="wideAction" disabled={busy === task.id} onClick={() => void transition(task, "complete")}><CheckCircle2 size={15} /> Завершити</button>}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function RulesScreen({ policies, refresh }: { policies: PolicyRule[]; refresh: () => Promise<void> }) {
  const [text, setText] = useState("");
  const [category, setCategory] = useState("general");
  const [effect, setEffect] = useState<PolicyRule["effect"]>("deny");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    try {
      await core<PolicyRule>("/policies", { method: "POST", body: JSON.stringify({ original_text: text.trim(), category, effect, priority: 100 }) });
      setText("");
      await refresh();
    } finally { setBusy(false); }
  }
  return (
    <>
      <form className="glassPanel" onSubmit={submit} style={{ borderRadius: 20, padding: 14, display: "grid", gap: 10 }}>
        <b>Додати реальне правило</b>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Наприклад: Не публікуй без мого схвалення" style={fieldStyle} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="category" style={fieldStyle} />
          <select value={effect} onChange={(e) => setEffect(e.target.value as PolicyRule["effect"])} style={fieldStyle}><option value="deny">Deny</option><option value="require_approval">Require approval</option><option value="allow">Allow</option></select>
        </div>
        <button className="wideAction" disabled={busy}><Plus size={15} /> Зберегти в Policy Engine</button>
      </form>
      <section style={{ display: "grid", gap: 10, marginTop: 12 }}>
        {policies.length === 0 && <div className="glassPanel" style={{ borderRadius: 18, padding: 14, color: "var(--muted)" }}>Користувацьких правил ще немає. Незмінні системні межі безпеки діють у Core окремо.</div>}
        {policies.map((rule) => <article className="ruleCard" key={rule.id} style={{ borderRadius: 16, padding: 14 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><strong>{rule.original_text}</strong><StatusChip tone={rule.effect === "deny" ? "red" : rule.effect === "require_approval" ? "amber" : "green"}>{rule.effect}</StatusChip></div><div style={{ color: "var(--muted)", marginTop: 8, fontSize: 12 }}>{rule.category} · priority {rule.priority}</div></article>)}
      </section>
    </>
  );
}

function MemoryScreen({ memory, refresh }: { memory: MemoryItem[]; refresh: () => Promise<void> }) {
  const [namespace, setNamespace] = useState("profile");
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!key.trim()) return;
    await core<MemoryItem>("/memory", { method: "PUT", body: JSON.stringify({ namespace, key: key.trim(), value }) });
    setKey(""); setValue(""); await refresh();
  }
  return (
    <>
      <form className="glassPanel" onSubmit={submit} style={{ borderRadius: 20, padding: 14, display: "grid", gap: 10 }}>
        <b>Запис у постійну памʼять</b>
        <input value={namespace} onChange={(e) => setNamespace(e.target.value)} placeholder="namespace" style={fieldStyle} />
        <input value={key} onChange={(e) => setKey(e.target.value)} placeholder="key" style={fieldStyle} />
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="value" style={fieldStyle} />
        <button className="wideAction"><Database size={15} /> Зберегти в Postgres</button>
      </form>
      <section className="memoryPanel" style={{ borderRadius: 20, padding: 14, marginTop: 12 }}>
        {memory.length === 0 ? <p style={{ color: "var(--muted)" }}>Памʼять поки порожня.</p> : memory.map((item, i) => <div key={item.id ?? `${item.namespace}-${item.key}-${i}`} style={{ padding: "11px 0", borderBottom: "1px solid var(--line)" }}><div style={{ color: "#958bff", fontSize: 11 }}>{item.namespace}</div><strong>{item.key}</strong><div style={{ color: "var(--muted)", marginTop: 4 }}>{typeof item.value === "string" ? item.value : JSON.stringify(item.value)}</div></div>)}
      </section>
    </>
  );
}

function ConnectorsScreen({ health }: { health: Health | null }) {
  const items = [
    { name: "ALTER Core", status: health?.status === "ok" ? "Підключено" : "Недоступний", live: health?.status === "ok", detail: health ? `v${health.version}` : "—" },
    { name: "Neon Postgres", status: health?.storage === "postgres" ? "Підключено" : "Не підтверджено", live: health?.storage === "postgres", detail: "Tasks · Rules · Memory · Audit" },
    { name: "Botpress", status: "Ще не підʼєднано до Core runtime", live: false, detail: "Окремий agent service" },
    { name: "Browser executor", status: "Не налаштовано", live: false, detail: "Playwright / remote session" },
    { name: "Android executor", status: "Не налаштовано", live: false, detail: "Isolated device runtime" },
  ];
  return <section style={{ display: "grid", gap: 10 }}>{items.map((item) => <article key={item.name} className="glassPanel" style={{ borderRadius: 18, padding: 14, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}><div><strong>{item.name}</strong><div style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>{item.detail}</div></div><StatusChip tone={item.live ? "green" : "amber"}>{item.status}</StatusChip></article>)}</section>;
}

const fieldStyle: React.CSSProperties = {
  width: "100%",
  border: "1px solid var(--line)",
  background: "rgba(255,255,255,.035)",
  borderRadius: 12,
  padding: "11px 12px",
  outline: "none",
};
