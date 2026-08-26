"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ModuleShell, { muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Task = { id: string; objective: string; status: string; current_step?: string | null; blocker?: string | null; updated_at: string; acceptance_criteria: string[] };

export default function TasksPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [objective, setObjective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try { setTasks(await core<Task[]>("/tasks?limit=250")); setError(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити задачі"); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function createTask() {
    const value = objective.trim();
    if (!value || busy) return;
    setBusy(true);
    try {
      const task = await core<Task>("/tasks", { method: "POST", body: JSON.stringify({ objective: value, acceptance_criteria: [] }) });
      await core(`/tasks/${task.id}/meta`, { method: "PUT", body: JSON.stringify({ expected_result: null, deadline: null, autonomy: "balanced", sources: [], notes: null }) });
      setObjective("");
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося створити задачу"); }
    finally { setBusy(false); }
  }

  return (
    <ModuleShell title="Задачі" eyebrow="OPERATIONS CENTER">
      <section style={{ ...panel, display: "grid", gap: 10 }}>
        <strong>Нова задача</strong>
        <textarea value={objective} onChange={(e) => setObjective(e.target.value)} rows={3} placeholder="Опиши результат, який хочеш отримати…" style={{ ...input, resize: "vertical" }} />
        <button type="button" onClick={() => void createTask()} disabled={busy || !objective.trim()} style={primary}>{busy ? "Створюю…" : "Створити"}</button>
      </section>
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
