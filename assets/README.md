# NoInsta Media Assets

This directory contains local media assets used by the NoInsta laptop client for productivity interventions.

## Default Assets

- `alert.png`: Default high-contrast warning graphic displayed when Instagram is opened.
- `alert.wav`: Default synthesized alert sound tone (16-bit 44.1kHz mono WAV).

## Supported Formats

### Images
- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- WebP (`.webp`)

### Audio
- MP3 (`.mp3`)
- WAV (`.wav`)
- OGG (`.ogg`)

### Video
- MP4 (`.mp4`)
- WebM (`.webm`)

## Custom Media Configuration

You can customize the media without modifying any code. Edit your `config.json` (located at `~/.config/noinsta/config.json` on Linux or `%APPDATA%\NoInsta\config.json` on Windows):

```json
{
  "media": {
    "image_path": "assets/alert.png",
    "video_path": "/path/to/custom_video.mp4",
    "audio_path": "assets/alert.wav",
    "loop_video": true,
    "loop_audio": true
  }
}
```

- When `video_path` is configured and points to an existing file, it takes precedence and is displayed in the intervention window.
- When `video_path` is null or missing, `image_path` is displayed.
- If media files are missing, NoInsta falls back gracefully to a high-visibility text warning banner and silent mode without crashing.
