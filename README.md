# Jupyter MicroPython Kernel

Jupyter kernel to interact with a MicroPython ESP8266 or ESP32 over its serial REPL.  

## Background

This had been proposed as for an enhancement to webrepl with the idea of a jupyter-like 
interface to webrepl rather than the faithful emulation of a command line: https://github.com/micropython/webrepl/issues/32

Other known projects that have implemented a Jupyter Micropython kernel are:
* https://github.com/adafruit/jupyter_micropython_kernel
* https://github.com/willingc/circuitpython_kernel
* https://github.com/TDAbboud/mpkernel
* https://github.com/takluyver/ubit_kernel

In my defence, this is not an effect of not-invented-here syndrome; I did not discover most of them until I 
had mostly written this one.  But for my purposes, this is more robust and contains debugging (of the 
serial connections) capability.

## Installation

First install Jupyter: http://jupyter.org/install.html (the Python3 version)

Then clone this repository to a directory.

Install this library (in editable mode) into Python3

    pip install -e jupyter_micropython_kernel

(This creates a small file pointing to this directory in the python/../site-packages 
directory, and makes it possible to "git update" the library later as it gets improved)
    
Install the kernel into jupyter itself    

    python -m jupyter_micropython_kernel.install

(This creates the small file ".local/share/jupyter/kernels/micropython/kernel.json" 
that jupyter uses to reference it's kernels

To find out where your kernelspecs are stored, type:

    jupyter kernelspec list


## Running

Now run Jupyter notebooks:

    jupyter notebook

In the notebook click the New notebook button in the upper right, you should see your
MicroPython kernel display name listed.  

The first cell will need to be something like:

    %serialconnect
    
or something that matches the serial port and baudrate that 
you connect to your MicroPython/ESP8266 with.

You should now be able to execute MicroPython commands 
by running the cells.

(There is a micropythondemo.ipynb file in the directory you could 
look at with some of the features shown.)

If a cell is taking too long to interrupt, it may respond 
to a "Kernel" -> "Interrupt" command. 

Alternatively hit Escape and then 'i' twice.

To upload the contents of a cell to a file, write: 
    %sendtofile yourfilename.py 
    
as the first line of the cell

To do a soft reboot (when you need to clear out the modules 
and recover some memory) type:
    %reboot

Note: Restarting the kernel does not actually reboot the device.  
Also, pressing the reset button will probably mess things up, because 
this interface relies on the ctrl-A non-echoing paste mode to do its stuff.


## Debugging

For reference, the notebooks here might be useful:
  https://github.com/goatchurchprime/jupyter_micropython_developer_notebooks

The system works by finding and connecting to a serial line and
then issuing the enter paste mode command Ctrl-A (hex 0x01)

In this mode blocks of to-be-executed text are ended with a Ctrl-D
(hex 0x04).

The response that comes back begins with an "OK" followed by the 
actual program response, followed by Ctrl-D, followed by any 
error messages, followed by a second Ctrl-D, followed by a '>'.

You can implement this interface (for debugging purposes) to find out 
how it's snarling up beginning with:
 "%serialconnect --raw"
and then doing
 %writebytes -b "sometext"
and 
 %readbytes
 

