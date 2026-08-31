"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Brain, Check, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import ModuleShell, { danger, field, good, muted, panel, primary, warn } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Preferences = {
  tone: string;
  length: "стисло" | "збалансовано" | "детально";
  language: string;
  notes: string;
  updated_at?: string;
};
type Summary = {
  pending_candidates: number;
  approved_candidates: number;
  lessons: number;
  active_triggers: number;
  preferences: Preferences;
  memory_commit_mode: string;
};
type Candidate = { id: string; key: string; kind: string; content: string; confidence: number; source: string; created_at: string };
type Lesson = { id: string; key: string; situation: string; lesson: string; tags: string[]; created_at: string };
type Trigger = { id: string; key: string; when: string; then: string; active: boolean; created_at: string };

export default function LearningPage() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [preferences, setPreferences] = useState<Preferences>({ tone: "прямий, дружній", length: "збалансовано", language: "українська", notes: "" });
  const [situation, setSituation] = useState("");
  const [lesson, setLesson] = useState("");
  const [when, setWhen] = useState("");
  const [then, setThen] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [nextSummary, nextCandidates, nextLessons, nextTriggers, nextPreferences] = await Promise.all([
        core<Summary>("/learning/summary"),
        core<Candidate[]>("/learning/candidates"),
        core<Lesson[]>("/learning/lessons"),
        core<Trigger[]>("/learning/triggers"),
        core<Preferences>("/learning/preferences"),
      ]);
      setSummary(nextSummary);
      setCandidates(nextCandidates);
      setLessons(nextLessons);
      setTriggers(nextTriggers);
      setPreferences(nextPreferences);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не вдалося відкрити центр навчання");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true); setError("");
    try { await work(); setNotice(success); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Дія не виконана"); }
    finally { setBusy(false); }
  }

  async function addLesson(event: FormEvent) {
    event.preventDefault();
    if (!situation.trim() || !lesson.trim()) return;
    await action(
      () => core("/learning/lessons", { method: "POST", body: JSON.stringify({ situation: situation.trim(), lesson: lesson.trim(), tags: [] }) }),
      "Урок збережено й буде врахований у релевантних відповідях.",
    );
    setSituation(""); setLesson("");
  }

  async function addTrigger(event: FormEvent) {
    event.preventDefault();
    if (!when.trim() || !then.trim()) return;
    await action(
      () => core("/learning/triggers", { method: "POST", body: JSON.stringify({ when: when.trim(), then: then.trim(), active: true }) }),
      "Контекстний тригер активовано.",
    );
    setWhen(""); setThen("");
  }

  async function savePreferences(event: FormEvent) {
    event.preventDefault();
    await action(
      () => core("/learning/preferences", { method: "PUT", body: JSON.stringify(preferences) }),
      "Стиль ALTER оновлено.",
    );
  }

  return (
    <ModuleShell
      title="Навчання ALTER"
      eyebrow="CONFIRMED MEMORY · LESSONS · TRIGGERS"
      action={<button type="button" onClick={() => void refresh()} disabled={busy} style={iconButton} aria-label="Оновити"><RefreshCw size={17} /></button>}
    >
      <section style={{ ...panel, borderColor: "rgba(139,124,255,.28)" }}>
        <div style={titleRow}><div style={brainIcon}><Brain size={23} /></div><div><strong>Навчання без самовільної зміни памʼяті</strong><div style={muted}>ALTER пропонує стійкі факти з розмови, але довгостроково зберігає їх лише після твого підтвердження.</div></div></div>
        <div style={metrics}>
          <Metric label="Чекають" value={summary?.pending_candidates ?? 0} tone="warn" />
          <Metric label="Підтверджено" value={summary?.approved_candidates ?? 0} tone="good" />
          <Metric label="Уроки" value={summary?.lessons ?? 0} />
          <Metric label="Тригери" value={summary?.active_triggers ?? 0} />
        </div>
      </section>

      {error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}
      {notice && <section style={{ ...panel, marginTop: 12, color: "#9af0bd", display: "flex", justifyContent: "space-between", gap: 10 }}>{notice}<button type="button" onClick={() => setNotice("")} style={plainButton}><X size={15} /></button></section>}

      <h2 style={heading}>Кандидати з розмов</h2>
      <section style={stack}>
        {candidates.map((candidate) => (
          <article key={candidate.id} style={panel}>
            <div style={row}><span style={{ ...pill, ...warn }}>{candidate.kind} · {Math.round(candidate.confidence * 100)}%</span><small style={muted}>{formatDate(candidate.created_at)}</small></div>
            <p style={copy}>{candidate.content}</p>
            <div style={actions}>
              <button disabled={busy} style={primary} onClick={() => void action(() => core(`/learning/candidates/${candidate.id}/approve`, { method: "POST", body: JSON.stringify({ kind: candidate.kind, importance: candidate.confidence }) }), "Факт підтверджено й додано до памʼяті.")}><Check size={15} /> Підтвердити</button>
              <button disabled={busy} style={danger} onClick={() => void action(() => core(`/learning/candidates/${candidate.id}`, { method: "DELETE" }), "Кандидат відхилено.")}><Trash2 size={15} /> Відхилити</button>
            </div>
          </article>
        ))}
        {candidates.length === 0 && <section style={{ ...panel, ...muted }}>Немає неперевірених фактів. Нові зʼявляться після явних фраз на кшталт «я люблю…», «я вирішив…» або «запамʼятай…».</section>}
      </section>

      <h2 style={heading}>Як ALTER має відповідати</h2>
      <form onSubmit={savePreferences} style={{ ...panel, display: "grid", gap: 9 }}>
        <input value={preferences.tone} onChange={(e) => setPreferences((item) => ({ ...item, tone: e.target.value }))} placeholder="Тон" style={field} />
        <div style={twoCols}>
          <select value={preferences.length} onChange={(e) => setPreferences((item) => ({ ...item, length: e.target.value as Preferences["length"] }))} style={field}><option value="стисло">Стисло</option><option value="збалансовано">Збалансовано</option><option value="детально">Детально</option></select>
          <input value={preferences.language} onChange={(e) => setPreferences((item) => ({ ...item, language: e.target.value }))} placeholder="Мова" style={field} />
        </div>
        <textarea value={preferences.notes} onChange={(e) => setPreferences((item) => ({ ...item, notes: e.target.value }))} placeholder="Додаткові побажання" rows={3} style={{ ...field, resize: "vertical" }} />
        <div style={actions}>
          <button disabled={busy} style={primary}><Check size={15} /> Зберегти стиль</button>
          <button type="button" disabled={busy} style={secondary} onClick={() => void action(() => core<Preferences>("/learning/preferences/learn", { method: "POST", body: "{}" }), "ALTER оновив довжину й мову за реальною історією розмов.")}><Sparkles size={15} /> Вивчити з чату</button>
        </div>
      </form>

      <h2 style={heading}>Уроки після помилок і правок</h2>
      <form onSubmit={addLesson} style={{ ...panel, display: "grid", gap: 9 }}>
        <input value={situation} onChange={(e) => setSituation(e.target.value)} placeholder="Коли це трапляється…" style={field} />
        <textarea value={lesson} onChange={(e) => setLesson(e.target.value)} placeholder="Як ALTER має діяти наступного разу…" rows={3} style={{ ...field, resize: "vertical" }} />
        <button disabled={busy || !situation.trim() || !lesson.trim()} style={primary}>Додати урок</button>
      </form>
      <section style={{ ...stack, marginTop: 9 }}>
        {lessons.map((item) => <article key={item.id} style={panel}><strong>{item.situation}</strong><p style={copy}>{item.lesson}</p><button disabled={busy} style={danger} onClick={() => void action(() => core(`/learning/lessons/${item.id}`, { method: "DELETE" }), "Урок видалено.")}><Trash2 size={14} /> Видалити</button></article>)}
      </section>

      <h2 style={heading}>Контекстні тригери</h2>
      <form onSubmit={addTrigger} style={{ ...panel, display: "grid", gap: 9 }}>
        <input value={when} onChange={(e) => setWhen(e.target.value)} placeholder="Коли…" style={field} />
        <textarea value={then} onChange={(e) => setThen(e.target.value)} placeholder="Тоді врахуй / запропонуй…" rows={3} style={{ ...field, resize: "vertical" }} />
        <button disabled={busy || !when.trim() || !then.trim()} style={primary}>Створити тригер</button>
      </form>
      <section style={{ ...stack, marginTop: 9 }}>
        {triggers.map((item) => <article key={item.id} style={panel}><div style={row}><strong>Коли: {item.when}</strong><span style={{ ...pill, ...(item.active ? good : muted) }}>{item.active ? "ACTIVE" : "PAUSED"}</span></div><p style={copy}>Тоді: {item.then}</p><div style={actions}><button disabled={busy} style={secondary} onClick={() => void action(() => core(`/learning/triggers/${item.id}`, { method: "PATCH", body: "{}" }), item.active ? "Тригер призупинено." : "Тригер активовано.")}>{item.active ? "Пауза" : "Увімкнути"}</button><button disabled={busy} style={danger} onClick={() => void action(() => core(`/learning/triggers/${item.id}`, { method: "DELETE" }), "Тригер видалено.")}><Trash2 size={14} /> Видалити</button></div></article>)}
      </section>
    </ModuleShell>
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: "good" | "warn" }) {
  return <div style={metric}><strong style={tone === "good" ? good : tone === "warn" ? warn : undefined}>{value}</strong><span>{label}</span></div>;
}

const stack: React.CSSProperties = { display: "grid", gap: 9 };
const heading: React.CSSProperties = { margin: "22px 2px 10px", fontSize: 18 };
const titleRow: React.CSSProperties = { display: "grid", gridTemplateColumns: "48px 1fr", gap: 11, alignItems: "center" };
const brainIcon: React.CSSProperties = { width: 48, height: 48, borderRadius: 15, display: "grid", placeItems: "center", color: "#c7c0ff", background: "rgba(118,102,255,.14)", border: "1px solid rgba(139,124,255,.26)" };
const metrics: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 7, marginTop: 13 };
const metric: React.CSSProperties = { border: "1px solid rgba(255,255,255,.08)", borderRadius: 12, padding: 9, background: "rgba(0,0,0,.14)", textAlign: "center" };
const row: React.CSSProperties = { display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 };
const copy: React.CSSProperties = { color: "rgba(255,255,255,.72)", fontSize: 13, lineHeight: 1.55, whiteSpace: "pre-wrap" };
const actions: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 8 };
const twoCols: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 };
const pill: React.CSSProperties = { display: "inline-flex", border: "1px solid rgba(255,255,255,.1)", borderRadius: 999, padding: "4px 7px", fontSize: 9 };
const secondary: React.CSSProperties = { ...primary, background: "rgba(255,255,255,.035)", borderColor: "rgba(255,255,255,.1)", color: "rgba(255,255,255,.72)", display: "inline-flex", alignItems: "center", gap: 6 };
const iconButton: React.CSSProperties = { width: 40, height: 40, display: "grid", placeItems: "center", border: "1px solid rgba(255,255,255,.1)", borderRadius: 13, background: "rgba(255,255,255,.04)", color: "#dcd8ef" };
const plainButton: React.CSSProperties = { border: 0, background: "transparent", color: "inherit", display: "grid", placeItems: "center" };
