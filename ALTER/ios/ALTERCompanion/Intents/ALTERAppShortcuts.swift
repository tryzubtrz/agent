import AppIntents

@available(iOS 26.0, *)
struct OpenALTERIntent: AppIntent {
    static var title: LocalizedStringResource = "Відкрити ALTER"
    static var description = IntentDescription("Відкриває головний cockpit ALTER.")
    static let supportedModes: IntentModes = [.foreground(.immediate)]

    @MainActor
    func perform() async throws -> some IntentResult {
        .result()
    }
}

@available(iOS 26.0, *)
struct ALTERAppShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: OpenALTERIntent(),
            phrases: [
                "Відкрий \(.applicationName)",
                "Покажи \(.applicationName)"
            ],
            shortTitle: "Відкрити ALTER",
            systemImageName: "sparkles"
        )
    }
}
