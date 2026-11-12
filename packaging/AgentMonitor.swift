// Native macOS window for Agent Monitor: WKWebView with an ephemeral cookie store; only our own origin may load.
// Usage: AgentMonitor <login url>. Without a URL (Finder/Spotlight launch) it asks the launcher for one.
import Cocoa
import WebKit

let bundleID = Bundle.main.bundleIdentifier ?? "local.AgentMonitor"
let openURL = Notification.Name(bundleID + ".open")

let launcher = Bundle.main.object(forInfoDictionaryKey: "AMLauncher") as? String

func runLauncher(_ arg: String) -> (Int32, String)? {
    guard let launcher else { return nil }
    let p = Process(), out = Pipe()
    p.executableURL = URL(fileURLWithPath: launcher)
    p.arguments = [arg]
    p.standardOutput = out
    guard (try? p.run()) != nil else { return nil }
    let data = out.fileHandleForReading.readDataToEndOfFile()
    p.waitUntilExit()
    return (p.terminationStatus, String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "")
}

func loginURL() -> String? {
    if CommandLine.arguments.count > 1 { return CommandLine.arguments[1] }
    guard let (rc, url) = runLauncher("--print-url"), rc == 0 else { return nil }
    return url
}

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate {
    let url: String
    var window: NSWindow!
    var view: WKWebView!

    init(url: String) { self.url = url }

    func applicationDidFinishLaunching(_ n: Notification) {
        let cfg = WKWebViewConfiguration()
        cfg.websiteDataStore = .nonPersistent()
        view = WKWebView(frame: .zero, configuration: cfg)
        view.navigationDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Agent Monitor"
        window.contentView = view
        window.setFrameAutosaveName("AgentMonitor")
        window.center()
        load(url)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        DistributedNotificationCenter.default().addObserver(forName: openURL, object: nil, queue: .main) { [weak self] n in
            guard let u = n.object as? String else { return }
            self?.load(u)  // re-login (server may have restarted) and raise
            self?.window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
        }
    }

    func load(_ s: String) { if let u = URL(string: s) { view.load(URLRequest(url: u)) } }

    func origin(_ s: String) -> String? {
        guard let u = URL(string: s), let host = u.host, let port = u.port else { return nil }
        return "\(u.scheme ?? "")://\(host):\(port)/"
    }

    func webView(_ v: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        let target = a.request.url?.absoluteString ?? ""
        decisionHandler(origin(url).map { target.hasPrefix($0) } == true ? .allow : .cancel)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { true }

    // Closing the app stops the server and every claude session it runs.
    func applicationWillTerminate(_ n: Notification) { _ = runLauncher("--stop") }
}

// Without Edit menu items, Cmd+C/V/X/A do nothing in the page's text fields.
func buildMenu() -> NSMenu {
    let main = NSMenu()
    let app = NSMenu(), edit = NSMenu(title: "Edit")
    app.addItem(withTitle: "Quit Agent Monitor", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
    edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
    edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
    edit.addItem(.separator())
    edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
    edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
    edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
    edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
    for m in [app, edit] { let i = NSMenuItem(); i.submenu = m; main.addItem(i) }
    return main
}

guard let url = loginURL() else { exit(1) }
let me = ProcessInfo.processInfo.processIdentifier
if let other = NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).first(where: { $0.processIdentifier != me }) {
    DistributedNotificationCenter.default().postNotificationName(openURL, object: url, userInfo: nil, deliverImmediately: true)
    other.activate()
    exit(0)
}
let app = NSApplication.shared
let delegate = AppDelegate(url: url)
app.delegate = delegate
app.setActivationPolicy(.regular)
app.mainMenu = buildMenu()
app.run()
