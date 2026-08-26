import AppIntents
import SwiftUI

@main
struct ALTERCompanionApp: App {
    @State private var appState = AppState()

    init() {
        if #available(iOS 26.0, *) {
            ALTERAppShortcuts.updateAppShortcutParameters()
        }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .preferredColorScheme(.dark)
        }
    }
}

private struct RootView: View {
    @State private var selectedTab: AppTab = .cockpit

    var body: some View {
        TabView(selection: $selectedTab) {
            NavigationStack {
                CockpitView()
            }
            .tag(AppTab.cockpit)
            .tabItem {
                Label("ALTER", systemImage: "sparkles")
            }

            NavigationStack {
                PlaceholderFeatureView(
                    title: "Tasks",
                    subtitle: "Черга, checkpoints, approvals і результати"
                )
            }
            .tag(AppTab.tasks)
            .tabItem {
                Label("Tasks", systemImage: "clock")
            }

            NavigationStack {
                PlaceholderFeatureView(
                    title: "Browser",
                    subtitle: "Live-view віддаленого Browser-профілю"
                )
            }
            .tag(AppTab.browser)
            .tabItem {
                Label("Browser", systemImage: "globe")
            }

            NavigationStack {
                PlaceholderFeatureView(
                    title: "Connectors",
                    subtitle: "OAuth, API та підключені пристрої"
                )
            }
            .tag(AppTab.connectors)
            .tabItem {
                Label("Connectors", systemImage: "cable.connector")
            }

            NavigationStack {
                PlaceholderFeatureView(
                    title: "Settings",
                    subtitle: "Rules, Vault, Memory, Models і People"
                )
            }
            .tag(AppTab.settings)
            .tabItem {
                Label("Settings", systemImage: "gearshape")
            }
        }
    }
}

private enum AppTab: Hashable {
    case cockpit
    case tasks
    case browser
    case connectors
    case settings
}

private struct PlaceholderFeatureView: View {
    let title: String
    let subtitle: String

    var body: some View {
        ContentUnavailableView(
            title,
            systemImage: "hammer",
            description: Text(subtitle)
        )
        .navigationTitle(title)
    }
}
