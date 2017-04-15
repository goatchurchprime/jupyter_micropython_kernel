import logging
import sys

from ipykernel.kernelapp import IPKernelApp

from jupyter_micropython_kernel.kernel import make_micropython_kernel


logging.basicConfig(level=logging.DEBUG)

# Parse out required port name and baud rate parameters.  Remove them from argv
# because the IPKernelApp will go on to parse the arguments and get confused
# if it finds extra args like them.  Not super elegant but I see no other way
# to pass custom arguments/parameters to kernels.
if len(sys.argv) < 3:
    raise RuntimeError('Expected at least PORT and BAUD parameters!')
port = sys.argv[1]
baud = sys.argv[2]
del sys.argv[1:3]

# Create and launch the kernel.
IPKernelApp.launch_instance(kernel_class=make_micropython_kernel(port, baud))
