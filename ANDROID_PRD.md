# NoInsta Android Client — Product Requirement Document (PRD)

**Document Version:** 1.0.0  
**Target Platform:** Android 8.0+ (API Level 26 through API Level 35)  
**Language & Framework:** Kotlin 2.x, Jetpack Compose, Coroutines & Flow, Android Jetpack  
**Companion Services:**
* **Backend Server:** `https://noinsta.platesight.in/` (FastAPI + PostgreSQL + WebSockets)
* **Desktop Client:** NoInsta Desktop (PySide6 / Windows & Linux)  
**Document Status:** Approved for Implementation  
**Last Updated:** September 2026  

---

## 1. Executive Summary & Core Objective

**NoInsta** is an intentional friction and digital discipline system designed to break reflexive social media habits. The system operates across two user endpoints coordinated by a central server:
1. **The Trigger (Android Phone):** Detects when the user launches Instagram.
2. **The Authority (NoInsta Cloud Server):** Authenticates devices, enforces a 5-minute global cooldown, checks laptop presence, and dispatches intervention commands.
3. **The Interrupter (Laptop Client):** Immediately brings up an un-ignorable modal window and sounds an alert, forcing the user to physically acknowledge their distraction before continuing.

### Core Android Objective
The Android client must reliably detect when the official Instagram application (`com.instagram.android`) or Instagram Lite (`com.instagram.lite`) enters the foreground, and immediately send an authenticated HTTPS event to the server with **latency under 300 milliseconds**, with **minimal battery consumption (<1.5% per 24 hours)**, while surviving aggressive OEM background process management.

---

## 2. High-Level Architecture & Interaction Flow

```text
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 ANDROID CLIENT                                  │
│                                                                                 │
│   ┌────────────────────────┐      Window Event     ┌────────────────────────┐   │
│   │ Accessibility Service  │ ────────────────────> │ Session State Machine  │   │
│   │ (Detection Engine)     │   com.instagram       │ (Debounce & Lifecycle) │   │
│   └────────────────────────┘                       └───────────┬────────────┘   │
│                                                                │                │
│                                                         Dispatch Event          │
│                                                                ▼                │
│   ┌────────────────────────┐    Network Restored   ┌────────────────────────┐   │
│   │ WorkManager Offline    │ <──────────────────── │ OkHttp / Retrofit API  │   │
│   │ Queue (Room DB)        │   Flush Cached Evts   │ Client + Auth Engine   │   │
│   └────────────────────────┘                       └───────────┬────────────┘   │
└────────────────────────────────────────────────────────────────┼────────────────┘
                                                                 │
                                          POST /api/v1/events    │  HTTPS (TLS 1.3)
                                          Bearer <Device_Token>  ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                               NOINSTA CLOUD SERVER                              │
│                          (https://noinsta.platesight.in/)                       │
│                                                                                 │
│   1. Validates Device Token & Extracts user_id                                  │
│   2. Idempotency check via client_event_id                                      │
│   3. Database row-lock: 5-minute global user cooldown                           │
│   4. Queries active WebSocket laptop connections with recent heartbeats         │
│   5. Dispatches intervention payload over WebSocket                             │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                                         │  WSS (JSON)
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              NOINSTA LAPTOP CLIENT                              │
│                                                                                 │
│   1. Receives { "type": "instagram_open", "event_id": "..." }                   │
│   2. Pops up on top of all windows (WindowStaysOnTopHint)                       │
│   3. Plays alert audio tone + displays alert graphic                            │
│   4. User presses [Stop / Acknowledge] -> Sends intervention_closed             │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Foreground Detection Engine: In-Depth Technical Specification

Android restricts background app monitoring. Two primary platform APIs can achieve package monitoring:
1. **AccessibilityService (`android.accessibilityservice.AccessibilityService`)** — **PRIMARY (MANDATORY)**
2. **UsageStatsManager (`android.app.usage.UsageStatsManager`)** — **SECONDARY / WATCHDOG**

### 3.1 Primary Mechanism: AccessibilityService

The Accessibility Service provides **event-driven, zero-polling, instantaneous (<50ms)** detection of package window transitions.

#### Why AccessibilityService?
* **Zero Polling Battery Cost:** The OS calls the service only when window events occur. No background CPU loops or scheduled timers are needed.
* **Instantaneous Response:** Fires as the Activity transition starts, allowing the server to alert the laptop before the user even finishes viewing their first Instagram post.
* **Reliability Across OEM Skins:** Works consistently across Samsung OneUI, Google Pixel, Xiaomi HyperOS, OnePlus OxygenOS, and Motorola.

#### Detection Criteria & Debouncing Logic
1. **Target Packages:**
   * Primary: `com.instagram.android`
   * Secondary (Optional): `com.instagram.lite`
2. **Event Filtering:**
   * Listen strictly to `AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED`.
   * Ignore notifications, toast messages, and child view changes (`TYPE_WINDOW_CONTENT_CHANGED`, `TYPE_NOTIFICATION_STATE_CHANGED`).
3. **Session Identification & State Machine:**
   * **Transition into Instagram:** If the previous foreground package was *NOT* Instagram and the current package is Instagram, transition state from `IDLE` to `ACTIVE`:
     * Generate a new `session_id = UUID.randomUUID().toString()`.
     * Dispatch `instagram_open` event.
   * **Transition out of Instagram:** If the previous foreground package was Instagram and the current package is *NOT* Instagram (e.g. user pressed Home, switched to another app, or locked device):
     * Dispatch `instagram_close` event with the current `session_id`.
     * Clear `session_id` and reset state to `IDLE`.
   * **Screen Off Handling:** Register a dynamic `BroadcastReceiver` for `Intent.ACTION_SCREEN_OFF`. If the user locks the phone while in Instagram, immediately dispatch `instagram_close`.
   * **Internal Navigation Debounce:** Sub-activities within Instagram (e.g. opening a DM, opening Camera, opening Reels, keyboard opening) also fire `TYPE_WINDOW_STATE_CHANGED` with `packageName = com.instagram.android`. The engine must verify that the *package* changed, not just an internal window class.

#### Accessibility Service Implementation

```kotlin
// DetectionAccessibilityService.kt
package in.platesight.noinsta.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.view.accessibility.AccessibilityEvent
import dagger.hilt.android.AndroidEntryPoint
import in.platesight.noinsta.domain.model.AppEventType
import in.platesight.noinsta.domain.usecase.ProcessAppEventUseCase
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

@AndroidEntryPoint
class DetectionAccessibilityService : AccessibilityService() {

    @Inject
    lateinit var processAppEventUseCase: ProcessAppEventUseCase

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)

    private var currentForegroundPackage: String = ""
    private var currentSessionId: String? = null
    private val targetPackages = setOf("com.instagram.android", "com.instagram.lite")

    private val screenLockReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (intent?.action == Intent.ACTION_SCREEN_OFF) {
                handleScreenOff()
            }
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        val info = AccessibilityServiceInfo().apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            notificationTimeout = 50 // ms debounce
            flags = AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
        }
        this.serviceInfo = info

        val filter = IntentFilter(Intent.ACTION_SCREEN_OFF)
        registerReceiver(screenLockReceiver, filter)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null || event.eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) return

        val newPackage = event.packageName?.toString() ?: return

        // Ignore non-application UI packages (e.g. system UI drop-down, volume sliders)
        if (isIgnoredSystemPackage(newPackage)) return

        if (newPackage == currentForegroundPackage) {
            // Internal window change within the same app; ignore
            return
        }

        val wasInstagram = targetPackages.contains(currentForegroundPackage)
        val isInstagram = targetPackages.contains(newPackage)

        currentForegroundPackage = newPackage

        if (!wasInstagram && isInstagram) {
            // Instagram Opened
            val newSessionId = UUID.randomUUID().toString()
            currentSessionId = newSessionId
            dispatchTrigger(AppEventType.INSTAGRAM_OPEN, newSessionId)
        } else if (wasInstagram && !isInstagram) {
            // Instagram Closed
            currentSessionId?.let { sessionId ->
                dispatchTrigger(AppEventType.INSTAGRAM_CLOSE, sessionId)
                currentSessionId = null
            }
        }
    }

    private fun handleScreenOff() {
        if (targetPackages.contains(currentForegroundPackage)) {
            currentForegroundPackage = ""
            currentSessionId?.let { sessionId ->
                dispatchTrigger(AppEventType.INSTAGRAM_CLOSE, sessionId)
                currentSessionId = null
            }
        }
    }

    private fun dispatchTrigger(type: AppEventType, sessionId: String) {
        serviceScope.launch {
            processAppEventUseCase(type, sessionId)
        }
    }

    private fun isIgnoredSystemPackage(pkg: String): Boolean {
        return pkg == "com.android.systemui" || 
               pkg == "android" || 
               pkg.contains("inputmethod")
    }

    override fun onInterrupt() {
        // Accessibility service interrupted by system
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            unregisterReceiver(screenLockReceiver)
        } catch (_: Exception) {}
        serviceScope.cancel()
    }
}
```

#### XML Configuration (`res/xml/accessibility_service_config.xml`)
```xml
<?xml version="1.0" encoding="utf-8"?>
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:description="@string/accessibility_service_description"
    android:accessibilityEventTypes="typeWindowStateChanged"
    android:accessibilityFeedbackType="feedbackGeneric"
    android:notificationTimeout="50"
    android:accessibilityFlags="flagDefault"
    android:canRetrieveWindowContent="false" />
```
> **Critical Privacy Note:** Notice `android:canRetrieveWindowContent="false"`. The service **cannot** read screen text, cannot see user posts, and cannot capture keystrokes. It only reads the foreground package name.

---

## 4. Background Persistence & OEM Survivability

Modern Android devices (especially Samsung, Xiaomi, Oppo, Vivo, OnePlus) terminate background services aggressively to save battery. The NoInsta Android app must implement the following multi-layered persistence architecture:

### 4.1 Foreground Service with Low-Priority Notification
An ongoing foreground service ensures Android does not kill the app's process under memory pressure.

* **Notification Channel:** `noinsta_service_channel` (Importance: `IMPORTANCE_LOW` — silent, no popup sound or vibration).
* **Notification Content:**
  * Title: `NoInsta Active`
  * Text: `Monitoring digital discipline • Paired to server`
  * Small Icon: Shield or discipline icon.
  * Ongoing: `true`.
* **Android 14+ (API 34) Foreground Service Type:**
  * Use `android:foregroundServiceType="specialUse"` with a declaration in `AndroidManifest.xml`:
  ```xml
  <service
      android:name=".service.NoInstaForegroundService"
      android:foregroundServiceType="specialUse"
      android:exported="false">
      <property
          android:name="android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE"
          android:value="Habit control cross-device intervention alerting system." />
  </service>
  ```

### 4.2 Exemption from Battery Optimization (Doze Mode)
To prevent the OS from suspending the network interface when the phone is idle:
* Prompt the user during onboarding to whitelist NoInsta from battery optimizations using `Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.
```kotlin
val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
    data = Uri.parse("package:${context.packageName}")
}
context.startActivity(intent)
```

### 4.3 Device Reboot Survivability (`BOOT_COMPLETED`)
Register a `BroadcastReceiver` to re-initialize the foreground service whenever the phone boots up:
```xml
<receiver
    android:name=".receiver.BootCompletedReceiver"
    android:enabled="true"
    android:exported="false">
    <intent-filter>
        <action android:name="android.intent.action.BOOT_COMPLETED" />
        <action android:name="android.intent.action.MY_PACKAGE_REPLACED" />
        <action android:name="android.intent.action.QUICKBOOT_POWERON" />
    </intent-filter>
</receiver>
```

---

## 5. Device Pairing & Authentication Protocol

The Android device acts as an authenticated **Device** in the NoInsta backend ecosystem.

### 5.1 Pairing Flow
1. The user creates a 6-character pairing code (via web dashboard or existing authenticated session).
2. The Android user opens the NoInsta app, sees the Pairing Screen, enters the 6-character code (e.g. `A3K9XZ`), and names their device (e.g. `"Pixel 8 Pro"`).
3. The app executes:
   `POST /api/v1/pairing/claim`
   ```json
   {
     "pairing_code": "A3K9XZ",
     "device_name": "Pixel 8 Pro",
     "device_type": "ANDROID"
   }
   ```
4. The server validates the code (TTL: 10 minutes, single-use, atomic), creates the device record, and returns:
   ```json
   {
     "device_id": "c10e3852-37f4-4f4b-8965-40aebf297374",
     "access_token": "eyJhbGciOiJIUzI1Ni...",
     "refresh_token": "d9a8f4c2...",
     "user_id": "17982603-d526-4f7a-8a7e-5af61fa4c24b",
     "message": "Device paired successfully."
   }
   ```
5. The Android client securely persists:
   * `device_id` (UUID string)
   * `access_token` (JWT, expires in 30 days)
   * `refresh_token` (Opaque token, expires in 90 days)
   * `user_id` (UUID string)

### 5.2 Token Storage & Keystore Security
* Use **Android Jetpack Security** (`androidx.security.crypto.EncryptedSharedPreferences`).
* The encryption keys are managed by the hardware **Android Keystore**, ensuring tokens cannot be extracted even on rooted or inspected devices.

```kotlin
// SecurePreferencesManager.kt
val masterKey = MasterKey.Builder(context)
    .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
    .build()

val securePrefs = EncryptedSharedPreferences.create(
    context,
    "noinsta_secure_prefs",
    masterKey,
    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
)
```

### 5.3 Automated Token Refresh Interceptor
Implement an OkHttp `Authenticator` that transparently handles HTTP 401 Unauthorized responses:
1. Intercepts HTTP 401.
2. Obtains a mutex lock to prevent concurrent duplicate refresh calls.
3. Calls `POST /api/v1/auth/refresh` with the stored `refresh_token`.
4. Updates `access_token` and `refresh_token` in `EncryptedSharedPreferences`.
5. Retries the failed request with the new `Authorization: Bearer <new_token>`.
6. If the refresh token is expired or revoked (HTTP 401/403), clears credentials, halts monitoring, and prompts the user to re-pair.

---

## 6. Event Ingestion & Server API Contract

All events sent by the Android phone use standard HTTPS REST endpoints on:
`https://noinsta.platesight.in/api/v1/events`

### 6.1 Event Ingestion Endpoint Specification

* **URL:** `POST https://noinsta.platesight.in/api/v1/events`
* **Headers:**
  * `Authorization: Bearer <device_access_token>`
  * `Content-Type: application/json`
* **Request Schema:**
  ```json
  {
    "event_type": "instagram_open",
    "occurred_at": "2026-09-10T15:20:00.123Z",
    "session_id": "phone_session_101",
    "client_event_id": "evt_d828f311-1898-4a3c"
  }
  ```
  * `event_type` (string, required): Either `"instagram_open"` or `"instagram_close"`.
  * `occurred_at` (ISO 8601 string, optional): Local timestamp when the event occurred.
  * `session_id` (string, optional): Unique ID representing the continuous Instagram foreground session.
  * `client_event_id` (string, optional): Client-generated unique UUID used by the server as an **idempotency key** to prevent duplicate dispatches if network requests are retried.

### 6.2 Server Response Matrix

#### Case 1: First Instagram Open (Intervention Triggered)
```json
HTTP/1.1 201 Created
Content-Type: application/json

{
  "success": true,
  "event_id": "d828f311-1898-4a3c-83fe-673a2848d68d",
  "intervention_triggered": true,
  "eligible_laptops_count": 1,
  "message": "Intervention successfully dispatched to online laptops."
}
```

#### Case 2: Second Instagram Open within 5 Minutes (Cooldown Active)
```json
HTTP/1.1 201 Created
Content-Type: application/json

{
  "success": true,
  "event_id": "f1042301-4432-47ba-8911-5321589124bc",
  "intervention_triggered": false,
  "eligible_laptops_count": 0,
  "message": "Event recorded; intervention suppressed due to 5-minute cooldown."
}
```

#### Case 3: Instagram Open when Laptop is Offline (No online laptops)
```json
HTTP/1.1 201 Created
Content-Type: application/json

{
  "success": true,
  "event_id": "a7318491-1102-48df-b210-6712394012ab",
  "intervention_triggered": false,
  "eligible_laptops_count": 0,
  "message": "Event recorded; no online laptops available."
}
```

#### Case 4: Instagram Close Event
```json
HTTP/1.1 201 Created
Content-Type: application/json

{
  "success": true,
  "event_id": "e9210432-8412-4211-9a74-1234567890ab",
  "intervention_triggered": false,
  "eligible_laptops_count": 0,
  "message": "Instagram close event recorded."
}
```

#### Case 5: Duplicate Replay (Idempotent Hit)
```json
HTTP/1.1 201 Created
Content-Type: application/json

{
  "success": true,
  "event_id": "d828f311-1898-4a3c-83fe-673a2848d68d",
  "intervention_triggered": false,
  "eligible_laptops_count": 0,
  "message": "Duplicate event recognized (idempotency key matched)."
}
```

---

## 7. Offline Resilience & Event Buffering Architecture

When the user opens Instagram in an area with poor connectivity, airplane mode, or during temporary network drops, events must not be lost.

### 7.1 Architecture: Room Database Buffer + WorkManager
1. When `instagram_open` or `instagram_close` fires:
   * Write the event immediately to a local SQLite database table (`pending_events`).
2. Immediately launch a coroutine to attempt transmission over OkHttp.
3. If the HTTP call succeeds (HTTP 201):
   * Delete the record from `pending_events`.
4. If the HTTP call fails (e.g. `IOException`, `SocketTimeoutException`, or no active network):
   * Keep the record in `pending_events` with `retry_count += 1`.
   * Enqueue an expedited `OneTimeWorkRequest` via **Jetpack WorkManager** with a `NetworkType.CONNECTED` constraint.
5. When connectivity is restored, WorkManager executes `FlushPendingEventsWorker`:
   * Reads pending events in ascending chronological order (`occurred_at ASC`).
   * Sends them sequentially to `POST /api/v1/events`.
   * Uses the stored `client_event_id` so the server can safely deduplicate.

### 7.2 Database Schema (`pending_events`)
```sql
CREATE TABLE pending_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    client_event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    session_id TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
```

---

## 8. User Interface & Screen Specifications

The UI is intentionally minimal, clean, and distraction-free, following **Material 3 (Material You)** guidelines.

### Screen 1: Onboarding & Permissions Wizard
* **Purpose:** Educate user and guide them to grant the 3 necessary permissions:
  1. **Accessibility Service:** Clear, transparent explanation: *"NoInsta needs accessibility to detect when Instagram launches. We never read your messages, posts, or screen content."* -> Deep-link to `Settings.ACTION_ACCESSIBILITY_SETTINGS`.
  2. **Battery Optimization Exemption:** *"Allow NoInsta to stay active in the background so alerts reach your laptop instantly."* -> Trigger `ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS`.
  3. **Notification Permission (Android 13+):** *"Required to display the active monitoring status."* -> Trigger `POST_NOTIFICATIONS` runtime request.

### Screen 2: Device Pairing Screen
* **Input Fields:**
  * 6-Character Pairing Code (Custom 6-box segmented PIN style or uppercase text input).
  * Device Name (Prefilled with `Build.MODEL`, e.g. "Pixel 8 Pro").
* **Actions:**
  * **[Pair Device]** Button: Shows spinner, makes API call, transitions to Dashboard upon success.
  * Helper Text: *"Generate a code on your NoInsta web dashboard or laptop client."*

### Screen 3: Main Dashboard Screen
* **Header:** NoInsta Logo + Status Badge:
  * 🟢 **"Active & Paired"** (Accessibility ON, Token Valid)
  * 🟠 **"Accessibility Disabled"** (Prompt with button: "Re-enable")
  * 🔴 **"Not Paired"** (Prompt: "Pair Now")
* **Device Info Card:**
  * Device Name: *Pixel 8 Pro*
  * Paired Account: *user@example.com*
  * Server URL: *https://noinsta.platesight.in/*
* **Statistics Card:**
  * Interventions Triggered Today: *e.g. 4*
  * Last Detected Session: *Today, 3:42 PM (4m 12s)*
* **Manual Trigger Test Button:**
  * **[Test Trigger Now]** -> Sends a synthetic `instagram_open` event to verify the laptop pops up immediately.
* **Pause Monitoring Action (Discipline Safeguard):**
  * Optional: "Pause for 30 minutes" with confirmation prompt.

### Screen 4: Settings & Diagnostics
* **Connection Status Test:** Pings `/api/v1/health` and displays server latency.
* **Unpair Device:** Revokes token via API (`POST /api/v1/auth/revoke`), clears local database and secure prefs.
* **View Privacy Disclosure:** Clear language outlining data handling.

---

## 9. Privacy, Security & Google Play Store Compliance

### 9.1 Accessibility Service Declaration Policy
To pass Google Play review and avoid policy strikes regarding `AccessibilityService`:
1. **Prominent In-App Disclosure:** Must display an unmissable, non-technical disclosure modal *before* redirecting to Android Accessibility Settings.
2. **Declaration Text:**
   * *"NoInsta uses the Android AccessibilityService API strictly to detect when the Instagram application is in the foreground. NoInsta does NOT record audio, does NOT read messages, does NOT capture keystrokes, and does NOT monitor any other application or personal data."*
3. **Google Play Console Form:**
   * Category: *Personal productivity / Digital wellbeing*.
   * Is this an accessibility tool for disabled users? -> *No*.
   * Detailed justification: *"This app is a habit-breaking tool that sends real-time cross-device notifications when designated habit-forming social media apps are opened."*

### 9.2 Network Security & TLS Enforcement
Declare in `res/xml/network_security_config.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <!-- Strictly forbid unencrypted HTTP traffic -->
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
    <domain-config>
        <domain includeSubdomains="true">noinsta.platesight.in</domain>
        <!-- Optional: Certificate Pinning can be configured here -->
    </domain-config>
</network-security-config>
```

---

## 10. Recommended Tech Stack & Android Libraries

| Layer | Recommended Library / Tool | Rationale |
| :--- | :--- | :--- |
| **Language** | Kotlin 2.0+ | Official modern standard, coroutine first-class support. |
| **UI Framework** | Jetpack Compose + Material 3 | Declarative, lightweight, reactive state management. |
| **Dependency Injection** | Dagger Hilt (`com.google.dagger:hilt-android`) | Clean singleton lifecycle for services and repositories. |
| **Networking** | OkHttp 4.12+ + Retrofit 2.11+ | Industry standard HTTP client with interceptor support. |
| **Serialization** | Kotlinx Serialization | Fast, reflection-free JSON parsing. |
| **Local Database** | Jetpack Room 2.6+ | Type-safe SQLite persistence for offline queue. |
| **Secure Storage** | AndroidX Security Crypto (`EncryptedSharedPreferences`) | Hardware-backed AES-256 GCM token storage. |
| **Background Sync** | Jetpack WorkManager | Guaranteed execution with network constraints. |
| **Logging** | Timber | Clean, debug-only log statements. |

---

## 11. Testing & Verification Checklist

### 11.1 Functional Acceptance Tests
1. **First Launch Flow:**
   * App installs cleanly -> wizard requests Accessibility, Battery, Notifications -> user pairs with valid code -> transitions to "Active".
2. **Detection Latency:**
   * Tapping Instagram app icon on home screen -> `POST /api/v1/events` completes in < 300ms on 4G/5G/Wi-Fi.
   * Laptop screen pops alert in < 500ms total end-to-end.
3. **Internal Navigation Non-Spam:**
   * Navigating within Instagram (Stories -> Feed -> Reels -> Profile -> Comments) does **NOT** fire additional `instagram_open` events.
4. **App Switch / Screen Off:**
   * Locking phone while in Instagram fires `instagram_close` event.
   * Swiping home fires `instagram_close` event.
5. **Cooldown Verification:**
   * Rapidly opening Instagram, closing, and reopening within 2 minutes:
     * Server receives second event, records it, but returns `intervention_triggered: false` with cooldown message.
     * Laptop does not pop duplicate intervention.
6. **Offline Recovery:**
   * Turn on Airplane Mode -> open Instagram -> event saved to Room DB -> turn off Airplane Mode -> WorkManager flushes event to server -> Server acknowledges.
7. **Reboot Persistence:**
   * Reboot device -> `BootCompletedReceiver` starts service -> Accessibility remains enabled -> Opening Instagram triggers alert.
