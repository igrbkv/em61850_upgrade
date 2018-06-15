#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from binascii import crc32, b2a_hex
import socket
import struct

class Tlv:
    def make_tlv(self, tag, val):
        b = bytearray(tag)
        if len(val) < 127:
            b += bytes([len(val)])
        else:
            sz = len(val)
            i = 0
            while int(sz):
                sz /= 256
                i += 1
            sz = i
            b += bytes([0x80 + sz])
            for i in range(sz):
                b += bytes([len(val) >> ((sz - 1 - i) * 8) & 0xff])
        return b + val

    def break_tlv(self, data):
        sz = 0
        tag = bytes([data[0]])
        if data[1] & 0x80:
            # FIXME !!!
            sz_len = (data[1] & 0x7f)
            sz = data[2]
            for i in range(1, sz_len):
                sz = sz << 8 + data[2 + i]
            value = data[sz_len + 2: sz_len + 2 + sz]
        else:
            sz = 1
            value = bytes(data[2: 2 + data[1]])
        return tag, value


class Packet(Tlv):
    def __init__(self):
        self.count = 0

    def encode(self, tlv):
        self.count += 1
        arr = self.count.to_bytes(2, 'big')
        tlv = arr + tlv
        tlv = self.make_tlv([0x80], tlv + crc32(tlv).to_bytes(4, 'big'))
        return self._stuff(tlv)

    def decode(self, data):
        return self._unstuff(data)

    def _stuff(self, tlv):
        ba = bytearray()
        ba += bytes([0xC0])
        for b in tlv:
            if b == 0xC0:
                ba += bytes([0xDB, 0xDC])
            elif b == 0xDB:
                ba += bytes([0xDB, 0xDD])
            else:
                ba += bytes([b])
        ba += bytes([0xC0])
        return ba

    def _unstuff(self, data):
        ba = bytearray()
        db = False
        for b in data:
            if b == 0xC0:
                db = False
                continue
            elif b == 0xDB:
                db = True
                continue
            elif b == 0xDC and db:
                ba += bytes([0xC0])
                db = False
            elif b == 0xDD and db:
                ba += bytes([0xDB])
                db = False
            else:
                if db:
                    ba += bytes([0xDB])
                    db = False
                ba += bytes([b])
        return ba


class TlvClient(Packet):
    sock = None
    host = '192.168.0.3'
    port = 1234
    value = bytearray()
    debug = 0 

    def _reopen_socket(self):
        if self.sock:
            self.sock.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5.0)


    def send_recv_tlv(self, tag, data):
        tlv = self.make_tlv(tag, data)
        # print(b2a_hex(tlv))
        msg = self.encode(tlv)
        if self.debug:
            print('To send: ', b2a_hex(msg))
        try:
            self._reopen_socket()
            self.sock.sendto(msg, (self.host, self.port))
        except socket.timeout:
            raise NameError('Таймаут передачи')

        if self.debug:
            print('Server reply :')
        for i in range(100):
            try:
                reply = self.sock.recv(4096)
            except socket.timeout:
                raise NameError('Таймаут ответа')
            if self.debug:
                print(b2a_hex(reply))
            reply = self.decode(bytes(reply))
            if self.debug:
                print(b2a_hex(reply))
            rtag, value = self.break_tlv(reply)
            if rtag[0] != 0x81:
                raise NameError('Неизвестный тег ответа ' + b2a_hex(tag).decode())
            # strip packet order number and crc
            rtag, value = self.break_tlv(bytes(value[2:-4]))
            if rtag == tag or rtag[0] in (0x31, 0x32):
                if self.debug:
                    print('tag=', b2a_hex(rtag), ' value=', b2a_hex(value))
                return rtag, value
        raise NameError('Неизвестный ответ')

class Sync(TlvClient):
    def _check_result(self, tag, value, err='Команда не выполнена'):
        if tag[0] == 0x32:
            if value[0] != 1:
                raise NameError(err)
        else:
            raise NameError('Неверный ответ')

    def set_devmode(self, mode):
        cmd_name = 'Установка режима работы платы синхронизации:'
        try:
            data = bytearray()
            mode = int(mode)
            data += mode.to_bytes(1, 'little')

            tag, value = self.send_recv_tlv(bytes([0xC8]), data)
            self._check_result(tag, value)

        except NameError as e:
            print(cmd_name, e)
        except:
            print(cmd_name, 'Неизвестная ошибка')
        else:
            return True
        return False

    def upgrade(self, rest):
        # FIXME not tested
        try:
            cmd_name = 'Обновление прошивки:'
            sz = path.getsize(rest)
            if sz != 768 * 1024:
                raise NameError('Неверный размер файла прошивки ' + sz)
            if self.debug:
                print('read device mode ...')
            tag, value = self.send_recv_tlv(bytes([0xC7]), bytes())
            mod = int(value[0])
            if mod == 0xFF:
                raise NameError('Плата уже в режиме обновления!')
            if mod == 0xFE:
                # service mode
                if self.debug:
                    print('clear all firmware ...')
                tag, value = self.send_recv_tlv(bytes([0xF4]), bytes([0]))
                self._check_result(tag, value, 'Ошибка очистки памяти')
                self.send_recv_tlv(bytes([0xF3]), bytes([0]))

            # reset last upgrade
            if self.debug:
                print('clear last firmware ...')
            tag, value = self.send_recv_tlv(bytes([0xF1]), bytes([0]))
            self._check_result(tag, value, 'Ошибка сброса прошивки!')
            i = 0
            if self.debug:
                print('write firmware ...')
            with open(rest, 'rb') as fw:
                buf = fw.read(1024)
                while buf:
                    tag, value = self.send_recv_tlv(bytes([0xF2]), buf)
                    self._check_result(tag, value, 'Ошибка записи прошивки!')
                    buf = fw.read(1024)
                    if self.debug:
                        print(i)
                    i += 1

            if self.debug:
                print('reset device ...')
            try:
                tag, value = self.send_recv_tlv(bytes([0xF3]), bytes([0]))
            except:
                # did not answer
                pass

        except FileNotFoundError as e:
            print(cmd_name, e)
        except NameError as e:
            print(cmd_name, e)
        except:
            print(cmd_name, 'Неизвестная ошибка')
        else:
            return True
        return False

    def set_output(self, rest):
        '''
        set_output (<N> <output-mode> <frequency Hz> <impulse duration s> <pulse delay s>)
        '''
        mode = ('off', 'off', 'active', 'active and inversion')
        cmd_name = 'Задание параметров выхода '
        try:
            rest = rest.split()
            data = bytearray()

            num = int(rest[0])
            mod = int(rest[1])
            freq = float(rest[2])
            dur = float(rest[3])
            delay = float(rest[4])
            if num not in range(1, 5):
                raise NameError('Неверный номер выхода ' + rest[0])
            cmd_name = cmd_name + str(num) 
            if mod not in range(0, len(mode)):
                raise NameError('Неверный режим ' + mod)
            if freq < 0.:
                raise NameError('Неверная частота ' + freq)
            if dur < 0.:
                raise NameError('Неверная длительность импульса ' + dur)
            if delay < 0.:
                raise NameError('Неверная задержка импульса ' + delay)

            data += mod.to_bytes(1, 'little')
            data += struct.pack('<d', freq)
            data += struct.pack('<d', dur)
            data += struct.pack('<d', delay)

            tag, value = self.send_recv_tlv(bytes([0xA1 + (num - 1) * 2]), data)
            self._check_result(tag, value)

        except ValueError as e:
            print(cmd_name, 'Неверное значение аргумента: ', e)
        except NameError as e:
            print(cmd_name, e)
        except:
            print(cmd_name, 'Неизвестная ошибка')
        else:
            return True
        return False


if __name__ == '__main__':
    sync = Sync()
    if not sync.set_devmode('3'):
        sys.exit(1)

    if len(sys.argv) == 2:
        if sync.upgrade(sys.argv[1]):
            pass
        else:
            sys.exit(1)

