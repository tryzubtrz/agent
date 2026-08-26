"use client";

import { useCallback, useEffect, useState } from "react";
import ModuleShell, { muted, panel, primary } from "@/components/ModuleShell";
import { core, formatDate } from "@/lib/core-client";

type Notification = { key: string; id: string; title?: string; body?: string; read: boolean; created_at?: string; source?: string };

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[]>([]); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { try { setItems(await core<Notification[]>("/notifications")); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити сповіщення"); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  async function read(item: Notification) { setBusy(true); try { await core(`/notifications/${item.key}/read`, { method: "POST", body: "{}" }); await refresh(); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося оновити"); } finally { setBusy(false); } }
  return <ModuleShell title="Сповіщення" eyebrow="IN-APP EVENT CENTER">
    <section style={{ ...panel, marginBottom: 12 }}><strong>{items.filter((item) => !item.read).length} непрочитаних</strong><p style={muted}>Тут ALTER збирає внутрішні повідомлення від автоматизацій та системних процесів. Push/email канали можна додати окремо, не змішуючи їх з Gmail.</p></section>
    {error && <section style={{ ...panel, color: "#ffaaa7", marginBottom: 12 }}>{error}</section>}
    <section style={{ display: "grid", gap: 9 }}>{items.length === 0 && <div style={panel}>Поки тихо.</div>}{items.map((item) => <article key={item.key} style={{ ...panel, opacity: item.read ? .6 : 1 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}><strong>{item.title || "ALTER"}</strong><span style={muted}>{formatDate(item.created_at)}</span></div>{item.body && <p style={{ ...muted, fontSize: 13 }}>{item.body}</p>}<div style={muted}>{item.source || "system"}</div>{!item.read && <button disabled={busy} onClick={() => void read(item)} style={{ ...primary, marginTop: 9 }}>Позначити прочитаним</button>}</article>)}</section>
  </ModuleShell>;
}
