// makeicon — renders MyAudio's app icon — v1.0
//
// Draws a macOS-style rounded square with a three-stop colour gradient and a
// white ♬ glyph, then writes a 1024pt PNG. build_icon.sh turns that into the
// .icns via sips + iconutil.
import AppKit
import Foundation

let size: CGFloat = 1024
let scale: CGFloat = 1  // 1024pt master; sips derives the smaller sizes

guard let context = CGContext(
    data: nil,
    width: Int(size * scale), height: Int(size * scale),
    bitsPerComponent: 8, bytesPerRow: 0,
    space: CGColorSpace(name: CGColorSpace.sRGB)!,
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
) else { fatalError("could not create context") }

context.scaleBy(x: scale, y: scale)

// macOS app icons sit in a squircle inset from the canvas edge.
let inset: CGFloat = size * 0.06
let rect = CGRect(x: inset, y: inset, width: size - inset * 2, height: size - inset * 2)
let radius = rect.width * 0.2237

let path = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)
context.saveGState()
context.addPath(path)
context.clip()

// Pink -> purple -> teal, corner to corner.
let colours = [
    CGColor(red: 1.00, green: 0.18, blue: 0.58, alpha: 1),
    CGColor(red: 0.48, green: 0.18, blue: 0.97, alpha: 1),
    CGColor(red: 0.19, green: 0.84, blue: 0.78, alpha: 1),
]
let gradient = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB)!,
                          colors: colours as CFArray,
                          locations: [0.0, 0.52, 1.0])!
context.drawLinearGradient(gradient,
                           start: CGPoint(x: rect.minX, y: rect.maxY),
                           end: CGPoint(x: rect.maxX, y: rect.minY),
                           options: [])

// Soft highlight across the top so it does not read as flat.
let sheen = CGGradient(colorsSpace: CGColorSpace(name: CGColorSpace.sRGB)!,
                       colors: [CGColor(red: 1, green: 1, blue: 1, alpha: 0.28),
                                CGColor(red: 1, green: 1, blue: 1, alpha: 0.0)] as CFArray,
                       locations: [0.0, 1.0])!
context.drawLinearGradient(sheen,
                           start: CGPoint(x: rect.midX, y: rect.maxY),
                           end: CGPoint(x: rect.midX, y: rect.midY),
                           options: [])
context.restoreGState()

// ♬ centred, in white, with a drop shadow for depth.
let nsContext = NSGraphicsContext(cgContext: context, flipped: false)
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = nsContext

let glyph = "♬"
var font = NSFont(name: "Apple Symbols", size: size * 0.56)
    ?? NSFont.systemFont(ofSize: size * 0.56)
// Apple Symbols renders ♬ small for its point size; nudge up if it looks thin.
if font.fontName == "AppleSymbols" {
    font = NSFont(name: "Apple Symbols", size: size * 0.64) ?? font
}

let shadow = NSShadow()
shadow.shadowColor = NSColor(calibratedWhite: 0, alpha: 0.28)
shadow.shadowOffset = NSSize(width: 0, height: -size * 0.012)
shadow.shadowBlurRadius = size * 0.03

let attributes: [NSAttributedString.Key: Any] = [
    .font: font,
    .foregroundColor: NSColor.white,
    .shadow: shadow,
]
let text = NSAttributedString(string: glyph, attributes: attributes)
let textSize = text.size()
text.draw(at: NSPoint(x: rect.midX - textSize.width / 2,
                      y: rect.midY - textSize.height / 2))

NSGraphicsContext.restoreGraphicsState()

guard let image = context.makeImage() else { fatalError("could not render") }
let out = URL(fileURLWithPath: CommandLine.arguments.count > 1
              ? CommandLine.arguments[1] : "icon.png")
let rep = NSBitmapImageRep(cgImage: image)
guard let data = rep.representation(using: .png, properties: [:]) else {
    fatalError("could not encode PNG")
}
try! data.write(to: out)
print("wrote \(out.path) (\(Int(size))x\(Int(size)))")
