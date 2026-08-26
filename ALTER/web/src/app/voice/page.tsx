"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import ModuleShell, { field, muted, panel, primary, warn } from "@/components/ModuleShell";
import { core } from "@/lib/core-client";

type AgentStatus = { configured: boolean; provider: string };
type Reply = { agent: { text: string } };
type Message = { role: "user" | "agent"; text: string };

type SpeechRecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start(): void;
  stop(): void;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};

export default function VoicePage() {
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [listening, setListening] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);

  useEffect(() => { core<AgentStatus>("/agent/status").then(setStatus).catch(() => setStatus(null)); }, []);

  function recognizer(): SpeechRecognitionLike | null {
    if (typeof window === "undefined") return null;
    const w = window as typeof window & { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike };
    const Constructor = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!Constructor) return null;
    if (!recognitionRef.current) {
      const instance = new Constructor();
      instance.lang = "uk-UA";
      instance.interimResults = true;
      instance.continuous = false;
      instance.onresult = (event) => {
        let transcript = "";
        for (let i = 0; i < event.results.length; i += 1) transcript += event.results[i][0].transcript;
        setText(transcript.trim());
      };
      instance.onend = () => setListening(false);
      instance.onerror = () => { setListening(false); setError("Браузер не зміг розпізнати голос. Можна надрукувати текст вручну."); };
      recognitionRef.current = instance;
    }
    return recognitionRef.current;
  }

  function toggleListening() {
    setError("");
    const instance = recognizer();
    if (!instance) { setError("На цьому браузері Speech Recognition недоступний. Текстовий режим лишається доступним."); return; }
    if (listening) { instance.stop(); setListening(false); return; }
    setListening(true); instance.start();
  }

  function speak(textToSpeak: string) {
    if (!speakReplies || typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(textToSpeak);
    utterance.lang = "uk-UA";
    utterance.rate = 1;
    window.speechSynthesis.speak(utterance);
  }

  async function submit(event: FormEvent) {
    event.preventDefault(); const value = text.trim(); if (!value || busy || !status?.configured) return;
    setBusy(true); setText(""); setMessages((items) => [...items, { role: "user", text: value }]);
    try {
      const reply = await core<Reply>("/conversation/respond", { method: "POST", body: JSON.stringify({ text: value, mode: "normal" }) });
      setMessages((items) => [...items, { role: "agent", text: reply.agent.text }]); speak(reply.agent.text); setError("");
    } catch (err) { setError(err instanceof Error ? err.message : "ALTER не зміг відповісти"); setText(value); }
    finally { setBusy(false); }
  }

  return (
    <ModuleShell title="Говорити" eyebrow="VOICE · STT · TTS">
      <section style={{ ...panel, display: "grid", gap: 7 }}><strong>{status?.configured ? "ALTER готовий до голосової розмови" : "AI runtime ще очікує credential"}</strong><div style={muted}>Розпізнавання та озвучення використовують можливості браузера. Whisper/Kokoro залишаються локальними кандидатами після підключення локального runtime.</div>{!status?.configured && <div style={warn}>Мікрофон може створити чернетку, але AI-відповідь не симулюється, доки specialist не online.</div>}</section>
      <section style={{ display: "grid", gap: 9, marginTop: 12 }}>{messages.map((message, index) => <article key={index} style={{ ...panel, marginLeft: message.role === 'user' ? 40 : 0, marginRight: message.role === 'agent' ? 40 : 0 }}><div style={muted}>{message.role === 'user' ? 'Ти' : 'ALTER'}</div><div style={{ marginTop: 5, lineHeight: 1.5 }}>{message.text}</div></article>)}</section>
      {error && <section style={{ ...panel, color: "#ffaaa7", marginTop: 12 }}>{error}</section>}
      <form onSubmit={submit} style={{ ...panel, display: "grid", gap: 9, marginTop: 12 }}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="Скажи або напиши…" style={{ ...field, resize: "vertical" }} />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}><button type="button" onClick={toggleListening} style={primary}>{listening ? "Зупинити мікрофон" : "🎙️ Диктувати"}</button><button type="button" onClick={() => setSpeakReplies((value) => !value)} style={primary}>{speakReplies ? "🔊 Голос увімкнено" : "🔇 Голос вимкнено"}</button></div>
        <button disabled={busy || !text.trim() || !status?.configured} style={primary}>{busy ? "ALTER думає…" : "Надіслати"}</button>
      </form>
    </ModuleShell>
  );
}
