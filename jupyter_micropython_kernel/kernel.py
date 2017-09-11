from ipykernel.kernelbase import Kernel
from pexpect import replwrap, EOF
import pexpect

from subprocess import check_output
import os.path

import re, logging
import signal

logger = logging.getLogger(__name__)

EXT_PROMPT = '[serPROMPT>'
EXT_PROMPT_CONTINUATION = '[serPROMPT+'
EXT_PROMPT_OUTPUT = '[serPROMPT:'

class EREPLWrapper(object):
    def __init__(self, child, line_output_callback):
        self.child = child
        self.line_output_callback = line_output_callback
        self.child.expect_exact([EXT_PROMPT], timeout=None)
        logger.info(["init", child.before])
 
    def run_command(self, command):
        # Split up multiline commands and feed them in bit-by-bit
        cmdlines = command.splitlines()
        if not cmdlines:
            raise ValueError("No command was given")

        cmdlines.append("\n")
        for line in cmdlines:
            logger.info(["sending:", line])
            self.child.sendline(line)
            # send straight through.  Buffering at async end

        # Command was fully submitted, now wait for the next prompt
        if cmdlines[0][:2] != "%%":
            self.child.sendline("%%D\n")
        
        pos = 1
        while pos != 0:
            pos = self.child.expect_exact([EXT_PROMPT, EXT_PROMPT_CONTINUATION, EXT_PROMPT_OUTPUT], timeout=None)
            logger.info(["rec:", pos, self.child.before])
            if pos != 1:
                self.line_output_callback(self.child.before)
        
        


class MicroPythonKernel(Kernel):
    implementation = 'micropython_kernel'
    implementation_version = "v1"

    banner = "MicroPython Serializer"

    language_info = {'name': 'micropython',
                     'codemirror_mode': 'python',
                     'mimetype': 'text/python',
                     'file_extension': '.py'}

    def __init__(self, **kwargs):
        Kernel.__init__(self, **kwargs)
        self.silent = False
        self._start_bash()

    def _start_bash(self):
        # Signal handlers are inherited by forked processes, and we can't easily
        # reset it from the subprocess. Since kernelapp ignores SIGINT except in
        # message handlers, we need to temporarily reset the SIGINT handler here
        # so that bash and its children are interruptible.
        sig = signal.signal(signal.SIGINT, signal.SIG_DFL)
        try:
            child = pexpect.spawn("python", ['-m', 'jupyter_micropython_kernel.asyncmodule.py'], echo=False, encoding='utf-8', codec_errors='replace')

            # Using IREPLWrapper to get incremental output
            self.bashwrapper = EREPLWrapper(child, line_output_callback=self.process_output)
        finally:
            signal.signal(signal.SIGINT, sig)

    def process_output(self, output):
        if not self.silent:
            # Send standard output
            stream_content = {'name': 'stdout', 'text': output}
            self.send_response(self.iopub_socket, 'stream', stream_content)

    def do_execute(self, code, silent, store_history=True,
                   user_expressions=None, allow_stdin=False):
        self.silent = silent
        if not code.strip():
            return {'status': 'ok', 'execution_count': self.execution_count,
                    'payload': [], 'user_expressions': {}}

        interrupted = False
        try:
            self.bashwrapper.run_command(code.rstrip())
        except KeyboardInterrupt:
            self.bashwrapper.child.sendline("%%C\n")
            #self.bashwrapper.child.sendintr()
            interrupted = True
            self.bashwrapper.child.expect_exact([EXT_PROMPT])
            output = self.bashwrapper.child.before
            self.process_output(output)
        except EOF:
            output = self.bashwrapper.child.before + 'Restarting Bash'
            self._start_bash()
            self.process_output(output)

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
