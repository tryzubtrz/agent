"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import ModuleShell, { danger, field, muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Row = { key: string; value: { id: string; title: string; starts_at: string; ends_at?: string | null; location?: string | null; notes?: string | null } };

function icsDate(value: string): string { return new Date(value).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, ""); }
function escapeIcs(value: string): string { return value.replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;"); }

export default function CalendarPage() {
  const [items, setItems] = useState<Row[]>([]); const [title, setTitle] = useState(""); const [starts, setStarts] = useState(""); const [ends, setEnds] = useState(""); const [location, setLocation] = useState(""); const [notes, setNotes] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { try { setItems(await core<Row[]>("/calendar")); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити календар"); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  async function create(event: FormEvent) { event.preventDefault(); if (!title.trim() || !starts) return; setBusy(true); try { await core("/calendar", { method: "POST", body: JSON.stringify({ title: title.trim(), starts_at: new Date(starts).toISOString(), ends_at: ends ? new Date(ends).toISOString() : null, location: location || null, notes: notes || null }) }); setTitle(""); setStarts(""); setEnds(""); setLocation(""); setNotes(""); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося створити подію"); } finally { setBusy(false); } }
  async function remove(row: Row) { setBusy(true); try { await core(`/memory/calendar/${encodeURIComponent(row.key)}`, { method: "DELETE" }); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося видалити подію"); } finally { setBusy(false); } }
  function exportIcs() { const events = items.map(({ value }) => ["BEGIN:VEVENT", `UID:${value.id}@alter`, `DTSTART:${icsDate(value.starts_at)}`, ...(value.ends_at ? [`DTEND:${icsDate(value.ends_at)}`] : []), `SUMMARY:${escapeIcs(value.title)}`, ...(value.location ? [`LOCATION:${escapeIcs(value.location)}`] : []), ...(value.notes ? [`DESCRIPTION:${escapeIcs(value.notes)}`] : []), "END:VEVENT"].join("\r\n")).join("\r\n"); const blob = new Blob([`BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//ALTER//Calendar//UK\r\n${events}\r\nEND:VCALENDAR\r\n`], { type: "text/calendar" }); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "ALTER-calendar.ics"; a.click(); URL.revokeObjectURL(url); }
  return <ModuleShell title="Календар" eyebrow="LOCAL CALENDAR · ICS" action={<button onClick={exportIcs} disabled={!items.length} style={primary}>Export .ics</button>}>
    <section style={{ ...panel, marginBottom: 12 }}><strong>Працює без Google/Gmail</strong><p style={muted}>Це власний календар ALTER у Neon. Можеш експортувати .ics і відкрити його в Apple Calendar. Google/Outlook OAuth не підключається зараз.</p></section>
    <form onSubmit={create} style={{ ...panel, display: "grid", gap: 8 }}><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Подія" style={field}/><div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}><input type="datetime-local" value={starts} onChange={(e) => setStarts(e.target.value)} style={field}/><input type="datetime-local" value={ends} onChange={(e) => setEnds(e.target.value)} style={field}/></div><input value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Місце" style={field}/><textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Нотатка" style={{ ...field, resize: "vertical" }}/><button disabled={busy || !title.trim() || !starts} style={primary}>Додати</button></form>
    {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
    <section style={{ display: "grid", gap: 9, marginTop: 14 }}>{items.sort((a,b) => a.value.starts_at.localeCompare(b.value.starts_at)).map((row) => <article key={row.key} style={panel}><strong>{row.value.title}</strong><div style={{ ...muted, marginTop: 6 }}>{formatDate(row.value.starts_at)}{row.value.ends_at ? ` → ${formatDate(row.value.ends_at)}` : ""}</div>{row.value.location && <div style={muted}>{row.value.location}</div>}<button onClick={() => void remove(row)} disabled={busy} style={{ ...danger, marginTop: 9 }}>Видалити</button></article>)}</section>
  </ModuleShell>;
}
