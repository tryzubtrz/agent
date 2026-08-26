"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary, warn } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Item = { key: string; next_due_at?: string | null; value: { id: string; name: string; prompt: string; cadence: string; hour_utc: number; weekday: number; enabled: boolean; mode: string; last_run_at?: string | null } };

export default function AutomationsPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [name, setName] = useState(""); const [prompt, setPrompt] = useState(""); const [cadence, setCadence] = useState("manual"); const [mode, setMode] = useState("create_task");
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const refresh = useCallback(async () => { try { setItems(await core<Item[]>("/automations")); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити автоматизації"); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  async function create(event: FormEvent) { event.preventDefault(); if (!name.trim() || !prompt.trim()) return; setBusy(true); try { await core("/automations", { method: "POST", body: JSON.stringify({ name: name.trim(), prompt: prompt.trim(), cadence, hour_utc: 12, weekday: 0, enabled: true, mode }) }); setName(""); setPrompt(""); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося створити"); } finally { setBusy(false); } }
  async function run(item: Item) { setBusy(true); try { await core(`/automations/${item.key}/run`, { method: "POST", body: "{}" }); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося запустити"); } finally { setBusy(false); } }
  async function remove(item: Item) { setBusy(true); try { await core(`/automations/${item.key}`, { method: "DELETE" }); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося видалити"); } finally { setBusy(false); } }
  return <ModuleShell title="Автоматизації" eyebrow="SCHEDULE · RUN · AUDIT">
    <section style={{ ...panel, marginBottom: 12 }}><strong>Cloud scheduler</strong><p style={muted}>Run now працює одразу. На поточному Vercel cloud tick запускається раз на день; він лише створює внутрішню задачу або in-app notification і не виконує зовнішніх side effects.</p><div style={warn}>Hourly/weekly cadence зберігається в моделі, але на Hobby cloud частота scheduler обмежена. Це показується чесно.</div></section>
    <form onSubmit={create} style={{ ...panel, display: "grid", gap: 9 }}><strong>Нова автоматизація</strong><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Назва" style={field}/><textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} rows={3} placeholder="Що ALTER має підготувати" style={{ ...field, resize: "vertical" }}/><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}><select value={cadence} onChange={(e) => setCadence(e.target.value)} style={field}><option value="manual">manual</option><option value="daily">daily</option><option value="weekly">weekly</option><option value="hourly">hourly (stored)</option></select><select value={mode} onChange={(e) => setMode(e.target.value)} style={field}><option value="create_task">створити задачу</option><option value="notify_only">тільки сповіщення</option></select></div><button disabled={busy || !name.trim() || !prompt.trim()} style={primary}>Створити</button></form>
    {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
    <section style={{ display: "grid", gap: 9, marginTop: 14 }}>{items.map((item) => <article key={item.key} style={panel}><div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{item.value.name}</strong><span style={badge}>{item.value.cadence}</span></div><p style={{ ...muted, margin: "7px 0" }}>{item.value.prompt}</p><div style={muted}>Наступна due: {formatDate(item.next_due_at)} · останній запуск: {formatDate(item.value.last_run_at)}</div><div style={{ display: "flex", gap: 8, marginTop: 10 }}><button disabled={busy} onClick={() => void run(item)} style={primary}>Run now</button><button disabled={busy} onClick={() => void remove(item)} style={danger}>Видалити</button></div></article>)}</section>
  </ModuleShell>;
}
const badge: React.CSSProperties = { border: "1px solid rgba(143,126,255,.25)", borderRadius: 999, padding: "5px 8px", color: "#c9c2ff", fontSize: 10 };
