import javax.inject.Inject

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// The repo root: android/ lives next to web/, bible_versions/ and tests/golden/.
val repoRoot: File = rootDir.parentFile

android {
    namespace = "com.bibleclip.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.bibleclip.app"
        minSdk = 26
        targetSdk = 34
        // 데스크톱과 같은 번호. versionCode = 주·부·수 각 두 자리(1.2.1 → 10201) — 늘기만 해야
        // 덮어 설치(업데이트)가 된다. android-v<versionName> 태그와 맞지 않으면 CI 가 멈춘다.
        versionCode = 10201
        versionName = "1.2.1"
    }

    // 개인 APK 배포: CI 가 BIBLECLIP_KEYSTORE* 환경변수로 서명한다. 없으면(로컬)
    // release 도 debug 키로 서명해 설치 시험은 되게 한다.
    signingConfigs {
        create("release") {
            val ks = System.getenv("BIBLECLIP_KEYSTORE")
            if (ks != null) {
                storeFile = file(ks)
                storePassword = System.getenv("BIBLECLIP_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("BIBLECLIP_KEY_ALIAS")
                keyPassword = System.getenv("BIBLECLIP_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (System.getenv("BIBLECLIP_KEYSTORE") != null)
                signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    testOptions {
        unitTests.all {
            // Golden vectors + the git-tracked bibles, shared with the Python tests.
            it.systemProperty("bibleclip.repoRoot", repoRoot.absolutePath)
        }
    }
}

/** web/ 와 기본 역본(KRV·KJV+)을 저장소에서 그대로 가져와 앱 assets 에 넣는다. */
abstract class RepoAssets : DefaultTask() {
    @get:InputDirectory
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val webDir: DirectoryProperty

    @get:InputFiles
    @get:PathSensitive(PathSensitivity.RELATIVE)
    abstract val bibles: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @get:Inject
    abstract val fs: FileSystemOperations

    @TaskAction
    fun run() {
        fs.sync {
            from(webDir) {
                into("web")
                // fonts.css 는 woff2 를 먼저 쓴다 — otf/ttf 사본(약 17MB)은 뺀다.
                exclude("fonts/Pretendard-*.otf", "fonts/Pretendard-*.ttf", "README.md")
            }
            from(bibles) { into("bible_versions") }
            into(outputDir)
        }
    }
}

val repoAssets = tasks.register<RepoAssets>("repoAssets") {
    webDir.set(repoRoot.resolve("web"))
    bibles.from(repoRoot.resolve("bible_versions/KRV.SQLite3"),
                repoRoot.resolve("bible_versions/KJV+.SQLite3"))
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(repoAssets, RepoAssets::outputDir)
    }
}

dependencies {
    implementation("androidx.webkit:webkit:1.8.0")

    testImplementation("junit:junit:4.13.2")
    // android.jar 의 org.json 은 JVM 테스트에서 껍데기뿐이라 진짜 구현을 넣는다.
    testImplementation("org.json:json:20231013")
    // 테스트는 같은 .SQLite3 파일을 JDBC 로 연다(android.database 는 기기 전용).
    testImplementation("org.xerial:sqlite-jdbc:3.44.1.0")
}
