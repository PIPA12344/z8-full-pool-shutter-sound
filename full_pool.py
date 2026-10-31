# SPDX-License-Identifier: MIT
# Copyright (c) 2026 PIPA12344
"""Experimental Z8 C3.11 full-pool shutter sound, derived from South-Bridge's research.

B is the full-sound entry. B/C/D/E share one 261120-byte pool, not four voices.
Only user-supplied EG modules are read/written. No camera or card access.
"""
import argparse
import binascii
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import struct
import wave

VERSION = '0.1.0-alpha.1'
ROOT = Path(__file__).resolve().parent
BASE = 0x40160000
EG_BYTES = 81807711
STOCK_SHA256 = 'f85e0138e2f5e660ece8560de62e0d12cb795e0e14983e50f20b61dce906c46c'
POOL_ROM, POOL_RAM, POOL_BYTES = 0x43FBB850, 0xA15C1B200, 261120
POOL_FRAMES, POOL_MS = 65280, 1360
THUNK = 0x40E347B4
UPSTREAM_COMMIT = '6bfbb01c95859d490e1135e7d2927a2fbc619642'
UPSTREAM_SHA256 = '10901a486629419de22d2e62eb9731c9ca948aee8f9af6c9d8fc1eb60dab9577'
UPSTREAM = ROOT / 'third_party/south_bridge/build_custom_sound.py'


def need(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check_stock(data):
    need(len(data) == EG_BYTES and digest(data) == STOCK_SHA256,
         'Exact original Nikon Z8 C3.11 EG required (with its 2-byte CRC); not an update package or QEMU MAIN.')
    need(binascii.crc_hqx(data, 0) == 0, 'Original EG CRC mismatch')


def read_eg(path):
    path = Path(path)
    need(path.is_file() and path.stat().st_size == EG_BYTES, 'EG must contain exactly 81807711 bytes')
    data = path.read_bytes()
    need(len(data) == EG_BYTES and binascii.crc_hqx(data, 0) == 0, 'EG length or CRC mismatch')
    return data


def upstream_converter():
    need(digest(UPSTREAM.read_bytes()) == UPSTREAM_SHA256, 'Pinned South-Bridge script was changed')
    spec = importlib.util.spec_from_file_location('_south_bridge_original', UPSTREAM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_wav(path):
    path = Path(path)
    need(path.is_file() and 0 < path.stat().st_size <= 64 * 1024 * 1024, 'Invalid or oversized WAV file')
    source = path.read_bytes()
    with wave.open(io.BytesIO(source), 'rb') as w:
        need((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype()) == (2, 2, 48000, 'NONE'),
             'Use 48000 Hz, stereo, PCM16 WAV; convert explicitly before building')
        frames = w.getnframes()
        need(1 <= frames <= POOL_FRAMES, 'WAV must contain 1..65280 frames (up to 1360ms); no automatic cropping')
        need(len(w.readframes(frames)) == frames * 4, 'Truncated WAV payload')
    # Unmodified upstream conversion, with the FULL pool frame count.
    # It pads short sources, fades the final 20ms of the pool, and normalizes to 84% peak.
    pcm = upstream_converter().load_wav(path, POOL_FRAMES).tobytes()
    need(len(pcm) == POOL_BYTES, 'Unexpected PCM output size')
    need(digest(path.read_bytes()) == digest(source), 'Source WAV changed during conversion')
    return pcm, dict(source_sha256=digest(source), source_frames=frames,
                     source_duration_ms=frames / 48, output_frames=POOL_FRAMES,
                     output_duration_ms=POOL_MS, zero_padding_frames=POOL_FRAMES-frames,
                     cropped=False, speed=1.0, pcm_sha256=digest(pcm),
                     format='48000Hz/stereo/PCM16', converter_sha256=UPSTREAM_SHA256)


def export_wav(pcm):
    target = io.BytesIO()
    with wave.open(target, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(pcm)
    return target.getvalue()


def length_thunk():
    # Author-written AArch64: MOVZ W0,low16; MOVK W0,high16,LSL#16; RET; NOP; NOP.
    return struct.pack('<5I', 0x52800000 | ((POOL_BYTES & 0xFFFF) << 5),
                       0x72A00000 | ((POOL_BYTES >> 16) << 5),
                       0xD65F03C0, 0xD503201F, 0xD503201F)


def patch_windows(pcm):
    need(len(pcm) == POOL_BYTES, 'A full 261120-byte pool is required')
    return [
        (0x40E347B4-BASE, length_thunk(), 'private 32-bit B length getter'),
        (0x43FB7DF0-BASE, struct.pack('<Q', 0x40E347A0), 'B-front uses B-main start address'),
        (0x43FB7EB8-BASE, struct.pack('<Q', THUNK), 'B-main length table'),
        (0x43FB7EC0-BASE, struct.pack('<Q', THUNK), 'B-front length table'),
        (POOL_ROM-BASE, pcm, 'replace pooled B/C/D/E PCM'),
    ]


def apply_patch(stock, base, pcm):
    check_stock(stock)
    need(len(base) == EG_BYTES and binascii.crc_hqx(base, 0) == 0, 'Invalid base EG')
    # A clean four-feature EG can be supplied separately, but its sound implementation
    # and initialization must still match stock. Patched 0409/0410 inputs are rejected.
    guards = [(0x40E342E4, 0x40E34608), (0x40E3469C, 0x40E349F8),
              (0x43FB7DA0, 0x43FB7F40), (0x43FBB850, 0x43FFB450)]
    for start, stop in guards:
        need(base[start-BASE:stop-BASE] == stock[start-BASE:stop-BASE],
             'Base EG already changes the sound subsystem; rebuild a clean base from stock')
    edits = patch_windows(pcm)
    result = bytearray(base)
    for offset, payload, _ in edits:
        result[offset:offset+len(payload)] = payload
    result[-2:] = binascii.crc_hqx(result[:-2], 0).to_bytes(2, 'big')
    result = bytes(result)
    verify_bytes(stock, base, result, pcm)
    return result


def verify_bytes(stock, base, candidate, pcm):
    check_stock(stock)
    need(len(base) == len(candidate) == EG_BYTES, 'EG length changed')
    need(binascii.crc_hqx(base, 0) == 0 and binascii.crc_hqx(candidate, 0) == 0, 'EG CRC mismatch')
    edits = patch_windows(pcm)
    windows = []
    for offset, payload, _ in edits:
        need(candidate[offset:offset+len(payload)] == payload, 'Declared patch payload mismatch')
        windows.append((offset, offset+len(payload)))
    windows.append((EG_BYTES-2, EG_BYTES))
    previous = 0
    for start, stop in sorted(windows):
        need(previous <= start and base[previous:start] == candidate[previous:start],
             'Overlapping patch or change outside declared windows')
        previous = stop
    need(base[previous:] == candidate[previous:], 'Unexpected trailing changes')
    return dict(status='PASS_BYTE_SCOPE_AND_CRC', base_sha256=digest(base),
                eg_sha256=digest(candidate), output_bytes=EG_BYTES,
                all_bytes_outside_declared_windows_preserved=True)


def build(stock_path, wav_path, output, base_path=None):
    output = Path(output)
    need(not output.exists(), 'Output directory already exists; no files will be overwritten')
    stock = read_eg(stock_path)
    check_stock(stock)
    base = read_eg(base_path) if base_path else stock
    pcm, audio = prepare_wav(wav_path)
    candidate = apply_patch(stock, base, pcm)
    byte_proof = verify_bytes(stock, base, candidate, pcm)
    from arm_audit import audit
    arm_proof = audit(stock, candidate, pcm)
    # Only create output after every in-memory check has succeeded.
    output.mkdir(parents=True, exist_ok=False)
    artifacts = {'patched-eg.bi':candidate, 'modified-main.bi':candidate[:-2], 'preview.wav':export_wav(pcm)}
    for name, data in artifacts.items():
        with (output/name).open('xb') as f:
            f.write(data)
        need(digest((output/name).read_bytes()) == digest(data), 'Output readback mismatch: ' + name)
    report = dict(schema=1, tool_version=VERSION, created_at=datetime.now(timezone.utc).isoformat(),
                  status='EXPERIMENTAL_BYTE_AND_BOUNDED_ARM_CHECKS_PASSED',
                  input_stock_sha256=digest(stock), base_sha256=digest(base),
                  audio=audio, playback_entry='B', borrowed_types=['B','C','D','E'],
                  donor_type_behavior='C/D/E retain short routes into the overwritten pool; fragments or silence',
                  requested_playback_ms=POOL_MS, source_audio_ms=audio['source_duration_ms'],
                  outputs={name:dict(bytes=len(data),sha256=digest(data)) for name,data in artifacts.items()},
                  byte_verification=byte_proof, arm_verification=arm_proof,
                  upstream=dict(repository='South-Bridge/z8-custom-shutter-sound', commit=UPSTREAM_COMMIT,
                                script_sha256=UPSTREAM_SHA256, license='MIT'),
                  patch_implementation='PIPA12344 experimental full-pool extension; not upstream-approved',
                  version_fields_changed=False, full_update_package_generated=False,
                  full_camera_emulator_tested=False, real_camera_tested=False,
                  limitations=['C3.11 layout only', 'Not four independent voices',
                               'Existing cap and shutter-event interruptions remain',
                               'No audio DMA/speaker verification; no promise of recoverability'])
    (output/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'SHA256SUMS.txt').write_text(''.join(digest(data)+'  '+name+'\n' for name,data in artifacts.items()),encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stock-eg', type=Path, required=True, help='Exact stock C3.11 EG including CRC')
    ap.add_argument('--base-eg', type=Path, help='Optional clean feature-patched EG with original sound subsystem')
    ap.add_argument('--wav', type=Path, required=True, help='PCM16 stereo 48kHz WAV, at most 1360ms')
    ap.add_argument('--out', type=Path, required=True, help='New local output directory')
    args = ap.parse_args()
    try:
        result = build(args.stock_eg,args.wav,args.out,args.base_eg)
    except (ValueError,OSError,wave.Error,EOFError) as exc:
        raise SystemExit('ERROR: '+str(exc)) from exc
    print(json.dumps(dict(status=result['status'],requested_playback_ms=POOL_MS,
                          source_audio_ms=result['source_audio_ms'],outputs=result['outputs']),indent=2))


if __name__ == '__main__':
    main()
