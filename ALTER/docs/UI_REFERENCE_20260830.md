# ALTER UI reference — 2026-08-30

Owner approved a mobile-first visual direction based on provided reference screens.

## Visual contract

- Dark obsidian / graphite base.
- Soft warm blurred environmental glow behind the app surface.
- Glass panels with thin graphite borders and restrained blue-violet neon focus states.
- High contrast white typography, muted secondary text, minimal gradients.
- Header: ALTER wordmark left, A mark centered, notification control right.
- Home cockpit: live task hero, progress, current surface, next step, pause/live-view/take-control controls, emergency stop, module grid, recent activity, sticky command composer.
- Other surfaces use the same card system: Tasks, Browser, Android, Rules, Vault, Models, Connectors, Memory, People, Files.
- Never present a disconnected runtime as active. UI status must come from live Core capability data.

## Functional contract

The design is not a static mockup. Interactive controls must call existing ALTER Core APIs where available. Unsupported Browser/Android/local-model actions remain visibly unavailable until their executors are actually connected.
