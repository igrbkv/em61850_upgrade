#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from binascii import crc32, b2a_hex
import socket

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
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)
    host = '192.168.0.2'
    port = 1234
    value = bytearray()
    debug = 0 

    def send_recv_tlv(self, tag, data):
        tlv = self.make_tlv(tag, data)
        # print(b2a_hex(tlv))
        msg = self.encode(tlv)
        if self.debug:
            print(b2a_hex(msg))
        try:
            self.sock.sendto(msg, (self.host, self.port))
        except socket.timeout:
            raise NameError('Таймаут передачи плате АЦП')
        try:
            reply = self.sock.recv(4096)
        except socket.timeout:
            raise NameError('Таймаут ответа платы АЦП')
        if self.debug:
            print('Server reply :', b2a_hex(reply))
        reply = self.decode(bytes(reply))
        if self.debug:
            print(b2a_hex(reply))
        tag, value = self.break_tlv(reply)
        if tag[0] != 0x81:
            raise NameError('Unknown tag ' + b2a_hex(tag).decode())
        # strip packet order number and crc
        tag, value = self.break_tlv(bytes(value[2:-4]))
        if self.debug:
            if tag[0] == 0x31:
                print('tag=', b2a_hex(tag), ' value=', b2a_hex(value), '(', value.decode(), ')')
            else:
                print('tag=', b2a_hex(tag), ' value=', b2a_hex(value))
        return tag, value

class Adc(TlvClient):

    def _check_result(self, tag, value, err='Команда не выполнена'):
        if tag[0] == 0x32:
            if not value[0]:
                raise NameError(err)
        else:
            raise NameError('Неверный ответ')
                    
    def upgrade(self, rest):
        """
        rest - firmware upgrade file path
        """
        try:
            cmd_name = 'Обновление прошивки платы АЦП:'
            sz = path.getsize(rest)
            if sz != 512 * 1024:
                raise NameError('Неверный размер файла прошивки:' + sz)
            tag, value = self.send_recv_tlv(bytes([0xF5]), bytes([0]))
            if value[0] == 0xFE:
                # service mode
                tag, value = self.send_recv_tlv(bytes([0xF4]), bytes([0]))
                self._check_result(tag, value, 'Ошибка очистки памяти платы.')
                # self.send_recv_tlv(bytes([0xF3]), bytes([0]))

            # reset last upgrade
            tag, value = self.send_recv_tlv(bytes([0xF1]), bytes([0]))
            self._check_result(tag, value, 'Ошибка сброса прошивки.')
            i = 0
            with open(rest, 'rb') as fw:
                buf = fw.read(1024)
                while buf:
                    tag, value = self.send_recv_tlv(bytes([0xF2]), buf)
                    self._check_result(tag, value, 'Ошибка записи прошивки')
                    buf = fw.read(1024)
                    i += 1

                # reset device
                try:
                    tag, value = self.send_recv_tlv(bytes([0xF3]), bytes([0]))
                except:
                    pass

        except FileNotFoundError as e:
            print(cmd_name, e)
        except NameError as e:
            print(cmd_name, e)
        except:
            print(cmd_name, "Неизвестная ошибка")
        else:
            return True
        return False


if __name__ == '__main__':
    adc = Adc()
    if adc.upgrade(sys.argv[1]):
        pass
    else:
        sys.exit(1)

