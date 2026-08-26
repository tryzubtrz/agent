"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Item = { namespace: string; key: string; value: unknown; updated_at?: string };

export default function MemoryPage() {
  const [items, setItems] = useState<Item[]>([]);
  const [content, setContent] = useState("");
  const [tags, setTags] = useState("");
  const [source, setSource] = useState("owner");
  const [sensitivity, setSensitivity] = useState("normal");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try { setItems(await core<Item[]>("/memory?namespace=memory&limit=250")); setError(""); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити памʼять"); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function save(event: FormEvent) {
    event.preventDefault(); if (!content.trim()) return; setBusy(true);
    try {
      const key = `memory:${Date.now()}`;
      await core("/memory", { method: "PUT", body: JSON.stringify({ namespace: "memory", key, value: { content: content.trim(), tags: tags.split(',').map((v) => v.trim()).filter(Boolean), source, sensitivity, confirmed: true, created_at: new Date().toISOString() } }) });
      setContent(""); setTags(""); await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося зберегти. Секрети потрібно класти у Vault."); }
    finally { setBusy(false); }
  }

  async function remove(item: Item) {
    setBusy(true); try { await core(`/memory/${encodeURIComponent(item.namespace)}/${encodeURIComponent(item.key)}`, { method: "DELETE" }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося забути запис"); } finally { setBusy(false); }
  }

  return (
    <ModuleShell title="Памʼять" eyebrow="MEMORY EXPLORER · PROVENANCE">
      <form onSubmit={save} style={{ ...panel, display: "grid", gap: 9 }}>
        <strong>Запамʼятати</strong>
        <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={4} placeholder="Факт, вподобання, контекст проєкту…" style={{ ...field, resize: "vertical" }} />
        <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="теги через кому" style={field} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}><input value={source} onChange={(e) => setSource(e.target.value)} placeholder="джерело" style={field} /><select value={sensitivity} onChange={(e) => setSensitivity(e.target.value)} style={field}><option value="normal">звичайне</option><option value="private">приватне</option><option value="temporary">тимчасове</option></select></div>
        <button disabled={busy || !content.trim()} style={primary}>Зберегти</button>
        <div style={muted}>Паролі, токени, API keys і private keys блокуються для звичайної памʼяті — для них є Vault.</div>
      </form>
      {error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}
      <section style={{ display: "grid", gap: 9, marginTop: 14 }}>
        {items.map((item) => {
          const value = item.value as Record<string, unknown>;
          return <article key={item.key} style={panel}><strong>{typeof value?.content === 'string' ? value.content : JSON.stringify(item.value)}</strong><div style={{ ...muted, marginTop: 7 }}>Джерело: {String(value?.source || 'legacy')} · чутливість: {String(value?.sensitivity || '—')} · {formatDate(item.updated_at)}</div>{Array.isArray(value?.tags) && <div style={{ ...muted, marginTop: 5 }}>Теги: {(value.tags as string[]).join(', ')}</div>}<button type="button" disabled={busy} onClick={() => void remove(item)} style={{ ...danger, marginTop: 10 }}>Забути</button></article>;
        })}
      </section>
    </ModuleShell>
  );
}
