"use client";

import {
  Activity,
  AlertTriangle,
  AppWindow,
  Archive,
  Bell,
  Bot,
  Brain,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleDollarSign,
  CirclePause,
  Cloud,
  Code2,
  Database,
  Eye,
  File,
  Files,
  Filter,
  Folder,
  Globe2,
  HardDrive,
  History,
  Home,
  KeyRound,
  Layers3,
  Link2,
  ListChecks,
  Lock,
  MemoryStick,
  MessageCircle,
  Mic,
  Monitor,
  MoreVertical,
  Pause,
  Play,
  Plug,
  Plus,
  Search,
  Send,
  Settings,
  Shield,
  ShieldCheck,
  Smartphone,
  Sparkles,
  SquareTerminal,
  Store,
  Trash2,
  UserPlus,
  Users,
  WandSparkles,
  Wifi
} from "lucide-react";
import { type ComponentType, type FormEvent, useMemo, useState } from "react";

type Screen =
  | "home"
  | "tasks"
  | "browser"
  | "connectors"
  | "models"
  | "vault"
  | "rules"
  | "people"
  | "android"
  | "files";

type NavItem = { id: Screen; label: string; icon: ComponentType<{ size?: number; strokeWidth?: number }> };

const modules: NavItem[] = [
  { id: "home", label: "ALTER", icon: Bot },
  { id: "files", label: "Файли", icon: Folder },
  { id: "browser", label: "Браузер", icon: Globe2 },
  { id: "models", label: "Моделі", icon: Brain },
  { id: "android", label: "Android", icon: Smartphone },
  { id: "rules", label: "Правила", icon: ShieldCheck },
  { id: "vault", label: "Сховище", icon: KeyRound },
  { id: "tasks", label: "Задачі", icon: ListChecks },
  { id: "connectors", label: "Конектори", icon: Plug },
  { id: "people", label: "Люди", icon: Users }
];

const bottomNav: NavItem[] = [
  { id: "home", label: "ALTER", icon: Home },
  { id: "tasks", label: "Задачі", icon: ListChecks },
  { id: "connectors", label: "Конектори", icon: Link2 },
  { id: "vault", label: "Сховище", icon: Lock },
  { id: "rules", label: "Правила", icon: Shield }
];

const taskColumns = [
  {
    title: "Заплановано",
    count: 3,
    tasks: [
      ["Публікація 30-секундного відео", "Сьогодні 20:00", "Високий"],
      ["Оновити опис і хештеги для відео", "Завтра 10:00", "Середній"],
      ["Тест моделі VideoGen v2", "12 хв тому", "Низький"]
    ]
  },
  {
    title: "Виконується",
    count: 2,
    tasks: [
      ["Оцінка погодження опису і хештегів", "2 хв тому", "Високий"],
      ["Задача «Збір референсів» виконана", "28 хв тому", "Середній"]
    ]
  },
  {
    title: "Чекає на мене",
    count: 1,
    tasks: [["Погодити опис і хештеги", "Сьогодні 18:00", "Високий"]]
  }
];

const connectors = [
  ["Google Drive", "читання · файли", "GD"],
  ["Notion", "читання · чернетки", "N"],
  ["YouTube", "читання · публікація", "YT"],
  ["Binance", "читання · торгівля", "BN"]
];

const models = [
  ["VideoGen V2", "92", "1.8 c", "$0.012", "ДОВІРЕНА"],
  ["CodeCraft 4.1", "89", "2.3 c", "$0.008", "ДОВІРЕНА"],
  ["VisionPro 1.3", "76", "2.9 c", "$0.010", "НА ПЕРЕВІРЦІ"]
];

const secrets = [
  ["aws-prod-readonly", "Хмарний сервіс", "Read-only", "2 хв тому"],
  ["pg-analytics", "База даних", "Read-write", "7 хв тому"],
  ["github-actions-bot", "Інтеграція", "Write", "12 хв тому"]
];

const rules = [
  ["Не відкривай TikTok", true, "Робочий час"],
  ["Не публікуй без чернетки", true, "Завжди"],
  ["Не витрачай більше $10 на одну задачу", true, "Завжди"],
  ["Не читай робочу пошту", false, "Завжди"]
] as const;

function Logo() {
  return <div className="alterLogo" aria-label="ALTER">A</div>;
}

function Header({ title, back, onBack }: { title?: string; back?: boolean; onBack?: () => void }) {
  return (
    <header className="appHeader">
      <div className="brandWord">ALTER</div>
      {title ? (
        <div className="screenTitleCompact">
          {back && <button className="iconButton ghost" onClick={onBack}><ChevronLeft size={20} /></button>}
          <span>{title}</span>
        </div>
      ) : <Logo />}
      <button className="iconButton notification" aria-label="Сповіщення"><Bell size={19} /><i /></button>
    </header>
  );
}

function StatusChip({ children, tone = "green" }: { children: React.ReactNode; tone?: "green" | "violet" | "amber" | "red" }) {
  return <span className={`statusChip ${tone}`}><i />{children}</span>;
}

function BottomNav({ screen, setScreen }: { screen: Screen; setScreen: (screen: Screen) => void }) {
  return (
    <nav className="bottomNav" aria-label="Основна навігація">
      {bottomNav.map(({ id, label, icon: Icon }) => (
        <button key={id} className={screen === id ? "active" : ""} onClick={() => setScreen(id)}>
          <Icon size={20} strokeWidth={1.7} />
          <span>{label}</span>
          {id === "tasks" && <b>3</b>}
        </button>
      ))}
    </nav>
  );
}

function HomeScreen({ setScreen }: { setScreen: (screen: Screen) => void }) {
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<string[]>([]);
  function send(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setMessages((items) => [...items, text.trim()]);
    setText("");
  }

  return (
    <>
      <Header />
      <div className="statusRow"><StatusChip>Виконує</StatusChip><span className="microPill"><ListChecks size={13}/> 3 активні задачі</span></div>

      <section className="focusCard glowBorder">
        <div className="focusTop">
          <div>
            <div className="eyebrow">ПОТОЧНА ЗАДАЧА</div>
            <h1>Публікація 30-секундного відео</h1>
          </div>
          <button className="orbPlay"><Play size={23} fill="currentColor" /></button>
        </div>
        <div className="progressTrack"><span style={{ width: "67%" }} /></div>
        <div className="focusMeta"><b>6/9 кроків</b><span><Globe2 size={15}/> Поточна поверхня <strong>Браузер</strong></span><span>Далі <strong>Погодити опис</strong></span></div>
      </section>

      <div className="tabStrip">
        <button className="active"><MessageCircle size={17}/> Чат</button>
        <button><Layers3 size={17}/> Артефакти</button>
        <button onClick={() => setScreen("files")}><Folder size={17}/> Файли</button>
        <button><History size={17}/> Хронологія</button>
      </div>

      <section className="chatPanel glassPanel">
        <div className="chatMessage agent">
          <Logo />
          <div><small>ALTER · 19:42</small><p>Починаю виконання задачі: створити та опублікувати 30-секундне відео.</p><ol><li>Аналіз цілі та аудиторії</li><li>Генерація сценарію</li><li>Створення відео</li><li>Підбір опису та хештегів</li><li>Погодження</li><li>Публікація та звіт</li></ol></div>
        </div>
        <div className="chatMessage user"><div className="userAvatar">В</div><div><small>Ви · 19:43</small><p>Ок, роби. Тема — понеділкове натхнення для продуктивності.</p></div></div>
        <div className="chatMessage agent">
          <Logo />
          <div className="wideMessage"><small>ALTER · 19:47</small><p>Чернетка готова. Переглянь і дай знати, що змінити.</p>
            <div className="draftCard">
              <div className="draftThumb"><div className="mountain"/><Play size={24} /></div>
              <div className="draftCopy"><strong>Чернетка відео v1</strong><span>30 сек · 16:9 · 1080p</span><p>Понеділок — новий старт. Маленькі кроки сьогодні = великі результати завтра.</p><div className="tags">#понеділок #продуктивність #фокус</div></div>
              <div className="draftActions"><button className="outlineAccent"><CheckCircle2 size={16}/> Схвалити</button><button className="outlineDanger">Відхилити</button><button>Ще варіант</button></div>
            </div>
          </div>
        </div>
        {messages.map((m) => <div className="chatMessage user" key={m}><div className="userAvatar">В</div><div><small>Ви · щойно</small><p>{m}</p></div></div>)}
        <div className="executionSummary"><div><span>Готово</span><b>4/6</b></div><div><span>Частково</span><b>1/6</b></div><div><span>Заблоковано</span><b>1/6</b></div></div>
      </section>

      <form className="commandComposer" onSubmit={send}>
        <button type="button" className="plusButton"><Plus size={22}/></button>
        <input value={text} onChange={(e)=>setText(e.target.value)} placeholder="Напишіть ALTER..." />
        <button type="button" className="voiceButton"><Mic size={20}/></button>
        <button className="sendButton"><Send size={18}/></button>
        <div className="composerModes"><button type="button"><Activity size={16}/> Говорити</button><button type="button"><Monitor size={16}/> Екран</button><button type="button">Режим: AUTO</button></div>
      </form>
    </>
  );
}

function BrowserScreen({ setScreen }: { setScreen: (screen: Screen) => void }) {
  const [control, setControl] = useState<"me"|"agent"|"shared">("shared");
  return (
    <>
      <Header title="Browser" back onBack={()=>setScreen("home")} />
      <div className="controlSegment">
        <button className={control==="me"?"active":""} onClick={()=>setControl("me")}>Я керую</button>
        <button className={control==="agent"?"active":""} onClick={()=>setControl("agent")}>Агент керує</button>
        <button className={control==="shared"?"active":""} onClick={()=>setControl("shared")}>Разом / Спільна сесія</button>
      </div>
      <div className="sessionStatus"><StatusChip>Спільна сесія активна</StatusChip><StatusChip tone="violet">ALTER Agent підключений</StatusChip></div>

      <section className="browserFrame glowBorder">
        <div className="browserTabs"><span>● Figma – Dashboard <b>×</b></span><span>◉ Analytics · ALTER <b>×</b></span><button>+</button></div>
        <div className="browserToolbar"><ChevronLeft size={17}/><ChevronRight size={17}/><Activity size={17}/><div className="address"><Lock size={14}/> https://app.figma.com/dashboard</div><MoreVertical size={17}/></div>
        <div className="fakeWeb">
          <aside><b>Figma</b><div className="fakeSearch">⌕ Пошук</div><span>◷ Останні</span><span>□ Чернетки</span><span>♙ Спільні з вами</span><span>⊞ Бібліотека команд</span><small>КОМАНДИ</small><span>◈ ALTER Labs ＋</span></aside>
          <main><h3>Дашборд</h3><small>Останні файли</small><div className="fileCards"><div><div className="filePreview dark"/><b>ALTER Design System</b><small>Змінено 2 год тому</small></div><div><div className="filePreview purple"/><b>Marketing Website</b><small>Змінено вчора</small></div><div className="selected"><div className="filePreview blue"/><b>Mobile App UI Kit</b><small>Змінено 3 дні тому</small></div></div></main>
          <aside className="agentRail"><h4>Поточне завдання</h4><p>Оновлення дизайн-системи</p><div className="miniProgress"><span/></div><h4>Останні дії агента</h4><ul><li>Відкрив файл ALTER Design System</li><li>Оновив компонент Button / Primary</li><li>Додав варіант Button / Primary / Icon</li></ul><h4>Авторизація</h4><StatusChip>Сесія авторизована</StatusChip></aside>
        </div>
      </section>
      <div className="browserActions"><button><Pause size={17}/> Пауза</button><button><Eye size={17}/> Live-перегляд</button><button className="primaryAction"><Play size={17}/> Продовжити завдання</button></div>
      <button className="wideAction"><Activity size={17}/> Передати керування агенту</button>
    </>
  );
}

function TasksScreen() {
  return (
    <>
      <Header />
      <div className="largeTabs"><button className="active">Задачі</button><button>Пам’ять</button></div>
      <div className="searchRow"><div className="searchBox"><Search size={18}/> Пошук задач, проектів, людей...</div><button className="filterButton"><Filter size={18}/> Фільтри</button><button className="roundPrimary"><Plus size={22}/></button></div>
      <section className="kanban">
        {taskColumns.map((column)=><div className="kanbanCol" key={column.title}><div className="kanbanHead"><b>{column.title}</b><span>{column.count}</span><MoreVertical size={16}/></div>{column.tasks.map((task)=><div className="taskCard" key={task[0]}><strong>{task[0]}</strong><small>▣ {task[1]}</small><div><Globe2 size={14}/><span className={`risk ${task[2]==="Високий"?"high":task[2]==="Середній"?"medium":"low"}`}>{task[2]}</span></div></div>)}</div>)}
        <div className="kanbanCol blocked"><div className="kanbanHead"><b>Заблоковано</b><span>1</span></div><div className="taskCard"><strong>Інтеграція з CMS</strong><small>Чекає на відповідь</small><div><Link2 size={14}/><span className="risk low">Низький</span></div></div></div>
        <div className="kanbanCol done"><div className="kanbanHead"><b>Готово</b><span>3</span></div><ul className="doneList"><li>Бекап сховища завершено</li><li>Публікація 30-сек. відео</li><li>Аналіз конкурентів (Q2)</li></ul></div>
      </section>
      <section className="memoryPanel glassPanel"><div className="sectionHead"><div><h2>Пам’ять</h2><p>Профіль · Світ / Проекти · Епізоди</p></div><Brain size={22}/></div><div className="profileCard"><div className="userAvatar big">В</div><div><b>Користувач: Ви</b><StatusChip>Активний</StatusChip><p>Контент-креатор і продюсер. Фокус на коротких відео, автоматизаціях та якості.</p><div className="tags"><span>Мова: Українська</span><span>Формат: 9:16</span><span>Стиль: Динамічний</span></div></div></div><div className="recurring"><Activity size={20}/><div><b>Щоденний звіт по контенту</b><small>Наступний запуск: сьогодні 21:00</small></div><button>Пауза</button></div></section>
    </>
  );
}

function ConnectorsScreen() {
  return (
    <>
      <Header title="Конектори" />
      <div className="largeTabs four"><button className="active">Через сервіс</button><button>API-ключ</button><button>Пристрій</button><button>Маркет</button></div>
      <p className="helper">Підключайте сервіси з мінімально необхідними правами. <StatusChip>Безпечно за замовчуванням</StatusChip></p>
      <h2 className="sectionHeading">Підключені сервіси</h2>
      <div className="connectorGrid">{connectors.map(([name,rights,badge])=><div className="connectorCard" key={name}><div className="connectorIcon">{badge}</div><MoreVertical size={17}/><h3>{name}</h3><StatusChip>Підключено</StatusChip><small>Права</small><p>{rights}</p></div>)}</div>
      <section className="oauthBanner glowBorder"><div className="oauthIcon"><ShieldCheck size={25}/></div><div><h3>Підключення сервісу через OAuth 2.0</h3><p>Надавайте тільки потрібні права — без паролів і зайвого доступу.</p></div><button className="primaryAction">Підключити сервіс</button></section>
      <section className="accessPanel glassPanel"><div className="sectionHead"><div><small>Остання перевірка доступу · 2 хв тому</small><h3>Доступ надано безпечно</h3></div><button>Тестувати знову</button></div><div className="permissionGrid"><span>✓ Читання</span><span>✓ Чернетки</span><span>✓ Публікація</span><span>✓ Файли</span></div></section>
      <h2 className="sectionHeading">Маркет конекторів</h2>
      <div className="marketList">{[["Airtable Connector","Популярний"],["GitHub Integration","Офіційний"],["Slack Notifier","Рекомендований"]].map(([n,t])=><div key={n}><div className="marketIcon"><Plug size={21}/></div><div><b>{n}</b><span>{t}</span><small>Права: читання, запис · Ризик: низький</small></div><button>Встановити</button></div>)}</div>
    </>
  );
}

function ModelsScreen() {
  return (
    <>
      <Header title="Моделі" />
      <div className="modelTabs"><button className="active">Доступні</button><button>Довірені</button><button>На перевірці <b>2</b></button><button>Локальні</button><button>API</button><button>Архів</button></div>
      <div className="searchRow"><div className="searchBox"><Search size={18}/> Пошук моделей...</div><button className="filterButton"><Filter size={18}/> Фільтри</button></div>
      <div className="modelList">{models.map(([name,quality,speed,cost,status],idx)=><article className="modelCard" key={name}><div className="modelTop"><div className={`modelGlyph g${idx}`}><Brain size={25}/></div><div><h2>{name}</h2><span className={status.includes("ПЕРЕВ")?"badge amber":"badge"}>{status}</span><small>Останній тест: {idx===0?"12 хв тому":idx===1?"1 год тому":"28 хв тому"}</small></div><StatusChip tone={idx===2?"amber":"green"}>{idx===2?"Тестується":"Онлайн"}</StatusChip><MoreVertical size={18}/></div><div className="capabilities"><span>Текст</span><span>Код</span>{idx!==1&&<span>Зображення</span>}<span>Tools</span></div><div className="modelStats"><div><small>Якість</small><b>{quality}/100</b><i style={{width:`${quality}%`}}/></div><div><small>Швидкість</small><b>{speed}</b></div><div><small>Вартість</small><b>{cost}</b><small>/1K токенів</small></div><div><small>Ліцензія</small><b>Комерційна</b></div></div></article>)}</div>
      <section className="comparison glassPanel"><small>Порівняння: поточна модель vs нова кандидатка</small><div><section><StatusChip>Поточна модель</StatusChip><h3>VideoGen V2</h3><b>92/100 · 1.8 c · $0.012</b></section><span className="vs">VS</span><section><StatusChip tone="amber">Нова кандидатка</StatusChip><h3>VideoGen V2.1</h3><b>94/100 · 2.1 c · $0.009</b></section></div><div className="comparisonActions"><button>Залишити поточну</button><button className="primaryAction">Перейти на нову</button><button>Порівняти ще</button></div></section>
    </>
  );
}

function VaultScreen() {
  return (
    <>
      <Header />
      <div className="titleWithActions"><div><h1>Сховище</h1><p>Керування секретними з’єднаннями та доступом через псевдоніми. Сирі значення приховані.</p></div><button className="roundPrimary"><Plus size={21}/></button><button className="filterButton"><Filter size={18}/> Фільтри</button></div>
      <div className="securityNotice"><Shield size={18}/> Показуються лише псевдоніми. Сирі секрети завжди приховані.</div>
      <div className="secretList">{secrets.map(([name,type,level,time],idx)=><article className="secretCard" key={name}><div className="secretIcon">{idx===0?"aws":idx===1?"pg":"gh"}</div><div className="secretMain"><div className="secretTitle"><h2>{name}</h2><span>{type}</span><MoreVertical size={17}/></div><div className="secretGrid"><span>Псевдонім <b>{name}</b></span><span>Рівень доступу <b>{level}</b></span><span>Статус <StatusChip>Активний</StatusChip></span><span>Остання перевірка <b>{time}</b></span></div><div className="secretActions"><button>Перевірити</button><button>Змінити права</button><button><Pause size={15}/> Призупинити</button><button className="danger">Відкликати</button></div></div></article>)}</div>
      <section className="usageLog glassPanel"><div className="sectionHead"><h2>Журнал використання</h2><button>Переглянути все</button></div>{[["Linux","aws-prod-readonly","Оновлення системи"],["Браузер","pg-analytics","Запит звіту"],["Конектори","github-actions-bot","Деплой релізу"]].map((x)=><div className="usageRow" key={x[0]}><span>{x[0]}</span><small>Використав {x[1]}</small><b>Завдання: {x[2]}</b><time>2 хв тому</time></div>)}</section>
    </>
  );
}

function RulesScreen() {
  const [state,setState]=useState(rules.map(r=>r[1]));
  return (
    <>
      <Header title="Правила" />
      <p className="lead">Встановлюйте особисті правила для ALTER. Він буде діяти згідно з ними кожного дня.</p>
      <div className="ruleComposer"><Plus size={22}/><input placeholder="Напишіть правило своїми словами"/><Mic size={19}/><button><Sparkles size={19}/></button></div>
      <div className="sectionHead"><h2>Мої правила <span className="countBubble">4</span></h2><small>Увімкнено: {state.filter(Boolean).length} з 4</small></div>
      <div className="rulesList">{rules.map(([name,,scope],idx)=><article className="ruleCard" key={name}><div className={`ruleSymbol r${idx}`}>{idx===0?"⊘":idx===1?"✎":idx===2?"$":"✉"}</div><div><h3>{name}</h3><div className="ruleMeta"><span>Статус <button className={`toggle ${state[idx]?"on":""}`} onClick={()=>setState(s=>s.map((v,i)=>i===idx?!v:v))}><i/></button></span><span>Сфера дії <b>{scope}</b></span><span>Винятки <b>{idx===1?"Клієнти":idx===2?"Термінові задачі":"Немає"}</b></span></div></div><button className="testButton">⚗ Тест</button></article>)}</div>
      <section className="immutable glowBorder"><div className="sectionHead"><div><h3>Системні межі безпеки <span>Незмінні</span></h3><p>Ці правила захищають Вас і дані. Їх не можна вимкнути.</p></div><Lock size={30}/></div><ul><li>Не розголошуй персональні дані</li><li>Не виконуй небезпечні команди</li><li>Поважай приватність інших</li></ul></section>
    </>
  );
}

function PeopleScreen() {
  return (
    <>
      <Header title="Люди" />
      <p className="lead">Керуйте доступом, ролями та ізольованими середовищами.</p>
      <div className="roleGrid">{[["Власник","Повний контроль над усіма даними, модулями та налаштуваннями.","Ви"],["Партнер","Довірений доступ до вибраних модулів та даних.","1 користувач"],["Гість","Обмежений доступ лише до наданих модулів та даних.","0 користувачів"]].map(([r,d,c],i)=><article key={r}><div className="roleIcon">{i===0?"♛":i===1?"🤝":"♙"}</div><h2>{r}</h2><p>{d}</p><span>{c}</span></article>)}</div>
      <section className="inviteBanner glassPanel"><div className="inviteIcon"><UserPlus size={26}/></div><div><h2>Додати людину</h2><p>Запросіть партнера через безпечне посилання.</p><a>Детальніше ›</a></div><button className="primaryAction">Створити запрошення</button></section>
      <section className="permissionsTable glassPanel"><h2>Права доступу</h2><p>Налаштуйте, що може бачити та змінювати кожна роль.</p><div className="permissionHeader"><span>Модуль</span><span>Власник</span><span>Партнер</span><span>Гість</span></div>{[["Браузер","Повний","Обмежений","Немає"],["Android","Повний","Обмежений","Немає"],["Файли","Повний","Обмежений","Немає"],["Пам’ять","Повний","Тільки читання","Немає"],["Задачі","Повний","Повний","Немає"],["Правила","Повний","Обмежений","Немає"]].map(r=><div className="permissionRow" key={r[0]}><b>{r[0]}</b><span>✓ {r[1]}</span><span>– {r[2]}</span><span>× {r[3]}</span></div>)}</section>
      <section className="environmentCard glassPanel"><h2>Ізольовані середовища</h2><p>Кожен користувач працює у власному просторі.</p><div className="personEnv"><div className="userAvatar">A</div><div><b>Андрій</b><small>Партнер · Запрошення прийнято</small></div><span>🌐 Браузер · Профілі: 3</span><span>📁 Файли: 128</span><span>🧠 Пам’ять: 42</span><ChevronRight size={18}/></div></section>
    </>
  );
}

function AndroidScreen() {
  const devices = [["Pixel 7 Pro","Виконує","Chrome","1.2 ГБ"],["Samsung S23","Очікує вас","Instagram","886 МБ"],["Xiaomi 13T","Показує, що пропонує","Telegram","1.6 ГБ"],["Pixel 6a","Очікує вас","YouTube","512 МБ"]];
  return (
    <>
      <Header title="Android" />
      <div className="androidTop"><button className="primaryAction"><Plus size={18}/> Додати пристрій</button><button className="filterButton"><ListChecks size={18}/></button></div>
      <section className="androidWorkspace"><div className="deviceList">{devices.map((d,i)=><button className={`deviceCard ${i===0?"active":""}`} key={d[0]}><div><h3>{d[0]}</h3><StatusChip tone={i===0?"green":"violet"}>{d[1]}</StatusChip><span>{d[2]}</span><small>{d[3]} вільно</small><div className="miniProgress"><span style={{width:`${70-i*12}%`}}/></div></div><Play size={20}/></button>)}<button className="createProfile"><Plus size={18}/> Створити профіль</button></div><div className="phonePanel glassPanel"><div className="phonePanelHead"><div><h2>Pixel 7 Pro</h2><StatusChip>Виконує</StatusChip></div><MoreVertical size={18}/></div><div className="androidPhone"><div className="phoneStatus">19:56 <Wifi size={14}/></div><div className="wallpaper"/><div className="appGrid">{["Chrome","Gmail","Maps","Drive","YouTube","Photos","Telegram","Play"].map(n=><div key={n}><span>{n[0]}</span><small>{n}</small></div>)}</div><div className="dock">● ● ● ●</div></div><button className="wideAction">↗ Відкрити</button><div className="phoneControls"><button>Клонувати профіль</button><button>Контрольна точка</button><button>Перезапустити</button><button>Запис екрана</button></div></div></section>
      <section className="agentState glassPanel"><h3>Стан агента</h3><div><StatusChip>Виконує</StatusChip><StatusChip tone="violet">Показує, що пропонує</StatusChip><span className="microPill">Ⅱ Очікує вас</span></div></section>
      <div className="warningBanner"><AlertTriangle size={22}/><p>Усі входи в акаунти, 2FA та CAPTCHA виконуються вручну власником перед продовженням. ALTER не має доступу до ваших облікових даних.</p></div>
    </>
  );
}

function FilesScreen() {
  return <><Header title="Файли"/><div className="searchRow"><div className="searchBox"><Search size={18}/> Пошук у файлах...</div><button className="roundPrimary"><Plus size={22}/></button></div><div className="fileLibrary">{[["ALTER Design System","FIG · 48 MB","2 год тому"],["Marketing Website","ZIP · 12 MB","вчора"],["Mobile App UI Kit","FIG · 64 MB","3 дні тому"],["Q2 Analytics","PDF · 8 MB","5 днів тому"]].map((f,i)=><article key={f[0]}><div className={`largeFilePreview p${i}`}><File size={30}/></div><h3>{f[0]}</h3><span>{f[1]}</span><small>{f[2]}</small></article>)}</div><section className="glassPanel storageCard"><div><HardDrive size={24}/><div><h3>Сховище ALTER</h3><p>Файли ізольовані за workspace та доступом.</p></div></div><div className="progressTrack"><span style={{width:"38%"}}/></div><small>19.4 GB із 50 GB</small></section></>;
}

export default function AlterApp() {
  const [screen, setScreen] = useState<Screen>("home");
  const content = useMemo(() => {
    switch (screen) {
      case "browser": return <BrowserScreen setScreen={setScreen}/>;
      case "tasks": return <TasksScreen/>;
      case "connectors": return <ConnectorsScreen/>;
      case "models": return <ModelsScreen/>;
      case "vault": return <VaultScreen/>;
      case "rules": return <RulesScreen/>;
      case "people": return <PeopleScreen/>;
      case "android": return <AndroidScreen/>;
      case "files": return <FilesScreen/>;
      default: return <HomeScreen setScreen={setScreen}/>;
    }
  }, [screen]);

  return (
    <main className="appShell">
      <div className="ambient one"/><div className="ambient two"/>
      <div className="appSurface">
        {screen === "home" && <div className="quickModules">{modules.slice(1,6).map(({id,label,icon:Icon})=><button key={id} onClick={()=>setScreen(id)}><Icon size={16}/><span>{label}</span></button>)}</div>}
        {content}
      </div>
      <BottomNav screen={screen} setScreen={setScreen}/>
    </main>
  );
}
