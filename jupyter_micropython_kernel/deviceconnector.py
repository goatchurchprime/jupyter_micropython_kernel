import logging, sys, time, os, re, binascii, subprocess
import serial, socket, serial.tools.list_ports, select
import websocket  # the old non async one

serialtimeout = 0.5
serialtimeoutcount = 10

wifimessageignore = re.compile("(\x1b\[[\d;]*m)?[WI] \(\d+\) (wifi|system_api|modsocket|phy|event|cpu_start|heap_init|network|wpa): ")

# this should take account of the operating system
def guessserialport():  
    lp = list(serial.tools.list_ports.grep(""))
    lp.sort(key=lambda X: (X.hwid == "n/a", X.device))  # n/a could be good evidence that the port is non-existent
    return [x.device  for x in lp]

# merge uncoming serial stream and break at OK, \x04, >, \r\n, and long delays 
# (must make this a member function so does not have to switch on the type of s)
def yieldserialchunk(s):
    res = [ ]
    n = 0
    wsresbuffer = b""
    wsresbufferI = 0
    while True:
        try:
            if type(s) == serial.Serial:
                b = s.read()
            elif type(s) == socket.socket:
                r,w,e = select.select([s], [], [], serialtimeout)
                if r:
                    b = s._sock.recv(1)
                else:
                    b = b''
                    
            else:  # websocket (break down to individual bytes)
                if wsresbufferI >= len(wsresbuffer):
                    r,w,e = select.select([s], [], [], serialtimeout)
                    if r:
                        wsresbuffer = s.recv()  # this comes as batches of strings, which beed to be broken to characters
                        if type(wsresbuffer) == str:
                            wsresbuffer = wsresbuffer.encode("utf8")   # handle fact that strings come back from this interface
                    else:
                        wsresbuffer = b''
                    wsresbufferI = 0
                    
                if len(wsresbuffer) > 0:
                    b = wsresbuffer[wsresbufferI:wsresbufferI+1]
                    wsresbufferI += 1
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


class DeviceConnector:
    def __init__(self, sres, sresSYS):
        self.workingserial = None
        self.workingsocket = None
        self.workingwebsocket = None
        self.workingserialchunk = None
        self.sres = sres   # two output functions borrowed across
        self.sresSYS = sresSYS
        self._esptool_command = None

    def workingserialreadall(self):  # usually used to clear the incoming buffer, results are printed out rather than used
        if self.workingserial:
            return self.workingserial.read_all()

        if self.workingwebsocket:
            res = [ ]
            while True:
                r,w,e = select.select([self.workingwebsocket],[],[],0.2)  # add a timeout to the webrepl, which can be slow
                if not r:
                    break
                res.append(self.workingwebsocket.recv())
            return "".join(res) # this is returning a text array, not bytes
                                # though a binary frame can be stipulated according to websocket.ABNF.OPCODE_MAP
                                # fix this when we see it

        # socket case, get it all down
        res = [ ]
        while True:
            r,w,e = select.select([self.workingsocket._sock],[],[],0)
            if not r:
                break
            res.append(self.workingsocket._sock.recv(1000))
            self.sres("Selected socket {}  {}\n".format(len(res), len(res[-1])))
        return b"".join(res)

    def disconnect(self, raw=False, verbose=False):
        if not raw:
            self.exitpastemode(verbose)   # this doesn't seem to do any good (paste mode is left on disconnect anyway)

        self.workingserialchunk = None
        if self.workingserial is not None:
            if verbose:
                self.sresSYS("\nClosing serial {}\n".format(str(self.workingserial)))
            self.workingserial.close()
            self.workingserial = None
        if self.workingsocket is not None:
            self.sresSYS("\nClosing socket {}\n".format(str(self.workingsocket)))
            self.workingsocket.close()
            self.workingsocket = None
        if self.workingwebsocket is not None:
            self.sresSYS("\nClosing websocket {}\n".format(str(self.workingwebsocket)))
            self.workingwebsocket.close()
            self.workingwebsocket = None

    def serialconnect(self, portname, baudrate, verbose):
        assert not  self.workingserial
        if type(portname) is int:
            portindex = portname
            possibleports = guessserialport()
            if possibleports:
                portname = possibleports[portindex]
                if len(possibleports) > 1:
                    self.sres("Found serial ports: {} \n".format(", ".join(possibleports)))
            else:
                self.sresSYS("No possible ports found")
                portname = ("COM4" if sys.platform == "win32" else "/dev/ttyUSB0")

        self.sresSYS("Connecting to --port={} --baud={} ".format(portname, baudrate))
        try:
            self.workingserial = serial.Serial(portname, baudrate, timeout=serialtimeout)
        except serial.SerialException as e:
            self.sres(e.strerror)
            self.sres("\n")
            possibleports = guessserialport()
            if possibleports:
                self.sresSYS("\nTry one of these ports as --port= \n  {}".format("\n  ".join(possibleports)))
            else:
                self.sresSYS("\nAre you sure your ESP-device is plugged in?")
            return

        for i in range(5001):
            if self.workingserial.isOpen():
                break
            time.sleep(0.01)
        if verbose:
            self.sresSYS(" [connected]")
        self.sres("\n")
        if verbose:
            self.sres(str(self.workingserial))
            self.sres("\n")

        if i != 0 and verbose:
            self.sres("Waited {} seconds for isOpen()\n".format(i*0.01))



    def socketconnect(self, ipnumber, portnumber):
        self.disconnect(verbose=True)

        self.sresSYS("Connecting to socket ({} {})\n".format(ipnumber, portnumber))
        s = socket.socket()
        try:
            self.sres("preconnect\n")
            s.connect(socket.getaddrinfo(ipnumber, portnumber)[0][-1])
            self.sres("Doing makefile\n")
            self.workingsocket = s.makefile('rwb', 0)
        except OSError as e:
            self.sres("Socket OSError {}".format(str(e)))
        except ConnectionRefusedError as e:
            self.sres("Socket ConnectionRefusedError {}".format(str(e)))


    def websocketconnect(self, websocketurl):
        self.disconnect(verbose=True)
        try:
            self.workingwebsocket = websocket.create_connection(websocketurl, 5)
            self.workingwebsocket.settimeout(serialtimeout)
        except socket.timeout:
            self.sres("Websocket Timeout after 5 seconds {}\n".format(websocketurl))
        except ValueError as e:
            self.sres("WebSocket ValueError {}\n".format(str(e)))
        except ConnectionResetError as e:
            self.sres("WebSocket ConnectionError {}\n".format(str(e)))
        except OSError as e:
            self.sres("WebSocket OSError {}\n".format(str(e)))
        except websocket.WebSocketException as e:
            self.sres("WebSocketException {}\n".format(str(e)))


    def esptool(self, espcommand, portname, binfile):
        self.disconnect(verbose=True)
        if type(portname) is int:
            possibleports = guessserialport()
            if possibleports:
                portname = possibleports[portname]
                if len(possibleports) > 1:
                    self.sres("Found serial ports {}: \n".format(", ".join(possibleports)))
            else:
                self.sres("No possible ports found")
                portname = ("COM4" if sys.platform == "win32" else "/dev/ttyUSB0")

        if self._esptool_command is None:  # this section for finding what the name of the command function is; may print junk into the jupyter logs
            for command in ("esptool.py", "esptool"):  
                try:
                    subprocess.check_call([command, "version"])
                    self._esptool_command = command
                    break
                except (subprocess.CalledProcessError, OSError):
                    pass
            if self._esptool_command is None:
                self.sres("esptool not found on path\n")
                return

        pargs = [self._esptool_command, "--port", portname]
        if espcommand == "erase":
            pargs.append("erase_flash")
        if espcommand == "esp32":
            pargs.extend(["--chip", "esp32", "write_flash", "-z", "0x1000"])
            pargs.append(binfile)
        if espcommand == "esp8266":
            pargs.extend(["--baud", "460800", "write_flash", "--flash_size=detect", "-fm", "dio", "0"])
            pargs.append(binfile)
        self.sresSYS("Executing:\n  {}\n\n".format(" ".join(pargs)))
        process = subprocess.Popen(pargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in process.stdout:
            x = line.decode()
            self.sres(x)
            if x[:12] == "Connecting..":
                self.sresSYS("[Press the PRG button now if required]\n")
        for line in process.stderr:
            self.sres(line.decode(), n04count=1)

    def mpycross(self, mpycrossexe, pyfile):
        pargs = [mpycrossexe, pyfile]
        self.sresSYS("Executing:  {}\n".format(" ".join(pargs)))
        process = subprocess.Popen(pargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in process.stdout:
            self.sres(line.decode())
        for line in process.stderr:
            self.sres(line.decode(), n04count=1)

    def receivestream(self, bseekokay, bwarnokaypriors=True, b5secondtimeout=False, bfetchfilecapture_nchunks=0):
        n04count = 0
        brebootdetected = False
        res = [ ]
        for j in range(2):  # for restarting the chunking when interrupted
            if self.workingserialchunk is None:
                self.workingserialchunk = yieldserialchunk(self.workingserial or self.workingsocket or self.workingwebsocket)

            indexprevgreaterthansign = -1
            index04line = -1
            for i, rline in enumerate(self.workingserialchunk):
                assert rline is not None

                # warning message when we are waiting on an OK
                if bseekokay and bwarnokaypriors and (rline != b'OK') and (rline != b'>') and rline.strip():
                    self.sres("\n[missing-OK]")

                # the main interpreting loop
                if rline == b'OK' and bseekokay:
                    if i != 0 and bwarnokaypriors:
                        self.sres("\n\n[Late OK]\n\n")
                    bseekokay = False

                # one of 2 Ctrl-Ds in the return from execute in paste mode
                elif rline == b'\x04':
                    n04count += 1
                    index04line = i

                # leaving condition where OK...x04...x04...> has been found in paste mode
                elif rline == b'>' and n04count >= 2 and not bseekokay:
                    if n04count != 2:
                        self.sres("[too many x04s %d]" % n04count)
                    break

                elif rline == b'':
                    if b5secondtimeout:
                        self.sres("[Timed out waiting for recognizable response]\n", 31)
                        return False
                    self.sres(".")  # dot holding position to prove it's alive

                elif rline == b'Type "help()" for more information.\r\n':
                    brebootdetected = True
                    self.sres(rline.decode(), n04count=n04count)

                elif rline == b'>':
                    indexprevgreaterthansign = i
                    self.sres('>', n04count=n04count)

                # looks for ">>> "
                elif rline == b' ' and brebootdetected and indexprevgreaterthansign == i-1:
                    self.sres("[reboot detected %d]" % n04count)
                    self.enterpastemode()  # this is unintentionally recursive, but after a reboot has been seen we need to get into paste mode
                    self.sres(' ', n04count=n04count)
                    break

                # normal processing of the string of bytes that have come in
                else:
                    try:
                        ur = rline.decode()
                    except UnicodeDecodeError:
                        ur = str(rline)
                    if not wifimessageignore.match(ur):
                        if bfetchfilecapture_nchunks:
                            if res and res[-1][-2:] != "\r\n":
                                res[-1] = res[-1] + ur   # need to rejoin strings that have been split on the b"OK" string by the lexical parser
                            else:
                                res.append(ur)
                            if (i%10) == 0:
                                self.sres("%d%% fetched\n" % int(len(res)/bfetchfilecapture_nchunks*100 + 0.5), clear_output=True)
                        else:
                            self.sres(ur, n04count=n04count)

            # else on the for-loop, means the generator has ended at a stop iteration
            # this happens with Keyboard interrupt, and generator needs to be rebuilt
            else:  # of the for-command
                self.workingserialchunk = None
                continue

            break   # out of the for loop
        return res if bfetchfilecapture_nchunks else True


    def sendtofile(self, destinationfilename, bmkdir, bappend, bbinary, bquiet, filecontents):
        if not (self.workingserial or self.workingwebsocket):
            self.sres("File transfers not implemented for sockets\n", 31)
            return

        if not bbinary:
            lines = filecontents.splitlines(True)
            maxlinelength = max(map(len, lines), default=0)
            if maxlinelength > 250:
                self.sres("Line length {} exceeds maximum for line ascii files, try --binary\n".format(maxlinelength), 31)
                return

        sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
        #def sswrite(x):  self.sres(str(x)); lsswrite(x)

        if bmkdir:
            dseq = [ d  for d in destinationfilename.split("/")[:-1]  if d]
            if dseq:
                sswrite(b'import os\r\n')
                for i in range(len(dseq)):
                    sswrite('try:  os.mkdir({})\r\n'.format(repr("/".join(dseq[:i+1]))).encode())
                    sswrite(b'except OSError:  pass\r\n')

        fmodifier = ("a" if bappend else "w")+("b" if bbinary else "")
        if bbinary:
            sswrite(b"import ubinascii; O6 = ubinascii.a2b_base64\r\n")
        sswrite("O=open({}, '{}')\r\n".format(repr(destinationfilename), fmodifier).encode())
        sswrite(b'\r\x04')  # intermediate execution
        self.receivestream(bseekokay=True)
        clear_output = True  # set this to False to help with debugging
        if bbinary:
            if type(filecontents) == str:
                filecontents = filecontents.encode()
                
            chunksize = 30
            nchunks = int(len(filecontents)/chunksize)

            for i in range(nchunks+1):
                bchunk = filecontents[i*chunksize:(i+1)*chunksize]
                sswrite(b'O.write(O6("')
                sswrite(binascii.b2a_base64(bchunk)[:-1])
                sswrite(b'"))\r\n')
                if (i%10) == 9:
                    sswrite(b'\r\x04')  # intermediate executions
                    self.receivestream(bseekokay=True)
                    if not bquiet:
                        self.sres("{}%, chunk {}".format(int((i+1)/(nchunks+1)*100), i+1), clear_output=clear_output)
            self.sres("Sent {} bytes in {} chunks to {}.\n".format(len(filecontents), i+1, destinationfilename), clear_output=not bquiet)
            
        else:
            i = -1
            linechunksize = 5

            if bappend:
                sswrite("O.write('\\n')\r\n".encode())   # avoid line concattenation on appends
            for i, line in enumerate(lines):
                sswrite("O.write({})\r\n".format(repr(line)).encode())
                if (i%linechunksize) == linechunksize-1:
                    sswrite(b'\r\x04')  # intermediate executions
                    self.receivestream(bseekokay=True)
                    if not bquiet:
                        self.sres("{}%, line {}\n".format(int((i+1)/(len(lines)+1)*100), i+1), clear_output=clear_output)
            self.sres("Sent {} lines ({} bytes) to {}.\n".format(i+1, len(filecontents), destinationfilename), clear_output=(clear_output and not bquiet))

        sswrite("O.close()\r\n".encode())
        sswrite("del O\r\n".encode())
        sswrite(b'\r\x04')
        self.receivestream(bseekokay=True)

    def fetchfile(self, sourcefilename, bbinary, bquiet):
        if not (self.workingserial or self.workingwebsocket):
            self.sres("File transfers not implemented for sockets\n", 31)
            return None
        sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
        
        if bbinary:
            chunksize = 30
            sswrite(b"import sys,os;O7=sys.stdout.write\r\n")
            sswrite(b"import ubinascii;O8=ubinascii.b2a_base64\r\n")
            sswrite("O=open({},'rb')\r\n".format(repr(sourcefilename)).encode())
            sswrite(b"O9=bytearray(%d)\r\n" % chunksize)
            sswrite("O4=os.stat({})[6]\r\n".format(repr(sourcefilename)).encode())
            sswrite(b"print(O4)\r\n")
            sswrite(b'\r\x04')   # intermediate execution to get chunk size
            chunkres = self.receivestream(bseekokay=True, bfetchfilecapture_nchunks=-1)
            try:
                nbytes = int("".join(chunkres))
            except ValueError:
                self.sres(str(chunkres))
                return None
                
            sswrite(b"O7(O8(O.read(O4%%%d)))\r\n" % chunksize)  # get sub-block
            sswrite(b"while O.readinto(O9): O7(O8(O9))\r\n")
            sswrite(b"O.close(); del O,O7,O8,O9,O4\r\n")
            sswrite(b'\r\x04')
            chunks = self.receivestream(bseekokay=True, bfetchfilecapture_nchunks=nbytes//chunksize+1)
            rres = [ ]
            for ch in chunks:
                try:
                    rres.append(binascii.a2b_base64(ch))
                except binascii.Error as e:
                    self.sres(str(e))
                    self.sres(str([ch]))
            res = b"".join(rres)
            if not bquiet:
                self.sres("Fetched {}={} bytes from {}.\n".format(len(res), nbytes, sourcefilename), clear_output=True)
            return res
        self.sres("non-binary mode not implemented")
        return None


    def enterpastemode(self, verbose=True):         # I don't think we ever make a connection and it's still in paste mode (this is revoked on connection break, but I am trying to use exitpastemode to make it better)
        # now sort out connection situation
        if self.workingserial or self.workingwebsocket:
            sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
            
            time.sleep(0.2)   # try to give a moment to connect before issuing the Ctrl-C
            sswrite(b'\x03')    # ctrl-C: kill off running programs
            time.sleep(0.1)
            l = self.workingserialreadall()
            if l[-6:] == b'\r\n>>> ':
                if verbose:
                    self.sres('repl is in normal command mode\n')
                    self.sres('[\\r\\x03\\x03] ')
                    self.sres(str(l))
            else:
                if verbose:
                    self.sres('normal repl mode not detected ')
                    self.sres(str(l))
                    self.sres('\nnot command mode\n')
                    
                
            #self.workingserial.write(b'\r\x02')        # ctrl-B: leave paste mode if still in it <-- doesn't work as when not in paste mode it reboots the device
            sswrite(b'\r\x01')        # ctrl-A: enter raw REPL
            time.sleep(0.1)
            l = self.workingserialreadall()
            if verbose and l:
                self.sres('\n[\\r\\x01] ')
                self.sres(str(l))
            sswrite(b'1\x04')         # single character program to run so receivestream works
        else:
            self.workingsocket.write(b'1\x04')         # single character program "1" to run so receivestream works
            
        return self.receivestream(bseekokay=True, bwarnokaypriors=False, b5secondtimeout=True)
        

        
    def exitpastemode(self, verbose):   # try to make it clean
        if self.workingserial or self.workingwebsocket:
            sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
            try:
                sswrite(b'\r\x03\x02')    # ctrl-C; ctrl-B to exit paste mode
                time.sleep(0.1)
                l = self.workingserialreadall()
            except serial.SerialException as e:
                self.sres("serial exception on close {}\n".format(str(e)))
                return
            
            if verbose:
                self.sresSYS('attempt to exit paste mode\n')
                self.sresSYS('[\\r\\x03\\x02] ')
                self.sres(str(l))
        

    def writebytes(self, bytestosend):
        if self.workingserial:
            nbyteswritten = self.workingserial.write(bytestosend)
            return ("serial.write {} bytes to {} at baudrate {}\n".format(nbyteswritten, self.workingserial.port, self.workingserial.baudrate))
        elif self.workingwebsocket:
            nbyteswritten = self.workingwebsocket.send(bytestosend)
            return ("serial.write {} bytes to {}\n".format(nbyteswritten, "websocket"))  # don't worry; it always includes more bytes than you think
        else:
            nbyteswritten = self.workingsocket.write(bytestosend)
            return ("serial.write {} bytes to {}\n".format(nbyteswritten, str(self.workingsocket)))

    def sendrebootmessage(self):
        if self.workingserial:
            self.workingserial.write(b"\x03\r")  # quit any running program
            self.workingserial.write(b"\x02\r")  # exit the paste mode with ctrl-B
            self.workingserial.write(b"\x04\r")  # soft reboot code
        elif self.workingwebsocket:
            self.workingwebsocket.send(b"\x03\r")  # quit any running program
            self.workingwebsocket.send(b"\x02\r")  # exit the paste mode with ctrl-B
            self.workingwebsocket.send(b"\x04\r")  # soft reboot code

    def writeline(self, line):
        if self.workingserial:
            self.workingserial.write(line.encode("utf8"))
            self.workingserial.write(b'\r\n')
        elif self.workingwebsocket:
            self.workingwebsocket.send(line.encode("utf8"))
            self.workingwebsocket.send(b'\r\n')
        else:
            self.workingsocket.write(line.encode("utf8"))
            self.workingsocket.write(b'\r\n')

    def serialexists(self):
        return self.workingserial or self.workingsocket or self.workingwebsocket
        
        
