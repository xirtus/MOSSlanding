#!/usr/bin/env swift
// Generate the DMG background image (600×340, Retina @2x = 1200×680).
// Native CoreGraphics + Core Text port of the previous Pillow-based
// make_dmg_bg.py — no third-party deps.
//
// Usage: swift scripts/make_dmg_bg.swift <output-png-path>

import AppKit
import CoreGraphics
import CoreImage
import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers

let W: Int = 1200
let H: Int = 680

let outPath: String = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : "/tmp/dmg_bg.png"

@inline(__always) func lerp(_ a: Double, _ b: Double, _ t: Double) -> Double { a + (b - a) * t }

func rgb(_ r: Int, _ g: Int, _ b: Int, alpha: Double = 1.0) -> CGColor {
    CGColor(red: Double(r)/255, green: Double(g)/255, blue: Double(b)/255, alpha: alpha)
}

func makeContext(width: Int, height: Int) -> CGContext {
    return CGContext(
        data: nil,
        width: width, height: height,
        bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    )!
}

let ctx = makeContext(width: W, height: H)
let w = CGFloat(W), h = CGFloat(H)

// Flip to top-down to mirror the Pillow coordinate system.
ctx.translateBy(x: 0, y: h)
ctx.scaleBy(x: 1, y: -1)

// ── Background gradient ───────────────────────────────────────────────────
let bgGradient = CGGradient(
    colorsSpace: CGColorSpaceCreateDeviceRGB(),
    colors: [rgb(10, 14, 30), rgb(18, 10, 38)] as CFArray,
    locations: [0.0, 1.0]
)!
ctx.drawLinearGradient(
    bgGradient,
    start: CGPoint(x: 0, y: 0),
    end:   CGPoint(x: 0, y: h),
    options: []
)

// ── Subtle grid lines (every W/12 px) ─────────────────────────────────────
let gridColor = rgb(40, 50, 90, alpha: 0.16)
ctx.setStrokeColor(gridColor)
ctx.setLineWidth(1)
let step = CGFloat(W / 12)
var x = CGFloat(0)
while x < w {
    ctx.move(to: CGPoint(x: x, y: 0))
    ctx.addLine(to: CGPoint(x: x, y: h))
    x += step
}
var y = CGFloat(0)
while y < h {
    ctx.move(to: CGPoint(x: 0, y: y))
    ctx.addLine(to: CGPoint(x: w, y: y))
    y += step
}
ctx.strokePath()

// ── Faint waveform decoration, then Gaussian-blur the layer ───────────────
let waveCtx = makeContext(width: W, height: H)
waveCtx.translateBy(x: 0, y: h)
waveCtx.scaleBy(x: 1, y: -1)
waveCtx.setLineWidth(1)
for i in 0..<3 {
    let amp = 18.0 + Double(i) * 12.0
    let freq = 0.008 - Double(i) * 0.001
    let offY = Double(H) * 0.72 + Double(i) * 18.0
    var px = 0
    var prev = CGPoint(x: 0, y: CGFloat(offY))
    while px <= W {
        let yv = offY + sin(Double(px) * freq + Double(i) * 1.2) * amp
        let cur = CGPoint(x: CGFloat(px), y: CGFloat(yv))
        let tH = Double(px) / Double(W)
        let r = lerp(30/255, 0/255,   tH)
        let g = lerp(80/255, 180/255, tH)
        let b = lerp(200/255, 255/255, tH)
        waveCtx.setStrokeColor(CGColor(red: r, green: g, blue: b, alpha: 0.16))
        waveCtx.move(to: prev)
        waveCtx.addLine(to: cur)
        waveCtx.strokePath()
        prev = cur
        px += 2
    }
}
if let waveImage = waveCtx.makeImage() {
    let ci = CIContext()
    let blurred = CIImage(cgImage: waveImage)
        .clampedToExtent()
        .applyingFilter("CIGaussianBlur", parameters: ["inputRadius": 2.0])
        .cropped(to: CGRect(x: 0, y: 0, width: W, height: H))
    if let blurredCG = ci.createCGImage(blurred, from: blurred.extent) {
        ctx.saveGState()
        ctx.scaleBy(x: 1, y: -1)
        ctx.translateBy(x: 0, y: -h)
        ctx.draw(blurredCG, in: CGRect(x: 0, y: 0, width: w, height: h))
        ctx.restoreGState()
    }
}

// ── Title + subtitle (Core Text) ──────────────────────────────────────────
func drawCenteredText(_ string: String, font: NSFont, color: CGColor, topY: CGFloat) {
    let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor(cgColor: color)!]
    let attr = NSAttributedString(string: string, attributes: attrs)
    let line = CTLineCreateWithAttributedString(attr)
    let bounds = CTLineGetBoundsWithOptions(line, .useOpticalBounds)
    let xPos = (w - bounds.width) / 2 - bounds.origin.x

    // Core Text draws upright, so undo the flip locally.
    ctx.saveGState()
    ctx.scaleBy(x: 1, y: -1)
    ctx.translateBy(x: 0, y: -h)
    // Convert top-down y to bottom-up y for the baseline.
    let baselineY = h - topY - bounds.height - bounds.origin.y
    ctx.textPosition = CGPoint(x: xPos, y: baselineY)
    CTLineDraw(line, ctx)
    ctx.restoreGState()
}

let titleFont = NSFont(name: "SF Pro Display", size: 52)
    ?? NSFont(name: "Helvetica", size: 52)
    ?? NSFont.systemFont(ofSize: 52)
let subFont = NSFont(name: "SF Pro Display", size: 28)
    ?? NSFont(name: "Helvetica", size: 28)
    ?? NSFont.systemFont(ofSize: 28)

drawCenteredText("MOSSlanding",
                 font: titleFont,
                 color: rgb(220, 235, 255),
                 topY: 40)
drawCenteredText("Drag to Applications to install",
                 font: subFont,
                 color: rgb(100, 120, 180),
                 topY: 108)

// ── Arrow between app and Applications ────────────────────────────────────
let ax = w / 2
let ay = h / 2 + 20
let arrow = rgb(60, 100, 200)
ctx.setStrokeColor(arrow)
ctx.setLineWidth(3)
ctx.move(to: CGPoint(x: ax - 60, y: ay))
ctx.addLine(to: CGPoint(x: ax + 60, y: ay))
ctx.strokePath()
ctx.setFillColor(arrow)
ctx.beginPath()
ctx.move(to: CGPoint(x: ax + 60, y: ay - 10))
ctx.addLine(to: CGPoint(x: ax + 80, y: ay))
ctx.addLine(to: CGPoint(x: ax + 60, y: ay + 10))
ctx.closePath()
ctx.fillPath()

// ── Save ──────────────────────────────────────────────────────────────────
guard let image = ctx.makeImage() else {
    FileHandle.standardError.write(Data("failed to render image\n".utf8))
    exit(1)
}
let url = URL(fileURLWithPath: outPath)
let type: CFString = UTType.png.identifier as CFString
guard let dest = CGImageDestinationCreateWithURL(url as CFURL, type, 1, nil) else {
    FileHandle.standardError.write(Data("could not open \(outPath) for write\n".utf8))
    exit(1)
}
CGImageDestinationAddImage(dest, image, nil)
if !CGImageDestinationFinalize(dest) {
    FileHandle.standardError.write(Data("could not finalize PNG \(outPath)\n".utf8))
    exit(1)
}
print("DMG background saved: \(outPath) (\(W)×\(H))")
