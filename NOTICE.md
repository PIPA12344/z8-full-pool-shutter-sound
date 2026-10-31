# Attribution and scope

This is a derivative research tool built on **South-Bridge's Nikon Z8 Custom Shutter Sound**:
https://github.com/South-Bridge/z8-custom-shutter-sound

Reference commit: 6bfbb01c95859d490e1135e7d2927a2fbc619642.

South-Bridge and the original contributors established the PCM resource mapping, kind dispatch,
initialization-copy mechanism, and original 340ms modification. Their documentation credits S3 /
s3lemming for resource-length and kind-dispatch insights. Those contributions remain credited here.

The original MIT-licensed script is vendored unchanged at third_party/south_bridge/build_custom_sound.py,
with its complete license and notice at third_party/south_bridge/LICENSE. Its load_wav routine is
called verbatim with the full pool frame count, and its SHA256 is verified before use.

The **new experimental extension by PIPA12344** pools the existing B/C/D/E resources, redirects the
B main/front entries, repurposes a retired 20-byte getter as a private 32-bit length thunk, requests
all 261120 bytes / 1360ms, adds bounded ARM execution and byte-scope verification, and rejects
incompatible or overlong input. These changes are not the upstream author's original patch and
have not been approved or warranted by that author. The original standalone script remains unchanged.

Original project research links:
- https://github.com/South-Bridge/z8-custom-shutter-sound/blob/main/docs/mechanism.md
- https://github.com/South-Bridge/z8-custom-shutter-sound/blob/main/docs/open-questions.md
- https://github.com/South-Bridge/z8-custom-shutter-sound/blob/main/docs/experiments.md

Related projects (references only, not vendored):
- https://github.com/RdWing/z8-qemu — camera firmware emulation
- https://github.com/XinmiaoZhao/NikonFirmwarePatch — separate firmware packaging/features toolkit

This repository does not contain Nikon firmware, extracted modules, original machine-code dumps,
complete update packages, calibration data, card images, audio assets, credentials, or decryption keys.
Public tests use generated synthetic data. Real-firmware integration tests require private user input.
Project-authored patch instruction encoders are source code, not extracted firmware payloads.

This project does not redistribute the related feature toolkit's GPL code or patches. Third-party
Python dependencies are installed separately and retain their own licenses. The MIT license on this
project does not relicense Nikon firmware, third-party projects, or user-provided audio.

Nikon and Z8 are trademarks of Nikon Corporation. This project is not affiliated with, endorsed by,
or supported by Nikon Corporation. No compatibility, hardware safety, playback, rollback, recovery,
or legal-compliance guarantee is made. The license's warranty terms apply; see docs/RISKS.md.
