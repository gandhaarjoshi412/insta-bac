# NoInsta Laptop Client

NoInsta is a cross-platform desktop background client for the NoInsta personal productivity-control system. When the user opens Instagram on their paired Android device, the NoInsta VPS pushes an authenticated event over an outbound TLS WebSocket (`wss://`), immediately triggering an attention-grabbing intervention on the laptop with custom local audio, video, or image media until acknowledged by the user.

---

## Supported Operating Systems

* **Windows 10 / 11**
* **Fedora Linux (Wayland)**
* **Fedora Linux (X11)**
* Other modern Linux distributions (GNOME, KDE, etc.)

---

## 1. Python Version Requirement

* **Python 3.11+** (Tested and validated on Python 3.11, 3.12, 3.13, and 3.14).

---

## 2. Installing Dependencies

Create and activate a virtual environment, then install the required packages:

### Linux (Fedora / Ubuntu / Debian)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Core Dependencies
* `PySide6`: Native Qt GUI, tray icon, attention window, and multimedia player (FFmpeg-backed).
* `websockets`: Asynchronous outbound TLS WebSocket client.
* `httpx`: TLS-verified HTTPS client for pairing and token refreshes.
* `pydantic`: Schema validation for protocol messages and configuration.
* `keyring`: Secure OS credential storage (Windows Credential Manager / Linux Secret Service).

---

## 3. Running the Application

Activate the virtual environment and start NoInsta:

```bash
python main.py
```

The application runs seamlessly in the background and places an indicator icon in the system tray:
* **Green**: Connected to VPS server and listening for events.
* **Orange**: Connecting or reconnecting.
* **Blue**: Authenticating.
* **Magenta / Pink**: Intervention active.
* **Grey**: Disconnected / Not paired.

---

## 4. Pairing the Device

On first launch, if the laptop has not yet been paired, the **NoInsta Device Pairing** dialog will automatically appear and fetch a new pairing code from the server:

```text
┌────────────────────────────────────────────────────────┐
│                        NOINSTA                         │
│                   Device Pairing                       │
│                                                        │
│  Laptop Name: [ Gandhaar-Fedora-Laptop               ] │
│                                                        │
│        Enter this code in your NoInsta Android app:    │
│                   ┌──────────────┐                     │
│                   │  A 7 K 9 Q 2 │                     │
│                   └──────────────┘                     │
│                     [Copy Code]                        │
│                                                        │
│  Status: ⏳ Waiting for Android phone to connect...    │
│                                                        │
│             [New Code]            [Done]               │
└────────────────────────────────────────────────────────┘
```

1. Launch NoInsta on your laptop (`python main.py` or `python main.py --pair`). The app contacts the server and displays a 6-character pairing code (e.g. `A7K9Q2`).
2. Open your **NoInsta Android app** and enter this 6-character pairing code into the **Pairing Code** field.
3. Tap **Pair Device** on your phone.
4. The server links both the laptop and phone records under your account, and the laptop dialog will automatically update: `✅ Paired successfully with <Android Device>!`.
5. Device credentials (`device_id`, `access_token`, `refresh_token`) are securely stored in your laptop's credential vault (`keyring` / Secret Service / Windows Credential Manager).
6. To re-pair or generate a new code at any time, right-click the system tray icon and select **Pair Device...** or run `python main.py --pair`.

---

## 5. Configuring Image, Video, and Audio Paths

Intervention media assets are stored **locally on your laptop**. The VPS server never uploads or serves heavy media files.

Configuration is saved in a platform-standard user directory:
* **Linux**: `~/.config/noinsta/config.json`
* **Windows**: `%APPDATA%\NoInsta\config.json`

### Example `config.json`
```json
{
  "server_url": "https://noinsta.platesight.in",
  "ws_url": null,
  "heartbeat_interval_seconds": 120,
  "reconnect_max_delay_seconds": 60,
  "log_level": "INFO",
  "media": {
    "image_path": "assets/alert.png",
    "video_path": null,
    "audio_path": "assets/alert.wav",
    "loop_video": true,
    "loop_audio": true
  },
  "window": {
    "always_on_top": true,
    "headline": "NO INSTAGRAM",
    "subheading": "STOP SCROLLING. GET BACK TO WORK.",
    "button_text": "CLOSE INTERVENTION",
    "width": 520,
    "height": 500
  }
}
```

### Media Priority & Fallbacks
1. **Video (`video_path`)**: Supported formats: `.mp4`, `.webm`. If configured and present, video plays in a loop in the center of the intervention dialog.
2. **Image (`image_path`)**: Supported formats: `.png`, `.jpg`, `.jpeg`, `.webp`. Used when `video_path` is null or unavailable.
3. **Audio (`audio_path`)**: Supported formats: `.wav`, `.mp3`, `.ogg`. Plays immediately when the intervention triggers and stops the instant the intervention is closed.
4. **Resilience**: If any media file is missing, NoInsta logs a warning and gracefully displays a high-contrast emergency warning banner without audio. It **never crashes** due to missing assets.

---

## 6. Running a Test Intervention

You can verify the intervention UI, display layout, and sound playback locally without needing to trigger Instagram from a phone:

### Via System Tray
Right-click the tray icon and select **⚡ Test Intervention**.

### Via Command Line
```bash
python main.py --test
```

Press <kbd>Space</kbd>, <kbd>Enter</kbd>, <kbd>Esc</kbd>, or click **CLOSE INTERVENTION** to dismiss the window and immediately stop audio and video playback.

---

## 7. Windows Startup Setup

To automatically start NoInsta whenever you log in to Windows:

```powershell
python main.py --enable-autostart
```

This registers the application in the current user's registry run key (`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`), requiring **no administrator rights**.

To disable Windows autostart:
```powershell
python main.py --disable-autostart
```

---

## 8. Fedora / Linux Startup Setup

NoInsta supports the standard XDG per-user autostart specification, fully compatible with GNOME, KDE, X11, and Wayland:

```bash
python main.py --enable-autostart
```

This writes `~/.config/autostart/noinsta.desktop` running under your user account with **no root/sudo privileges required**.

To verify autostart status:
```bash
python main.py --check-autostart
```

To disable Linux autostart:
```bash
python main.py --disable-autostart
```

---

## 9. Server URL Configuration

By default, the client communicates with:
* **HTTPS**: `https://noinsta.platesight.in/`
* **WSS**: `wss://noinsta.platesight.in/ws/device/{device_id}`

To point to a staging or local development server, update `server_url` in `config.json`:
```json
{
  "server_url": "https://your-custom-server.com"
}
```
The WebSocket URL will automatically derive to `wss://your-custom-server.com/ws/device/{device_id}` with strict TLS certificate verification.

---

## 10. Expected WebSocket Protocol

The laptop maintains an outbound TLS WebSocket connection behind NAT/firewalls. Inbound server ports are not needed.

### A. Authentication Handshake (Client -> Server)
Sent immediately upon connection:
```json
{
  "type": "authenticate",
  "device_id": "device_123",
  "access_token": "...",
  "timestamp": "2026-09-10T12:00:00Z"
}
```
HTTP headers `Authorization: Bearer <access_token>` and `X-Device-Id: <device_id>` are also attached during connection negotiation.

### B. Heartbeat Beacon (Client -> Server)
Sent every 120 seconds over the persistent WebSocket independently of UI state:
```json
{
  "type": "heartbeat",
  "device_id": "device_123",
  "timestamp": "2026-09-10T12:02:00Z"
}
```

### C. Instagram Open Event (Server -> Client)
Sent by the VPS when the user opens Instagram on their phone:
```json
{
  "type": "instagram_open",
  "event_id": "evt_abc123",
  "timestamp": "2026-09-10T12:03:00Z"
}
```

Client acknowledges receipt immediately:
```json
{
  "type": "intervention_received",
  "event_id": "evt_abc123",
  "device_id": "device_123",
  "timestamp": "2026-09-10T12:03:01Z"
}
```

### D. Intervention Dismissed (Client -> Server)
Sent when the user clicks the Close button or dismisses the window:
```json
{
  "type": "intervention_closed",
  "event_id": "evt_abc123",
  "device_id": "device_123",
  "timestamp": "2026-09-10T12:03:15Z"
}
```
If the network is temporarily unreachable when dismissed, the event is retained in an in-memory queue and automatically flushed upon reconnection.

### E. Strict Command Vocabulary (Security)
The WebSocket client enforces a strictly whitelisted vocabulary. Only the following incoming commands are processed:
* `instagram_open`
* `ping`
* `heartbeat_ack`
* `auth_error`

**Arbitrary command execution and remote shell execution are completely prohibited.** Unknown or malformed JSON payloads are discarded safely with a warning.

---

## 11. How to Debug Connection Failures

### Check Application Logs
Detailed logs are written to both standard output and the persistent log file:
* **Linux**: `~/.config/noinsta/noinsta.log`
* **Windows**: `%APPDATA%\NoInsta\noinsta.log`

### Common Issues & Troubleshooting

| Issue | Cause | Solution |
|---|---|---|
| **Status stays "Connecting..."** | Network offline or VPS temporarily unreachable | The client automatically retries with exponential backoff (`1s, 2s, 4s, 8s, 16s, 30s, 60s`). Check Wi-Fi or firewall. |
| **"Authentication error"** | Expired access token or revoked device | The client automatically attempts a token refresh using the stored refresh token. If rejected, click **Pair Device...** in the tray to re-pair. |
| **Silent intervention (no audio)** | Audio file path missing or audio device muted | Verify `audio_path` in `config.json`. Check that PipeWire / PulseAudio / Windows Sound is not muted. |
| **Duplicate windows not showing** | Event deduplication protection | The client suppresses duplicate `event_id` occurrences within 10 minutes to protect against network replays. |
| **Keyring warning on headless Linux** | Secret Service daemon not available in minimal tty | NoInsta automatically falls back to an isolated `chmod 0600` user-only credential file at `~/.config/noinsta/.device_credentials`. |

---

## 12. Running the Test Suite

Run unit and integration tests:

```bash
pytest -v
```
