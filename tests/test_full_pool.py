# SPDX-License-Identifier: MIT
import binascii
import hashlib
import io
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X30, UC_ARM64_REG_PC
import full_pool as f


def make_wav(path, frames, rate=48000, channels=2, width=2):
    samples = (np.sin(np.arange(frames)*2*np.pi*440/rate)*10000).astype('<i2')
    if width == 2:
        raw = np.repeat(samples[:,None],channels,axis=1).tobytes()
    else:
        raw = bytes(frames*channels*width)
    with wave.open(str(path),'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(raw)
    return path


def fix_crc(data):
    data = bytearray(data)
    data[-2:] = binascii.crc_hqx(data[:-2],0).to_bytes(2,'big')
    return bytes(data)


class AudioAndThunkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_original_converter_is_unchanged(self):
        self.assertEqual(f.digest(f.UPSTREAM.read_bytes()),f.UPSTREAM_SHA256)

    def test_new_arm_thunk_returns_full_32bit_pool_length(self):
        # Only executes new, project-authored instructions; contains no Nikon code.
        uc = Uc(UC_ARCH_ARM64,UC_MODE_ARM)
        uc.mem_map(0x1000,0x1000)
        uc.mem_write(0x1000,f.length_thunk())
        uc.reg_write(UC_ARM64_REG_X30,0x1800)
        uc.emu_start(0x1000,0x1800,count=20)
        self.assertEqual(uc.reg_read(UC_ARM64_REG_PC),0x1800)
        self.assertEqual(uc.reg_read(UC_ARM64_REG_X0),261120)
        self.assertNotEqual(uc.reg_read(UC_ARM64_REG_X0),261120 & 65535)

    def test_short_sources_pad_to_full_pool_without_speed_change(self):
        for frames in (1,16320,59392):
            with self.subTest(frames=frames):
                wav = make_wav(self.root/f'{frames}.wav',frames)
                original = wav.read_bytes()
                pcm,info = f.prepare_wav(wav)
                self.assertEqual(len(pcm),261120)
                self.assertEqual(info['output_duration_ms'],1360)
                self.assertEqual(info['source_frames'],frames)
                self.assertEqual(info['zero_padding_frames'],65280-frames)
                self.assertEqual(pcm[frames*4:],bytes((65280-frames)*4))
                self.assertEqual(wav.read_bytes(),original)
                self.assertFalse(info['cropped'])
                self.assertEqual(info['speed'],1.0)

    def test_exact_1360ms_is_accepted(self):
        pcm,info = f.prepare_wav(make_wav(self.root/'full.wav',65280))
        self.assertEqual(len(pcm),261120)
        self.assertEqual(info['zero_padding_frames'],0)
        self.assertEqual(pcm[-4:],bytes(4))

    def test_overlong_audio_is_rejected_without_changing_source(self):
        wav = make_wav(self.root/'long.wav',65281)
        original = wav.read_bytes()
        with self.assertRaisesRegex(ValueError,'no automatic cropping'):
            f.prepare_wav(wav)
        self.assertEqual(wav.read_bytes(),original)

    def test_empty_and_wrong_formats_are_rejected(self):
        for frames,rate,channels,width in [(0,48000,2,2),(48,44100,2,2),(48,48000,1,2),(48,48000,2,1)]:
            with self.subTest(parameters=(frames,rate,channels,width)):
                wav = make_wav(self.root/'bad.wav',frames,rate,channels,width)
                with self.assertRaises(ValueError):
                    f.prepare_wav(wav)

    def test_truncated_wav_is_rejected(self):
        wav = make_wav(self.root/'truncated.wav',16)
        data = bytearray(wav.read_bytes())
        struct.pack_into('<I',data,40,128)  # Claims more data than the file contains.
        wav.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'Truncated'):
            f.prepare_wav(wav)

    def test_exported_preview_has_exact_pool_duration(self):
        data = f.export_wav(bytes(261120))
        with wave.open(io.BytesIO(data),'rb') as w:
            self.assertEqual((w.getframerate(),w.getnchannels(),w.getsampwidth(),w.getnframes()),(48000,2,2,65280))

    def test_existing_output_is_never_overwritten(self):
        directory = self.root/'existing'
        directory.mkdir()
        keep = directory/'keep.txt'
        keep.write_text('keep')
        with self.assertRaisesRegex(ValueError,'already exists'):
            f.build('missing-stock','missing-wav',directory)
        self.assertEqual(keep.read_text(),'keep')


class SyntheticByteScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Synthetic zero fixture generated here, NOT a Nikon firmware dump.
        # The test-only expected hash is patched below. Production keeps its exact stock hash.
        cls.stock = bytes(f.EG_BYTES)
        cls.pcm = bytes(261120)
        cls.fixture_hash = f.digest(cls.stock)

    def setUp(self):
        self.hash_patch = patch.object(f,'STOCK_SHA256',self.fixture_hash)
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)

    def test_unrelated_base_feature_bytes_are_preserved(self):
        base = bytearray(self.stock)
        base[0x1000:0x1008] = b'FEATURE!'
        base = fix_crc(base)
        candidate = f.apply_patch(self.stock,base,self.pcm)
        self.assertEqual(candidate[0x1000:0x1008],b'FEATURE!')
        self.assertEqual(binascii.crc_hqx(candidate,0),0)
        self.assertEqual(len(candidate),f.EG_BYTES)
        self.assertEqual(struct.unpack_from('<Q',candidate,0x43FB7DF0-f.BASE)[0],0x40E347A0)

    def test_preexisting_sound_patch_is_rejected(self):
        for address in (0x40E347B4,0x40E34920,0x43FB7DF0,0x43FBB850):
            with self.subTest(address=hex(address)):
                base = bytearray(self.stock)
                base[address-f.BASE] ^= 1
                with self.assertRaisesRegex(ValueError,'sound subsystem'):
                    f.apply_patch(self.stock,fix_crc(base),self.pcm)

    def test_unlisted_change_is_detected_even_with_valid_crc(self):
        candidate = bytearray(f.apply_patch(self.stock,self.stock,self.pcm))
        candidate[0x2000] ^= 1
        with self.assertRaisesRegex(ValueError,'outside declared'):
            f.verify_bytes(self.stock,self.stock,fix_crc(candidate),self.pcm)

    def test_invalid_crc_is_detected(self):
        candidate = bytearray(f.apply_patch(self.stock,self.stock,self.pcm))
        candidate[-1] ^= 1
        with self.assertRaisesRegex(ValueError,'CRC'):
            f.verify_bytes(self.stock,self.stock,bytes(candidate),self.pcm)

    def test_unknown_stock_is_rejected(self):
        candidate = bytearray(self.stock)
        candidate[0x100] = 1
        with self.assertRaisesRegex(ValueError,'Exact original'):
            f.check_stock(fix_crc(candidate))


@unittest.skipUnless(os.environ.get('Z8_STOCK_EG'),'Private integration requires user-supplied Z8_STOCK_EG')
class PrivateFirmwareIntegration(unittest.TestCase):
    def test_actual_stock_instructions_rebuild_full_pool_and_routes(self):
        from arm_audit import audit
        stock = f.read_eg(os.environ['Z8_STOCK_EG'])
        f.check_stock(stock)
        with tempfile.TemporaryDirectory() as directory:
            wav = make_wav(Path(directory)/'synthetic-1237.wav',59392)
            pcm,info = f.prepare_wav(wav)
            candidate = f.apply_patch(stock,stock,pcm)
            result = audit(stock,candidate,pcm)
        self.assertTrue(result['full_pcm_ram_match'])
        self.assertEqual(result['routes'][0]['bytes'],261120)
        self.assertEqual(result['routes'][1]['bytes'],261120)
        self.assertEqual(len(result['cap_checks']),15)
        self.assertTrue(result['frame_count_minus_one_fits_u16'])


if __name__ == '__main__':
    unittest.main()
