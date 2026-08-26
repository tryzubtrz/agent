"use client";

import { useEffect, useState } from "react";
import ModuleShell, { field, muted, panel, primary } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type Settings = { language: string; voice_enabled: boolean; notifications_enabled: boolean; autonomy: "ask_often" | "balanced" | "high"; remember_conversations: boolean; theme: "dark" | "system" };
const defaults: Settings = { language: "uk", voice_enabled: true, notifications_enabled: true, autonomy: "balanced", remember_conversations: true, theme: "dark" };

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings>(defaults); const [busy, setBusy] = useState(false); const [saved, setSaved] = useState(false); const [error, setError] = useState("");
  useEffect(() => { core<Settings>("/settings").then(setSettings).catch((err) => setError(err instanceof Error ? err.message : "Не вдалося завантажити")); }, []);
  async function save() { setBusy(true); setSaved(false); try { setSettings(await core<Settings>("/settings", { method: "PUT", body: JSON.stringify(settings) })); setSaved(true); setError(""); } catch (err) { setError(err instanceof Error ? err.message : "Не вдалося зберегти"); } finally { setBusy(false); } }
  const toggle = (key: keyof Settings) => setSettings((value) => ({ ...value, [key]: !value[key] } as Settings));
  return <ModuleShell title="Налаштування" eyebrow="OWNER PREFERENCES · PERSISTENT">
    <section style={{ ...panel, display: "grid", gap: 12 }}>
      <label><div style={muted}>Мова</div><select value={settings.language} onChange={(e) => setSettings({ ...settings, language: e.target.value })} style={field}><option value="uk">Українська</option><option value="en">English</option><option value="pl">Polski</option></select></label>
      <label><div style={muted}>Автономність за замовчуванням</div><select value={settings.autonomy} onChange={(e) => setSettings({ ...settings, autonomy: e.target.value as Settings["autonomy"] })} style={field}><option value="ask_often">Часто питати</option><option value="balanced">Збалансовано</option><option value="high">Висока автономність</option></select></label>
      <Toggle label="Голосові відповіді" value={settings.voice_enabled} onClick={() => toggle("voice_enabled")}/><Toggle label="In-app сповіщення" value={settings.notifications_enabled} onClick={() => toggle("notifications_enabled")}/><Toggle label="Памʼятати історію розмов" value={settings.remember_conversations} onClick={() => toggle("remember_conversations")}/>
      <label><div style={muted}>Тема</div><select value={settings.theme} onChange={(e) => setSettings({ ...settings, theme: e.target.value as Settings["theme"] })} style={field}><option value="dark">Темна</option><option value="system">Системна</option></select></label>
      <button onClick={() => void save()} disabled={busy} style={primary}>{busy ? "Зберігаю…" : "Зберегти"}</button>{saved && <div style={{ color: "#9af0bd" }}>Збережено в ALTER.</div>}
    </section>{error && <section style={{ ...panel, marginTop: 12, color: "#ffaaa7" }}>{error}</section>}
  </ModuleShell>;
}
function Toggle({ label, value, onClick }: { label: string; value: boolean; onClick: () => void }) { return <button type="button" onClick={onClick} style={{ ...panel, display: "flex", justifyContent: "space-between", color: "inherit", textAlign: "left" }}><span>{label}</span><strong style={{ color: value ? "#9af0bd" : "#ffd28b" }}>{value ? "ON" : "OFF"}</strong></button>; }
