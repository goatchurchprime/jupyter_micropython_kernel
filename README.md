# Jupyter MicroPython Kernel

Jupyter kernel to interact with a MicroPython or CircuitPython board over its serial REPL.  
Note this is _highly_ experimental and still alpha/beta quality.  
Try it out but don't be surprised if it behaves in odd or unexpected ways!

## Installation

First install Jupyter: http://jupyter.org/install.html

Then clone this repository and install the setup.py (assuming python 3.0, be
sure to use the same version of python as Jupyter is installed with):

    pip install -e /path/to/jupyter_micropython_kernel
    python -m jupyter_micropython_kernel.install

If you need to update the port and baudrate of the connection in 
jupyter_micropython_kernel/jupyter_micropython_kernel/install.py 
from "/dev/ttyUSB0", "115200" change it there, and rerun the install command again.

To find out where your kernelspecs are stored, type:
    jupyter kernelspec list

Now run Jupyter notebooks:

    jupyter notebook

In the notebook click the New button in the upper right, you should see your
MicroPython kernel display name listed.  Click it to create a notebook using
that board connection (make sure the board is connected first!).
