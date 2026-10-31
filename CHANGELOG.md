# Changelog

## Validation update — 2026-11-01

- Record maintainer-reported completion of QEMU boot, real-camera installation and shutter-sound playback.
- Keep the reported scope separate from unrecorded modes, exact playback duration, internal DMA timing and recovery guarantees.

## 0.1.0-alpha.1 — 2026-11-01

- Publish the B/C/D/E shared-pool extension based on South-Bridge's MIT-licensed work.
- B main/front request all 261120 bytes / 1360ms, independent of an example clip.
- Accept 1..65280 frames of PCM16 stereo 48kHz WAV; pad short input and reject overlong input.
- Preserve the pinned converter and attribution; separate the new patch logic explicitly.
- Add byte/CRC guards, bounded ARM execution, public synthetic and private opt-in tests.
- Source/docs only: no firmware, audio, card images, or flash automation.
- At initial publication, full emulator boot and real-camera behavior were unverified; see the validation update above and docs/VALIDATION.md for current progress. Internal DMA timing and recovery are not established by the reported tests.
