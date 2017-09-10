#!/usr/bin/env python3

# code taken from: https://bitbucket.org/goatchurch/bbhquad/src/14a0120f951ca10cbe4acb67efd5f9dc7a22684b/polarcode/websocketmodule.py?at=master&fileviewer=file-view-default

import sys, logging
import asyncio, serial

#logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO, format='%(lineno)d - %(levelname)s - %(message)s')
logger = logging

eloop = asyncio.get_event_loop()
eloop.set_debug(True)

ser = None
replstate = "unknown"     # rawrequested, rawmode
commandstate = "unknown"  # ready, streamingto, awaitingresult, returningresult

# print(_) to get last variable result

async def transferline():
    global replstate, commandstate, ser
    while True:
        line = await eloop.run_in_executor(None, sys.stdin.readline)
        if line[:2] == "%%":
            line = line[2:].strip()
                
                
            if line == "CONN":
                ser = serial.Serial("/dev/ttyUSB0", 115200)
                print(ser)

            if line == "S":
                print(replstate, "serinwaiting", ser.inWaiting(), recbuffer)

            if line == "C":
                ser.write(b'\x02\r\x03\x03') # ctrl-B ctrl-C twice: interrupt any running program
                
            elif line == "R":  # request raw webrepl
                ser.write(b'\r\x03\x03') # ctrl-C twice: interrupt any running program
                while ser.inWaiting() != 0:
                    ser.read(1)
                ser.write(b'\r\x01') # ctrl-A: enter raw REPL
                replstate = "rawrequested"
                logger.info("%%{}".format(replstate))
                
            elif line == "D":  # end of series
                commandstate = "awaitingresult"
                await eloop.run_in_executor(None, ser.write, b"\x04\r")
                print("%%", commandstate)
                
            elif line == "F":  # should always be empty
                print("fetching")
                while ser.inWaiting() != 0:
                    print(ser.read(1), end="")
                print(".....")

        else:
            if commandstate == "ready":
                commandstate = "streamingto"
            await eloop.run_in_executor(None, ser.write, (line+"\r").encode("utf8"))
            logger.info("%% {}".format(commandstate))


srr = bytearray(b'raw REPL; CTRL-B to exit\r\n>')
sok = bytearray(b'OK')
sstop = bytearray(b'\x04\x04>')
recbuffer = [ ]
async def serreadchar():
    global replstate, commandstate
    while True:

        if ser == None:
            print("Type %%CONN to connect")
            await asyncio.sleep(10)
            continue
            
        c = await eloop.run_in_executor(None, ser.read, 1)
        
        recbuffer.append(c)
        if replstate == "rawrequested" and recbuffer[-1] == b'>':
            if bytearray(ord(b) for b in recbuffer[-len(srr):]) == srr:  # there has to be a better way
                replstate = "rawmode"
                commandstate = "ready"
                logger.info("%% {} {}".format(replstate, commandstate))
                recbuffer.clear()
                
        if commandstate == "awaitingresult":
            if bytearray(ord(b) for b in recbuffer[-len(sok):]) == sok:
                commandstate = "returningresult"
                logger.info("%% {}".format(commandstate))
                recbuffer.clear()
        
        if commandstate == "returningresult":
            if bytearray(ord(b) for b in recbuffer[-len(sstop):]) == sstop:
                commandstate = "ready"
                logger.info("%% {}".format(commandstate))
                recbuffer.clear()
            
        if commandstate == "returningresult" and len(recbuffer) and recbuffer[-1] == b'\n':
            print(commandstate, [bytearray(ord(b)  for b in recbuffer)])
            recbuffer.clear()
        
        await asyncio.sleep(0.001)

print("%%R to enter raw webrepl mode")
print("%%D to end block of code")

t1 = eloop.create_task(serreadchar())
t2 = eloop.create_task(transferline())
eloop.run_forever()





    

