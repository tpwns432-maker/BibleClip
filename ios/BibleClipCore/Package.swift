// swift-tools-version:5.9
// BibleClip 엔진 — android/.../core/ (Kotlin) 의 1:1 이식. 화면 없이 `swift test` 로
// tests/golden/*.json (Python 엔진이 쓴 정답) 과 비교한다. docs/IOS_PLAN.md 0단계.
import PackageDescription

let package = Package(
    name: "BibleClipCore",
    platforms: [.iOS(.v17), .macOS(.v13)],
    products: [
        .library(name: "BibleClipCore", targets: ["BibleClipCore"]),
    ],
    targets: [
        .target(name: "BibleClipCore"),
        .testTarget(name: "BibleClipCoreTests", dependencies: ["BibleClipCore"]),
    ]
)
