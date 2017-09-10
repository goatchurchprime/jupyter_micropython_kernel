import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging
#logger = logging.getLogger(__name__)

from ipykernel.kernelbase import Kernel
import pkg_resources

from jupyter_micropython_kernel.pyboard import Pyboard


# Create global logger for debug messages.
# Get version from setuptools.  This is used to tell Jupyter the version of
# this kernel.
version = pkg_resources.require('jupyter_micropython_kernel')[0].version



def make_micropython_kernel(port, baud):
    # Create a MicroPython kernel class and return it.  This is done so instance
    # specific config like port and baud rate can be set.  Unfortunately the
    # IPython kernel wrapper design doesn't appear to allow for
    # instance-specific configuration (i.e. you don't create the instance
    # and call its constructor to control how it's built).  As a workaround
    # we'll just build a separate kernel class with a class-specific port and
    # baud rate baked in.
    class MicroPythonKernel(Kernel):
        implementation = 'micropython'
        implementation_version = version
        language = 'micropython'
        language_version = version
        language_info = {
            'name': 'python',
            'mimetype': 'text/x-python',
            'file_extension': '.py',
        }
        banner = 'MicroPython Kernel - port: {} - baud: {}'.format(port, baud)

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            # Open MicroPython board and enter raw REPL which resets the board
            # and makes it ready to accept commands.
            logger.debug('Opening33 MicroPython board connection on port: {} baud: {}'.format(port, baud))
            self._board = Pyboard(port, baudrate=baud)
            self._board.enter_raw_repl()

        def do_execute(self, code, silent, store_history=True,
                       user_expressions=None, allow_stdin=False):
                           
            logger.debug("Received executing ccccode", [code])
                           
            # Run the specified code on the connected MicroPython board.
            result, error = self._board.exec_raw(code)
            
            logger.debug('Result: {} Error: {}'.format(result, error))
            # If there was an error send it back, otherwise send the result.
            # Make sure to convert this to a JSON serializable string from the
            # raw bytes (assumes UTF-8 encoding).  This doesn't really feel
            # like the right way to send back errors but the docs are really
            # hard to figure out what's expected (do you send a stream_content
            # with name stderr? is there more to return?).
            failed = error is not None and len(error) > 0
            response = result.decode('utf-8') if not failed else error.decode('utf-8')
            
            # Send the result when not in silent mode.
            if not silent:
                stream_content = {'name': 'stdout', 'text': response }
                self.send_response(self.iopub_socket, 'stream', stream_content)
            return {'status': 'ok' if not failed else 'error',
                    # The base class increments the execution count
                    'execution_count': self.execution_count,
                    'payload': [],
                    'user_expressions': {},
                   }

        def do_shutdown(self, restart):
            # Be nice and try to exit the raw REPL, but ignore any failure
            # in case the connection is already dead.
            logger.debug('Shutting down MicroPython board connection.')
            try:
                self._board.exit_raw_repl()
            except:
                pass
            self._board.close()

    return MicroPythonKernel
