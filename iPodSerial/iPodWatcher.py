#!/usr/bin/env python
# encoding: utf-8
"""
iPodWatcher.py

Watches both sides of the conversation between an iPod and a serial device.

Created by Brian Lalor on 2010-12-07.
Copyright (c) 2010 __MyCompanyName__. All rights reserved.
"""

import sys
import getopt
import serial
import threading
import datetime, time
import traceback
import string
import struct

help_message = '''
The help message goes here.
'''

def make_printable(x):
    result = []
    for y in x:
        if y in string.printable:
            result.append(y)
        elif y == '\x00':
            break
        else:
            result.append('.')
        
    return "".join(result)


def make_num(x):
    return struct.unpack('>I', "".join(x))[0]


def identity(x):
    return " ".join(['%02x' % (ord(c),) for c in x])


def format_ms(x):
    et_m = int((x / 1000.0) / 60)
    et_s = (x / 1000.0) % 60
    
    return '%d:%06.3f' % (et_m, et_s)


def decode_poll_update(x):
    polling_type = ord(x[0])
    polling_type_str = "<UNKNOWN>"
    polling_val = identity(x[1:])
    
    if polling_type in POLLING_UPDATE:
        polling_type_str = POLLING_UPDATE[polling_type]
    
    if len(x[1:]) == 4:
        polling_val = make_num(x[1:])
        
        if polling_type == 0x04:
            polling_val = format_ms(polling_val)
    
    return 'mode: %s, value: %s' % (polling_type_str, polling_val)


class Usage(Exception):
    def __init__(self, msg):
        self.msg = msg


class Formatter(object):
    def __init__(self):
        self.__output_lock = threading.RLock()
    
    def output(self, msg):
        with self.__output_lock:
            print msg
            sys.stdout.flush()
        
    

FEEDBACK_RESULT = {
    0x00 : 'Success',
    0x02 : 'Failure',
    0x04 : 'Exceeded limit/byte count wrong',
    0x05 : 'is a response, not a command',
}

ITEM_TYPES = {
    0x01 : 'Playlist',
    0x02 : 'Artist',
    0x03 : 'Album',
    0x04 : 'Genre',
    0x05 : 'Song',
    0x06 : 'Composer',
}

PLAYBACK_STATUS = {
    0x00 : 'Stopped',
    0x01 : 'Playing',
    0x02 : 'Paused',
    
}

POLLING_MODE = {
    0x00 : 'Start',
    0x01 : 'Stop',
}

POLLING_UPDATE = {
    0x01 : 'track change',
    0x02 : 'Stop after FFwd?',
    0x03 : 'Stop after FRwd?',
    0x04 : 'elapsed time',
}

PLAYBACK_CONTROL = {
    0x01 : 'Play/Pause',
    0x02 : 'Stop',
    0x03 : 'Skip++',
    0x04 : 'Skip--',
    0x05 : 'FFwd',
    0x06 : 'FRwd',
    0x07 : 'Stop FFwd/FRwd',
}

REPEAT_SHUFFLE_MODE = {
    0x00 : 'Off',
    0x01 : 'Songs',
    0x02 : 'Albums',
}

MODE_MAP = {
    0x00 : 'Switching',
    0x01 : 'Voice recorder',
    0x02 : 'Simple remote',
    0x03 : 'Request mode status',
    0x04 : 'Advanced remote',
}

COMMANDS = {
    0x00 : {
        (0x01, 0x02) : ("Switch to simple", None),
        (0x01, 0x04) : ("Switch to advanced", None),
    },
    0x04 : {
        (0x00, 0x01) : ("Result", lambda x: '%s, result %s' % (COMMANDS[0x04][(ord(x[1]), ord(x[2]))][0], FEEDBACK_RESULT[ord(x[0])])),
        (0x00, 0x12) : ("Get iPod type", None),
        (0x00, 0x13) : ("iPod type", identity),
        (0x00, 0x14) : ("Get iPod name", None),
        (0x00, 0x15) : ("iPod name", make_printable),
        (0x00, 0x16) : ("Switch to main library playlist", None),
        (0x00, 0x17) : ("Switch to item", lambda x: 'type: %s, number: %d' % (ITEM_TYPES[ord(x[0])], make_num(x[1:]))),
        (0x00, 0x18) : ("Get count of the given type", lambda x: 'type: %s' % (ITEM_TYPES[ord(x[0])],)),
        (0x00, 0x19) : ("count of the requested type", make_num),
        (0x00, 0x1a) : ("Get names for range of the given type", lambda x: 'type: %s, offset: %d, count: %d' % (ITEM_TYPES[ord(x[0])], make_num(x[1:5]), make_num(x[5:]))),
        (0x00, 0x1b) : ("names for index in range of requested type", lambda x: '[%d] %s' % (make_num(x[0:4]), make_printable(x[4:]))),
        (0x00, 0x1c) : ("Get time and status info", None),
        (0x00, 0x1d) : ("time and status info", lambda x: 'trk len: %s, elapsed: %s, playback status: %s' % (format_ms(make_num(x[:4])), format_ms(make_num(x[4:8])), PLAYBACK_STATUS[ord(x[-1])])),
        (0x00, 0x1E) : ("Get current position in playlist", None),
        (0x00, 0x1f) : ("current position in playlist", make_num),
        (0x00, 0x20) : ("Get title", make_num),
        (0x00, 0x21) : ("title", make_printable),
        (0x00, 0x22) : ("Get artist", make_num),
        (0x00, 0x23) : ("artist", make_printable),
        (0x00, 0x24) : ("Get album", make_num),
        (0x00, 0x25) : ("album", make_printable),
        (0x00, 0x26) : ("Set polling mode", lambda x: POLLING_MODE[ord(x[0])]),
        (0x00, 0x27) : ("Poll", decode_poll_update),
        (0x00, 0x28) : ("Execute switch", None),
        (0x00, 0x29) : ("Playback control", lambda x: PLAYBACK_CONTROL[ord(x[0])]),
        (0x00, 0x2C) : ("Get shuffle mode", None),
        (0x00, 0x2d) : ("shuffle mode", lambda x: REPEAT_SHUFFLE_MODE[ord(x[0])]),
        (0x00, 0x2E) : ("Set shuffle mode", lambda x: REPEAT_SHUFFLE_MODE[ord(x[0])]),
        (0x00, 0x2F) : ("Get repeat mode", None),
        (0x00, 0x30) : ("repeat mode", lambda x: REPEAT_SHUFFLE_MODE[ord(x[0])]),
        (0x00, 0x31) : ("Set repeat mode", lambda x: REPEAT_SHUFFLE_MODE[ord(x[0])]),
        (0x00, 0x32) : ("Upload picture", None),
        (0x00, 0x33) : ("Get max picture size", None),
        (0x00, 0x34) : ("max picture size", identity),
        (0x00, 0x35) : ("Get number of songs in playlist", None),
        (0x00, 0x36) : ("number of songs in playlist", make_num),
    }
}


class Decoder(threading.Thread):
    """docstring for Decoder"""
    def __init__(self, port, write_fn, side = 'left'):
        super(Decoder, self).__init__()
        self.__port = port
        self.__side = side
        
        self.__write_fn = write_fn
        self.__stopped = False
        
        self.daemon = True
        
    
    def write(self, msg):
        if self.__side == 'left':
            self.__write_fn("--> " + msg)
        else:
            self.__write_fn('<-- ' + msg)
        
    
    def shutdown(self):
        self.__stopped = True
    
    
    def run(self):
        """docstring for run"""
        
        self.write("running")
        
        buf = []
        discarded_data = []
        last_packet_rx_ts = None
        delta_ts = None
        
        ser = serial.Serial(port = self.__port, baudrate = 38400, timeout = 1)
        try:
            while not self.__stopped:
                byte_read = ser.read()
                if not byte_read:
                    continue
                
                buf.append(byte_read)
                
                if len(buf) > 3:
                    if buf[:2] == ['\xff', '\x55']:
                        if delta_ts == None:
                            if last_packet_rx_ts == None:
                                delta_ts = 0.0
                            else:
                                delta_ts = (time.time() - last_packet_rx_ts) * 1000.0
                            
                            last_packet_rx_ts = time.time()
                        
                        # found start
                        if discarded_data:
                            self.write("discarded data: " + str(discarded_data))
                            discarded_data = []
                        
                        pkt_len = ord(buf[2])
                        if len(buf[3:]) >= (pkt_len + 1):
                            packet = buf[:pkt_len + 4]
                            
                            # have enough data to decode the packet
                            # provided_cksum = ord(buf[pkt_len + 3])
                            provided_cksum = ord(packet[-1])
                            
                            cksum = 0
                            try:
                                for b in packet[2:-1]:
                                    cksum += ord(b)
                                
                                cksum = (0x100 - cksum) & 0xff
                            except:
                                cksum = -1
                            
                            if provided_cksum != cksum:
                                self.write("invalid checksum; got %2x expected %2x" % (cksum, provided_cksum))
                                discarded_data.append(buf.pop(0))
                                continue
                            
                            # remove the packet from the buffer
                            buf = buf[len(packet):]
                            
                            mode = ord(packet[3])
                            mode_name = None
                            if mode in MODE_MAP:
                                mode_name = MODE_MAP[mode]
                            
                            command = tuple([ord(c) for c in packet[4:6]])
                            command_name = None
                            if mode_name and (command in COMMANDS[mode]):
                                command_name, param_decoder = COMMANDS[mode][command]
                            
                            parameter = packet[6:-1]
                            if param_decoder:
                                parameter = " -- " + str(param_decoder(parameter))
                            else:
                                parameter = ''
                            
                            byte_stream = " ".join(['%02x' % ord(c) for c in packet])
                            if len(byte_stream) > 60:
                                byte_stream = " ".join(byte_stream[:59].split()[:-1]) + " ..."
                            
                            self.write(
                                '%5dms: <%-60s> [%02x] (%02x %02x) %s%s' % (
                                    delta_ts,
                                    byte_stream,
                                    mode, command[0], command[1],
                                    command_name,
                                    parameter
                                )
                            )
                            
                            delta_ts = None
                            
                        
                    
                    else:
                        # garbage data at the front
                        discarded_data.append(buf.pop(0))
                
            
        
        finally:
            self.write("closing")
            ser.close()

def main(argv=None):
    if argv is None:
        argv = sys.argv
    try:
        try:
            opts, args = getopt.getopt(argv[1:], "ho:v", ["help", "output="])
        except getopt.error, msg:
            raise Usage(msg)
    
        # option processing
        for option, value in opts:
            if option == "-v":
                verbose = True
            if option in ("-h", "--help"):
                raise Usage(help_message)
            if option in ("-o", "--output"):
                output = value
    
    except Usage, err:
        print >> sys.stderr, sys.argv[0].split("/")[-1] + ": " + str(err.msg)
        print >> sys.stderr, "\t for help use --help"
        return 2
    
    rx_device, tx_device = args[:2]
    
    formatter = Formatter()
    rx_decoder = Decoder(rx_device, formatter.output, 'left')
    tx_decoder = Decoder(tx_device, formatter.output, 'right')
    
    rx_decoder.start()
    tx_decoder.start()
    
    try:
        while True:
            time.sleep(5)
        
    finally:
        rx_decoder.shutdown()
        tx_decoder.shutdown()
        
        rx_decoder.join()
        tx_decoder.join()
        
    
    


if __name__ == "__main__":
    sys.exit(main())
