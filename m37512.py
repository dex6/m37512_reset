#!/usr/bin/python3

import smbus  # pip3 install smbus-cffi
import struct
from collections import namedtuple

from pprint import pprint
from hexdump import hexdump as _hexdump
def h(it, hdr=''):
    for line in _hexdump(bytes(it), result='generator'):
        print(hdr + line)


_MemBlock = namedtuple('MemBlock', ['addr', 'length', 'offset'])

_memmap = {
        'B' : _MemBlock(0x1000, 0x0800, 0x0000),
        'A' : _MemBlock(0x1800, 0x0800, 0x0800),
        '3' : _MemBlock(0x4000, 0x4000, 0x1000),
        '2' : _MemBlock(0x8000, 0x4000, 0x5000),
        '1' : _MemBlock(0xC000, 0x2000, 0x9000),
        '0' : _MemBlock(0xE000, 0x2000, 0xB000),
}


class VerificationError(Exception):
    pass


class M37512_Flash:

    def __init__(self, i2c_bus, bat_addr=0x0B):
        self.bus = smbus.SMBus(i2c_bus)
        self.bat_addr = bat_addr

    def __read16B(self, addr):
        """Read 16 bytes from flash memory (one transaction)"""
        # 0xFF -> sets read address (data=[AddrLO, AddrHI]); 0xFE -> returns 16 bytes
        self.bus.write_block_data(self.bat_addr, 0xFF, list(struct.pack('<H', addr)))
        r = bytes(self.bus.read_block_data(self.bat_addr, 0xFE))
        assert len(r) == 16  # if this fails, SMBUS API of your chip is probably different...
        return r

    def __read_block(self, block):
        """Read complete flash memory block (without verification)"""
        addr, length = _memmap[block.upper()][0:2]
        d = bytearray(length)
        i = 0
        while i < length:
            d[i:i+16] = self.__read16B(addr+i)
            i += 16
        return d

    def read_block(self, block):
        """Read complete flash memory block (with verification)"""
        d1 = self.__read_block(block)
        d2 = self.__read_block(block)
        if d1 != d2:
            raise VerificationError
        h(d1)
        return d1





if __name__ == "__main__":
    pprint(_memmap)
    dev = M37512_Flash(5)
    dev.read_block('1')
