"use client";

import {
  Bot,
  Brain,
  CheckCircle2,
  ChevronRight,
  CircleStop,
  Clock3,
  FileArchive,
  Files,
  Globe2,
  KeyRound,
  MemoryStick,
  MessageSquareText,
  Mic,
  MonitorSmartphone,
  Paperclip,
  Play,
  PlugZap,
  Send,
  Settings,
  ShieldCheck,
  Smartphone,
  SquareTerminal,
  Store,
  UsersRound
} from "lucide-react";
import { type ComponentType, type FormEvent, useMemo, useState } from "react";

type ModuleItem = {
  label: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
  state?: "ready" | "planned" | "attention";
};

const modules: ModuleItem[] = [
  { label: "ALTER", icon: Bot, state: "ready" },
  { label: "Files", icon: Files, state: "ready" },
  { label: "Browser", icon: Globe2, state: "planned" },
  { label: "Console", icon: SquareTerminal, state: "planned" },
  { label: "Android", icon: Smartphone, state: "planned" },
  { label: "Rules", icon: ShieldCheck, state: "ready" },
  { label: "Vault", icon: KeyRound, state: "ready" },
  { label: "Models", icon: MemoryStick, state: "ready" },
  { label: "Market", icon: Store, state: "planned" },
  { label: "Tasks", icon: Clock3, state: "ready" },
  { label: "Connectors", icon: PlugZap, state: "attention" },
  { label: "Memory", icon: Brain, state: "ready" },
  { label: "People", icon: UsersRound, state: "ready" },
  { label: "Settings", icon: Settings, state: "ready" }
];

const activity = [
  "Архітектура control plane створена",
  "Threat model доданий",
  "Botpress очікує повторного підключення акаунта"
];

export default function CockpitPage() {
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState("Звичайно");
  const [submitted, setSubmitted] = useState<string[]>([]);

  const readyCount = useMemo(
    () => modules.filter((item) => item.state === "ready").length,
    []
  );

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = message.trim();
    if (!value) return;
    setSubmitted((items) => [...items, value]);
    setMessage("");
  }

  return (
    <main className="shell">
      <section className="topbar">
        <div className="brandBlock">
          <div className="monogram">A</div>
          <div>
            <div className="eyebrow">PERSONAL CONTROL PLANE</div>
            <h1>ALTER</h1>
          </div>
        </div>
        <button className="statusPill" type="button" aria-label="Статус ALTER">
          <span className="statusDot" /> Виконує
        </button>
      </section>

      <section className="heroCard">
        <div className="cardHead">
          <div>
            <div className="eyebrow">ЗАРАЗ</div>
            <h2>Будую основу ALTER</h2>
          </div>
          <div className="taskCount">1 активна</div>
        </div>

        <div className="progressTrack" aria-label="Прогрес задачі">
          <span style={{ width: "36%" }} />
        </div>

        <div className="taskMeta">
          <span><CheckCircle2 size={16} /> 3 етапи завершено</span>
          <span><Play size={16} /> Далі: cockpit + iOS</span>
        </div>

        <div className="heroActions">
          <button className="primaryButton" type="button">
            <MonitorSmartphone size={17} /> Відкрити live-view
          </button>
          <button className="secondaryButton" type="button">
            <CircleStop size={17} /> Пауза
          </button>
        </div>
      </section>

      <section className="sectionBlock">
        <div className="sectionTitleRow">
          <div>
            <div className="eyebrow">РОБОЧИЙ ПРОСТІР</div>
            <h3>Модулі</h3>
          </div>
          <span className="muted">{readyCount} готових основ</span>
        </div>

        <div className="moduleGrid">
          {modules.map(({ label, icon: Icon, state }) => (
            <button className="moduleCard" key={label} type="button">
              <div className="moduleIcon">
                <Icon size={22} strokeWidth={1.8} />
              </div>
              <span>{label}</span>
              <i className={`moduleState ${state ?? "planned"}`} />
            </button>
          ))}
        </div>
      </section>

      <section className="approvalCard">
        <div className="approvalIcon"><PlugZap size={20} /></div>
        <div className="approvalCopy">
          <div className="eyebrow">ПОТРІБНА ДІЯ</div>
          <strong>Botpress не підключив акаунт</strong>
          <p>Ядро ALTER продовжує будуватися. Botpress буде доданий як окремий спеціаліст після авторизації.</p>
        </div>
        <button className="chevronButton" type="button" aria-label="Відкрити деталі">
          <ChevronRight size={20} />
        </button>
      </section>

      <section className="activityCard">
        <div className="sectionTitleRow compact">
          <div>
            <div className="eyebrow">ОСТАННІ ПОДІЇ</div>
            <h3>Журнал</h3>
          </div>
          <FileArchive size={18} />
        </div>
        <div className="activityList">
          {activity.map((item, index) => (
            <div className="activityItem" key={item}>
              <span className="timelineDot" />
              <div>
                <strong>{item}</strong>
                <small>{index === 0 ? "щойно" : `${index + 1} кроки тому`}</small>
              </div>
            </div>
          ))}
          {submitted.map((item) => (
            <div className="activityItem" key={item}>
              <span className="timelineDot accent" />
              <div>
                <strong>Нова команда: {item}</strong>
                <small>режим: {mode}</small>
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="composerSpacer" />

      <form className="composer" onSubmit={submit}>
        <div className="composerTools">
          <button type="button" aria-label="Додати вкладення"><Paperclip size={19} /></button>
          <button type="button" aria-label="Диктувати"><Mic size={19} /></button>
          <select value={mode} onChange={(event) => setMode(event.target.value)} aria-label="Режим задачі">
            <option>Швидко</option>
            <option>Звичайно</option>
            <option>Глибоко</option>
            <option>Лише план</option>
            <option>Чернетка</option>
          </select>
        </div>
        <div className="composerRow">
          <MessageSquareText size={19} />
          <input
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Що робимо?"
            aria-label="Команда для ALTER"
          />
          <button className="sendButton" type="submit" aria-label="Надіслати">
            <Send size={18} />
          </button>
        </div>
      </form>
    </main>
  );
}
