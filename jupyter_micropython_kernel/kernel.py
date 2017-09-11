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
            pos = self.child.expect_exact([EXT_PROMPT, EXT_PROMPT_CONTINUATION], timeout=None)
            logger.info(["rec:", pos, self.child.before])
            self.line_output_callback(self.child.before + '\n')
        
        
    def _expect_prompt(self):
        # "None" means we are executing code from a Jupyter cell by way of the run_command
        # in the do_execute() code below, so do incremental output.
        while True:
            pos = self.child.expect_exact([EXT_PROMPT, EXT_PROMPT_CONTINUATION, u'\n'], timeout=None)
            logger.info(["expro:", pos, self.child.before])
            if pos == 2:
                self.line_output_callback(self.child.before + '\n')
            else:
                if len(self.child.before) != 0:
                    self.line_output_callback(self.child.before)
                break
        return pos


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
            self.bashwrapper._expect_prompt()
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

    def do_complete(self, code, cursor_pos):
        code = code[:cursor_pos]
        default = {'matches': [], 'cursor_start': 0,
                   'cursor_end': cursor_pos, 'metadata': dict(),
                   'status': 'ok'}

        if not code or code[-1] == ' ':
            return default

        tokens = code.replace(';', ' ').split()
        if not tokens:
            return default

        matches = []
        token = tokens[-1]
        start = cursor_pos - len(token)

        if token[0] == '$':
            # complete variables
            cmd = 'compgen -A arrayvar -A export -A variable %s' % token[1:] # strip leading $
            output = self.bashwrapper.run_command(cmd).rstrip()
            completions = set(output.split())
            # append matches including leading $
            matches.extend(['$'+c for c in completions])
        else:
            # complete functions and builtins
            cmd = 'compgen -cdfa %s' % token
            output = self.bashwrapper.run_command(cmd).rstrip()
            matches.extend(output.split())

        if not matches:
            return default
        matches = [m for m in matches if m.startswith(token)]

        return {'matches': sorted(matches), 'cursor_start': start,
                'cursor_end': cursor_pos, 'metadata': dict(),
                'status': 'ok'}
