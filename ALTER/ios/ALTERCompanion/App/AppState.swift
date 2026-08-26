import Foundation
import Observation

@Observable
final class AppState {
    enum AgentStatus: String {
        case idle = "Вільний"
        case planning = "Планує"
        case executing = "Виконує"
        case waiting = "Чекає на вас"
        case blocked = "Заблоковано"
        case recovering = "Відновлення"
        case done = "Готово"
    }

    struct ActiveTask: Identifiable, Equatable {
        let id: UUID
        var title: String
        var progress: Double
        var completedSteps: Int
        var nextStep: String

        init(
            id: UUID = UUID(),
            title: String,
            progress: Double,
            completedSteps: Int,
            nextStep: String
        ) {
            self.id = id
            self.title = title
            self.progress = progress
            self.completedSteps = completedSteps
            self.nextStep = nextStep
        }
    }

    var status: AgentStatus = .executing
    var activeTask = ActiveTask(
        title: "Будую основу ALTER",
        progress: 0.36,
        completedSteps: 3,
        nextStep: "Cockpit + iOS companion"
    )
    var pendingApprovals = 1
    var composerText = ""
    var taskMode = "Звичайно"

    func submitComposer() {
        let trimmed = composerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        composerText = ""
        status = .planning
    }
}
