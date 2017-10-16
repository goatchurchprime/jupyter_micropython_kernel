import logging, sys, time, os, re, base64, subprocess
import serial, socket, serial.tools.list_ports, select
import websocket  # the old non async one

serialtimeout = 0.5
serialtimeoutcount = 10

# see http://ascii-table.com/ansi-escape-sequences.php for colour codes on lines
wifimessageignore = re.compile("(\x1b\[[\d;]*m)?[WI] \(\d+\) (wifi|system_api|modsocket|phy|event|cpu_start|heap_init): ")

# this should take account of the operating system
def guessserialport():  
    return sorted([x[0]  for x in serial.tools.list_ports.grep("")])

# merge uncoming serial stream and break at OK, \x04, >, \r\n, and long delays 
# (must make this a member function so does not have to switch on the type of s)
def yieldserialchunk(s):
    res = [ ]
    n = 0
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
            else:  # websocket
                r,w,e = select.select([s], [], [], serialtimeout)
                if r:
                    b = s.recv()
                    if type(b) == str:
                        b = b.encode("utf8")   # handle fact that strings come back from this interface
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
    def __init__(self, sres):
        self.workingserial = None
        self.workingsocket = None
        self.workingwebsocket = None
        self.workingserialchunk = None
        self.sres = sres

    def workingserialreadall(self):  # usually used to clear the incoming buffer, results are printed out rather than used
        if self.workingserial:
            return self.workingserial.read_all()
            
        if self.workingwebsocket:
            res = [ ]
            while True:
                r,w,e = select.select([self.workingwebsocket],[],[],0)
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

    def disconnect(self, raw):
        if not raw:
            self.exitpastemode()
        self.workingserialchunk = None
        if self.workingserial is not None:
            self.sres("\nClosing serial {}\n".format(str(self.workingserial)))
            self.workingserial.close() 
            self.workingserial = None
        if self.workingsocket is not None:
            self.sres("\nClosing socket {}\n".format(str(self.workingsocket)))
            self.workingsocket.close() 
            self.workingsocket = None
        if self.workingwebsocket is not None:
            self.sres("\nClosing websocket {}\n".format(str(self.workingwebsocket)))
            self.workingwebsocket.close() 
            self.workingwebsocket = None

    def serialconnect(self, portname, baudrate):
        self.disconnect(False)

        if type(portname) is int:
            possibleports = guessserialport()
            if possibleports:
                portname = possibleports[portname]
                if len(possibleports) > 1:
                    self.sres("Found serial ports {}: \n".format(", ".join(possibleports)))
            else:
                self.sres("No possible ports found")
                portname = ("COM4" if sys.platform == "win32" else "/dev/ttyUSB0")
            
        self.sres("Connecting to Serial {} baud={}\n".format(portname, baudrate))
        try:
            self.workingserial = serial.Serial(portname, baudrate, timeout=serialtimeout)
        except serial.SerialException as e:
            self.sres(e.strerror)
            self.sres("\n")
            possibleports = guessserialport()
            if possibleports:
                self.sres("\nTry one of these ports:\n  {}".format("\n  ".join(possibleports)))
            else:
                self.sres("\nAre you sure your ESP-device is plugged in?")
            return
            
        for i in range(5001):
            if self.workingserial.isOpen():
                break
            time.sleep(0.01)
        if i != 0:
            self.sres("Waited {} seconds for isOpen()\n".format(i*0.01))
        
    def socketconnect(self, ipnumber, portnumber):
        self.disconnect(False)

        self.sres("Connecting to socket ({} {})\n".format(ipnumber, portnumber))
        s = socket.socket()
        self.sres("Connecting to socket ({} {})\n".format(ipnumber, portnumber))
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
        self.disconnect(False)
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
        self.disconnect(True)
        if type(portname) is int:
            possibleports = guessserialport()
            if possibleports:
                portname = possibleports[portname]
                if len(possibleports) > 1:
                    self.sres("Found serial ports {}: \n".format(", ".join(possibleports)))
            else:
                self.sres("No possible ports found")
                portname = ("COM4" if sys.platform == "win32" else "/dev/ttyUSB0")

        pargs = ["esptool.py", "--port", portname]
        if espcommand == "erase":
            pargs.append("erase_flash")
        if espcommand == "esp32":
            pargs.extend(["--chip", "esp32", "write_flash", "-z", "0x1000"])
            pargs.append(binfile)
        if espcommand == "esp8266":
            pargs.extend(["--baud", "460800", "write_flash", "--flash_size=detect", "0"])
            pargs.extend(["--flash_mode", "dio"])
            pargs.append(binfile)
        self.sres("Executing:\n  {}\n\n".format(" ".join(pargs)))
        process = subprocess.Popen(pargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for line in process.stdout:
            self.sres(line.decode())
        for line in process.stderr:
            self.sres(line.decode(), n04count=1)


    def receivestream(self, bseekokay, bwarnokaypriors=True, b5secondtimeout=False):
        n04count = 0
        brebootdetected = False
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
                        self.sres("[Timed out waiting for recognizable response]\n")
                        break
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
                        self.sres(ur, n04count=n04count)
        
            # else on the for-loop, means the generator has ended at a stop iteration
            # this happens with Keyboard interrupt, and generator needs to be rebuilt
            else:  # of the for-command 
                self.workingserialchunk = None
                continue
                    
            break   # out of the for loop

    def sendtofile(self, destinationfilename, bappend, bbinary, filecontents):
        if self.workingserial or self.workingwebsocket:
            sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
            fmodifier = ("a" if bappend else "w")+("b" if bbinary else "")
            if bbinary:
                sswrite(b"import ubinascii; O6 = ubinascii.a2b_base64\r\n")
            sswrite("O=open({}, '{}')\r\n".format(repr(destinationfilename), fmodifier).encode())
            if bbinary:
                chunksize = 30
                nchunks = int(len(filecontents)/chunksize)
                for i in range(nchunks+1):
                    bchunk = filecontents[i*chunksize:(i+1)*chunksize]
                    sswrite(b'O.write(O6("')
                    sswrite(base64.encodebytes(bchunk)[:-1])
                    sswrite(b'"))\r\n')
                    if (i%10) == 9:
                        sswrite(b'\r\x04')  # intermediate executions
                        self.receivestream(bseekokay=True)
                        self.sres("{}%, chunk {}".format(int((i+1)/(nchunks+1)*100), i+1), clear_output=True)
                self.sres("Sent {} bytes in {} chunks.".format(len(filecontents), i+1), clear_output=True)
                
            else:
                lines = filecontents.splitlines(True)
                i = -1
                for i, line in enumerate(lines):
                    sswrite("O.write({})\r\n".format(repr(line)).encode())
                    if (i%10) == 9:
                        sswrite(b'\r\x04')  # intermediate executions
                        self.receivestream(bseekokay=True)
                        self.sres("{}%, line {}\n".format(int((i+1)/(len(lines)+1)*100), i+1), clear_output=True)
                self.sres("Sent {} lines ({} bytes).".format(i+1, len(filecontents)), clear_output=True)

            sswrite("O.close()\r\n".encode())
            sswrite("del O\r\n".encode())
            sswrite(b'\r\x04')
            self.receivestream(bseekokay=True)
            
        else:
            self.sres("File transfers implemented for sockets\n")

    def enterpastemode(self):         # I don't think we ever make a connection and it's still in paste mode (this is revoked on connection break, but I am trying to use exitpastemode to make it better)
        # now sort out connection situation
        if self.workingserial or self.workingwebsocket:
            sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
            
            sswrite(b'\r\x03\x03')    # ctrl-C: kill off running programs
            time.sleep(0.1)
            l = self.workingserialreadall()
            if l[-6:] == b'\r\n>>> ':
                self.sres('repl is in normal command mode\n')
                self.sres('[\\r\\x03\\x03] ')
                self.sres(str(l))
            else:
                self.sres('normal repl mode not detected ')
                self.sres(str(l))
                self.sres('\nnot command mode\n')
                    
                
            #self.workingserial.write(b'\r\x02')        # ctrl-B: leave paste mode if still in it <-- doesn't work as when not in paste mode it reboots the device
            sswrite(b'\r\x01')        # ctrl-A: enter raw REPL
            time.sleep(0.1)
            l = self.workingserialreadall()
            if l:
                self.sres('\n[\\r\\x01] ')
                self.sres(str(l))
            sswrite(b'1\x04')         # single character program to run so receivestream works
        else:
            self.workingsocket.write(b'1\x04')         # single character program to run so receivestream works
        self.receivestream(bseekokay=True, bwarnokaypriors=False)
        
    def exitpastemode(self):   # try to make it clean
        if self.workingserial or self.workingwebsocket:
            sswrite = self.workingserial.write  if self.workingserial  else self.workingwebsocket.send
            try:
                sswrite(b'\r\x03\x02')    # ctrl-C; ctrl-B to exit paste mode
                time.sleep(0.1)
                l = self.workingserialreadall()
            except serial.SerialException as e:
                self.sres("serial exceptionon close {}\n".format(str(e)))
                return
            
            self.sres('attempt to exit past mode\n')
            self.sres('[\\r\\x03\\x02] ')
            self.sres(str(l))
        

    def writebytes(self, bytestosend):
        if self.workingserial:
            nbyteswritten = self.workingserial.write(bytestosend)
            return ("serial.write {} bytes to {} at baudrate {}".format(nbyteswritten, self.workingserial.port, self.workingserial.baudrate))
        elif self.workingwebsocket:
            nbyteswritten = self.workingwebsocket.send(bytestosend)
            return ("serial.write {} bytes to {}".format(nbyteswritten, "websocket"))
        else:
            nbyteswritten = self.workingsocket.write(bytestosend)
            return ("serial.write {} bytes to {}".format(nbyteswritten, str(self.workingsocket)))

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
        
        
