"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Rule = { id: string; original_text: string; category: string; effect: "allow" | "deny" | "require_approval"; enabled: boolean; priority: number };
type Conflict = { category: string; rule_ids: string[]; effects: string[]; winner: string };
type DryRun = { effect: string; reason: string; matched_rule_id?: string | null; executed: false };

export default function RulesPage() {
  const [rules, setRules] = useState<Rule[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [text, setText] = useState("");
  const [category, setCategory] = useState("general");
  const [effect, setEffect] = useState<Rule["effect"]>("deny");
  const [testCategory, setTestCategory] = useState("general");
  const [testRisk, setTestRisk] = useState("read");
  const [dryRun, setDryRun] = useState<DryRun | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [r, c] = await Promise.all([core<Rule[]>("/policies"), core<Conflict[]>("/policies/conflicts")]);
      setRules(r); setConflicts(c); setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити правила"); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function createRule(event: FormEvent) {
    event.preventDefault(); if (!text.trim()) return; setBusy(true);
    try { await core("/policies", { method: "POST", body: JSON.stringify({ original_text: text.trim(), category, effect, priority: 100 }) }); setText(""); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося створити правило"); }
    finally { setBusy(false); }
  }

  async function toggle(rule: Rule) {
    setBusy(true); try { await core(`/policies/${rule.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !rule.enabled }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося змінити правило"); } finally { setBusy(false); }
  }

  async function remove(rule: Rule) {
    setBusy(true); try { await core(`/policies/${rule.id}`, { method: "DELETE" }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося видалити правило"); } finally { setBusy(false); }
  }

  async function test() {
    setBusy(true); setDryRun(null);
    try { setDryRun(await core<DryRun>("/policies/dry-run", { method: "POST", body: JSON.stringify({ category: testCategory, operation: "test_operation", risk: testRisk, parameters: {} }) })); setError(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Dry-run не вдався"); } finally { setBusy(false); }
  }

  return (
    <ModuleShell title="Policy Studio" eyebrow="RULES · DRY-RUN · CONFLICTS">
      <form onSubmit={createRule} style={{ ...panel, display: "grid", gap: 9 }}>
        <strong>Нове правило</strong>
        <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder="Наприклад: завжди запитуй мене перед публічною дією" style={{ ...field, resize: "vertical" }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="category" style={field} />
          <select value={effect} onChange={(e) => setEffect(e.target.value as Rule["effect"])} style={field}><option value="deny">Заборонити</option><option value="require_approval">Потребує схвалення</option><option value="allow">Дозволити</option></select>
        </div>
        <button disabled={busy || !text.trim()} style={primary}>Зберегти</button>
      </form>

      {conflicts.length > 0 && <section style={{ ...panel, marginTop: 12, borderColor: "rgba(255,184,77,.3)" }}><strong>Конфлікти: {conflicts.length}</strong><div style={{ ...muted, marginTop: 5 }}>ALTER показує правила однієї категорії з різними ефектами. Виграє правило з вищим пріоритетом.</div></section>}
      {error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}

      <section style={{ display: "grid", gap: 9, marginTop: 12 }}>
        {rules.map((rule) => <article key={rule.id} style={{ ...panel, opacity: rule.enabled ? 1 : .55 }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{rule.original_text}</strong><span style={badge}>{rule.effect}</span></div>
          <div style={{ ...muted, marginTop: 6 }}>{rule.category} · priority {rule.priority} · {rule.enabled ? "активне" : "вимкнене"}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}><button type="button" disabled={busy} onClick={() => void toggle(rule)} style={primary}>{rule.enabled ? "Вимкнути" : "Увімкнути"}</button><button type="button" disabled={busy} onClick={() => void remove(rule)} style={danger}>Видалити</button></div>
        </article>)}
      </section>

      <section style={{ ...panel, display: "grid", gap: 9, marginTop: 14 }}>
        <strong>Перевірити правило без виконання</strong>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}><input value={testCategory} onChange={(e) => setTestCategory(e.target.value)} style={field} /><select value={testRisk} onChange={(e) => setTestRisk(e.target.value)} style={field}><option value="read">read</option><option value="reversible">reversible</option><option value="public">public</option><option value="financial">financial</option><option value="irreversible">irreversible</option><option value="authentication">authentication</option></select></div>
        <button type="button" onClick={() => void test()} disabled={busy} style={primary}>Dry-run</button>
        {dryRun && <div style={{ padding: 10, borderRadius: 12, background: "rgba(111,91,255,.08)" }}><strong>{dryRun.effect}</strong><div style={muted}>{dryRun.reason}</div><div style={muted}>Нічого не виконано.</div></div>}
      </section>
    </ModuleShell>
  );
}
const badge: React.CSSProperties = { whiteSpace: "nowrap", border: "1px solid rgba(143,126,255,.25)", borderRadius: 999, padding: "5px 8px", fontSize: 10, color: "#c9c2ff" };
