"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Task = { id: string; objective: string; status: string; current_step?: string | null; blocker?: string | null; acceptance_criteria: string[]; created_at: string; updated_at: string };
type Event = { id: number; event_type: string; created_at: string; payload: Record<string, unknown> };
type Inspector = { task: Task; meta: Record<string, unknown>; events: Event[]; pending_action_digest?: string | null };

export default function TaskPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const [data, setData] = useState<Inspector | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expected, setExpected] = useState("");
  const [deadline, setDeadline] = useState("");
  const [autonomy, setAutonomy] = useState("balanced");
  const [notes, setNotes] = useState("");

  const refresh = useCallback(async () => {
    try {
      const result = await core<Inspector>(`/tasks/${id}/inspector`);
      setData(result);
      setExpected(String(result.meta.expected_result || ""));
      setDeadline(typeof result.meta.deadline === "string" ? String(result.meta.deadline).slice(0, 16) : "");
      setAutonomy(String(result.meta.autonomy || "balanced"));
      setNotes(String(result.meta.notes || ""));
      setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося відкрити задачу"); }
  }, [id]);
  useEffect(() => { void refresh(); }, [refresh]);

  async function control(action: "pause" | "resume" | "retry" | "cancel") {
    setBusy(true);
    try { await core(`/tasks/${id}/control`, { method: "POST", body: JSON.stringify({ action }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Дія не виконана"); }
    finally { setBusy(false); }
  }

  async function saveMeta() {
    setBusy(true);
    try {
      await core(`/tasks/${id}/meta`, { method: "PUT", body: JSON.stringify({ expected_result: expected || null, deadline: deadline ? new Date(deadline).toISOString() : null, autonomy, sources: [], notes: notes || null }) });
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося зберегти"); }
    finally { setBusy(false); }
  }

  if (!data) return <ModuleShell title="Задача" eyebrow="TASK INSPECTOR"><section style={panel}>{error || "Завантажую…"}</section></ModuleShell>;
  const task = data.task;

  return (
    <ModuleShell title="Task Inspector" eyebrow="EXPLAIN · CONTROL · RECOVER">
      <section style={{ ...panel, display: "grid", gap: 9 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong style={{ fontSize: 19 }}>{task.objective}</strong><span style={badge}>{task.status}</span></div>
        <div style={muted}>Поточний крок: {task.current_step || "—"}</div>
        {task.blocker && <div style={{ color: "#ffd28b" }}>Причина блокування: {task.blocker}</div>}
        <div style={muted}>Створено {formatDate(task.created_at)} · оновлено {formatDate(task.updated_at)}</div>
        {data.pending_action_digest && <div style={{ ...muted, wordBreak: "break-all" }}>Pending action digest: {data.pending_action_digest}</div>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {!['done','failed','cancelled','paused'].includes(task.status) && <button disabled={busy} onClick={() => void control('pause')} style={primary}>Пауза</button>}
          {task.status === 'paused' && <button disabled={busy} onClick={() => void control('resume')} style={primary}>Продовжити</button>}
          {['failed','blocked_by_rule','recovering'].includes(task.status) && <button disabled={busy} onClick={() => void control('retry')} style={primary}>Повторити</button>}
          {!['done','cancelled'].includes(task.status) && <button disabled={busy} onClick={() => void control('cancel')} style={danger}>Скасувати</button>}
        </div>
      </section>

      <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
        <strong>Очікуваний результат і автономність</strong>
        <textarea value={expected} onChange={(e) => setExpected(e.target.value)} rows={3} placeholder="Що вважати готовим результатом" style={{ ...field, resize: "vertical" }} />
        <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} style={field} />
        <select value={autonomy} onChange={(e) => setAutonomy(e.target.value)} style={field}><option value="ask_often">Часто питати</option><option value="balanced">Збалансовано</option><option value="high">Висока автономність</option></select>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Нотатки" style={{ ...field, resize: "vertical" }} />
        <button disabled={busy} onClick={() => void saveMeta()} style={primary}>Зберегти</button>
      </section>

      {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
      <section style={{ marginTop: 14 }}>
        <strong>Хронологія</strong>
        <div style={{ display: "grid", gap: 8, marginTop: 9 }}>
          {data.events.length === 0 && <div style={panel}>Подій поки немає.</div>}
          {data.events.map((event) => <article key={event.id} style={panel}><div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{event.event_type}</strong><span style={muted}>{formatDate(event.created_at)}</span></div><pre style={pre}>{JSON.stringify(event.payload, null, 2)}</pre></article>)}
        </div>
      </section>
    </ModuleShell>
  );
}

const badge: React.CSSProperties = { whiteSpace: "nowrap", border: "1px solid rgba(143,126,255,.25)", background: "rgba(111,91,255,.08)", color: "#c9c2ff", borderRadius: 999, padding: "6px 9px", fontSize: 10 };
const pre: React.CSSProperties = { margin: "8px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word", color: "rgba(255,255,255,.55)", fontSize: 11 };
