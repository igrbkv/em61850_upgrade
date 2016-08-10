#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import fcntl
from os import listdir
from binascii import crc32, b2a_hex
import socket
from os import path
import struct
import syslog
from time import sleep

SIOCGIFADDR = 0x8915
IP_ADR_GAIN = 1
DEBUG = 1
MAX_ATTEMPTS = 15


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
    count = 0

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


class Socket(Packet):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5.0)
        # host = '10.0.40.177'
        self.debug = DEBUG
        self.value = bytearray()
        self.host = self._host()
        self.port = 1234

    def dprint(self, msg):
        if self.debug:
            syslog.syslog(msg)

    def _host(self):
        """
        adc_brd_ip = em_ip + IP_ADR_GAIN (e.g. 10.0.40.12 ==> 10.0.40.14)
        """
        # wait for ethernet initialization
        iface = None
        for attmpt in range(MAX_ATTEMPTS):
            ifaces = listdir('/sys/class/net/')
            for i in ifaces:
                if i[0] == 'e':
                    iface = i
                    break
            sleep(1)
        if iface is None:
            raise BaseException('Ethernet interface is not exist!')

        ifaces = listdir('/sys/class/net/')
        for i in ifaces:
            if i[0] == 'b':
                iface = i
                break
        if iface is None:
            raise BaseException('Network interface is not exist!')
        host = socket.inet_ntoa(fcntl.ioctl(
            self.sock.fileno(), SIOCGIFADDR,
            struct.pack('256s', iface[:15].encode('utf-8')))[20:24])
        host = host.split('.')
        host[3] = str(int(host[3]) + IP_ADR_GAIN)
        return '.'.join(host)

    def _print_result(self, tag, value):
        if self.debug > 1:
            res = None
            try:
                if tag[0] == 0x32:
                    res = ('Fail', 'Ok')[value[0]]
                elif tag[0] == 0x31:
                    res = value.decode()
            except:
                pass
            if res:
                self.dprint(res)
            else:
                self.dprint('tag=', b2a_hex(tag), ' value=', b2a_hex(value))

    def send_tlv(self, tag, data):
        tlv = self.make_tlv(tag, data)
        # self.dprint(str(b2a_hex(tlv)))
        msg = self.encode(tlv)
        if self.debug > 1:
            self.dprint('To send: ' + str(b2a_hex(msg)))
        self.sock.sendto(msg, (self.host, self.port))
        if self.debug > 1:
            self.dprint('Server reply :')
        while True:
            reply = self.sock.recv(4096)
            # self.dprint(str(b2a_hex(reply)))
            reply = self.decode(bytes(reply))
            if self.debug > 1:
                self.dprint(str(b2a_hex(reply)))
            rtag, value = self.break_tlv(reply)
            if rtag[0] != 0x81:
                raise BaseException('Unknown tag ' + b2a_hex(tag).decode())
            # strip packet order number and crc
            rtag, value = self.break_tlv(bytes(value[2:-4]))
            if rtag == tag or rtag[0] in (0x31, 0x32):
                if self.debug > 1:
                    self.dprint('tag={} value={}'.format(b2a_hex(rtag), b2a_hex(value)))
                break
        return rtag, value

    def versions_equal(self, path):
        # installed version
        tag, value = self.send_tlv(bytes([0xF0]), bytes())
        value = value[:3] + value[4:8]
        old_version = struct.unpack('<3BI', value)

        with open(path, 'rb') as f:
            fsize = f.seek(0, 2)
            f.seek(fsize - 16, 0)
            buf = f.read(7)
            new_version = struct.unpack('<3BI', buf)

        syslog.syslog('sync board current ver.:{}.{}.{} ({}) new ver.:{}.{}.{} ({})'.
            format(old_version[0], old_version[1], old_version[2], old_version[3],
            new_version[0], new_version[1], new_version[2], new_version[3]))

        return old_version == new_version

    def adc_upgrade(self):
        image_path = sys.argv[1]
        sz = path.getsize(image_path)
        if sz != 512 * 1024:
            raise BaseException('Bad file size:' + sz)

        self.dprint('adc_upgrade')
        if self.versions_equal(image_path):
            syslog.syslog('Versions are equal. Skeep adc board firmware upgrade.')
            return

        self.dprint('read device mode ...')
        tag, value = self.send_tlv(bytes([0xF5]), bytes())
        if tag[0] != 0xF5:
            raise BaseException('Read deviceMode failed!')
        mod = int(value[0])
        if mod == 0xFF:
            raise BaseException('The device is already in firmware update mode!')
        if mod == 0xFE:
            # service mode
            self.dprint('clear all firmware ...')
            tag, value = self.send_tlv(bytes([0xF4]), bytes([0]))
            if tag[0] != 0xF4 or value[0] != 1:
                raise BaseException('Clear all firmware failed!')
            self.send_tlv(bytes([0xF3]), bytes([0]))

        # reset last upgrade
        self.dprint('clear last firmware ...')
        tag, value = self.send_tlv(bytes([0xF1]), bytes([0]))
        if tag[0] != 0xF1 or value[0] != 1:
            raise BaseException('Reset firmware failed!')
        i = 0
        self.dprint('write firmware ...')
        with open(image_path, 'rb') as fw:
            buf = fw.read(1024)
            while buf:
                tag, value = self.send_tlv(bytes([0xF2]), buf)
                if self.debug > 1:
                    self.dprint('{}'.format(i))
                if tag[0] != 0xF2 or value[0] != 1:
                    raise BaseException("Write firmware failed!")
                buf = fw.read(1024)
                i += 1

            self.dprint('blocks written: {}'.format(i))

        self.dprint('reset device ...')
        try:
            tag, value = self.send_tlv(bytes([0xF3]), bytes([0]))
        except socket.timeout:
            pass


def main():
    '''
    try:
    '''
    syslog.openlog('emupgrade')
    ret = -1
    Socket().adc_upgrade()
    ret = 0
    '''
    except FileNotFoundError as e:
        syslog.syslog(e)
        ret = -2
    except BaseException as e:
        syslog.syslog(e)
        ret = -3
    except (ValueError or IndexError) as e:
        syslog.syslog(e)
        ret = -4
    except socket.timeout:
        syslog.syslog('*** timeout')
        ret = -5
    finally:
        if ret == -1:
            syslog.syslog('Unknown error!')
        sys.exit(ret)
    '''


if __name__ == '__main__':
    main()
