from ipykernel.kernelbase import Kernel
from pexpect import replwrap, EOF
import pexpect

from subprocess import check_output
import os.path

import re, logging
import signal

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

EXT_PROMPT = '[serPROMPT>'
EXT_PROMPT_CONTINUATION = '[serPROMPT+'
EXT_PROMPT_OUTPUT = '[serPROMPT:'


class MicroPythonKernel(Kernel):
    implementation = 'micropython_kernel'
    implementation_version = "v2"

    banner = "MicroPython Serializer"

    language_info = {'name': 'micropython',
                     'codemirror_mode': 'python',
                     'mimetype': 'text/python',
                     'file_extension': '.py'}

    def __init__(self, **kwargs):
        Kernel.__init__(self, **kwargs)
        self.silent = False
        self.startasyncmodule()

    def startasyncmodule(self):
        self.asyncmodule = pexpect.spawn("python", ['-m', 'jupyter_micropython_kernel.asyncmodule.py'], echo=False, encoding='utf-8', codec_errors='replace')
        self.asyncmodule.expect_exact([EXT_PROMPT])
        logger.info(["init", self.asyncmodule.before])

    def sendcommand(self, command):
        cmdlines = command.splitlines(True)
        
        # Instantiate a connection %%CONN port baudrate
        if cmdlines[0][:6] == "%%CONN":
            self.asyncmodule.sendline(cmdlines[0])   # connection type
            
        # copy cell contents into a file on the device (by hackily saving it)
        elif cmdlines[0][:6] == "%%FILE":
            fname = cmdlines[0].split()[1]
            self.asyncmodule.sendline("O=open({}, 'w')".format(repr(fname)))
            line1 = 1 if (len(cmdlines)<=1 or cmdlines[1].strip()) else 2  # trim first blank line if blank
            for line in cmdlines[line1:]:
                self.asyncmodule.sendline("O.write({})".format(repr(line)))
            self.asyncmodule.sendline("O.close()")
            self.asyncmodule.sendline("%%D")
            self.process_output("{} lines send".format(len(cmdlines)-line1))

        # run the cell contents as normal
        else:
            for line in cmdlines:
                logger.debug(["sending:", line])
                self.asyncmodule.send(line)   # send straight through.  Buffering at async end
            self.asyncmodule.sendline("\n%%D")

    def receivestream(self):
        pos = 1
        while pos != 0:
            pos = self.asyncmodule.expect_exact([EXT_PROMPT, EXT_PROMPT_CONTINUATION, EXT_PROMPT_OUTPUT])
            logger.debug(["rec:", pos, self.asyncmodule.before])
            if pos != 1:
                self.process_output(self.asyncmodule.before)

    def process_output(self, output):
        if not self.silent:
            # Send standard output
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def do_execute(self, code, silent, store_history=True, user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count, 'payload': [], 'user_expressions': {}}

        interrupted = False
        try:
            self.sendcommand(code)
            self.receivestream()
            
        except KeyboardInterrupt:
            logger.info("Sending %%C")
            self.asyncmodule.sendline("%%C\n")
            interrupted = True
            self.receivestream()

        except EOF:
            self.process_output(self.asyncmodule.before + 'Restarting Bash')
            self.startasyncmodule()

        if interrupted:
            return {'status': 'abort', 'execution_count': self.execution_count}

        exitcode = 0
        if exitcode:
            error_content = {'execution_count': self.execution_count,
                             'ename': '', 'evalue': str(exitcode), 'traceback': []}

            self.send_response(self.iopub_socket, 'error', error_content)
            error_content['status'] = 'error'
            return error_content
        else:
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}
                    

    # to do (if possible, though might be difficult in paste mode): word completion technology!
    #def do_complete(self, code, cursor_pos):
    #    code = code[:cursor_pos]
    #    default = {'matches': [], 'cursor_start': 0,
    #               'cursor_end': cursor_pos, 'metadata': dict(),
    #               'status': 'ok'}
    #    return default
