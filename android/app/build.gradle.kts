plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.tom.device"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.tom.device"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "0.3.0"
        buildConfigField("String", "TOM_VOICE_WS_URL", "\"${System.getenv("TOM_VOICE_WS_URL") ?: ""}\"")
        buildConfigField("String", "TOM_BRIDGE_WS_URL", "\"${System.getenv("TOM_BRIDGE_WS_URL") ?: ""}\"")
        buildConfigField("String", "TOM_DEVICE_ID", "\"${System.getenv("TOM_DEVICE_ID") ?: ""}\"")
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.activity:activity-ktx:1.13.0")
    implementation("com.google.android.material:material:1.13.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
