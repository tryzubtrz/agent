import SwiftUI

struct CockpitView: View {
    @Environment(AppState.self) private var appState

    private let modules: [CockpitModule] = [
        .init(title: "ALTER", symbol: "sparkles", status: .ready),
        .init(title: "Files", symbol: "folder", status: .ready),
        .init(title: "Browser", symbol: "globe", status: .planned),
        .init(title: "Console", symbol: "terminal", status: .planned),
        .init(title: "Android", symbol: "smartphone", status: .planned),
        .init(title: "Rules", symbol: "shield", status: .ready),
        .init(title: "Vault", symbol: "key", status: .ready),
        .init(title: "Models", symbol: "cpu", status: .ready),
        .init(title: "Market", symbol: "storefront", status: .planned),
        .init(title: "Tasks", symbol: "clock", status: .ready),
        .init(title: "Connectors", symbol: "cable.connector", status: .attention),
        .init(title: "Memory", symbol: "brain", status: .ready),
        .init(title: "People", symbol: "person.2", status: .ready),
        .init(title: "Settings", symbol: "gearshape", status: .ready)
    ]

    private let columns = [
        GridItem(.adaptive(minimum: 72), spacing: 10)
    ]

    var body: some View {
        @Bindable var state = appState

        ScrollView {
            VStack(spacing: 20) {
                header
                activeTaskCard
                moduleSection
                connectorAlert
                recentActivity
            }
            .padding(.horizontal, 16)
            .padding(.bottom, 112)
        }
        .safeAreaInset(edge: .bottom) {
            composer(state: $state)
        }
        .background(background)
        .toolbar(.hidden, for: .navigationBar)
    }

    private var header: some View {
        HStack(spacing: 12) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(Color.indigo.opacity(0.18))
                Text("A")
                    .font(.headline.weight(.bold))
            }
            .frame(width: 44, height: 44)

            VStack(alignment: .leading, spacing: 2) {
                Text("PERSONAL CONTROL PLANE")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text("ALTER")
                    .font(.title3.weight(.bold))
            }

            Spacer()

            Label(appState.status.rawValue, systemImage: "circle.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.green)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(.green.opacity(0.08), in: Capsule())
                .accessibilityLabel("Статус ALTER: \(appState.status.rawValue)")
        }
        .padding(.top, 8)
    }

    private var activeTaskCard: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("ЗАРАЗ")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(appState.activeTask.title)
                        .font(.title2.weight(.bold))
                }

                Spacer()

                Text("1 активна")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.indigo)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 7)
                    .background(.indigo.opacity(0.1), in: Capsule())
            }

            ProgressView(value: appState.activeTask.progress)
                .tint(.indigo)

            HStack {
                Label("\(appState.activeTask.completedSteps) етапи", systemImage: "checkmark.circle")
                Spacer()
                Label(appState.activeTask.nextStep, systemImage: "play.fill")
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            HStack(spacing: 10) {
                Button {
                    appState.status = .waiting
                } label: {
                    Label("Live-view", systemImage: "rectangle.inset.filled.and.person.filled")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(.indigo)

                Button {
                    appState.status = .idle
                } label: {
                    Label("Пауза", systemImage: "pause.fill")
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(18)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(.white.opacity(0.07))
        }
    }

    private var moduleSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 3) {
                    Text("РОБОЧИЙ ПРОСТІР")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text("Модулі")
                        .font(.headline)
                }
                Spacer()
            }

            LazyVGrid(columns: columns, spacing: 10) {
                ForEach(modules) { module in
                    Button {
                        // Routing is added per feature as modules become connected.
                    } label: {
                        ModuleTile(module: module)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Модуль \(module.title)")
                }
            }
        }
    }

    private var connectorAlert: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "cable.connector")
                .frame(width: 38, height: 38)
                .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
                .foregroundStyle(.orange)

            VStack(alignment: .leading, spacing: 4) {
                Text("ПОТРІБНА ДІЯ")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text("Botpress потребує повторного підключення")
                    .font(.subheadline.weight(.semibold))
                Text("Ядро ALTER продовжує роботу незалежно від цього конектора.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer(minLength: 0)
        }
        .padding(14)
        .background(.orange.opacity(0.055), in: RoundedRectangle(cornerRadius: 18))
        .overlay {
            RoundedRectangle(cornerRadius: 18)
                .stroke(.orange.opacity(0.16))
        }
    }

    private var recentActivity: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Останні події")
                .font(.headline)

            ActivityRow(title: "Архітектура control plane створена", symbol: "checkmark.circle.fill", tint: .green)
            ActivityRow(title: "Threat model доданий", symbol: "shield.checkered", tint: .green)
            ActivityRow(title: "Botpress очікує авторизацію", symbol: "exclamationmark.circle.fill", tint: .orange)
        }
        .padding(16)
        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 20))
    }

    private func composer(state: Bindable<AppState>) -> some View {
        VStack(spacing: 8) {
            HStack {
                Button("+") { }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Додати вкладення")

                Button {
                } label: {
                    Image(systemName: "mic")
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Диктувати")

                Spacer()

                Picker("Режим задачі", selection: state.taskMode) {
                    Text("Швидко").tag("Швидко")
                    Text("Звичайно").tag("Звичайно")
                    Text("Глибоко").tag("Глибоко")
                    Text("Лише план").tag("Лише план")
                    Text("Чернетка").tag("Чернетка")
                }
                .pickerStyle(.menu)
                .font(.caption)
            }
            .foregroundStyle(.secondary)

            HStack(spacing: 10) {
                TextField("Що робимо?", text: state.composerText, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.plain)

                Button {
                    appState.submitComposer()
                } label: {
                    Image(systemName: "arrow.up")
                        .font(.headline.weight(.bold))
                        .frame(width: 38, height: 38)
                }
                .buttonStyle(.borderedProminent)
                .buttonBorderShape(.roundedRectangle(radius: 12))
                .tint(.indigo)
                .accessibilityLabel("Надіслати")
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 9)
        .padding(.bottom, 8)
        .background(.ultraThinMaterial)
    }

    private var background: some View {
        LinearGradient(
            colors: [Color.black, Color.indigo.opacity(0.11), Color.black],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }
}

private struct CockpitModule: Identifiable {
    enum Status { case ready, planned, attention }

    let id = UUID()
    let title: String
    let symbol: String
    let status: Status
}

private struct ModuleTile: View {
    let module: CockpitModule

    var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(spacing: 8) {
                Image(systemName: module.symbol)
                    .font(.system(size: 20, weight: .medium))
                    .foregroundStyle(.indigo)
                    .frame(width: 38, height: 38)
                    .background(.indigo.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))

                Text(module.title)
                    .font(.caption2)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity, minHeight: 84)
            .background(.white.opacity(0.035), in: RoundedRectangle(cornerRadius: 16))
            .overlay {
                RoundedRectangle(cornerRadius: 16)
                    .stroke(.white.opacity(0.07))
            }

            Circle()
                .fill(statusColor)
                .frame(width: 6, height: 6)
                .padding(8)
        }
    }

    private var statusColor: Color {
        switch module.status {
        case .ready: .green
        case .planned: .gray
        case .attention: .orange
        }
    }
}

private struct ActivityRow: View {
    let title: String
    let symbol: String
    let tint: Color

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: symbol)
                .foregroundStyle(tint)
            Text(title)
                .font(.subheadline)
            Spacer()
        }
    }
}

#Preview {
    NavigationStack {
        CockpitView()
    }
    .environment(AppState())
    .preferredColorScheme(.dark)
}
