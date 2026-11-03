// swift make_icon.swift  → icon.png (1024×1024). A play button turning into lines
// of notes, on the app's blue. Rebuild AppIcon.icns with make_icon.sh.
import AppKit

let size = 1024.0
// An explicit pixel canvas: NSImage.lockFocus would draw at 2x on a Retina Mac.
let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size),
                           bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                           colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
let ctx = NSGraphicsContext.current!.cgContext

// macOS icon grid: 824 pt rounded square centered on a 1024 canvas.
let inset = 100.0, side = size - 2 * inset
let tile = CGPath(roundedRect: CGRect(x: inset, y: inset, width: side, height: side),
                  cornerWidth: 185, cornerHeight: 185, transform: nil)
ctx.addPath(tile); ctx.clip()
let colors = [NSColor(srgbRed: 0.27, green: 0.52, blue: 0.98, alpha: 1).cgColor,
              NSColor(srgbRed: 0.09, green: 0.22, blue: 0.62, alpha: 1).cgColor] as CFArray
let grad = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: [0, 1])!
ctx.drawLinearGradient(grad, start: CGPoint(x: 0, y: size), end: CGPoint(x: size, y: 0), options: [])

ctx.setFillColor(NSColor.white.cgColor)
// Play triangle, left.
let tri = CGMutablePath()
tri.move(to: CGPoint(x: 260, y: 680)); tri.addLine(to: CGPoint(x: 260, y: 344))
tri.addLine(to: CGPoint(x: 520, y: 512)); tri.closeSubpath()
ctx.addPath(tri); ctx.fillPath()
// Note lines, right, getting shorter.
for (i, w) in [264.0, 214.0, 164.0].enumerated() {
    let y = 640.0 - Double(i) * 128.0
    ctx.addPath(CGPath(roundedRect: CGRect(x: 560, y: y - 26, width: w, height: 52),
                       cornerWidth: 26, cornerHeight: 26, transform: nil))
}
ctx.fillPath()
NSGraphicsContext.current = nil
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "icon.png"))
