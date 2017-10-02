from ipykernel.kernelbase import Kernel
import logging, sys, time, os, re
import serial, socket, serial.tools.list_ports, select

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

serialtimeout = 0.5
serialtimeoutcount = 10

# use of argparse for handling the %commands in the cells
import argparse, shlex

ap_serialconnect = argparse.ArgumentParser(prog="%serialconnect", add_help=False)
ap_serialconnect.add_argument('--raw', help='Just open connection', action='store_true')
ap_serialconnect.add_argument('portname', type=str, default=0, nargs="?")
ap_serialconnect.add_argument('baudrate', type=int, default=115200, nargs="?")

ap_socketconnect = argparse.ArgumentParser(prog="%socketconnect", add_help=False)
ap_socketconnect.add_argument('--raw', help='Just open connection', action='store_true')
ap_socketconnect.add_argument('ipnumber', type=str)
ap_socketconnect.add_argument('portnumber', type=int)

ap_writebytes = argparse.ArgumentParser(prog="%writebytes", add_help=False)
ap_writebytes.add_argument('-b', help='binary', action='store_true')
ap_writebytes.add_argument('stringtosend', type=str)

ap_sendtofile = argparse.ArgumentParser(prog="%sendtofile", add_help=False)
ap_sendtofile.add_argument('destinationfilename', type=str)

def parseap(ap, percentstringargs1):
    try:
        return ap.parse_known_args(percentstringargs1)[0]
    except SystemExit:  # argparse throws these because it assumes you only want to do the command line
        return None  # should be a default one
        
# try to get the pc_webrepl to connect successfully to hotspot_webrepl (or a viarouter_webrepl)
#   pay attention to the problematic workingserialreadall() functon and the blockingness
#   begin with raw serial back and forth; then handle the nasty \x04 interface
#   then look at websocket implementation (and its connection to the ESP8266)

# then make the websocket from the ESP32 as well
# then make one that serves out sensor data just automatically
# and access and read that from javascript
# and get the webserving of webpages (and javascript) also to happen

# * wifi settings and passwords into a file saved on the ESP
# * change name of process_output() to sres() for string_response()

# * find out how sometimes things get printed in green
#    colour change to green is done by the character \x1b
#    don't know how to change back to black or to the yellow colour  (these are the syntax highlighting colours)
# * insert comment reminding you to run "python -m jupyter_micropython_kernel.install"
#    after this pip install
# %readbytes now looks redundant
# * record incoming bytes (eg when in enterpastemode) that haven't been printed 
#    and print them when there is Ctrl-C
# * micropython_notebooks -> developer_micropython_notebooks
# * improve the help in usage argparses
# * capability to suppress "I (200055) wifi:" messages
# * build a serial/socket handling object class

# merge uncoming serial stream and break at OK, \x04, >, \r\n, and long delays 
def yieldserialchunk(s):
    res = [ ]
    n = 0
    while True:
        try:
            if type(s) == serial.Serial:
                b = s.read()
            else:
                r,w,e = select.select([s], [], [], serialtimeout)
                if r:
                    b = s._sock.recv(1)
                else:
                    b = b''
                    
        except serial.SerialException as e:
            yield b"\r\n**[ys] "
            yield str(type(e)).encode("utf8")
            yield b"\r\n**[ys] "
            yield str(e).encode("utf8")
            yield b"\r\n\r\n"
            break
            
        if not b:
            if res and (res[0] != 'O' or len(res) > 3):
                yield b''.join(res)
                res.clear()
            else:
                n += 1
                if (n%serialtimeoutcount) == 0:
                    yield b''   # yield a blank line every (serialtimeout*serialtimeoutcount) seconds
                
        elif b == b'K' and len(res) >= 1 and res[-1] == b'O':
            if len(res) > 1:
                yield b''.join(res[:-1])
            yield b'OK'
            res.clear()
        elif b == b'\x04' or b == b'>':
            if res:
                yield b''.join(res)
            yield b
            res.clear()
        else:
            res.append(b)
            if b == b'\n' and len(res) >= 2 and res[-2] == b'\r':
                yield b''.join(res)
                res.clear()

# this should take account of the operating system
def guessserialport():  
    return sorted([x[0]  for x in serial.tools.list_ports.grep("")])

class MicroPythonKernel(Kernel):
    implementation = 'micropython_kernel'
    implementation_version = "v3"

    banner = "MicroPython Serializer"

    language_info = {'name': 'micropython',
                     'codemirror_mode': 'python',
                     'mimetype': 'text/python',
                     'file_extension': '.py'}

    def __init__(self, **kwargs):
        Kernel.__init__(self, **kwargs)
        self.silent = False
        self.workingserial = None  # a serial.Serial or a socket.SocketIO
        self.workingserialchunk = None
        
    def workingserialreadall(self):  # usually used to clear the incoming buffer
        assert self.workingserial is not None
        if type(self.workingserial) == serial.Serial:
            return self.workingserial.read_all()

        # socket case, get it all down
        res = [ ]
        while True:
            r,w,e = select.select([self.workingserial._sock],[],[],0)
            if not r:
                break
            res.append(self.workingserial._sock.recv(1000))
            self.process_output("Selected socket {}  {}\n".format(len(res), len(res[-1])))
        return b"".join(res)
        
        
    def serialconnect(self, portname, baudrate):
        if self.workingserial is not None:
            self.process_output("Closing old serial {}\n".format(str(self.workingserial)))
            self.workingserial.close()
            self.workingserial = None

        if type(portname) is int:
            possibleports = guessserialport()
            if possibleports:
                portname = possibleports[portname]
                if len(possibleports) > 1:
                    self.process_output("Found serial ports {}: \n".format(", ".join(possibleports)))
            else:
                self.process_output("No possible ports found")
                portname = ("COM4" if sys.platform == "win32" else "/dev/ttyUSB0")
            
        self.process_output("Connecting to Serial {} baud={}\n".format(portname, baudrate))
        try:
            self.workingserial = serial.Serial(portname, baudrate, timeout=serialtimeout)
        except serial.SerialException as e:
            self.process_output(e.strerror)
            self.process_output("\n")
            possibleports = guessserialport()
            if possibleports:
                self.process_output("\nTry one of these ports:\n  {}".format("\n  ".join(possibleports)))
            else:
                self.process_output("\nAre you sure your ESP-device is plugged in?")
            return
            
        for i in range(5001):
            if self.workingserial.isOpen():
                break
            time.sleep(0.01)
        self.process_output("Waited {} seconds for isOpen()\n".format(i*0.01))
        

    def socketconnect(self, ipnumber, portnumber):
        if self.workingserial is not None:
            self.process_output("Closing old serial {}\n".format(str(self.workingserial)))
            self.workingserial.close()
            self.workingserial = None

        self.process_output("Connecting to socket ({} {})\n".format(ipnumber, portnumber))
        s = socket.socket()
        self.process_output("Connecting to socket ({} {})\n".format(ipnumber, portnumber))
        try:
            self.process_output("preconnect\n")
            s.connect(socket.getaddrinfo(ipnumber, portnumber)[0][-1])
            self.process_output("Doing makefile\n")
            self.workingserial = s.makefile('rwb', 0)
        except OSError as e:
            self.process_output("Socket OSError {}".format(str(e)))
        except ConnectionRefusedError as e:
            self.process_output("Socket ConnectionRefusedError {}".format(str(e)))


    def sendtofile(self, destinationfilename, cellcontents):
        for i, line in enumerate(cellcontents.splitlines(True)):
            if i == 0:
                self.workingserial.write("O=open({}, 'w')\r\n".format(repr(destinationfilename)).encode())
                continue
                
            self.workingserial.write("O.write({})\r\n".format(repr(line)).encode())
            if (i%10) == 0:
                self.workingserial.write(b'\r\x04')
                self.receivestream(bseekokay=True)
                self.process_output("{} lines sent so far\n".format(i))

        self.workingserial.write("O.close()\r\n".encode())
        self.workingserial.write(b'\r\x04')
        self.receivestream(bseekokay=True)
        self.process_output("{} lines sent done".format(len(cmdlines)-1))

    
    def interpretpercentline(self, percentline, cellcontents):
        percentstringargs = shlex.split(percentline)
        percentcommand = percentstringargs[0]

        if percentcommand == ap_serialconnect.prog:
            apargs = parseap(ap_serialconnect, percentstringargs[1:])
            self.serialconnect(apargs.portname, apargs.baudrate)
            if self.workingserial:
                self.process_output("\n ** Serial connected **\n\n")
                self.process_output(str(self.workingserial))
                self.process_output("\n")
                if not apargs.raw:
                    self.enterpastemode()
            return None

        if percentcommand == ap_socketconnect.prog:
            apargs = parseap(ap_socketconnect, percentstringargs[1:])
            self.socketconnect(apargs.ipnumber, apargs.portnumber)
            if self.workingserial:
                self.process_output("\n ** Socket connected **\n\n")
                self.process_output(str(self.workingserial))
                self.process_output("\n")
                #if not apargs.raw:
                #    self.enterpastemode()
            return None

        if percentcommand == "%lsmagic":
            self.process_output(ap_serialconnect.format_usage())
            self.process_output("%lsmagic list magic commands\n")
            self.process_output("%suppressendcode doesn't send x04 or wait to read after sending the cell\n")
            self.process_output("  (assists for debugging using %writebytes and %readbytes)\n")
            self.process_output("%writebytes does serial.write() on a string b'binary_stuff' \n")
            self.process_output(ap_writebytes.format_usage())
            self.process_output("%readbytes does serial.read_all()\n")
            self.process_output("%rebootdevice reboots device\n")
            self.process_output("%disconnects disconnects serial\n")
            self.process_output(ap_sendtofile.format_usage())
            self.process_output(ap_socketconnect.format_usage())
            self.process_output("%sendtofile name.py uploads subsequent text to file\n")
            return None

        if percentcommand == "%disconnect":
            if self.workingserial is not None:
                self.process_output("Closing serial {}\n".format(str(self.workingserial)))
                self.workingserial.close() 
                self.workingserial = None
            return None
        
        # remaining commands require a connection
        if self.workingserial is None:
            return cellcontents
            
        if percentcommand == ap_writebytes.prog:
            apargs = parseap(ap_writebytes, percentstringargs[1:])
            bytestosend = apargs.stringtosend.encode().decode("unicode_escape").encode()
            nbyteswritten = self.workingserial.write(bytestosend)
            if type(self.workingserial) == serial.Serial:
                self.process_output("serial.write {} bytes to {} at baudrate {}".format(nbyteswritten, self.workingserial.port, self.workingserial.baudrate))
            else:
                self.process_output("serial.write {} bytes to {}".format(nbyteswritten, str(self.workingserial)))
            return None
            
        if percentcommand == "%readbytes":
            l = self.workingserialreadall()
            self.process_output(str([l]))
            return None
            
        if percentcommand == "%rebootdevice":
            self.workingserial.write(b"\x03\r")  # quit any running program
            self.workingserial.write(b"\x02\r")  # exit the paste mode with ctrl-B
            self.workingserial.write(b"\x04\r")  # soft reboot code
            self.enterpastemode()
            return None
            
        if percentcommand == "%reboot":
            self.process_output("Did you mean %rebootdevice?\n")
            return None

        if percentcommand == "%reboot":
            self.process_output("Did you mean %rebootdevice?\n")
            return None

        if percentcommand in ("%savetofile", "%savefile", "%sendfile"):
            self.process_output("Did you mean to write %sendtofile?\n")
            return None

        if percentcommand == ap_sendtofile.prog:
            apargs = parseap(ap_sendtofile, percentstringargs[1:])
            cellcontents = re.sub("^\s*%sendtofile.*\n(?:[ \r]*\n)?", "", cellcontents)
            sendtofile(apargs.destinationfilename, cellcontents)
            return None

        return cellcontents
        
    def runnormalcell(self, cellcontents, bsuppressendcode):
        cmdlines = cellcontents.splitlines(True)
        r = self.workingserialreadall()
        if r:
            self.process_output('[priorstuff] ')
            self.process_output(str(r))
            
        for line in cmdlines:
            if line:
                if line[-2:] == '\r\n':
                    line = line[:-2]
                elif line[-1] == '\n':
                    line = line[:-1]
                self.workingserial.write(line.encode("utf8"))
                self.workingserial.write(b'\r\n')
                r = self.workingserialreadall()
                if r:
                    self.process_output('[duringwriting] ')
                    self.process_output(str(r))
                    
        if not bsuppressendcode:
            self.workingserial.write(b'\r\x04')
            self.receivestream(bseekokay=True)
        
    def sendcommand(self, cellcontents):
        bsuppressendcode = False  # can't yet see how to get this signal through
        
        # extract any %-commands we have here at the start (or ending?)
        mpercentline = re.match("\s*(%.*)", cellcontents)
        if mpercentline:
            cellcontents = self.interpretpercentline(mpercentline.group(1), cellcontents)
            if cellcontents is None:
                return
                
        if self.workingserial is None:
            self.process_output("No serial connected\n")
            self.process_output("  %serialconnect to connect\n")
            self.process_output("  %lsmagic to list commands")
            return
            
        # run the cell contents as normal
        if cellcontents:
            self.runnormalcell(cellcontents, bsuppressendcode)
            
    def enterpastemode(self):
        assert self.workingserial
        # now sort out connection situation
        self.workingserial.write(b'\r\x03\x03')    # ctrl-C: kill off running programs
        l = self.workingserialreadall()
        if l:
            self.process_output('[x03x03] ')
            self.process_output(str(l))
        #self.workingserial.write(b'\r\x02')        # ctrl-B: leave paste mode if still in it <-- doesn't work as when not in paste mode it reboots the device
        self.workingserial.write(b'\r\x01')        # ctrl-A: enter raw REPL
        self.workingserial.write(b'1\x04')         # single character program to run so receivestream works
        self.receivestream(bseekokay=True, bwarnokaypriors=False)

    def receivestream(self, bseekokay, bwarnokaypriors=True, b5secondtimeout=False):
        n04count = 0
        brebootdetected = False
        for j in range(2):  # for restarting the chunking when interrupted
            if self.workingserialchunk is None:
                self.workingserialchunk = yieldserialchunk(self.workingserial)
 
            indexprevgreaterthansign = -1
            for i, rline in enumerate(self.workingserialchunk):
                assert rline is not None
                
                # warning message when we are waiting on an OK
                if bseekokay and bwarnokaypriors and (rline != b'OK') and (rline != b'>') and rline.strip():
                    self.process_output("\n[missing-OK]")
 
                # the main interpreting loop
                if rline == b'OK' and bseekokay:
                    if i != 0 and bwarnokaypriors:
                        self.process_output("\n\n[Late OK]\n\n")
                    bseekokay = False

                # one of 2 Ctrl-Ds in the return from execute in paste mode
                elif rline == b'\x04':
                    n04count += 1

                # leaving condition where OK...x04...x04...> has been found in paste mode
                elif rline == b'>' and n04count >= 2 and not bseekokay:
                    if n04count != 2:
                        self.process_output("[too many x04s %d]" % n04count)
                    break

                elif rline == b'':
                    if b5secondtimeout:
                        self.process_output("[Timed out waiting for recognizable response]\n")
                        break
                    self.process_output(".")  # dot holding position to prove it's alive

                elif rline == b'Type "help()" for more information.\r\n':
                    brebootdetected = True
                    self.process_output(rline.decode())
                    
                elif rline == b'>':
                    indexprevgreaterthansign = i
                    self.process_output('>')
                    
                # looks for ">>> "
                elif rline == b' ' and brebootdetected and indexprevgreaterthansign == i-1: 
                    self.process_output("[reboot detected %d]" % n04count)
                    self.enterpastemode()  # this is unintentionally recursive, but after a reboot has been seen we need to get into paste mode
                    self.process_output(' ')
                    break
                    
                # normal processing of the string of bytes that have come in
                else:
                    try:
                        ur = rline.decode()
                    except UnicodeDecodeError:
                        ur = str(rline)
                    self.process_output(ur)
        
            # else on the for-loop, means the generator has ended at a stop iteration
            # this happens with Keyboard interrupt, and generator needs to be rebuilt
            else:  # of the for-command 
                self.workingserialchunk = None
                continue
                    
            break   # out of the for loop

    def process_output(self, output):
        if not self.silent:
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}

        interrupted = False
        if self.workingserial:
            priorbuffer = None
            try:
                priorbuffer = self.workingserialreadall()
            except KeyboardInterrupt:
                interrupted = True
            except OSError as e:
                priorbuffer = []
                self.process_output("\n\n***Connecton broken [%s]\n" % str(e.strerror))
                self.process_output("You may need to reconnect")
                
            if priorbuffer:
                for pbline in priorbuffer.splitlines():
                    try:
                        ur = pbline.decode()
                    except UnicodeDecodeError:
                        ur = str(pbline)
                    self.process_output('[leftinbuffer] ')
                    self.process_output(ur)
                    self.process_output('\n')

        try:
            if not interrupted:
                self.sendcommand(code)
        except KeyboardInterrupt:
            interrupted = True
        except OSError as e:
            self.process_output("\n\n***OSError [%s]\n\n" % str(e.strerror))
        #except pexpect.EOF:
        #    self.process_output(self.asyncmodule.before + 'Restarting Bash')
        #    self.startasyncmodule()

        if interrupted:
            self.process_output("\n\n*** Sending Ctrl-C\n\n")
            if self.workingserial:
                self.workingserial.write(b'\r\x03')
                interrupted = True
                self.receivestream(bseekokay=False, b5secondtimeout=True)
            return {'status': 'abort', 'execution_count': self.execution_count}

        # everything already gone out with send_response(), but could detect errors (text between the two \x04s
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
                    
