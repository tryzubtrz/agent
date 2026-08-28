"use client";

import Link from "next/link";
import { Brain, CheckCircle2, Cpu, HardDrive, Route, Server, ShieldCheck, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

type Model = {
  id: string;
  provider: string;
  display_name: string;
  capabilities: string[];
  configured: boolean;
  credential_configured: boolean;
  action: string;
  side_effects: boolean;
  policy_boundary: string;
  source: "cloud" | "local";
  install_state: "ready" | "credential_required" | "requires_local_runtime" | string;
  license: string;
  requirements: string;
};

type Catalog = {
  models: Model[];
  configured: number;
  local_runtime_connected: boolean;
  installation_policy: string;
};

type Routed = { selected: string; provider: string; purpose: string; mode: string; reason: string };

async function core<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/core${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!response.ok) {
    let message = "";
    try {
      const payload = await response.json();
      message = typeof payload?.detail === "string" ? payload.detail : payload?.detail?.message || "";
    } catch {
      message = await response.text().catch(() => "");
    }
    throw new Error(message || `Core returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export default function ModelsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [purpose, setPurpose] = useState("reasoning");
  const [mode, setMode] = useState("normal");
  const [routed, setRouted] = useState<Routed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try { setCatalog(await core<Catalog>("/models/catalog")); setError(null); }
    catch (err) { setError(err instanceof Error ? err.message : "Не вдалося завантажити registry"); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const cloud = useMemo(() => catalog?.models.filter((model) => model.source === "cloud") ?? [], [catalog]);
  const local = useMemo(() => catalog?.models.filter((model) => model.source === "local") ?? [], [catalog]);

  async function testRoute() {
    setBusy(true); setRouted(null);
    try {
      const result = await core<Routed>("/models/route", { method: "POST", body: JSON.stringify({ purpose, mode }) });
      setRouted(result); setError(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Немає доступної моделі"); }
    finally { setBusy(false); }
  }

  return (
    <main style={shell}>
      <header style={header}><Link href="/" style={back}>← ALTER</Link><div><div style={eyebrow}>MODEL ROUTER · LIVE</div><h1 style={title}>Моделі</h1></div><Brain size={25} /></header>

      <section style={truthPanel}>
        <div style={truthIcon}><ShieldCheck size={21} /></div>
        <div>
          <strong>Тільки перевірені стани</strong>
          <p style={muted}>Ready означає, що модель справді доступна ALTER. Каталог локальних моделей — це план інсталяції, а не вигаданий статус «працює».</p>
        </div>
      </section>

      {error && <section style={errorBox}>{error}</section>}

      <div style={stats}>
        <Stat value={catalog?.configured ?? "—"} label="підключено" />
        <Stat value={cloud.length || "—"} label="хмарних" />
        <Stat value={local.length || "—"} label="локальних у каталозі" />
      </div>

      <SectionTitle icon={Server} title="Підключені провайдери" detail="Беруть участь у production-маршрутизації лише після реальної перевірки." />
      <section style={list}>
        {cloud.map((model) => <ModelCard key={model.id} model={model} />)}
      </section>

      <section style={{ ...panel, marginTop: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}><HardDrive size={18} color="#ffd28b" /><strong>Локальний runtime не підключений</strong></div>
        <p style={muted}>Vercel і телефон не можуть самі запустити ці ваги. Потрібен окремий компʼютер або GPU-сервер під контролем власника; далі — перевірка ліцензії, sandbox, benchmark і лише потім довіра моделі.</p>
        <span style={{ ...badge, ...waiting }}><XCircle size={12} /> {catalog?.local_runtime_connected ? "Connected" : "Requires host"}</span>
      </section>

      <SectionTitle icon={Cpu} title="10 локальних кандидатів" detail="Не встановлені. Показані реальні вимоги до обладнання та ліцензії." />
      <section style={list}>
        {local.map((model) => <ModelCard key={model.id} model={model} />)}
      </section>

      <section style={{ ...panel, marginTop: 16, display: "grid", gap: 10 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}><Route size={18} /><strong>Перевірити production-маршрут</strong></div>
        <p style={muted}>Router вибирає лише налаштовану модель. Якщо потрібного capability немає, ALTER поверне чесну помилку замість демо-відповіді.</p>
        <div style={fields}>
          <select value={purpose} onChange={(event) => setPurpose(event.target.value)} style={field}>
            <option value="chat">chat</option><option value="reasoning">reasoning</option><option value="planning">planning</option><option value="summarization">summarization</option><option value="coding">coding</option><option value="vision">vision</option><option value="image">image</option><option value="video">video</option><option value="speech_to_text">speech to text</option><option value="text_to_speech">text to speech</option><option value="ocr">ocr</option><option value="retrieval">retrieval</option>
          </select>
          <select value={mode} onChange={(event) => setMode(event.target.value)} style={field}>
            <option value="quick">quick</option><option value="normal">normal</option><option value="deep">deep</option><option value="plan">plan</option>
          </select>
        </div>
        <button type="button" onClick={() => void testRoute()} disabled={busy} style={primary}>{busy ? "Перевіряю…" : "Вибрати модель"}</button>
        {routed && <div style={result}><strong>{routed.selected}</strong><div style={muted}>{routed.reason}</div></div>}
      </section>
    </main>
  );
}

function SectionTitle({ icon: Icon, title: text, detail }: { icon: typeof Brain; title: string; detail: string }) {
  return <div style={sectionTitle}><Icon size={19} /><div><strong>{text}</strong><div style={muted}>{detail}</div></div></div>;
}

function ModelCard({ model }: { model: Model }) {
  const ready = model.configured;
  return (
    <article style={panel}>
      <div style={modelHead}>
        <div style={icon}><Brain size={20} /></div>
        <div style={{ minWidth: 0 }}><strong>{model.display_name}</strong><div style={muted}>{model.provider} · {model.action}</div></div>
        <span style={{ ...badge, ...(ready ? good : waiting) }}>{ready ? <><CheckCircle2 size={12} /> Ready</> : <><XCircle size={12} /> Not installed</>}</span>
      </div>
      <div style={chips}>{model.capabilities.map((capability) => <span key={capability} style={chip}>{capability}</span>)}</div>
      <dl style={facts}>
        <div><dt style={term}>Вимоги</dt><dd style={definition}>{model.requirements}</dd></div>
        <div><dt style={term}>Ліцензія</dt><dd style={definition}>{model.license}</dd></div>
        <div><dt style={term}>Межа</dt><dd style={definition}>{model.policy_boundary} · side effects: {model.side_effects ? "можливі" : "ні"}</dd></div>
      </dl>
    </article>
  );
}

function Stat({ value, label }: { value: string | number; label: string }) {
  return <div style={stat}><strong style={{ fontSize: 20 }}>{value}</strong><span style={muted}>{label}</span></div>;
}

const shell: React.CSSProperties = { minHeight: "100dvh", maxWidth: 760, margin: "0 auto", padding: "max(18px, env(safe-area-inset-top)) 14px calc(30px + env(safe-area-inset-bottom))", color: "#f4f2ff" };
const header: React.CSSProperties = { display: "grid", gridTemplateColumns: "auto 1fr auto", gap: 12, alignItems: "center", marginBottom: 14 };
const back: React.CSSProperties = { color: "#b8b2d8", textDecoration: "none", fontWeight: 700 };
const title: React.CSSProperties = { margin: "2px 0 0", fontSize: 26 };
const eyebrow: React.CSSProperties = { fontSize: 10, color: "#958bff", letterSpacing: ".12em" };
const panel: React.CSSProperties = { border: "1px solid rgba(255,255,255,.1)", background: "rgba(255,255,255,.035)", borderRadius: 18, padding: 14 };
const truthPanel: React.CSSProperties = { ...panel, display: "grid", gridTemplateColumns: "43px 1fr", gap: 10, alignItems: "center", borderColor: "rgba(93,224,154,.18)" };
const truthIcon: React.CSSProperties = { width: 43, height: 43, display: "grid", placeItems: "center", borderRadius: 13, color: "#9af0bd", background: "rgba(93,224,154,.07)" };
const errorBox: React.CSSProperties = { ...panel, borderColor: "rgba(255,100,100,.35)", color: "#ffaaa7", marginTop: 12 };
const muted: React.CSSProperties = { color: "rgba(255,255,255,.55)", fontSize: 12, lineHeight: 1.5, margin: "4px 0 0" };
const stats: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(3,1fr)", gap: 7, marginTop: 10 };
const stat: React.CSSProperties = { ...panel, display: "grid", gap: 1, textAlign: "center", padding: 10 };
const sectionTitle: React.CSSProperties = { display: "flex", gap: 9, alignItems: "center", margin: "20px 3px 9px", color: "#d9d4ff" };
const list: React.CSSProperties = { display: "grid", gap: 10 };
const modelHead: React.CSSProperties = { display: "grid", gridTemplateColumns: "42px minmax(0,1fr) auto", gap: 10, alignItems: "center" };
const icon: React.CSSProperties = { width: 42, height: 42, display: "grid", placeItems: "center", borderRadius: 13, background: "rgba(118,102,255,.1)", color: "#aaa1ff" };
const badge: React.CSSProperties = { borderRadius: 999, padding: "6px 9px", fontSize: 10, display: "inline-flex", gap: 5, alignItems: "center", whiteSpace: "nowrap" };
const good: React.CSSProperties = { color: "#9af0bd", border: "1px solid rgba(93,224,154,.25)", background: "rgba(93,224,154,.08)" };
const waiting: React.CSSProperties = { color: "#ffd28b", border: "1px solid rgba(255,184,77,.25)", background: "rgba(255,184,77,.08)" };
const chips: React.CSSProperties = { display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 };
const chip: React.CSSProperties = { borderRadius: 999, padding: "5px 8px", background: "rgba(255,255,255,.04)", border: "1px solid rgba(255,255,255,.08)", color: "rgba(255,255,255,.7)", fontSize: 11 };
const facts: React.CSSProperties = { display: "grid", gap: 8, margin: "12px 0 0", paddingTop: 11, borderTop: "1px solid rgba(255,255,255,.07)" };
const term: React.CSSProperties = { color: "rgba(255,255,255,.38)", fontSize: 9, textTransform: "uppercase", letterSpacing: ".07em" };
const definition: React.CSSProperties = { color: "rgba(255,255,255,.67)", fontSize: 11, lineHeight: 1.45, margin: "2px 0 0" };
const fields: React.CSSProperties = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 };
const field: React.CSSProperties = { width: "100%", border: "1px solid rgba(255,255,255,.1)", background: "rgba(0,0,0,.2)", color: "#fff", borderRadius: 12, padding: "11px 12px", outline: "none" };
const primary: React.CSSProperties = { minHeight: 42, border: "1px solid rgba(143,126,255,.35)", background: "rgba(111,91,255,.15)", color: "#d9d3ff", borderRadius: 12, fontWeight: 700 };
const result: React.CSSProperties = { padding: 12, borderRadius: 13, border: "1px solid rgba(93,224,154,.2)", background: "rgba(93,224,154,.05)" };
