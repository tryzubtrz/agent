"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type PendingAction = { attempt_id?: string | null; operation: string; target?: string | null; category: string; risk: string };
type Task = { id: string; objective: string; status: string; current_step?: string | null; blocker?: string | null; acceptance_criteria: string[]; pending_action?: PendingAction | null; created_at: string; updated_at: string };
type Event = { id: number; event_type: string; created_at: string; payload: Record<string, unknown> };
type TaskPlan = { plan: string; provider: string; mode: string; boundary: string; side_effects_performed: false; created_at: string };
type TaskResult = { result_summary: string; verification_evidence: string[]; artifact_refs: string[]; acceptance_criteria_met: true; verification_method: "owner_attestation" };
type ActionResult = { execution_id?: string; attempt_id: string; action_digest: string; operation: string; target?: string | null; succeeded: boolean; result_summary: string; verification_evidence: string[]; artifact_refs: string[]; verification_method: "owner_attestation" };
type Inspector = {
  task: Task;
  meta: Record<string, unknown>;
  plan?: TaskPlan | null;
  result?: TaskResult | null;
  action_results: ActionResult[];
  events: Event[];
  pending_action_digest?: string | null;
  pending_action_attempt_id?: string | null;
};

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
  const [resultSummary, setResultSummary] = useState("");
  const [verificationEvidence, setVerificationEvidence] = useState("");
  const [artifactRefs, setArtifactRefs] = useState("");
  const [acceptanceConfirmed, setAcceptanceConfirmed] = useState(false);
  const [actionSucceeded, setActionSucceeded] = useState(true);
  const [actionSummary, setActionSummary] = useState("");
  const [actionEvidence, setActionEvidence] = useState("");
  const [actionArtifacts, setActionArtifacts] = useState("");

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

  async function control(action: "pause" | "resume" | "retry" | "cancel" | "authentication_complete") {
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

  async function createPlan() {
    setBusy(true);
    try {
      await core("/tasks/" + id + "/plan", {
        method: "POST",
        body: JSON.stringify({ mode: "plan", context: notes.trim() }),
      });
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося створити план"); }
    finally { setBusy(false); }
  }

  async function completeTask() {
    const evidence = splitLines(verificationEvidence);
    const artifacts = splitLines(artifactRefs);
    if (!resultSummary.trim() || evidence.length === 0 || !acceptanceConfirmed) return;
    setBusy(true);
    try {
      await core("/tasks/" + id + "/complete", {
        method: "POST",
        body: JSON.stringify({
          result_summary: resultSummary.trim(),
          verification_evidence: evidence,
          artifact_refs: artifacts,
          acceptance_criteria_met: true,
        }),
      });
      setResultSummary("");
      setVerificationEvidence("");
      setArtifactRefs("");
      setAcceptanceConfirmed(false);
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завершити задачу"); }
    finally { setBusy(false); }
  }

  async function attestActionResult() {
    const evidence = splitLines(actionEvidence);
    if (!data?.pending_action_digest || !data.pending_action_attempt_id || !actionSummary.trim() || evidence.length === 0) return;
    setBusy(true);
    try {
      await core("/tasks/" + id + "/action-result", {
        method: "POST",
        body: JSON.stringify({
          action_digest: data.pending_action_digest,
          attempt_id: data.pending_action_attempt_id,
          succeeded: actionSucceeded,
          result_summary: actionSummary.trim(),
          verification_evidence: evidence,
          artifact_refs: splitLines(actionArtifacts),
        }),
      });
      setActionSummary("");
      setActionEvidence("");
      setActionArtifacts("");
      setActionSucceeded(true);
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося підтвердити результат дії"); }
    finally { setBusy(false); }
  }

  if (!data) return <ModuleShell title="Задача" eyebrow="TASK INSPECTOR"><section style={panel}>{error || "Завантажую…"}</section></ModuleShell>;
  const task = data.task;
  const canPause = ["ready", "executing", "recovering"].includes(task.status);

  return (
    <ModuleShell title="Task Inspector" eyebrow="EXPLAIN · CONTROL · RECOVER">
      <section style={{ ...panel, display: "grid", gap: 9 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong style={{ fontSize: 19 }}>{task.objective}</strong><span style={badge}>{task.status}</span></div>
        <div style={muted}>Поточний крок: {task.current_step || "—"}</div>
        {task.blocker && <div style={{ color: "#ffd28b" }}>Причина блокування: {task.blocker}</div>}
        <div style={muted}>Створено {formatDate(task.created_at)} · оновлено {formatDate(task.updated_at)}</div>
        {data.pending_action_digest && <div style={{ ...muted, wordBreak: "break-all" }}>Pending action digest: {data.pending_action_digest}</div>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {canPause && <button disabled={busy} onClick={() => void control('pause')} style={primary}>Пауза</button>}
          {task.status === 'paused' && <button disabled={busy} onClick={() => void control('resume')} style={primary}>Продовжити</button>}
          {['awaiting_login','awaiting_mfa'].includes(task.status) && <button disabled={busy} onClick={() => void control('authentication_complete')} style={primary}>Я завершив вхід / 2FA</button>}
          {['failed','blocked_by_rule','recovering'].includes(task.status) && <button disabled={busy} onClick={() => void control('retry')} style={primary}>Повторити</button>}
          {!['done','cancelled'].includes(task.status) && <button disabled={busy} onClick={() => void control('cancel')} style={danger}>Скасувати</button>}
        </div>
      </section>

      <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
        <strong>План виконання</strong>
        {task.acceptance_criteria.length > 0 && (
          <div>
            <div style={muted}>Критерії готовності</div>
            <ul style={list}>{task.acceptance_criteria.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        )}
        {data.plan ? (
          <>
            <pre style={planText}>{data.plan.plan}</pre>
            <div style={muted}>Створено через {data.plan.provider} · без зовнішніх дій · {formatDate(data.plan.created_at)}</div>
          </>
        ) : (
          <div style={muted}>Перевіреного плану ще немає.</div>
        )}
        {["intake", "planning", "recovering"].includes(task.status) && (
          <button disabled={busy} onClick={() => void createPlan()} style={primary}>
            {busy ? "ALTER планує…" : "Створити план через ALTER"}
          </button>
        )}
      </section>

      <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
        <strong>Очікуваний результат і автономність</strong>
        <textarea value={expected} onChange={(e) => setExpected(e.target.value)} rows={3} placeholder="Що вважати готовим результатом" style={{ ...field, resize: "vertical" }} />
        <input type="datetime-local" value={deadline} onChange={(e) => setDeadline(e.target.value)} style={field} />
        <select value={autonomy} onChange={(e) => setAutonomy(e.target.value)} style={field}><option value="ask_often">Часто питати</option><option value="balanced">Збалансовано</option><option value="high">Висока автономність</option></select>
        <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} placeholder="Нотатки" style={{ ...field, resize: "vertical" }} />
        <button disabled={busy} onClick={() => void saveMeta()} style={primary}>Зберегти</button>
      </section>

      {task.status === "executing" && task.pending_action && data.pending_action_digest && data.pending_action_attempt_id && (
        <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
          <strong>Перевірка активної дії</strong>
          <div style={muted}>
            {task.pending_action.operation} · {task.pending_action.target || "без цілі"} · ризик {task.pending_action.risk}
          </div>
          <select value={actionSucceeded ? "success" : "failure"} onChange={(event) => setActionSucceeded(event.target.value === "success")} style={field}>
            <option value="success">Дія виконана успішно</option>
            <option value="failure">Дія завершилась помилкою</option>
          </select>
          <textarea value={actionSummary} onChange={(event) => setActionSummary(event.target.value)} rows={3} placeholder="Фактичний результат дії" style={{ ...field, resize: "vertical" }} />
          <textarea value={actionEvidence} onChange={(event) => setActionEvidence(event.target.value)} rows={3} placeholder={"Докази перевірки — по одному на рядок"} style={{ ...field, resize: "vertical" }} />
          <textarea value={actionArtifacts} onChange={(event) => setActionArtifacts(event.target.value)} rows={2} placeholder="Артефакти — по одному на рядок (необов’язково)" style={{ ...field, resize: "vertical" }} />
          <button disabled={busy || !actionSummary.trim() || splitLines(actionEvidence).length === 0} onClick={() => void attestActionResult()} style={actionSucceeded ? primary : danger}>
            {actionSucceeded ? "Підтвердити виконання дії" : "Зафіксувати помилку й відновити"}
          </button>
        </section>
      )}

      {data.action_results.length > 0 && (
        <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
          <strong>Результати дій</strong>
          {data.action_results.map((item, index) => (
            <article key={item.execution_id || `${item.action_digest}:${index}`} style={{ borderTop: "1px solid rgba(255,255,255,.08)", paddingTop: 9 }}>
              <div style={{ color: item.succeeded ? "#a9efc4" : "#ffaaa7" }}>{item.operation}: {item.succeeded ? "успішно" : "помилка"}</div>
              <div style={resultText}>{item.result_summary}</div>
              <ul style={list}>{item.verification_evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}</ul>
              {item.artifact_refs.length > 0 && (
                <div>
                  <div style={muted}>Артефакти</div>
                  <ul style={list}>{item.artifact_refs.map((artifact) => <li key={artifact}>{artifact}</li>)}</ul>
                </div>
              )}
            </article>
          ))}
        </section>
      )}

      {data.result ? (
        <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
          <strong>Результат, підтверджений власником</strong>
          <div style={resultText}>{data.result.result_summary}</div>
          <div>
            <div style={muted}>Докази перевірки</div>
            <ul style={list}>{data.result.verification_evidence.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          {data.result.artifact_refs.length > 0 && (
            <div>
              <div style={muted}>Артефакти</div>
              <ul style={list}>{data.result.artifact_refs.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          )}
        </section>
      ) : ["ready", "recovering"].includes(task.status) ? (
        <section style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
          <strong>Підтвердження результату власником</strong>
          <textarea
            aria-label="Підсумок результату"
            value={resultSummary}
            onChange={(event) => setResultSummary(event.target.value)}
            rows={3}
            placeholder="Що фактично створено або виконано"
            style={{ ...field, resize: "vertical" }}
          />
          <textarea
            aria-label="Докази перевірки"
            value={verificationEvidence}
            onChange={(event) => setVerificationEvidence(event.target.value)}
            rows={3}
            placeholder={"Докази перевірки — по одному на рядок\nНаприклад: 42 тести пройшли"}
            style={{ ...field, resize: "vertical" }}
          />
          <textarea
            aria-label="Посилання на артефакти"
            value={artifactRefs}
            onChange={(event) => setArtifactRefs(event.target.value)}
            rows={2}
            placeholder="Посилання або ID артефактів — по одному на рядок (необов’язково)"
            style={{ ...field, resize: "vertical" }}
          />
          <label style={checkLine}>
            <input type="checkbox" checked={acceptanceConfirmed} onChange={(event) => setAcceptanceConfirmed(event.target.checked)} />
            Я як власник перевірив: критерії готовності виконані
          </label>
          <button
            disabled={busy || !resultSummary.trim() || splitLines(verificationEvidence).length === 0 || !acceptanceConfirmed}
            onClick={() => void completeTask()}
            style={primary}
          >
            Підтвердити результат і завершити
          </button>
        </section>
      ) : null}

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

function splitLines(value: string): string[] {
  return value.split("\n").map((item) => item.trim()).filter(Boolean);
}

const badge: React.CSSProperties = { whiteSpace: "nowrap", border: "1px solid rgba(143,126,255,.25)", background: "rgba(111,91,255,.08)", color: "#c9c2ff", borderRadius: 999, padding: "6px 9px", fontSize: 10 };
const pre: React.CSSProperties = { margin: "8px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word", color: "rgba(255,255,255,.55)", fontSize: 11 };
const planText: React.CSSProperties = { ...pre, margin: 0, color: "rgba(255,255,255,.78)", lineHeight: 1.55 };
const resultText: React.CSSProperties = { whiteSpace: "pre-wrap", lineHeight: 1.55, color: "rgba(255,255,255,.84)" };
const list: React.CSSProperties = { margin: "7px 0 0", paddingLeft: 20, color: "rgba(255,255,255,.72)", lineHeight: 1.55 };
const checkLine: React.CSSProperties = { display: "flex", gap: 9, alignItems: "flex-start", color: "rgba(255,255,255,.72)", fontSize: 13, lineHeight: 1.4 };
