"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Row = { key: string; value: { id: string; name: string; email?: string | null; phone?: string | null; notes?: string | null } };

export default function ContactsPage() {
  const [items, setItems] = useState<Row[]>([]); const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [phone, setPhone] = useState(""); const [notes, setNotes] = useState(""); const [query, setQuery] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const refresh = useCallback(async () => { try { setItems(await core<Row[]>("/contacts")); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити контакти"); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  const filtered = useMemo(() => { const needle = query.trim().toLowerCase(); if (!needle) return items; return items.filter((row) => JSON.stringify(row.value).toLowerCase().includes(needle)); }, [items, query]);
  async function create(event: FormEvent) { event.preventDefault(); if (!name.trim()) return; setBusy(true); try { await core("/contacts", { method: "POST", body: JSON.stringify({ name: name.trim(), email: email || null, phone: phone || null, notes: notes || null }) }); setName(""); setEmail(""); setPhone(""); setNotes(""); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося додати контакт"); } finally { setBusy(false); } }
  async function remove(row: Row) { setBusy(true); try { await core(`/memory/contact/${encodeURIComponent(row.key)}`, { method: "DELETE" }); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося видалити"); } finally { setBusy(false); } }
  return <ModuleShell title="Контакти" eyebrow="PRIVATE CONTACT CONTEXT">
    <section style={{ ...panel, marginBottom: 12 }}><strong>Приватна контактна база ALTER</strong><p style={muted}>Не синхронізується з Google/Gmail. Дані зберігаються в твоєму workspace і використовуються лише як дозволений контекст.</p></section>
    <form onSubmit={create} style={{ ...panel, display: "grid", gap: 8 }}><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Імʼя" style={field}/><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}><input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" style={field}/><input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Телефон" style={field}/></div><textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Контекст / нотатка" style={{ ...field, resize: "vertical" }}/><button disabled={busy || !name.trim()} style={primary}>Додати</button></form>
    <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Пошук…" style={{ ...field, marginTop: 12 }}/>
    {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
    <section style={{ display: "grid", gap: 9, marginTop: 12 }}>{filtered.map((row) => <article key={row.key} style={panel}><strong>{row.value.name}</strong>{row.value.email && <div style={muted}>{row.value.email}</div>}{row.value.phone && <div style={muted}>{row.value.phone}</div>}{row.value.notes && <p style={muted}>{row.value.notes}</p>}<button onClick={() => void remove(row)} disabled={busy} style={{ ...danger, marginTop: 8 }}>Видалити</button></article>)}</section>
  </ModuleShell>;
}
