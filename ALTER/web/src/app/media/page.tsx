"use client";

import Link from "next/link";
import { Film, Image as ImageIcon, RefreshCw, Sparkles } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import ModuleShell, { muted, panel, primary, warn } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Status = { provider: string; configured: boolean; state: string; capabilities: string[]; cost_confirmation_required: boolean; local_runtime_connected: boolean; output_persistence: string };
type Job = { id: string; provider_task_id: string; provider: string; kind: "image" | "video"; prompt: string; ratio: string; duration?: number | null; status: string; estimated_cost?: unknown };
type ProviderTask = { id: string; status: string; output: string[]; failure?: string | null; provider: string; output_urls_ephemeral: boolean };

export default function MediaPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [kind, setKind] = useState<"image" | "video">("image");
  const [prompt, setPrompt] = useState("");
  const [ratio, setRatio] = useState<"square" | "landscape" | "portrait">("square");
  const [duration, setDuration] = useState<5 | 10>(5);
  const [confirm, setConfirm] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [providerTask, setProviderTask] = useState<ProviderTask | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refreshStatus = useCallback(async () => {
    try { setStatus(await core<Status>("/media/status")); setError(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося перевірити Media provider"); }
  }, []);
  useEffect(() => { void refreshStatus(); }, [refreshStatus]);

  async function submit(event: FormEvent) {
    event.preventDefault(); if (!prompt.trim() || !confirm || busy || !status?.configured) return;
    setBusy(true); setError(""); setJob(null); setProviderTask(null);
    try {
      const result = await core<Job>("/media/generate", { method: "POST", body: JSON.stringify({ kind, prompt: prompt.trim(), ratio, duration, confirm_external_cost: true }) });
      setJob(result);
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося запустити генерацію"); }
    finally { setBusy(false); }
  }

  async function poll() {
    if (!job || busy) return; setBusy(true); setError("");
    try { setProviderTask(await core<ProviderTask>(`/media/tasks/${encodeURIComponent(job.provider_task_id)}`)); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося перевірити generation task"); }
    finally { setBusy(false); }
  }

  return (
    <ModuleShell title="Media Center" eyebrow="IMAGE · VIDEO · COST-GATED" action={<Link href="/vault" style={{ ...primary, textDecoration: "none" }}>Vault</Link>}>
      <section style={{ ...panel, display: "grid", gap: 8 }}>
        <div style={{ display: "flex", gap: 9, alignItems: "center" }}><Sparkles size={19} /><strong>{status?.configured ? "Media provider готовий" : "Потрібен окремий media API secret"}</strong></div>
        <div style={muted}>ALTER може запускати генерацію зображень і відео через окремий provider. Кожен запуск вимагає явного підтвердження витрат. Локальні FLUX/Wan залишаються у Model Registry до появи GPU runtime.</div>
        {!status?.configured && <div style={warn}>Зайди у Vault → `vault:runway` → встав Developer API secret. Не надсилай його в чат.</div>}
        <div style={{ display: "flex", gap: 7, flexWrap: "wrap" }}><span style={chip}>Provider: {status?.provider || "—"}</span><span style={chip}>Cost gate: ON</span><span style={chip}>Local GPU: {status?.local_runtime_connected ? "connected" : "not connected"}</span></div>
      </section>

      {error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}

      <form onSubmit={submit} style={{ ...panel, marginTop: 12, display: "grid", gap: 10 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <button type="button" style={{ ...choice, ...(kind === "image" ? selected : {}) }} onClick={() => setKind("image")}><ImageIcon size={16} /> Зображення</button>
          <button type="button" style={{ ...choice, ...(kind === "video" ? selected : {}) }} onClick={() => setKind("video")}><Film size={16} /> Відео</button>
        </div>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Опиши, що створити…" rows={5} style={field} />
        <div style={{ display: "grid", gridTemplateColumns: kind === "video" ? "1fr 1fr" : "1fr", gap: 8 }}>
          <select value={ratio} onChange={(e) => setRatio(e.target.value as typeof ratio)} style={field}><option value="square">1:1</option><option value="landscape">16:9</option><option value="portrait">9:16</option></select>
          {kind === "video" && <select value={duration} onChange={(e) => setDuration(Number(e.target.value) as 5 | 10)} style={field}><option value={5}>5 сек</option><option value={10}>10 сек</option></select>}
        </div>
        <label style={confirmRow}><input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /><span>Я підтверджую, що ця генерація може використати зовнішні кредити provider.</span></label>
        <button disabled={busy || !status?.configured || !prompt.trim() || !confirm} style={primary}>{busy ? "Працюю…" : "Запустити генерацію"}</button>
      </form>

      {job && <section style={{ ...panel, marginTop: 12, display: "grid", gap: 9 }}><strong>Generation task створено</strong><div style={muted}>Provider task: {job.provider_task_id} · {job.kind} · status {job.status}</div><button type="button" onClick={() => void poll()} disabled={busy} style={primary}><RefreshCw size={15} /> Перевірити результат</button></section>}

      {providerTask && <section style={{ ...panel, marginTop: 12, display: "grid", gap: 9 }}><strong>Status: {providerTask.status}</strong>{providerTask.failure && <div style={{ color: "#ffaaa7" }}>{providerTask.failure}</div>}{providerTask.output.map((url) => providerTask.status === "SUCCEEDED" ? (kind === "image" ? <img key={url} src={url} alt="ALTER generated" style={media} /> : <video key={url} src={url} controls playsInline style={media} />) : null)}{providerTask.output.length > 0 && <div style={warn}>Provider URLs можуть бути тимчасовими. Durable object storage для raw media ще потребує окремого storage credential.</div>}</section>}
    </ModuleShell>
  );
}

const chip: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", borderRadius: 999, padding: "6px 9px", color: "#c9c2ff", fontSize: 11 };
const field: React.CSSProperties = { width: "100%", boxSizing: "border-box", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: "11px 12px", outline: "none", resize: "vertical" };
const choice: React.CSSProperties = { minHeight: 42, borderRadius: 12, border: "1px solid rgba(255,255,255,.08)", background: "rgba(255,255,255,.025)", color: "#aaa", display: "flex", alignItems: "center", justifyContent: "center", gap: 6 };
const selected: React.CSSProperties = { borderColor: "rgba(143,126,255,.35)", background: "rgba(111,91,255,.15)", color: "#d9d3ff" };
const confirmRow: React.CSSProperties = { display: "grid", gridTemplateColumns: "18px 1fr", gap: 8, alignItems: "start", color: "rgba(255,255,255,.7)", fontSize: 12, lineHeight: 1.45 };
const media: React.CSSProperties = { width: "100%", maxHeight: "65dvh", objectFit: "contain", borderRadius: 14, background: "#000" };
