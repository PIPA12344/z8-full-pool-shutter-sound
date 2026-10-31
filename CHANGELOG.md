# Changelog

## 0.1.0-alpha.1 — 2026-11-01

- Publish the B/C/D/E shared-pool extension based on South-Bridge's MIT-licensed work.
- B main/front request all 261120 bytes / 1360ms, independent of an example clip.
- Accept 1..65280 frames of PCM16 stereo 48kHz WAV; pad short input and reject overlong input.
- Preserve the pinned converter and attribution; separate the new patch logic explicitly.
- Add byte/CRC guards, bounded ARM execution, public synthetic and private opt-in tests.
- Source/docs only: no firmware, audio, card images, or flash automation.
- Full emulator boot, DMA/speaker output, real camera behavior and recovery remain unverified.
