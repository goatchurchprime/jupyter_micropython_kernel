#!/usr/bin/env python3

# code taken from: https://bitbucket.org/goatchurch/bbhquad/src/14a0120f951ca10cbe4acb67efd5f9dc7a22684b/polarcode/websocketmodule.py?at=master&fileviewer=file-view-default

import sys, logging
import asyncio, serial

EXT_PROMPT = '[serPROMPT>'
EXT_PROMPT_CONTINUATION = '[serPROMPT+'

#logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
logging.basicConfig(level=logging.INFO, format='%(lineno)d - %(levelname)s - %(message)s')
logger = logging

eloop = asyncio.get_event_loop()
eloop.set_debug(True)

sermessages = asyncio.Queue()
ser = None
replstate = "unknown"     # rawrequested, rawmode
commandstate = "unknown"  # ready, streamingto, awaitingresult, returningresult

# print(_) to get last variable result
async def transferline():
    global replstate, commandstate, ser
    while True:
      try:
        line = await eloop.run_in_executor(None, sys.stdin.readline)
        if line[:6] == "%%CONN":
            bline = line[6:].strip() or "/dev/ttyUSB0 115200"
            bline = bline.split()
            logger.info(str(bline))
            try:
                ser = serial.Serial(bline[0], int(bline[1]))
            except serial.SerialException:
                logger.info("NNNope")
                ser = None
            except Exception as e:
                print("what", type(e), e)
            if ser is not None:
                print(ser)
                ser.write(b'\r\x03\x03') # ctrl-C twice: interrupt any running program
                while ser.inWaiting() != 0:
                    ser.read(1)
                ser.write(b'\r\x01') # ctrl-A: enter raw REPL
                replstate = "rawrequested"
                logger.info("%%{}".format(replstate))
                sys.stdout.write("\n")
                sys.stdout.write(EXT_PROMPT_CONTINUATION)
                sys.stdout.flush()
                sermessages.put_nowait("conn")
                continue
            else:
                sys.stdout.write("   serial connection failed\n")
                line = "fff"

        if line.strip() == "%%S":
            sys.stdout.write(str([replstate, "serinwaiting", ser, (ser and ser.inWaiting()), recbuffer]))
            sys.stdout.write("\n")
            sys.stdout.write(EXT_PROMPT)
            sys.stdout.flush()
            continue
                
        if ser is None:
            sys.stdout.write(str(line))
            sys.stdout.write("   We have no connection yet\n")
            if line.strip() == "%%D":
                sys.stdout.write(EXT_PROMPT)
            else:
                sys.stdout.write(EXT_PROMPT_CONTINUATION)
            sys.stdout.flush()
            continue
            
        if line[:2] == "%%":
            line = line[2:].strip()
            if line[0] == "S":
                print(replstate, "serinwaiting", ser.inWaiting(), recbuffer)

            if line[0] == "C":
                ser.write(b'\r\x03') # ctrl-B ctrl-C twice: interrupt any running program
                
            elif line[0] == "R":  # request raw webrepl
                ser.write(b'\r\x03\x03') # ctrl-C twice: interrupt any running program
                while ser.inWaiting() != 0:
                    ser.read(1)
                ser.write(b'\r\x01') # ctrl-A: enter raw REPL
                replstate = "rawrequested"
                logger.info("%%{}".format(replstate))
                
            elif line[0] == "D":  # end of series
                commandstate = "awaitingresult"
                await eloop.run_in_executor(None, ser.write, b"\x04\r")
                print("%%", commandstate)
                
            elif line[0] == "F":  # should always be empty
                print("fetching")
                while ser.inWaiting() != 0:
                    print(ser.read(1), end="")
                print(".....")

        else:
            if commandstate == "ready":
                commandstate = "streamingto"
            await eloop.run_in_executor(None, ser.write, (line+"\r").encode("utf8"))
            sys.stdout.write("\n")
            sys.stdout.write(EXT_PROMPT_CONTINUATION)
            sys.stdout.flush()
            logger.info("%% {}".format(commandstate))
      except Exception as e:
        print("eeek", type(e), e)

srr = bytearray(b'raw REPL; CTRL-B to exit\r\n>')
sok = bytearray(b'OK')
sstop = bytearray(b'\x04>')  # there's two \x04s if not an exception
recbuffer = [ ]
async def serreadchar():
    global replstate, commandstate
    while True:
      try:
        # this should await not zero
        while ser is None:
            logger.info("Type %%CONN to connect")
            await sermessages.get()
            
        c = await eloop.run_in_executor(None, ser.read, 1)
        
        recbuffer.append(c)
        if replstate == "rawrequested" and recbuffer[-1] == b'>':
            if bytearray(ord(b) for b in recbuffer[-len(srr):]) == srr:  # there has to be a better way
                replstate = "rawmode"
                commandstate = "ready"
                logger.info("%% {} {}".format(replstate, commandstate))
                sys.stdout.write("\n")
                sys.stdout.write("hip")
                sys.stdout.write("\n")
                sys.stdout.write(EXT_PROMPT_CONTINUATION)
                sys.stdout.write("\n")
                sys.stdout.write(EXT_PROMPT)
                sys.stdout.flush()
                recbuffer.clear()
                sys.stdout.flush()
                
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
                sys.stdout.write(EXT_PROMPT)
                sys.stdout.flush()
                
        if commandstate == "returningresult" and len(recbuffer) and recbuffer[-1] == b'\n':
            sys.stdout.write(b"".join(recbuffer).decode("utf8"))
            sys.stdout.write(EXT_PROMPT_CONTINUATION)
            recbuffer.clear()
        
        await asyncio.sleep(0.001)
      except Exception as e:
        print("ddeeek", type(e), e)

print("%%R to enter raw webrepl mode")
print("%%D to end block of code")
sys.stdout.write(EXT_PROMPT)
sys.stdout.flush()

t1 = eloop.create_task(serreadchar())
t2 = eloop.create_task(transferline())
eloop.run_forever()





    

