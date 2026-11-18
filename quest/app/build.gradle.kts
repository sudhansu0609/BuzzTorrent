plugins {
  alias(libs.plugins.android.application)
  alias(libs.plugins.jetbrains.kotlin.android)
}

// Signed with the TV app's key (android/buzztv.keystore); its password lives in android/build_apk.py.
val tvDir = rootProject.file("../android")
val ksPass: String =
    Regex("""KS_PASS\s*=\s*"([^"]+)"""").find(File(tvDir, "build_apk.py").readText())?.groupValues?.get(1) ?: ""

android {
  namespace = "com.buzzcaf.buzztorrent.vr"
  compileSdk = 35

  defaultConfig {
    applicationId = "com.buzzcaf.buzztorrent.vr"
    minSdk = 34 // Horizon OS is Android 14
    targetSdk = 34
    versionCode = 2
    versionName = "1.1"
    ndk { abiFilters += "arm64-v8a" } // the Quest's only ABI
  }

  signingConfigs {
    create("buzz") {
      storeFile = File(tvDir, "buzztv.keystore")
      storePassword = ksPass
      keyAlias = "buzztv"
      keyPassword = ksPass
    }
  }

  buildTypes {
    release {
      isMinifyEnabled = false
      signingConfig = signingConfigs.getByName("buzz")
    }
  }

  // The 2D browse screen, its JavaScript bridge, the setup page and the playlist logic are the
  // TV app's own sources, shared rather than copied.
  sourceSets {
    getByName("main") {
      java.srcDirs("src/main/java", File(tvDir, "src"))
      assets.srcDirs("src/main/assets", File(tvDir, "assets"))
    }
  }

  packaging { resources.excludes.add("META-INF/LICENSE") }
  lint {
    abortOnError = false
    checkReleaseBuilds = false
  }
  compileOptions {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
  }
  kotlinOptions { jvmTarget = "17" }
}

dependencies {
  implementation(libs.androidx.core.ktx)
  implementation(libs.meta.spatial.sdk.base)
  implementation(libs.meta.spatial.sdk.toolkit)
  implementation(libs.meta.spatial.sdk.vr)
  implementation(libs.media3.exoplayer)
  implementation(libs.media3.effect)   // samples the film's colour so the room can glow with it
  implementation(libs.media3.ffmpeg.decoder) // AC3, E-AC3, DTS, TrueHD sound the Quest has no decoder for
}
