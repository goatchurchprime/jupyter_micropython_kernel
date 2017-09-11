import logging
import sys

logging.basicConfig(level=logging.DEBUG)

from ipykernel.kernelapp import IPKernelApp
from .kernel import MicroPythonKernel
IPKernelApp.launch_instance(kernel_class=MicroPythonKernel)

