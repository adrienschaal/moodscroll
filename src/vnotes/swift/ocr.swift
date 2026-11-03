// ocr <frames-dir>
// Prints one JSON line per .jpg: {"file": "0001.jpg", "lines": ["...", ...]}.
// Uses Apple's Vision framework, so it runs on-device and needs no model download.
import AppKit
import Foundation
import Vision

let dir = URL(fileURLWithPath: CommandLine.arguments[1])
let files = try FileManager.default.contentsOfDirectory(atPath: dir.path)
    .filter { $0.hasSuffix(".jpg") }.sorted()

for f in files {
    var lines: [String] = []
    if let img = NSImage(contentsOf: dir.appendingPathComponent(f)),
       let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.automaticallyDetectsLanguage = true
        req.usesLanguageCorrection = true
        try? VNImageRequestHandler(cgImage: cg).perform([req])
        for o in req.results ?? [] {
            if let t = o.topCandidates(1).first, t.confidence > 0.4 {
                lines.append(t.string)
            }
        }
    }
    let rec: [String: Any] = ["file": f, "lines": lines]
    let data = try JSONSerialization.data(withJSONObject: rec)
    print(String(data: data, encoding: .utf8)!)
}
