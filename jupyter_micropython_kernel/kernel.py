from ipykernel.kernelbase import Kernel
import logging, sys, serial, time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

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
            if res and (res[0] != 'O' or len(res) > 3 or True):
                yield b''.join(res)
                res.clear()
            else:
                n += 1
                if (n%10) == 0:
                    yield b'.'
                
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

    def sendcommand(self, command):
        cmdlines = command.splitlines(True)
        
        # Instantiate a connection %%CONN port baudrate
        if cmdlines[0][:6] == "%%CONN":
            line = cmdlines[0]
            bline = line[6:].strip() or "/dev/ttyUSB0 115200"
            bline = bline.split()
            if self.workingserial is not None:
                self.process_output("Closing old serial\n")
                self.workingserial.close() 
                self.workingserial = None
            self.process_output("Connecting to Serial({}, {})\n".format(bline[0], bline[1]))
            try:
                self.workingserial = serial.Serial(bline[0], int(bline[1]), timeout=0.5)
            except serial.SerialException as e:
                self.process_output(e.strerror)

            if self.workingserial:
                self.process_output("Serial connected {}\n".format(str(self.workingserial)))
                self.enterpastemode()

        elif self.workingserial is None:
            self.process_output("No serial connected; write %%CONN to connect")

        elif cmdlines[0][:7] == "%%CHECK":
            l = self.workingserial.read_all()
            self.process_output(str([l]))
            
        elif cmdlines[0][:7] == "%%RECS":
            self.receivestream(bseekokay=False)
            
        elif cmdlines[0][:8] == "%%REBOOT":
            self.workingserial.write(b"\x03\r")  # quit any running program
            self.workingserial.write(b"\x02\r")  # exit the paste mode with ctrl-B
            self.workingserial.write(b"\x04\r")  # soft reboot code
            self.enterpastemode()

        # copy cell contents into a file on the device (by hackily saving it)
        elif cmdlines[0][:6] == "%%FILE":
            for i, line in enumerate(cmdlines):
                if i == 0:
                    fname = cmdlines[0].split()[1]
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


        elif cmdlines[0].strip() == "%lsmagic":
            self.process_output("%%CONN /dev/ttyUSB0 115200\n")
            self.process_output("%%CHECK does serial.read_all()\n")
            self.process_output("%%RECS does interpret stream normally\n")
            self.process_output("%%NOREC at start suppresses receivestream\n")
            self.process_output("%%REBOOT reboots device\n")
            self.process_output("%%FILE name.py uploads subsequent text to file\n")

        # run the cell contents as normal
        else:
            bsuppressreceivestream = (cmdlines[0][:7] == "%%NOREC")
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

    def receivestream(self, bseekokay, bwarnokaypriors=True):
        n04count = 0
        brebootdetected = False
        for j in range(2):  # for restarting the chunking when interrupted
            if self.workingserialchunk is None:
                self.workingserialchunk = yieldserialchunk(self.workingserial)
 
            indexprevgreaterthansign = -1
            for i, rline in enumerate(self.workingserialchunk):
                assert rline is not None
                if rline == b'OK' and bseekokay:
                    if i != 0 and bwarnokaypriors:
                        self.process_output("\n\n[Late OK]\n\n")
                    bseekokay = False
                    continue
                    
                elif bseekokay and bwarnokaypriors:
                    if (rline != b'>') and rline.strip()):
                        self.process_output("\n[missing-OK]")
                    
                # leaving condition where OK...x04...x04...> has been found
                if n04count >= 2 and rline == b'>' and not bseekokay:
                    if n04count != 2:
                        self.process_output("[too many x04s %d]" % n04count)
                    break

                if rline == b'\x04':
                    n04count += 1
                    continue

                if rline == b'Type "help()" for more information.\r\n':
                    brebootdetected = True
                if rline == b'>':
                    indexprevgreaterthansign = i
                    
                # looks for ">>> "
                if brebootdetected and rline == b' ' and indexprevgreaterthansign == i-1: 
                    self.process_output("[reboot detected]" % n04count)
                    self.enterpastemode()  # unintentionally recursive, this
                    break
                    
                #if bseekokay and not bwarnokaypriors and (rline == b'>' or not rline.strip()):
                #    continue
                    
                try:
                    ur = rline.decode("utf8")
                except UnicodeDecodeError:
                    ur = str(rline)
                self.process_output(ur)
                
            else:   # we've hit a stop iteration, happens with Keyboard interrupt, and generator needs to be rebuilt
                self.workingserialchunk = None
                continue
                    
            break   # out of the while loop

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
            logger.info("Sending %%C")
            self.process_output("\n\n*** Sending x03\n\n")
            if self.workingserial:
                self.workingserial.write(b'\r\x03')
                interrupted = True
                self.receivestream(bseekokay=False)
            return {'status': 'abort', 'execution_count': self.execution_count}


        # everything already gone out with send_response(), but could detect errors (text between the two \x04s
        return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}
                    
