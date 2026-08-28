"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ModuleShell, { muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Task = { id: string; objective: string; status: string; current_step?: string | null; blocker?: string | null; updated_at: string; acceptance_criteria: string[] };
type PlannedTask = { task: Task; plan: { plan: string } };
type Session = { authenticated: boolean; role: "owner" | "operator" | "viewer"; capabilities: string[] };

const DEFAULT_ACCEPTANCE_CRITERION = "Запитаний результат створено та підтверджено конкретними доказами.";

function hasCapability(session: Session | null, required: string): boolean {
  if (!session) return false;
  if (session.role === "owner") return true;
  const caps = new Set(session.capabilities);
  return caps.has("*") || caps.has(required);
}

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [objective, setObjective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [items, sessionResponse] = await Promise.all([
        core<Task[]>("/tasks?limit=250"),
        fetch("/api/auth/session", { cache: "no-store" }),
      ]);
      setTasks(items);
      if (sessionResponse.ok) setSession(await sessionResponse.json() as Session);
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити задачі"); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  const canWrite = hasCapability(session, "tasks.write");

  async function createTask() {
    const value = objective.trim();
    if (!value || busy || !canWrite) return;
    setBusy(true);
    setError("");
    setNotice("");

    let task: Task;
    try {
      task = await core<Task>("/tasks", {
        method: "POST",
        body: JSON.stringify({ objective: value, acceptance_criteria: [DEFAULT_ACCEPTANCE_CRITERION] }),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося створити задачу");
      setBusy(false);
      return;
    }

    // Creation is the only atomic step. Never report it as failed after Core has
    // returned a task id: retrying from that state would create a duplicate task.
    setObjective("");
    const followUpErrors: string[] = [];
    let plannedStatus = "";

    try {
      try {
        await core(`/tasks/${task.id}/meta`, {
          method: "PUT",
          body: JSON.stringify({ expected_result: value, deadline: null, autonomy: "balanced", sources: [], notes: null }),
        });
      } catch (metaError) {
        followUpErrors.push(metaError instanceof Error ? metaError.message : "Метадані задачі не збережено");
      }

      try {
        const planned = await core<PlannedTask>(`/tasks/${task.id}/plan`, {
          method: "POST",
          body: JSON.stringify({ mode: "plan", context: "" }),
        });
        plannedStatus = planned.task.status;
      } catch (planError) {
        followUpErrors.push(planError instanceof Error ? planError.message : "Автопланування не виконано");
      }

      await refresh();
      if (followUpErrors.length === 0) {
        setNotice(`Задачу створено і сплановано. Статус: ${plannedStatus}.`);
      } else if (plannedStatus) {
        setNotice(`Задачу створено і сплановано зі статусом ${plannedStatus}, але частину метаданих не вдалося зберегти. Задача не втрачена.`);
      } else {
        setNotice("Задачу створено, але ALTER не зміг завершити автоматичне налаштування. Відкрий Task Inspector — задача не втрачена.");
      }
      setError(followUpErrors.join(" · "));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ModuleShell title="Задачі" eyebrow="OPERATIONS CENTER">
      {canWrite ? (
        <section style={{ ...panel, display: "grid", gap: 10 }}>
          <strong>Нова задача</strong>
          <div style={muted}>Опиши результат. ALTER створить задачу, зафіксує критерій перевірки й одразу спробує сформувати план — без ручного «Ready».</div>
          <textarea value={objective} onChange={(e) => setObjective(e.target.value)} rows={3} placeholder="Що потрібно отримати в результаті?" style={{ ...input, resize: "vertical" }} />
          <button type="button" onClick={() => void createTask()} disabled={busy || !objective.trim()} style={primary}>{busy ? "ALTER планує…" : "Створити й спланувати"}</button>
        </section>
      ) : (
        <section style={{ ...panel, color: "rgba(255,255,255,.62)" }}>
          Режим перегляду: ти можеш читати задачі й їхні результати, але не створювати та не змінювати їх.
        </section>
      )}
      {notice && <section style={{ ...panel, marginTop: 12, color: "#9af0bd" }}>{notice}</section>}
      {error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}
      <section style={{ display: "grid", gap: 10, marginTop: 14 }}>
        {tasks.length === 0 && <div style={panel}>Поки немає задач.</div>}
        {tasks.map((task) => (
          <Link key={task.id} href={`/tasks/${task.id}`} style={{ ...panel, display: "grid", gap: 8, textDecoration: "none", color: "inherit" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
              <strong>{task.objective}</strong><span style={badge}>{task.status}</span>
            </div>
            <div style={muted}>Крок: {task.current_step || "—"}{task.blocker ? ` · ${task.blocker}` : ""}</div>
            <div style={muted}>Оновлено: {formatDate(task.updated_at)}</div>
          </Link>
        ))}
      </section>
    </ModuleShell>
  );
}

const input: React.CSSProperties = { width: "100%", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: 12, outline: "none", font: "inherit" };
const badge: React.CSSProperties = { whiteSpace: "nowrap", border: "1px solid rgba(143,126,255,.25)", background: "rgba(111,91,255,.08)", color: "#c9c2ff", borderRadius: 999, padding: "5px 8px", fontSize: 10 };

