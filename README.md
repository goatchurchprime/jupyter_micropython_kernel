# Jupyter MicroPython Kernel

Jupyter kernel to interact with a MicroPython or CircuitPython board over its serial REPL.  Note this is _highly_ experimental and still alpha/beta quality.  Try it out but don't be surprised if it behaves in odd or unexpected ways!

## Installation

First install Jupyter: http://jupyter.org/install.html

Then clone this repository and install the setup.py (assuming python 3.0, be
sure to use the same version of python as Jupyter is installed with):

    python3 setup.py install

On Mac OSX and some Linux flavors you might need to run as root with sudo for
the above command.  Make sure the installation completes successfully and that
you do not see any error messages.

Finally create a Jupyter kernel specification for the serial port and baud rate
of your MicroPython board.  Unfortunately there is no UI or ability to pick the
serial port/baud from the notebook so you'll have to bake this in to a kernel
configuration.

From the Jupyter kernel docs find your user specific Jupyter kernel spec location: http://jupyter-client.readthedocs.io/en/latest/kernels.html#kernel-specs  You want the **user** location:

*   Windows: %APPDATA%\jupyter\kernels (note if you aren't sure where this is located see: http://www.pcworld.com/article/2690709/windows/whats-in-the-hidden-windows-appdata-folder-and-how-to-find-it-if-you-need-it.html)
*   macOS: ~/Library/Jupyter/kernels
*   Linux: ~/.local/share/jupyter/kernels

Create the above kernels folder if it doesn't already exist. Then inside the
kernels folder create a new folder called 'micropython' and copy the included
kernel.json file inside it.

Open the copied kernel.json file and edit it so the 4th line:

    "/dev/tty.SLAB_USBtoUART", "115200",

Is the serial name and baud rate of your MicroPython board.  For example if using COM4 and 115200 baud you would change it to:

    "COM4", "115200",

Also change the display name of the kernel on line 6:

    "display_name": "MicroPython - /dev/tty.SLAB_USBtoUART",

Set a value that describes your board, like:

    "display_name": "MicroPython - COM4",

This is the name you will see in Jupyter's notebook UI when picking the kernel
to start.  You don't need to change any other config in the kernel.json.  Be
very careful to make sure all the commands, double quotes, etc. are present
(this needs to be a valid JSON formatted file).

At this point you should have the following file: (Jupyter kernel spec location above)/micropython/kernel.json

Now run Jupyter notebooks:

    jupyter notebook

In the notebook click the New button in the upper right, you should see your
MicroPython kernel display name listed.  Click it to create a notebook using
that board connection (make sure the board is connected first!).
