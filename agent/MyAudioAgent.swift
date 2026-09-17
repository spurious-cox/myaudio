// MyAudioAgent — launchd shim for the AirPlay agent — v1.0 — SUPERSEDED
//
// NOT BUILT OR SHIPPED. A shim does not move the name TCC shows: the Local
// Network entry follows the binary that makes the calls, which was still the
// child interpreter, so Privacy & Security kept saying "python". build.sh now
// copies the interpreter itself to Resources/MyAudioAgent instead. Kept as a
// record of what the responsible-process rule does and does not cover.
//
// launchd runs THIS rather than the interpreter directly, so the Local Network
// prompt and the row in Privacy & Security carry the app's name instead of an
// anonymous "python". The agent still has to be a plain command-line process --
// a GUI bundle is never offered that permission on macOS -- so this stays a
// small binary whose only job is to start the interpreter and wait on it.
//
// The interpreter runs as a CHILD rather than via exec: TCC attributes access
// to the responsible process, which is the one launchd started, and execing
// would replace that identity with python's again.
//
// Build (the compiled binary is kept beside this source, as coreaudio_helper is):
//   swiftc -O -o agent/MyAudioAgent agent/MyAudioAgent.swift \
//       -Xlinker -sectcreate -Xlinker __TEXT -Xlinker __info_plist \
//       -Xlinker agent/MyAudioAgent-Info.plist

import Foundation

// Set before the child starts, read by the signal handlers. Swift C-function
// pointers cannot capture context, so this has to be global.
var childPid: pid_t = 0

let exePath = Bundle.main.executablePath ?? CommandLine.arguments[0]
let me = URL(fileURLWithPath: exePath).resolvingSymlinksInPath()

// <bundle>/Contents/Resources/MyAudioAgent
let resources = me.deletingLastPathComponent()
let contents = resources.deletingLastPathComponent()

let python = contents.appendingPathComponent("MacOS/python")
let script = resources.appendingPathComponent("myaudio_agent.py")
let lib = resources.appendingPathComponent("lib")

let versionTag = "python3.14"
let zipName = "python314.zip"

var env = ProcessInfo.processInfo.environment
// Bytecode written next to the source breaks the bundle's code signature.
env["PYTHONDONTWRITEBYTECODE"] = "1"
env["PYTHONHOME"] = resources.path
env["PYTHONPATH"] = [
    lib.appendingPathComponent(zipName).path,
    lib.appendingPathComponent(versionTag).path,
    lib.appendingPathComponent(versionTag).appendingPathComponent("lib-dynload").path,
    resources.path,
].joined(separator: ":")

let proc = Process()
proc.executableURL = python
proc.arguments = [script.path]
proc.environment = env

// launchctl bootout sends SIGTERM to this process; pass it on, or the
// interpreter is left running with no parent and the socket is never cleaned up.
signal(SIGTERM) { sig in if childPid > 0 { kill(childPid, sig) } }
signal(SIGINT) { sig in if childPid > 0 { kill(childPid, sig) } }

do {
    try proc.run()
} catch {
    FileHandle.standardError.write("MyAudioAgent: cannot start \(python.path): \(error)\n".data(using: .utf8)!)
    exit(1)
}

childPid = proc.processIdentifier
proc.waitUntilExit()
exit(proc.terminationStatus)
