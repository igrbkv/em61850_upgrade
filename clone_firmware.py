#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Программа клонирует текущий файл прошивки, увеличивая
номер версии, меняя дату и контрольную сумму.
Файл состоит из двух частей одинаковой длины:
<дата1>
<версия 16-байт>
<crc32(дата1+версия) litle-endian 4-байта>
<дата2>
<версия 16-байт>
<crc32(дата2+версия) litle-endian 4-байта>

имя файла прошивки:
em_[sync_|adc_]firmware_2_2_2_20160804.bin


"""

import sys
import zlib
import shutil
import os
import struct
import time

DEBUG = True
SYNCFILESIZE = 786432
ADCFILESIZE = 524288


def crc32(fname, offset, size):
    crc = 0
    with open(fname, 'rb') as f:
        f.seek(offset, 0)
        bsize = 1024
        bytes_read = 0
        while bytes_read != size:
            if bsize > size - bytes_read:
                bsize = size - bytes_read
            buf = f.read(bsize)
            bytes_read = bytes_read + bsize
            crc = zlib.crc32(buf, crc)
    return crc


def unpack(vals):
    return struct.unpack('<3BI5B', vals)


def pack(vals):
    return struct.pack('<3BI5B', vals[0], vals[1], vals[2], vals[3], vals[4],
    vals[5], vals[6], vals[7], vals[8])


def increment(v):
    v = list(v)
    v[2] = v[2] + 1
    if v[2] > 255:
        v[2] = 0
        v[1] = v[1] + 1
        if v[1] > 255:
            v[1] = 0
            v[0] = v[0] + 1
            if v[0] > 255:
                raise BaseException('Version number is too big!')
    tm = time.localtime()
    v[3] = tm.tm_year * 10000 + tm.tm_mon * 100 + tm.tm_mday
    return v


def main():
    if len(sys.argv) < 2:
        print("usage:")
        print(sys.argv[0].split('/')[-1] + ' <firmware file>')
        return

    try:
        tmp_fn = '.clone.tmp'
        shutil.copyfile(sys.argv[1], tmp_fn)

        with open(tmp_fn, 'r+b') as f:
            fsize = f.seek(0, 2)
            if fsize < 512:
                raise BaseException('File too small!')
            prefix = ''
            if fsize == SYNCFILESIZE:
                prefix = 'sync_'
            elif fsize == ADCFILESIZE:
                prefix = 'adc_'

            half_fsize = int(fsize / 2)

            # first half
            f.seek(half_fsize - 16, 0)
            buf = f.read(12)
            last1 = unpack(buf)

            if DEBUG:
                print(last1)
                f.seek(half_fsize - 4, 0)
                buf = f.read(4)
                crc1 = struct.unpack('<I', buf)[0]
                print('internal crc', format(crc1, '08X'))
                print('my calc', format(crc32(tmp_fn, 0, half_fsize - 4), '08X'))

            new1 = increment(last1)
            f.seek(half_fsize - 16, 0)
            buf = pack(new1)
            f.write(buf)

            if DEBUG:
                f.seek(half_fsize - 16, 0)
                buf = f.read(12)
                new1 = unpack(buf)
                print(new1)

            crc1_new = crc32(tmp_fn, 0, half_fsize - 4)
            buf = struct.pack('<I', crc1_new)
            f.seek(half_fsize - 4, 0)
            f.write(buf)

            if DEBUG:
                f.seek(half_fsize - 4, 0)
                buf = f.read(4)
                crc1 = struct.unpack('<I', buf)[0]
                print('internal crc', format(crc1, '08X'))
                print('my calc', format(crc1_new, '08X'))

            # second half
            f.seek(fsize - 16, 0)
            buf = f.read(12)
            last1 = unpack(buf)

            if DEBUG:
                print(last1)
                f.seek(fsize - 4, 0)
                buf = f.read(4)
                crc1 = struct.unpack('<I', buf)[0]
                print('internal crc', format(crc1, '08X'))
                print('my calc', format(crc32(tmp_fn, half_fsize, half_fsize - 4), '08X'))

            new1 = increment(last1)
            f.seek(fsize - 16, 0)
            buf = pack(new1)
            f.write(buf)

            if DEBUG:
                f.seek(fsize - 16, 0)
                buf = f.read(12)
                new1 = unpack(buf)
                print(new1)

            crc1_new = crc32(tmp_fn, half_fsize, half_fsize - 4)
            buf = struct.pack('<I', crc1_new)
            f.seek(fsize - 4, 0)
            f.write(buf)

            if DEBUG:
                f.seek(fsize - 4, 0)
                buf = f.read(4)
                crc1 = struct.unpack('<I', buf)[0]
                print('internal crc', format(crc1, '08X'))
                print('my calc', format(crc1_new, '08X'))

        dst_fn = 'em_{}firmware_{}_{}_{}_{}.bin'.format(prefix, new1[0], new1[1], new1[2], new1[3])
        os.rename(tmp_fn, dst_fn)
        print(dst_fn)
    except IOError as e:
        print(e)
    except FileNotFoundError as e:
        print(e)
    except BaseException as e:
        print(e)
    finally:
        if os.access(tmp_fn, os.F_OK):
            os.unlink(tmp_fn)


if __name__ == '__main__':
    main()
