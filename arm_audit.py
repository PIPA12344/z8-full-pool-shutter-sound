# SPDX-License-Identifier: MIT
# Copyright (c) 2026 PIPA12344
"""Bounded execution of user-supplied Z8 ARM64 audio routines.

No camera peripherals, RTOS scheduling, DMA, or speaker behavior is emulated.
Does not import the experimental builder or its patch definitions.
"""
import binascii
import hashlib
import struct

import numpy as np
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm64_const import (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2,
    UC_ARM64_REG_W0, UC_ARM64_REG_W3, UC_ARM64_REG_X20, UC_ARM64_REG_SP,
    UC_ARM64_REG_X30, UC_ARM64_REG_PC)

BASE = 0x40160000


def need(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def retired_references(stock):
    """Bounded static reference check, not proof against arbitrary computed pointers."""
    target, end = 0x40E347B4, 0x40E347C8
    words = np.frombuffer(stock[:len(stock)//4*4], dtype='<u4')
    ix = np.flatnonzero((words & 0x7C000000) == 0x14000000)
    imm = (words[ix] & 0x3FFFFFF).astype(np.int64)
    imm = np.where(imm & (1 << 25), imm - (1 << 26), imm)
    destinations = BASE + ix * 4 + imm * 4
    direct = [hex(BASE + int(i)*4) for i in ix[(destinations >= target) & (destinations < end)]]
    need(not direct, 'Retired address getter has direct branch references: ' + str(direct))
    positions, at = [], 0
    pattern = struct.pack('<Q', target)
    while True:
        at = stock.find(pattern, at)
        if at < 0:
            break
        positions.append(BASE + at)
        at += 1
    need(positions == [0x43FB7DF0], 'Unexpected literal references to retired getter')
    return dict(direct_branch_refs=direct, literal_pointer_refs=[hex(p) for p in positions],
                sole_literal_reference_replaced=True,
                scope='B/BL targets and literal 64-bit pointers; arbitrary computed references not proven absent')


class ArmAudio:
    def __init__(self, eg):
        self.uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.uc.mem_map(BASE, (len(eg) + 4095) & ~4095)
        self.uc.mem_write(BASE, eg)
        self.uc.mem_map(0xA15C00000, 0x80000)
        self.uc.mem_map(0xA038F0000, 0x20000)
        self.uc.mem_map(0x20000000, 0x100000)
        self.stack = 0x200F0000
        self.stop = 0x20000000
        self.uc.reg_write(UC_ARM64_REG_SP, self.stack)
        self.copies = []
        self.hook = self.uc.hook_add(UC_HOOK_CODE, self._hook)

    def _hook(self, uc, address, size, user):
        if address == 0x40CA9AA0:
            destination = uc.reg_read(UC_ARM64_REG_X1)
            source = uc.reg_read(UC_ARM64_REG_X2)
            count = uc.reg_read(UC_ARM64_REG_W3)
            need(0 < count <= 28800, 'Unexpected initialization copy size')
            need(0xA15C00000 <= destination and destination + count <= 0xA15C80000,
                 'Initialization copy outside mapped resource RAM')
            data = bytes(uc.mem_read(source, count))
            uc.mem_write(destination, data)
            self.copies.append((source, destination, count))
            uc.reg_write(UC_ARM64_REG_X0, 0)
            uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_X30))

    def execute(self, start, end, count=2000):
        self.uc.emu_start(start, end, count=count)
        need(self.uc.reg_read(UC_ARM64_REG_PC) == end, 'ARM routine did not reach expected stop')

    def call(self, address, argument):
        self.uc.reg_write(UC_ARM64_REG_X0, argument)
        self.uc.reg_write(UC_ARM64_REG_X30, self.stop)
        self.uc.reg_write(UC_ARM64_REG_SP, self.stack)
        self.execute(address, self.stop, 300)
        return self.uc.reg_read(UC_ARM64_REG_X0)

    def initialize_resources(self):
        self.uc.reg_write(UC_ARM64_REG_X0, 1)
        self.execute(0x40E342E4, 0x40E34608)
        need(len(self.copies) == 18, 'Expected 18 original ROM-to-RAM copies')
        rows = self.copies[2:]
        need(len(rows) == 16, 'Expected four resource segments per B/C/D/E type')
        rom, ram = 0x43FBB850, 0xA15C1B200
        for i, (source, destination, count) in enumerate(rows):
            need((source, destination, count) == (rom, ram, (28800, 9600, 19200, 7680)[i % 4]),
                 'B/C/D/E pool is not contiguous with the expected mapping')
            rom += count
            ram += count
        need(rom == 0x43FFB450 and ram == 0xA15C5AE00, 'Unexpected end of pooled resources')
        return [dict(rom=hex(s), ram=hex(d), bytes=n) for s, d, n in self.copies]

    def cap_result(self, byte_count, cap, start, stop, offset):
        state = 0x20010000
        self.uc.reg_write(UC_ARM64_REG_SP, self.stack)
        self.uc.reg_write(UC_ARM64_REG_X20, state)
        self.uc.reg_write(UC_ARM64_REG_W0, byte_count)
        self.uc.mem_write(state + 0x24, struct.pack('<I', cap))
        self.uc.mem_write(self.stack, bytes(64))
        self.execute(start, stop, 100)
        return struct.unpack('<I', self.uc.mem_read(self.stack + offset, 4))[0]


def audit(stock, candidate, pcm):
    need(len(candidate) == 81807711 and binascii.crc_hqx(candidate, 0) == 0, 'Invalid experimental EG')
    need(len(pcm) == 261120, 'Invalid extended audio length')
    need(candidate[0x40E342E4-BASE:0x40E34608-BASE] == stock[0x40E342E4-BASE:0x40E34608-BASE],
         'Original initialization instructions were changed')
    refs = retired_references(stock)
    arm = ArmAudio(candidate)
    copies = arm.initialize_resources()
    restored = bytes(arm.uc.mem_read(0xA15C1B200, len(pcm)))
    need(restored == pcm, 'Actual ARM initialization did not reconstruct the entire PCM stream')
    need(bytes(arm.uc.mem_read(0xA15C1B200 + len(pcm), 261120-len(pcm))) == bytes(261120-len(pcm)),
         'Unused pool tail is not silent')
    routes = []
    for kind in range(10, 26):
        address = arm.call(0x40E3469C, kind)
        length = arm.call(0x40E348F4, kind)
        need(0xA15C1B200 <= address and address + length <= 0xA15C5AE00,
             f'kind {kind}: out-of-pool address or length')
        if kind in (10, 11):
            need(address == 0xA15C1B200 and length == len(pcm), 'B-main/front route does not use full PCM')
        else:
            need(length == (19200 if kind % 4 == 0 else 7680 if kind % 4 == 1 else
                             28800 if kind % 4 == 2 else 9600), 'Unexpected shared getter length change')
        routes.append(dict(kind=kind, address=hex(address), bytes=length, duration_ms=length/192))
    # Execute all three original, different cap-handling instruction sequences.
    caps = []
    for start, stop, offset in [(0x40E34FB0, 0x40E34FEC, 16),
                                (0x40E350C8, 0x40E35104, 8),
                                (0x40E35168, 0x40E351A4, 8)]:
        for cap in (0, 66, 340, 1000, 2000):
            submitted = arm.cap_result(len(pcm), cap, start, stop, offset)
            expected = len(pcm) if not cap else min(len(pcm), cap * 192)
            need(submitted == expected, 'Original cap path truncated or wrapped unexpectedly')
            caps.append(dict(path=hex(start), cap_ms=cap, submitted_bytes=submitted))
    return dict(status='PASS_BOUNDED_ARM_ROUTINES', actual_original_init_copy_calls=18,
                pcm_reconstructed_in_ram_sha256=sha(restored), full_pcm_ram_match=True,
                resource_copy_mapping=copies, routes=routes, cap_checks=caps, retired_getter_references=refs,
                stereo_frames=len(pcm)//4, frame_count_minus_one=len(pcm)//4-1,
                frame_count_minus_one_fits_u16=(0 <= len(pcm)//4-1 <= 65535),
                abstraction='Unicorn executes actual ARM64 routines; copy API modeled as bounded memcpy',
                scope='No RTOS boot, audio DMA, physical timing, speaker output, or camera test')
