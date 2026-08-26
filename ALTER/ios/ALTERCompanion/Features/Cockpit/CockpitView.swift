import SwiftUI

struct CockpitView: View {
    @Environment(AppState.self) private var appState

    private let modules: [CockpitModule] = [
        .init(title: "Файли", symbol: "folder", tint: .indigo),
        .init(title: "Браузер", symbol: "globe", tint: .blue),
        .init(title: "Моделі", symbol: "brain", tint: .purple),
        .init(title: "Android", symbol: "iphone", tint: .indigo),
        .init(title: "Правила", symbol: "shield", tint: .green),
        .init(title: "Сховище", symbol: "lock", tint: .orange),
        .init(title: "Задачі", symbol: "checklist", tint: .indigo),
        .init(title: "Конектори", symbol: "link", tint: .cyan),
        .init(title: "Люди", symbol: "person.2", tint: .purple)
    ]

    var body: some View {
        @Bindable var state = appState

        ZStack {
            background

            ScrollView {
                VStack(spacing: 14) {
                    header
                    compactModules
                    activeTask
                    contentTabs
                    conversation
                    executionSummary
                }
                .padding(.horizontal, 14)
                .padding(.top, 6)
                .padding(.bottom, 150)
            }
            .scrollIndicators(.hidden)
        }
        .safeAreaInset(edge: .bottom) {
            composer(state: $state)
        }
        .toolbar(.hidden, for: .navigationBar)
        .preferredColorScheme(.dark)
    }

    private var header: some View {
        HStack {
            Text("ALTER")
                .font(.system(size: 28, weight: .light, design: .rounded))
                .tracking(6)

            Spacer()

            ZStack {
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .stroke(.white.opacity(0.22), lineWidth: 1)
                    .background(
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(.white.opacity(0.025))
                    )
                Text("A")
                    .font(.system(size: 23, weight: .light, design: .rounded))
                    .rotationEffect(.degrees(-5))
            }
            .frame(width: 42, height: 42)

            Spacer()

            ZStack(alignment: .topTrailing) {
                Image(systemName: "bell")
                    .font(.system(size: 17, weight: .medium))
                    .frame(width: 42, height: 42)
                    .background(.black.opacity(0.25), in: Circle())
                    .overlay(Circle().stroke(.white.opacity(0.10)))

                Circle()
                    .fill(Color.indigo)
                    .frame(width: 6, height: 6)
                    .shadow(color: .indigo.opacity(0.8), radius: 5)
                    .offset(x: -5, y: 5)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var compactModules: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 7) {
                ForEach(modules.prefix(5)) { module in
                    Label(module.title, systemImage: module.symbol)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 7)
                        .background(.white.opacity(0.025), in: Capsule())
                        .overlay(Capsule().stroke(.white.opacity(0.07)))
                }
            }
        }
    }

    private var activeTask: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("ПОТОЧНА ЗАДАЧА")
                        .font(.caption2.weight(.bold))
                        .tracking(1.3)
                        .foregroundStyle(.secondary)

                    Text(appState.activeTask.title)
                        .font(.system(size: 24, weight: .semibold, design: .rounded))
                        .fixedSize(horizontal: false, vertical: true)
                }

                Spacer(minLength: 4)

                Button {
                    appState.status = .executing
                } label: {
                    Image(systemName: "play.fill")
                        .font(.system(size: 20, weight: .bold))
                        .foregroundStyle(Color.indigo)
                        .frame(width: 58, height: 58)
                        .background(
                            RadialGradient(
                                colors: [.indigo.opacity(0.24), .black.opacity(0.12)],
                                center: .topLeading,
                                startRadius: 5,
                                endRadius: 58
                            ),
                            in: RoundedRectangle(cornerRadius: 19, style: .continuous)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 19, style: .continuous)
                                .stroke(.indigo.opacity(0.35))
                        )
                        .shadow(color: .indigo.opacity(0.18), radius: 18)
                }
                .buttonStyle(.plain)
            }

            ProgressView(value: appState.activeTask.progress)
                .tint(.indigo)
                .scaleEffect(x: 1, y: 1.25, anchor: .center)

            HStack(spacing: 14) {
                Text("\(appState.activeTask.completedSteps)/\(appState.activeTask.totalSteps) кроків")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.indigo)

                Spacer()

                Label(appState.activeTask.surface, systemImage: "globe")
                    .font(.caption)
                    .foregroundStyle(.secondary)

                VStack(alignment: .leading, spacing: 1) {
                    Text("Далі")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(appState.activeTask.nextStep)
                        .font(.caption.weight(.semibold))
                        .lineLimit(1)
                }
            }
        }
        .padding(16)
        .alterCard(glow: true)
    }

    private var contentTabs: some View {
        HStack(spacing: 4) {
            TabLabel(title: "Чат", symbol: "bubble.left", selected: true)
            TabLabel(title: "Артефакти", symbol: "cube", selected: false)
            TabLabel(title: "Файли", symbol: "folder", selected: false)
            TabLabel(title: "Хронологія", symbol: "clock", selected: false)
        }
        .padding(5)
        .background(.black.opacity(0.30), in: RoundedRectangle(cornerRadius: 15))
        .overlay(RoundedRectangle(cornerRadius: 15).stroke(.white.opacity(0.07)))
    }

    private var conversation: some View {
        VStack(spacing: 0) {
            ChatRow(
                isAgent: true,
                title: "ALTER · 19:42",
                message: "Починаю виконання задачі: створити та опублікувати 30-секундне відео.",
                details: "1. Аналіз цілі та аудиторії\n2. Генерація сценарію\n3. Створення відео\n4. Підбір опису та хештегів\n5. Погодження\n6. Публікація та звіт"
            )

            Divider().overlay(.white.opacity(0.05))

            ChatRow(
                isAgent: false,
                title: "Ви · 19:43",
                message: "Ок, роби. Тема — понеділкове натхнення для продуктивності.",
                details: nil
            )

            Divider().overlay(.white.opacity(0.05))

            VStack(alignment: .leading, spacing: 10) {
                ChatRow(
                    isAgent: true,
                    title: "ALTER · 19:47",
                    message: "Чернетка готова. Переглянь і дай знати, що змінити.",
                    details: nil
                )

                DraftCard()
                    .padding(.leading, 42)
            }
            .padding(.bottom, 12)
        }
        .padding(.horizontal, 12)
        .alterCard()
    }

    private var executionSummary: some View {
        HStack(spacing: 8) {
            SummaryTile(title: "Готово", value: "4/6", tint: .green)
            SummaryTile(title: "Частково", value: "1/6", tint: .orange)
            SummaryTile(title: "Заблоковано", value: "1/6", tint: .red)
        }
    }

    private func composer(state: Bindable<AppState>) -> some View {
        VStack(spacing: 8) {
            HStack(spacing: 8) {
                Button { } label: {
                    Image(systemName: "plus")
                        .font(.headline.weight(.bold))
                        .frame(width: 42, height: 42)
                        .background(
                            LinearGradient(colors: [.indigo, .purple], startPoint: .topLeading, endPoint: .bottomTrailing),
                            in: RoundedRectangle(cornerRadius: 13)
                        )
                }
                .buttonStyle(.plain)

                TextField("Напишіть ALTER...", text: state.composerText, axis: .vertical)
                    .lineLimit(1...4)
                    .textFieldStyle(.plain)
                    .padding(.horizontal, 12)
                    .frame(minHeight: 42)
                    .background(.white.opacity(0.035), in: RoundedRectangle(cornerRadius: 13))

                Button { } label: {
                    Image(systemName: "mic")
                        .frame(width: 38, height: 38)
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)

                Button {
                    appState.submitComposer()
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.headline.weight(.bold))
                        .frame(width: 40, height: 40)
                        .background(.indigo, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
            }

            HStack(spacing: 6) {
                ComposerMode(title: "Говорити", symbol: "waveform")
                ComposerMode(title: "Екран", symbol: "display")
                ComposerMode(title: "Режим: \(appState.taskMode)", symbol: "slider.horizontal.3")
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 10)
        .padding(.bottom, 8)
        .background(.ultraThinMaterial)
        .overlay(alignment: .top) { Divider().overlay(.white.opacity(0.07)) }
    }

    private var background: some View {
        ZStack {
            Color.black
            RadialGradient(
                colors: [.indigo.opacity(0.18), .clear],
                center: UnitPoint(x: 0.05, y: 0.2),
                startRadius: 0,
                endRadius: 260
            )
            RadialGradient(
                colors: [Color.orange.opacity(0.08), .clear],
                center: UnitPoint(x: 0.95, y: 0.58),
                startRadius: 0,
                endRadius: 240
            )
        }
        .ignoresSafeArea()
    }
}

private struct CockpitModule: Identifiable {
    let id = UUID()
    let title: String
    let symbol: String
    let tint: Color
}

private struct TabLabel: View {
    let title: String
    let symbol: String
    let selected: Bool

    var body: some View {
        Label(title, systemImage: symbol)
            .font(.caption2)
            .foregroundStyle(selected ? Color.indigo : .secondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(selected ? Color.indigo.opacity(0.10) : .clear, in: RoundedRectangle(cornerRadius: 11))
            .overlay(
                RoundedRectangle(cornerRadius: 11)
                    .stroke(selected ? Color.indigo.opacity(0.45) : .clear)
            )
    }
}

private struct ChatRow: View {
    let isAgent: Bool
    let title: String
    let message: String
    let details: String?

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Group {
                if isAgent {
                    Text("A")
                        .font(.headline.weight(.light))
                        .rotationEffect(.degrees(-5))
                } else {
                    Text("В")
                        .font(.caption.weight(.semibold))
                }
            }
            .frame(width: 32, height: 32)
            .background(isAgent ? Color.white.opacity(0.025) : Color.indigo.opacity(0.16), in: Circle())
            .overlay(Circle().stroke(isAgent ? Color.white.opacity(0.12) : Color.indigo.opacity(0.35)))

            VStack(alignment: .leading, spacing: 5) {
                Text(title)
                    .font(.caption2)
                    .foregroundStyle(.secondary)

                Text(message)
                    .font(.subheadline)
                    .foregroundStyle(.primary)

                if let details {
                    Text(details)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineSpacing(2)
                }
            }

            Spacer(minLength: 0)
        }
        .padding(.vertical, 12)
    }
}

private struct DraftCard: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                ZStack {
                    LinearGradient(
                        colors: [Color.orange.opacity(0.75), Color.brown.opacity(0.55), Color.black],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    Image(systemName: "mountain.2.fill")
                        .font(.system(size: 34))
                        .foregroundStyle(.black.opacity(0.5))
                    Image(systemName: "play.fill")
                        .font(.title3)
                        .foregroundStyle(.white)
                        .shadow(radius: 5)
                }
                .frame(width: 92, height: 118)
                .clipShape(RoundedRectangle(cornerRadius: 10))

                VStack(alignment: .leading, spacing: 5) {
                    Text("Чернетка відео v1")
                        .font(.subheadline.weight(.semibold))
                    Text("30 сек · 16:9 · 1080p")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("Понеділок — новий старт. Маленькі кроки сьогодні = великі результати завтра.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("#понеділок #продуктивність #фокус")
                        .font(.caption2)
                        .foregroundStyle(.indigo)
                }
            }

            HStack(spacing: 6) {
                DraftButton(title: "Схвалити", symbol: "checkmark.circle", tint: .indigo)
                DraftButton(title: "Відхилити", symbol: "xmark.circle", tint: .red)
                DraftButton(title: "Ще", symbol: "arrow.triangle.2.circlepath", tint: .secondary)
            }
        }
        .padding(10)
        .background(.white.opacity(0.025), in: RoundedRectangle(cornerRadius: 14))
        .overlay(RoundedRectangle(cornerRadius: 14).stroke(.white.opacity(0.08)))
    }
}

private struct DraftButton: View {
    let title: String
    let symbol: String
    let tint: Color

    var body: some View {
        Label(title, systemImage: symbol)
            .font(.caption2)
            .foregroundStyle(tint)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(.white.opacity(0.02), in: RoundedRectangle(cornerRadius: 9))
            .overlay(RoundedRectangle(cornerRadius: 9).stroke(tint.opacity(0.30)))
    }
}

private struct SummaryTile: View {
    let title: String
    let value: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2)
                .foregroundStyle(tint)
            Text(value)
                .font(.headline.weight(.semibold))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(11)
        .background(tint.opacity(0.055), in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(tint.opacity(0.15)))
    }
}

private struct ComposerMode: View {
    let title: String
    let symbol: String

    var body: some View {
        Label(title, systemImage: symbol)
            .font(.caption2)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
            .background(.white.opacity(0.025), in: RoundedRectangle(cornerRadius: 10))
    }
}

private extension View {
    func alterCard(glow: Bool = false) -> some View {
        background(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .fill(.ultraThinMaterial)
                .background(
                    LinearGradient(
                        colors: [Color.white.opacity(0.03), Color.black.opacity(0.12)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    in: RoundedRectangle(cornerRadius: 20, style: .continuous)
                )
        )
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(glow ? Color.indigo.opacity(0.42) : Color.white.opacity(0.075))
        )
        .shadow(color: glow ? Color.indigo.opacity(0.10) : .black.opacity(0.20), radius: glow ? 18 : 12, y: 8)
    }
}

#Preview {
    NavigationStack {
        CockpitView()
    }
    .environment(AppState())
    .preferredColorScheme(.dark)
}
