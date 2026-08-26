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
        var totalSteps: Int
        var nextStep: String
        var surface: String

        init(
            id: UUID = UUID(),
            title: String,
            progress: Double,
            completedSteps: Int,
            totalSteps: Int,
            nextStep: String,
            surface: String
        ) {
            self.id = id
            self.title = title
            self.progress = progress
            self.completedSteps = completedSteps
            self.totalSteps = totalSteps
            self.nextStep = nextStep
            self.surface = surface
        }
    }

    var status: AgentStatus = .executing
    var activeTask = ActiveTask(
        title: "Публікація 30-секундного відео",
        progress: 0.67,
        completedSteps: 6,
        totalSteps: 9,
        nextStep: "Погодити опис і хештеги",
        surface: "Браузер"
    )
    var pendingApprovals = 1
    var composerText = ""
    var taskMode = "AUTO"

    func submitComposer() {
        let trimmed = composerText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        composerText = ""
        status = .planning
    }
}
