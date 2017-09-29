from ipykernel.kernelbase import Kernel
import logging, sys, serial, time, os

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

serialtimeout = 0.5
serialtimeoutcount = 10

# merge uncoming serial stream and break at OK, \x04, >, \r\n, and long delays 
def yieldserialchunk(s):
    res = [ ]
    n = 0
    while True:
        try:
            b = s.read()
        except serial.SerialException as e:
            yield str(e).encode("utf8")
            yield str(type(e)).encode("utf8")
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
    return sorted([ os.path.join("/dev/", k)  for k in os.listdir("/dev/")  if k[:6] == "ttyUSB" ])

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
        self.workingserial = None
        self.workingserialchunk = None
        
    def serialconnect(self, cmdline0spl):
        if self.workingserial is not None:
            self.process_output("Closing old serial {}\n".format(str(self.workingserial)))
            self.workingserial.close() 
            self.workingserial = None
        
        baudrate = 115200
        if len(cmdline0spl) >= 3:
            try:
                baudrate = int(cmdline0spl[2])
            except ValueError:
                self.process_output("Bad baud rate setting")

        if len(cmdline0spl) >= 2:
            portname = cmdline0spl[1]
        else:
            possibleports = guessserialport()
            portname = possibleports[0]  if possibleports else "/dev/ttyUSB0"
            
            
        self.process_output("Connecting to Serial ({}, {})\n".format(portname, baudrate))
        try:
            self.workingserial = serial.Serial(portname, baudrate, timeout=serialtimeout)
        except serial.SerialException as e:
            self.process_output(e.strerror)
            possibleports = guessserialport()
            if possibleports:
                self.process_output("\nTry one of these ports:\n  {}".format("\n  ".join(possibleports)))
            else:
                self.process_output("\nAre you sure your ESP8266 is plugged in?")
    
    def sendcommand(self, command):

        # extract any %-commands we have here at the start (or ending?)
        cmdlines = command.splitlines(True)
        for cmdline0 in cmdlines:
            cmdline0 = cmdline0.strip()
            if cmdline0:
                break
        cmdline0spl1 = cmdline0.split(maxsplit=1)
        cmdline00 = cmdline0spl1[0]
        
        # Instantiate a connection %%CONN port baudrate
        if cmdline00 == "%serialconnect":
            self.serialconnect(cmdline0.split())
            if self.workingserial:
                self.process_output("\n ** Serial connected **\n\n")
                self.process_output(str(self.workingserial))
                self.process_output("\n")
                self.enterpastemode()

        elif self.workingserial is None:
            self.process_output("No serial connected\n")
            self.process_output("  %serialconnect to connect\n")
            self.process_output("  %lsmagic to list commands")

        elif cmdline00 == "%writebytes":
            if len(cmdline0spl1) > 1:
                nbyteswritten = self.workingserial.write(eval(cmdline0spl1[1]))
                self.process_output("serial.write {} bytes to {} at baudrate {}".format(nbyteswritten, self.workingserial.port, self.workingserial.baudrate))
            
        elif cmdline00 == "%readbytes":
            l = self.workingserial.read_all()
            self.process_output(str([l]))
            
        elif cmdline00 == "%rebootdevice":
            self.workingserial.write(b"\x03\r")  # quit any running program
            self.workingserial.write(b"\x02\r")  # exit the paste mode with ctrl-B
            self.workingserial.write(b"\x04\r")  # soft reboot code
            self.enterpastemode()

        # copy cell contents into a file on the device (by hackily saving it)
        elif cmdline00 == "%sendtofile":
            cmdattr = cmdline0.split()[1:]
            bsendasbinary = False
            fsource = None
            fname = "uploadfile"

            # need to parse string with quotes (maybe use the settings command line thing to parse)
            if len(cmdattr) >= 1 and cmdattr[0] == '-b':
                bsendasbinary = True
                del cmdattr[0]
            if len(cmdattr) >= 2 and cmdattr[0] == '-src':
                fsource = cmdattr[1]
                del cmdattr[:2]
            if len(cmdattr) >= 1:
                fname = cmdattr[0]

            for i, line in enumerate(cmdlines):
                if i == 0:
                    self.workingserial.write("O=open({}, 'w')\r\n".format(repr(fname)).encode("utf8"))
                    continue
                    
                if i == 1 and not line.strip():
                    continue   # skip first blank line
                    
                self.workingserial.write("O.write({})\r\n".format(repr(line)).encode("utf8"))
                if (i%10) == 0:
                    self.workingserial.write(b'\r\x04')
                    self.receivestream(bseekokay=True)
                    self.process_output("{} lines sent so far\n".format(i))

            self.workingserial.write("O.close()\r\n".encode("utf8"))
            self.workingserial.write(b'\r\x04')
            self.receivestream(bseekokay=True)
            self.process_output("{} lines sent done".format(len(cmdlines)-1))


        elif cmdline00 == "%lsmagic":
            self.process_output("%serialconnect [/dev/ttyUSB0] [115200]\n")
            self.process_output("%suppressendcode doesn't send x04 or wait to read after sending the cell\n")
            self.process_output("  (assists for debugging using %writebytes and %readbytes)\n")
            self.process_output("%writebytes does serial.write() on a string b'binary_stuff' \n")
            self.process_output("%readbytes does serial.read_all()\n")
            self.process_output("%rebootdevice reboots device\n")
            self.process_output("%sendtofile name.py uploads subsequent text to file\n")

        # run the cell contents as normal
        else:
            bsuppressreceivestream = (cmdline00 == "%suppressendcode")
            if bsuppressreceivestream:
                cmdlines = cmdlines[1:]

            r = self.workingserial.read_all()
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
                    r = self.workingserial.read_all()
                    if r:
                        self.process_output('[duringwriting] ')
                        self.process_output(str(r))
                        
            self.workingserial.write(b'\r\x04')
            if not bsuppressreceivestream:
                self.receivestream(bseekokay=True)

    def enterpastemode(self):
        assert self.workingserial
        # now sort out connection situation
        self.workingserial.write(b'\r\x03\x03')    # ctrl-C: kill off running programs
        l = self.workingserial.read_all()
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
                    self.process_output(rline.decode("utf8"))
                    
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
                        ur = rline.decode("utf8")
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
        try:
            self.sendcommand(code)
        except KeyboardInterrupt:
            interrupted = True
        except OSError as e:
            self.process_output("\n\n*** [%s]\n\n" % str(e.strerror))
        #except pexpect.EOF:
        #    self.process_output(self.asyncmodule.before + 'Restarting Bash')
        #    self.startasyncmodule()

        if interrupted:
            self.process_output("\n\n*** Sending x03\n\n")
            if self.workingserial:
                self.workingserial.write(b'\r\x03')
                interrupted = True
                self.receivestream(bseekokay=False, b5secondtimeout=True)
            return {'status': 'abort', 'execution_count': self.execution_count}


        # everything already gone out with send_response(), but could detect errors (text between the two \x04s
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
                    
