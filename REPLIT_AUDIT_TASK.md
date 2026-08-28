# ALTER — Replit audit/fix task

Працюй ТІЛЬКИ в гілці `replit-audit-fixes`. Не змінюй `main` і не деплой production.

Мета: провести незалежний аудит і виправити зовнішній Web UX ALTER, не ламаючи Core, security boundaries, Vault, RBAC, Botpress, scheduler, RAG, memory чи production API.

## Вихідний live сайт
https://alter-live.vercel.app

## Що вже відомо з зовнішнього аудиту
1. Порожній submit на auth gate не дає зрозумілого feedback. Або disabled CTA до введення значення, або локальна validation-помилка + focus.
2. Поле доступу має мати коректний accessible name: зв’язаний label/input та/або aria-label.
3. Уточнити рольову термінологію: Owner / запрошений учасник; Operator і Viewer — ролі учасника, не окрема роль Member.
4. Зробити локалізацію послідовнішою; технічні терміни Core/RBAC/runtime можна залишати лише там, де це свідомо потрібно.
5. Перевірити mobile widths, padding, overflow і touch targets на вузьких viewport.
6. Додати/перевірити Content-Security-Policy без поломки Next.js/Vercel і необхідних API/telemetry requests.
7. Виправити favicon.ico, robots.txt, sitemap.xml так, щоб це були реальні службові ресурси, а не app shell/404.
8. Нормалізувати auth validation UX; не послаблювати security і не розкривати різницю, яка допоможе перебору credentials.
9. Перевірити loading/error/empty states auth gate і logout/session-expiry handling, якщо це доступно без зміни security model.
10. Покращити branding/production feel, але не робити редизайн заради редизайну і не ламати поточну dark/glass мову ALTER.

## Обов’язкові обмеження
- Не виводити й не логувати секрети.
- Не змінювати Vault encryption, bearer auth, RBAC, approval/policy boundaries без доказаної необхідності.
- Не додавати Browser executor, Android, PC control, Telegram, Gmail або TikTok.
- Не переводити protected screens у public.
- Не підміняти реальні функції mock/stub-ами.
- Не заявляти, що щось працює, без тесту.

## Перед завершенням
- Запусти всі наявні Web/Core/Botpress checks, які зачіпають зміни.
- Перевір production build Web.
- Дай короткий звіт: що змінено, що свідомо не змінено, які тести пройшли, які ризики залишились.
- Не merge в main і не деплой production. Після завершення зміни перегляне власник/ChatGPT і лише тоді буде merge/deploy.
