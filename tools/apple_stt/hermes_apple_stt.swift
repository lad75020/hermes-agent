import AVFAudio
import Foundation
import Speech

@available(macOS 26.0, *)
struct Response: Encodable {
    let ok: Bool
    let transcript: String?
    let error: String?
    let status: String?
}

@available(macOS 26.0, *)
func emit(_ response: Response) {
    let encoder = JSONEncoder()
    if let data = try? encoder.encode(response), let text = String(data: data, encoding: .utf8) {
        print(text)
    } else {
        print("{\"ok\":false,\"error\":\"Could not encode Apple Speech response\"}")
    }
}

@available(macOS 26.0, *)
func transcriber(for language: String) async throws -> (SpeechTranscriber, Locale) {
    guard SpeechTranscriber.isAvailable else {
        throw NSError(domain: "HermesAppleSTT", code: 1, userInfo: [NSLocalizedDescriptionKey: "SpeechTranscriber is unavailable on this Mac"])
    }
    let requested = Locale(identifier: language)
    guard let supported = await SpeechTranscriber.supportedLocale(equivalentTo: requested) else {
        throw NSError(domain: "HermesAppleSTT", code: 2, userInfo: [NSLocalizedDescriptionKey: "Apple Speech does not support locale \(language)"])
    }
    return (SpeechTranscriber(locale: supported, preset: .transcription), supported)
}

@available(macOS 26.0, *)
func assetsInstalled(for locale: Locale) async -> Bool {
    // status(forModules:) can report "supported" for a usable shared model on
    // macOS 26. Check installedLocales as shown in Apple's WWDC25 sample.
    await SpeechTranscriber.installedLocales.contains(locale)
}

@available(macOS 26.0, *)
func ensureAssets(_ transcriber: SpeechTranscriber, locale: Locale, download: Bool) async throws -> String {
    let modules: [any SpeechModule] = [transcriber]
    if await assetsInstalled(for: locale) { return "installed" }
    guard download else {
        throw NSError(domain: "HermesAppleSTT", code: 3, userInfo: [NSLocalizedDescriptionKey: "Apple Speech assets are not installed (set stt.apple.download_assets: true to opt in)"])
    }
    guard let request = try await AssetInventory.assetInstallationRequest(supporting: modules) else {
        throw NSError(domain: "HermesAppleSTT", code: 4, userInfo: [NSLocalizedDescriptionKey: "Apple Speech assets cannot be installed for this locale"])
    }
    try await request.downloadAndInstall()
    guard await assetsInstalled(for: locale) else {
        throw NSError(domain: "HermesAppleSTT", code: 5, userInfo: [NSLocalizedDescriptionKey: "Apple Speech assets were not installed"])
    }
    return "installed"
}

@main
struct HermesAppleSTT {
    static func main() async {
        guard #available(macOS 26.0, *) else {
            print("{\"ok\":false,\"error\":\"Apple STT requires macOS 26 or later\"}")
            return
        }
        let args = Array(CommandLine.arguments.dropFirst())
        guard let command = args.first else {
            print("{\"ok\":false,\"error\":\"Usage: status|transcribe --language <locale> [--input <file>] [--download-assets]\"}")
            return
        }
        var language = Locale.current.identifier
        if let languageIndex = args.firstIndex(of: "--language") {
            guard args.indices.contains(languageIndex + 1) else {
                emit(Response(ok: false, transcript: nil, error: "Missing --language value", status: nil))
                return
            }
            language = args[languageIndex + 1]
        }
        do {
            let (module, locale) = try await transcriber(for: language)
            if command == "status" {
                let modules: [any SpeechModule] = [module]
                let status = await assetsInstalled(for: locale) ? "installed" : String(describing: await AssetInventory.status(forModules: modules))
                emit(Response(ok: true, transcript: nil, error: nil, status: status))
                return
            }
            guard command == "transcribe", let inputIndex = args.firstIndex(of: "--input"), args.indices.contains(inputIndex + 1) else {
                emit(Response(ok: false, transcript: nil, error: "Missing --input for transcribe", status: nil))
                return
            }
            _ = try await ensureAssets(module, locale: locale, download: args.contains("--download-assets"))
            let audio = try AVAudioFile(forReading: URL(fileURLWithPath: args[inputIndex + 1]))
            let analyzer = SpeechAnalyzer(modules: [module])
            try await analyzer.start(inputAudioFile: audio, finishAfterFile: true)
            var parts: [String] = []
            for try await result in module.results where result.isFinal {
                let text = String(result.text.characters).trimmingCharacters(in: .whitespacesAndNewlines)
                if !text.isEmpty { parts.append(text) }
            }
            withExtendedLifetime(analyzer) {}
            emit(Response(ok: true, transcript: parts.joined(separator: " "), error: nil, status: "installed"))
        } catch {
            emit(Response(ok: false, transcript: nil, error: error.localizedDescription, status: nil))
        }
    }
}
