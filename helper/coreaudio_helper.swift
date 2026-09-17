// coreaudio_helper v1.1 — CoreAudio + IOBluetooth bridge for MyAudio.app
// Usage:
//   coreaudio_helper list                 -> JSON array of output devices
//   coreaudio_helper setvol <uid> <0..1>  -> set device volume
//   coreaudio_helper setdefault <uid>     -> make device the default output
//   coreaudio_helper sources              -> JSON array of apps currently playing
//   coreaudio_helper btlist               -> JSON array of paired Bluetooth audio devices
//   coreaudio_helper btconnect <addr>     -> connect a paired Bluetooth device
//   coreaudio_helper btdisconnect <addr>  -> disconnect a Bluetooth device
import AppKit
import CoreAudio
import Foundation
import IOBluetooth

let sysObj = AudioObjectID(kAudioObjectSystemObject)

func addr(_ sel: AudioObjectPropertySelector,
          _ scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
          _ element: AudioObjectPropertyElement = kAudioObjectPropertyElementMain) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(mSelector: sel, mScope: scope, mElement: element)
}

func fourCC(_ v: UInt32) -> String {
    let b = [UInt8((v >> 24) & 255), UInt8((v >> 16) & 255), UInt8((v >> 8) & 255), UInt8(v & 255)]
    return (String(bytes: b, encoding: .ascii) ?? "").trimmingCharacters(in: .whitespaces)
}

func objectList(_ id: AudioObjectID, _ sel: AudioObjectPropertySelector) -> [AudioObjectID] {
    var a = addr(sel)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(id, &a, 0, nil, &size) == noErr, size > 0 else { return [] }
    var ids = [AudioObjectID](repeating: 0, count: Int(size) / MemoryLayout<AudioObjectID>.size)
    guard AudioObjectGetPropertyData(id, &a, 0, nil, &size, &ids) == noErr else { return [] }
    return ids
}

func stringProp(_ id: AudioObjectID, _ sel: AudioObjectPropertySelector) -> String {
    var a = addr(sel)
    var size = UInt32(MemoryLayout<CFString?>.size)
    var out: CFString?
    let st = withUnsafeMutablePointer(to: &out) {
        AudioObjectGetPropertyData(id, &a, 0, nil, &size, $0)
    }
    return st == noErr ? (out as String? ?? "") : ""
}

func u32Prop(_ id: AudioObjectID, _ sel: AudioObjectPropertySelector) -> UInt32? {
    var a = addr(sel)
    var size = UInt32(MemoryLayout<UInt32>.size)
    var v: UInt32 = 0
    return AudioObjectGetPropertyData(id, &a, 0, nil, &size, &v) == noErr ? v : nil
}

func outputChannels(_ id: AudioObjectID) -> Int {
    var a = addr(kAudioDevicePropertyStreamConfiguration, kAudioObjectPropertyScopeOutput)
    var size: UInt32 = 0
    guard AudioObjectGetPropertyDataSize(id, &a, 0, nil, &size) == noErr, size > 0 else { return 0 }
    let buf = UnsafeMutableRawPointer.allocate(byteCount: Int(size), alignment: 16)
    defer { buf.deallocate() }
    guard AudioObjectGetPropertyData(id, &a, 0, nil, &size, buf) == noErr else { return 0 }
    let abl = buf.assumingMemoryBound(to: AudioBufferList.self)
    return UnsafeMutableAudioBufferListPointer(abl).reduce(0) { $0 + Int($1.mNumberChannels) }
}

// Volume lives on the main element for most devices, but some expose only
// per-channel elements, so fall back to scanning the first few channels.
func volumeElements(_ id: AudioObjectID) -> [AudioObjectPropertyElement] {
    var main = addr(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput)
    if AudioObjectHasProperty(id, &main) { return [kAudioObjectPropertyElementMain] }
    var found: [AudioObjectPropertyElement] = []
    for ch in 1...UInt32(max(outputChannels(id), 2)) {
        var a = addr(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, ch)
        if AudioObjectHasProperty(id, &a) { found.append(ch) }
    }
    return found
}

func getVolume(_ id: AudioObjectID) -> Float32? {
    let els = volumeElements(id)
    guard !els.isEmpty else { return nil }
    var total: Float32 = 0
    var n = 0
    for el in els {
        var a = addr(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, el)
        var size = UInt32(MemoryLayout<Float32>.size)
        var v: Float32 = 0
        if AudioObjectGetPropertyData(id, &a, 0, nil, &size, &v) == noErr { total += v; n += 1 }
    }
    return n > 0 ? total / Float32(n) : nil
}

func setVolume(_ id: AudioObjectID, _ value: Float32) -> Bool {
    let v = min(max(value, 0), 1)
    var ok = false
    for el in volumeElements(id) {
        var a = addr(kAudioDevicePropertyVolumeScalar, kAudioObjectPropertyScopeOutput, el)
        var settable: DarwinBoolean = false
        guard AudioObjectIsPropertySettable(id, &a, &settable) == noErr, settable.boolValue else { continue }
        var val = v
        if AudioObjectSetPropertyData(id, &a, 0, nil, UInt32(MemoryLayout<Float32>.size), &val) == noErr { ok = true }
    }
    return ok
}

func isMuted(_ id: AudioObjectID) -> Bool {
    var a = addr(kAudioDevicePropertyMute, kAudioObjectPropertyScopeOutput)
    guard AudioObjectHasProperty(id, &a) else { return false }
    var size = UInt32(MemoryLayout<UInt32>.size)
    var v: UInt32 = 0
    return AudioObjectGetPropertyData(id, &a, 0, nil, &size, &v) == noErr && v != 0
}

func defaultOutput() -> AudioObjectID {
    u32Prop(sysObj, kAudioHardwarePropertyDefaultOutputDevice) ?? 0
}

func setDefaultOutput(_ id: AudioObjectID) -> Bool {
    var ok = false
    for sel in [kAudioHardwarePropertyDefaultOutputDevice, kAudioHardwarePropertyDefaultSystemOutputDevice] {
        var a = addr(sel)
        var v = id
        if AudioObjectSetPropertyData(sysObj, &a, 0, nil, UInt32(MemoryLayout<AudioObjectID>.size), &v) == noErr { ok = true }
    }
    return ok
}

func outputDevices() -> [(id: AudioObjectID, uid: String)] {
    objectList(sysObj, kAudioHardwarePropertyDevices)
        .filter { outputChannels($0) > 0 }
        .map { ($0, stringProp($0, kAudioDevicePropertyDeviceUID)) }
}

func find(_ uid: String) -> AudioObjectID? {
    outputDevices().first { $0.uid == uid }?.id
}

// MARK: - Playing sources

/// Apps currently sending audio to an output device (macOS 14.2+).
func playingSources() -> [[String: Any]] {
    var out: [[String: Any]] = []
    for proc in objectList(sysObj, kAudioHardwarePropertyProcessObjectList) {
        guard let running = u32Prop(proc, kAudioProcessPropertyIsRunningOutput), running != 0 else { continue }
        let bundle = stringProp(proc, kAudioProcessPropertyBundleID)
        var pid: pid_t = 0
        var a = addr(kAudioProcessPropertyPID)
        var size = UInt32(MemoryLayout<pid_t>.size)
        AudioObjectGetPropertyData(proc, &a, 0, nil, &size, &pid)
        let app = NSRunningApplication(processIdentifier: pid)
        let name = app?.localizedName ?? bundle.components(separatedBy: ".").last ?? "Unknown"
        out.append(["bundle": bundle, "pid": Int(pid), "name": name])
    }
    return out
}

// MARK: - Bluetooth

func btAudioDevices() -> [IOBluetoothDevice] {
    let paired = (IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice]) ?? []
    return paired.filter { $0.deviceClassMajor == UInt32(kBluetoothDeviceClassMajorAudio) }
}

func btFind(_ address: String) -> IOBluetoothDevice? {
    let wanted = address.lowercased().replacingOccurrences(of: ":", with: "-")
    return btAudioDevices().first {
        ($0.addressString ?? "").lowercased().replacingOccurrences(of: ":", with: "-") == wanted
    }
}

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write(("error: " + msg + "\n").data(using: .utf8)!)
    exit(1)
}

func emit(_ object: Any) {
    let data = try! JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
}

let args = Array(CommandLine.arguments.dropFirst())
switch args.first {
case "list":
    let def = defaultOutput()
    var out: [[String: Any]] = []
    for (id, uid) in outputDevices() {
        let vol = getVolume(id)
        out.append([
            "uid": uid,
            "name": stringProp(id, kAudioObjectPropertyName),
            "transport": u32Prop(id, kAudioDevicePropertyTransportType).map { fourCC($0) } ?? "",
            "channels": outputChannels(id),
            "isDefault": id == def,
            "muted": isMuted(id),
            "volume": vol.map { Double($0) } as Any,
            "canSetVolume": vol != nil,
        ])
    }
    emit(out)

case "sources":
    emit(playingSources())

case "btlist":
    emit(btAudioDevices().map { device -> [String: Any] in
        [
            "address": (device.addressString ?? "").replacingOccurrences(of: "-", with: ":"),
            "name": device.name ?? "Bluetooth device",
            "connected": device.isConnected(),
        ]
    })

case "btconnect":
    guard args.count == 2, let device = btFind(args[1]) else { fail("no such Bluetooth device") }
    if device.openConnection() != kIOReturnSuccess { fail("could not connect \(args[1])") }

case "btdisconnect":
    guard args.count == 2, let device = btFind(args[1]) else { fail("no such Bluetooth device") }
    if device.closeConnection() != kIOReturnSuccess { fail("could not disconnect \(args[1])") }

case "setvol":
    guard args.count == 3, let v = Float32(args[2]) else { fail("usage: setvol <uid> <0..1>") }
    guard let id = find(args[1]) else { fail("no such device: \(args[1])") }
    if !setVolume(id, v) { fail("volume not settable on \(args[1])") }

case "setdefault":
    guard args.count == 2 else { fail("usage: setdefault <uid>") }
    guard let id = find(args[1]) else { fail("no such device: \(args[1])") }
    if !setDefaultOutput(id) { fail("could not set default output to \(args[1])") }

default:
    fail("usage: coreaudio_helper list|sources|btlist|btconnect <addr>|btdisconnect <addr>|setvol <uid> <0..1>|setdefault <uid>")
}
