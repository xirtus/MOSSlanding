#!/usr/bin/env swift
// Generate a polished MOSSlanding app icon at every required macOS size.
// Native CoreGraphics port of the previous Pillow-based make_icon.py — no
// third-party deps; runs against the macOS Swift toolchain that already
// ships with Xcode CLT.
//
// Usage: swift scripts/make_icon.swift <output-iconset-dir>

import AppKit
import CoreGraphics
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers

let sizes: [Int] = [16, 32, 64, 128, 256, 512, 1024]

let outDir: String = CommandLine.arguments.count > 1
    ? CommandLine.arguments[1]
    : "MOSSlanding.app/Contents/Resources/AppIcon.iconset"

@inline(__always) func lerp(_ a: Double, _ b: Double, _ t: Double) -> Double { a + (b - a) * t }

func rgb(_ r: Int, _ g: Int, _ b: Int, alpha: Double = 1.0) -> CGColor {
    CGColor(red: Double(r)/255, green: Double(g)/255, blue: Double(b)/255, alpha: alpha)
}

func makeContext(size: Int) -> CGContext {
    return CGContext(
        data: nil,
        width: size, height: size,
        bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    )!
}

func makeIcon(size: Int) -> CGImage {
    let ctx = makeContext(size: size)
    let s = CGFloat(size)

    // Flip y so coordinates read top-down (matches the Pillow version).
    ctx.translateBy(x: 0, y: s)
    ctx.scaleBy(x: 1, y: -1)

    let margin = s * 0.04
    let cornerR = s * 0.22
    let bgRect = CGRect(x: margin, y: margin, width: s - 2 * margin, height: s - 2 * margin)
    let bgPath = CGPath(roundedRect: bgRect, cornerWidth: cornerR, cornerHeight: cornerR, transform: nil)

    // ── Background gradient (midnight blue → deep violet) ─────────────────
    ctx.saveGState()
    ctx.addPath(bgPath)
    ctx.clip()
    let bgGradient = CGGradient(
        colorsSpace: CGColorSpaceCreateDeviceRGB(),
        colors: [rgb(15, 20, 42), rgb(28, 15, 52)] as CFArray,
        locations: [0.0, 1.0]
    )!
    ctx.drawLinearGradient(
        bgGradient,
        start: CGPoint(x: 0, y: 0),
        end:   CGPoint(x: 0, y: s),
        options: []
    )

    // Subtle inner top-rim highlight.
    let topRim = CGRect(x: margin, y: margin, width: s - 2 * margin, height: s * 0.55 - margin)
    let topRimPath = CGPath(roundedRect: topRim, cornerWidth: cornerR, cornerHeight: cornerR, transform: nil)
    ctx.addPath(topRimPath)
    ctx.setFillColor(rgb(80, 100, 200, alpha: 0.07))
    ctx.fillPath()
    ctx.restoreGState()

    // ── Waveform bars ─────────────────────────────────────────────────────
    let barHeights: [CGFloat] = [0.18, 0.35, 0.55, 0.78, 1.0, 0.68, 0.38, 0.22]
    let n = barHeights.count
    let totalBarW = s * 0.62
    let spacing = totalBarW / (CGFloat(n) * 2 - 1)
    let barW = spacing
    let xStart = (s - totalBarW) / 2
    let maxBarH = s * 0.46
    let centerY = s * 0.52

    for (i, hFrac) in barHeights.enumerated() {
        let bh = maxBarH * hFrac
        let bx = xStart + CGFloat(i) * (barW + spacing)
        let by1 = centerY - bh
        let by2 = centerY + bh
        let br = barW * 0.45

        let tH = Double(i) / Double(n - 1)
        let topColor = CGColor(
            red:   lerp( 50/255, 0/255,   tH),
            green: lerp(130/255, 220/255, tH),
            blue:  lerp(255/255, 255/255, tH),
            alpha: 1
        )
        let botColor = CGColor(
            red:   lerp( 30/255, 0/255,   tH),
            green: lerp( 80/255, 160/255, tH),
            blue:  lerp(200/255, 220/255, tH),
            alpha: 1
        )
        let barGradient = CGGradient(
            colorsSpace: CGColorSpaceCreateDeviceRGB(),
            colors: [topColor, botColor] as CFArray,
            locations: [0.0, 1.0]
        )!

        let barRect = CGRect(x: bx, y: by1, width: barW, height: by2 - by1)
        let barPath = CGPath(roundedRect: barRect, cornerWidth: br, cornerHeight: br, transform: nil)

        ctx.saveGState()
        ctx.addPath(barPath)
        ctx.clip()
        ctx.drawLinearGradient(
            barGradient,
            start: CGPoint(x: 0, y: by1),
            end:   CGPoint(x: 0, y: by2),
            options: []
        )
        ctx.restoreGState()
    }

    // ── Bar bloom (Gaussian) — only on icons big enough to show it ───────
    if size >= 64 {
        let bloomCtx = makeContext(size: size)
        bloomCtx.translateBy(x: 0, y: s)
        bloomCtx.scaleBy(x: 1, y: -1)
        for (i, hFrac) in barHeights.enumerated() {
            let bh = maxBarH * hFrac
            let bx = xStart + CGFloat(i) * (barW + spacing)
            let tH = Double(i) / Double(n - 1)
            let color = CGColor(
                red:   lerp( 80/255,  0/255,   tH),
                green: lerp(160/255, 230/255, tH),
                blue:  lerp(255/255, 255/255, tH),
                alpha: 0.14
            )
            bloomCtx.setFillColor(color)
            let bloomRect = CGRect(
                x: bx - barW * 0.3,
                y: centerY - bh - barW * 0.3,
                width: barW * 1.6,
                height: 2 * bh + barW * 0.6
            )
            let bloomPath = CGPath(roundedRect: bloomRect, cornerWidth: barW, cornerHeight: barW, transform: nil)
            bloomCtx.addPath(bloomPath)
            bloomCtx.fillPath()
        }
        let bloomImage = bloomCtx.makeImage()!
        let radius = max(2.0, Double(size) / 40.0)
        let ci = CIContext()
        let blurred = CIImage(cgImage: bloomImage)
            .clampedToExtent()
            .applyingFilter("CIGaussianBlur", parameters: ["inputRadius": radius])
            .cropped(to: CGRect(x: 0, y: 0, width: size, height: size))
        if let blurredCG = ci.createCGImage(blurred, from: blurred.extent) {
            // Undo the flip so the upright bloom composites correctly.
            ctx.saveGState()
            ctx.scaleBy(x: 1, y: -1)
            ctx.translateBy(x: 0, y: -s)
            ctx.draw(blurredCG, in: CGRect(x: 0, y: 0, width: s, height: s))
            ctx.restoreGState()
        }
    }

    // ── Outer rim ─────────────────────────────────────────────────────────
    let bw = max(1.0, Double(size) / 180.0)
    let rimRect = bgRect.insetBy(dx: CGFloat(bw), dy: CGFloat(bw))
    let rimPath = CGPath(
        roundedRect: rimRect,
        cornerWidth: cornerR - CGFloat(bw),
        cornerHeight: cornerR - CGFloat(bw),
        transform: nil
    )
    ctx.addPath(rimPath)
    ctx.setStrokeColor(rgb(120, 160, 255, alpha: 0.18))
    ctx.setLineWidth(CGFloat(bw))
    ctx.strokePath()

    return ctx.makeImage()!
}

func savePNG(_ image: CGImage, to path: String) {
    let url = URL(fileURLWithPath: path)
    let type: CFString = UTType.png.identifier as CFString
    guard let dest = CGImageDestinationCreateWithURL(url as CFURL, type, 1, nil) else {
        FileHandle.standardError.write(Data("could not open \(path) for write\n".utf8))
        return
    }
    CGImageDestinationAddImage(dest, image, nil)
    if !CGImageDestinationFinalize(dest) {
        FileHandle.standardError.write(Data("could not finalize PNG \(path)\n".utf8))
    }
}

let fm = FileManager.default
try? fm.createDirectory(atPath: outDir, withIntermediateDirectories: true)

for size in sizes {
    let icon = makeIcon(size: size)
    if size <= 512 {
        savePNG(icon, to: "\(outDir)/icon_\(size)x\(size).png")
    }
    if size >= 32 {
        let half = size / 2
        savePNG(icon, to: "\(outDir)/icon_\(half)x\(half)@2x.png")
    }
}

let files = (try? fm.contentsOfDirectory(atPath: outDir).filter { $0.hasSuffix(".png") }) ?? []
print("Icon PNGs written to \(outDir)  (\(files.count) files)")
