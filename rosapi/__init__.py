import binascii
import hashlib

import logging


logger = logging.getLogger(__name__)


class RosAPIError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        if isinstance(self.value, dict) and self.value.get('message'):
            return self.value['message']
        else:
            return self.value


class RosAPIFatalError(RosAPIError):
    pass


class RosAPI(object):
    """Routeros api"""

    def __init__(self, socket):
        self.socket = socket

    def login(self, username, pwd):
        for _, attrs in self.talk(['/login']):
            token = binascii.unhexlify(attrs['ret'])
        hasher = hashlib.md5()
        hasher.update('\x00')
        hasher.update(pwd)
        hasher.update(token)
        self.talk(['/login', '=name=' + username,
                   '=response=00' + hasher.hexdigest()])

    def talk(self, words):
        if self.write_sentence(words) == 0:
            return
        output = []
        while True:
            input_sentence = self.read_sentence()
            if not len(input_sentence):
                continue
            attrs = {}
            reply = input_sentence.pop(0)
            for line in input_sentence:
                try:
                    second_eq_pos = line.index('=', 1)
                except IndexError:
                    attrs[line[1:]] = ''
                else:
                    attrs[line[1:second_eq_pos]] = line[second_eq_pos + 1:]
            output.append((reply, attrs))
            if reply == '!done':
                if output[0][0] == '!trap':
                    raise RosAPIError(output[0][1])
                if output[0][0] == '!fatal':
                    self.socket.close()
                    raise RosAPIFatalError(output[0][1])
                return output

    def write_sentence(self, words):
        words_written = 0
        for word in words:
            self.write_word(word)
            words_written += 1
        self.write_word('')
        return words_written

    def read_sentence(self):
        sentence = []
        while True:
            word = self.read_word()
            if not len(word):
                return sentence
            sentence.append(word)

    def write_word(self, word):
        self.write_lenght(len(word))
        self.write_string(word)
        logger.debug('>>> %s' % word)

    def read_word(self):
        word = self.read_string(self.read_length())
        logger.debug('>>> %s' % word)
        return word

    def write_lenght(self, length):
        if length < 0x80:
            self.write_string(chr(length))
        elif length < 0x4000:
            length |= 0x8000
            self.write_string(chr((length >> 8) & 0xFF))
            self.write_string(chr(length & 0xFF))
        elif length < 0x200000:
            length |= 0xC00000
            self.write_string(chr((length >> 16) & 0xFF))
            self.write_string(chr((length >> 8) & 0xFF))
            self.write_string(chr(length & 0xFF))
        elif length < 0x10000000:
            length |= 0xE0000000
            self.write_string(chr((length >> 24) & 0xFF))
            self.write_string(chr((length >> 16) & 0xFF))
            self.write_string(chr((length >> 8) & 0xFF))
            self.write_string(chr(length & 0xFF))
        else:
            self.write_string(chr(0xF0))
            self.write_string(chr((length >> 24) & 0xFF))
            self.write_string(chr((length >> 16) & 0xFF))
            self.write_string(chr((length >> 8) & 0xFF))
            self.write_string(chr(length & 0xFF))

    def read_length(self):
        i = ord(self.read_string(1))
        if (i & 0x80) == 0x00:
            pass
        elif (i & 0xC0) == 0x80:
            i &= ~0xC0
            i <<= 8
            i += ord(self.read_string(1))
        elif (i & 0xE0) == 0xC0:
            i &= ~0xE0
            i <<= 8
            i += ord(self.read_string(1))
            i <<= 8
            i += ord(self.read_string(1))
        elif (i & 0xF0) == 0xE0:
            i &= ~0xF0
            i <<= 8
            i += ord(self.read_string(1))
            i <<= 8
            i += ord(self.read_string(1))
            i <<= 8
            i += ord(self.read_string(1))
        elif (i & 0xF8) == 0xF0:
            i = ord(self.read_string(1))
            i <<= 8
            i += ord(self.read_string(1))
            i <<= 8
            i += ord(self.read_string(1))
            i <<= 8
            i += ord(self.read_string(1))
        else:
            raise RosAPIFatalError('Unknown value: %x' % i)
        return i

    def write_string(self, string):
        sent_overal = 0
        while sent_overal < len(string):
            sent = self.socket.send(string[sent_overal:])
            if sent == 0:
                raise RosAPIFatalError('Connection closed by remote end.')
            sent_overal += sent

    def read_string(self, length):
        received_overal = ''
        while len(received_overal) < length:
            received = self.socket.recv(length - len(received_overal))
            if received == 0:
                raise RosAPIFatalError('Connection closed by remote end.')
            received_overal += received
        return received_overal
