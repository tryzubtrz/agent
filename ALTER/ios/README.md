# ALTER iOS Companion

Native SwiftUI companion foundation for the ALTER control plane.

## Scope

The iOS app is a secure owner cockpit, not a hidden device-control agent. It can provide:

- authenticated ALTER chat and task status;
- approvals and push notifications;
- files and media upload through user-granted pickers;
- deep links / App Intents / Shortcuts for supported actions;
- Browser/Android live-view surfaces hosted by the ALTER cloud control plane;
- connector and policy management.

It must not claim unrestricted control of iOS, silently bypass authentication, or access data outside Apple-granted permissions.

## UI architecture

- iOS 17+ baseline.
- SwiftUI `TabView` + per-feature `NavigationStack`.
- `@Observable` root state owned by the app shell.
- environment injection for shared API/session services.
- explicit loading/error/waiting-for-owner states.
- small feature views rather than a single giant screen.

This folder currently contains the app shell and cockpit screen. An Xcode project/workspace should be generated or created when the code is opened in the iOS development environment.
