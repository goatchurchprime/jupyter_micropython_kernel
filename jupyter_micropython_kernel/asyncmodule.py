#!/usr/bin/env python3

import sys, logging
import asyncio, serial

EXT_PROMPT = '[serPROMPT>'
EXT_PROMPT_CONTINUATION = '[serPROMPT+'
EXT_PROMPT_OUTPUT = '[serPROMPT:'

logging.basicConfig(level=logging.WARNING, format='%(lineno)d - %(levelname)s - %(message)s')
logger = logging

eloop = asyncio.get_event_loop()
eloop.set_debug(True)


# this encapsulates a state machine for the condition of the serial line
serialstate = "notconnected"
workingserial = None
serialinitialsignal = asyncio.Queue()

def swrite(msg, prompt):
    sys.stdout.write(msg)
    sys.stdout.write(prompt)
    sys.stdout.flush()

# print(_) to get last variable result
async def transferline():
    global replstate, serialstate, workingserial
    while True:
      try:
        line = await eloop.run_in_executor(None, sys.stdin.readline)
        
        if line[:6] == "%%CONN":
            bline = line[6:].strip() or "/dev/ttyUSB0 115200"
            bline = bline.split()
            if workingserial is not None:
                swrite("Closing old serial\n", EXT_PROMPT_OUTPUT)
                workingserial.close() 
                workingserial = None
            swrite("Connecting to Serial({}, {})\n".format(bline[0], bline[1]), EXT_PROMPT_OUTPUT)
            try:
                workingserial = serial.Serial(bline[0], int(bline[1]))
            except serial.SerialException as e:
                swrite(e.strerror, EXT_PROMPT)

            # this cycle could be done via the sermessages queue
            if workingserial is not None:
                serialstate = "justconnected"
                serialinitialsignal.put_nowait("go")  # unstick the serialinitialsignal.get() at start of serreadchar()

        elif line.strip() == "%%C":
            if serialstate == "rawmodereceiving":
                workingserial.write(b'\r\x03')        # ctrl-C to interrupt running program
                
        elif workingserial is None:
            swrite("Serial connection state is {} {}\n".format(serialstate, str([line])), 
                   (EXT_PROMPT if line.strip() == "%%D" else EXT_PROMPT_CONTINUATION))
        
        elif serialstate != "rawmodeready":
            if line.strip():  # trim out loose '\n's that get through
                swrite("DSerial connection state is {} {}\n".format(serialstate, str([line])), 
                       (EXT_PROMPT if line.strip() == "%%D" else EXT_PROMPT_CONTINUATION))
                   
        elif line.strip() == "%%REBOOT":
            workingserial.write(b"\x02\r")  # exit the paste mode with ctrl-B
            workingserial.write(b"\x04\r")  # soft reboot code
            serialstate = "justconnected"   # set into state where it re-enters the paste mode

        elif line.strip() == "%%D":
            workingserial.write(b"\x04\r")
            serialstate = "rawmodecodesent"
            
        else:
            workingserial.write((line+"\r").encode("utf8"))
            swrite("\n", EXT_PROMPT_CONTINUATION)
      except Exception as e:
        print("eeek", type(e), e)

def bytecharlist(b):  return [chr(c).encode("utf8")  for c in b]
srr = bytecharlist(b'raw REPL; CTRL-B to exit\r\n>')
sok = bytecharlist(b'OK')
sstop = bytecharlist(b'\x04>')  # there's two \x04s if not an exception

recbuffer = [ ]
async def serreadchar():
    global replstate, serialstate, workingserial
    while True:
      try:
        # this should await not zero
        if workingserial is None:
            await serialinitialsignal.get()    # effectively waiting for workingserial to not be None
        elif serialstate == "justconnected":
            workingserial.write(b'\r\x03\x03') # ctrl-C twice: interrupt any running program
            serialstate = "waitforinitialclear"
        elif serialstate == "waitforinitialclear":
            while workingserial.inWaiting() != 0:
                workingserial.read(1)
            workingserial.write(b'\r\x01')     # ctrl-A: enter raw REPL
            serialstate = "rawmoderequested"
        else:
            try:
                c = await eloop.run_in_executor(None, workingserial.read, 1)
            except serial.SerialException as e:
                swrite(str(e), EXT_PROMPT)   # e.strerror is None (how?)
                workingserial = None
                serialstate = "notconnected"
                continue
                
            recbuffer.append(c)
            if serialstate == "rawmoderequested":
                if recbuffer[-1] == b'>' and recbuffer[-len(srr):] == srr:
                    serialstate = "rawmodeready"
                    swrite("ready", EXT_PROMPT)
                    recbuffer.clear()
                
        if serialstate == "rawmodecodesent":
            if recbuffer[-len(sok):] == sok:
                serialstate = "rawmodereceiving"
                recbuffer.clear()
        
        if serialstate == "rawmodereceiving":
            if recbuffer[-len(sstop):] == sstop:
                serialstate = "rawmodeready"
                logger.info("%% {}".format(serialstate))
                recbuffer.clear()
                swrite("", EXT_PROMPT)
                
            elif len(recbuffer) and recbuffer[-1] == b'\n':
                if recbuffer[0] == b"\x04":
                    del recbuffer[:1]  # remove the 0x04 that demarks the start of the exception
                swrite(b"".join(recbuffer).decode("utf8"), EXT_PROMPT_OUTPUT)
                recbuffer.clear()
        
        await asyncio.sleep(0.001)
      except Exception as e:
        print("ddeeek", type(e), e)

swrite("%%D to end block of code", EXT_PROMPT)
t1 = eloop.create_task(serreadchar())
t2 = eloop.create_task(transferline())
eloop.run_forever()





    

