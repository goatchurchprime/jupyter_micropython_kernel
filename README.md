# Jupyter MicroPython Kernel

Jupyter kernel to interact with a MicroPython ESP8266 or ESP32 over its serial REPL.  

Also with capabilities to work through the WEBREPL (available on ESP8266 only), 
do Ctrl-C, transfer files and esptools flashing (useful for deployment).
See https://github.com/goatchurchprime/jupyter_micropython_developer_notebooks 
for examples.

## Installation

First install Jupyter: http://jupyter.org/install.html (the Python3 version).
**They strongly recommended you use the [Anaconda Distribution](https://www.anaconda.com/download/)**

Then clone this repository to a directory using TortoiseGIT or with the shell command (ie on a command line):

    git clone https://github.com/goatchurchprime/jupyter_micropython_kernel.git

Install this library (in editable mode) into Python3 using the shell command:

    pip install -e jupyter_micropython_kernel

This creates a small file pointing to this directory in the python/../site-packages 
directory, and makes it possible to "git update" the library later as it gets improved.
(Things can go wrong here, and you might need "pip3" or "sudo pip" if you have 
numerous different versions of python installed


Install the kernel into jupyter itself using the shell command:

    python -m jupyter_micropython_kernel.install

(This creates the small file ".local/share/jupyter/kernels/micropython/kernel.json" 
that jupyter uses to reference it's kernels

To find out where your kernelspecs are stored, you can type:

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

'''On Windows it can sometimes be difficult to find the Serial (COM-port) 
and the right driver.  This is not unique to the jupyter_micropython_kernel
and is a function of the USB chip that is on the breakout board containing 
your ESP32/ESP8266.  Find the USB connection in the Device list to see what driver 
it needs or look for instructions from the supplier of the board.'''

There is a micropythondemo.ipynb file in the directory you could 
look at with some of the features shown.

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

You can list all the functions with:
    %lsmagic


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
 
## Background

This had been proposed as an enhancement to webrepl with the idea of a jupyter-like 
interface to webrepl rather than their faithful emulation of a command line: https://github.com/micropython/webrepl/issues/32

My first implementation operated a spawned-process asyncronous sub-kernel that handled the serial connection. 
Ascync technology requires the whole program to work this way, or none of it.  
So my next iteration was going to do it using standard python threads to handle the blocking 
of the serial connections.  

However, further review proved that this was unnecessarily complex if you consider the whole 
kernel itself to be operating asyncronously with the front end notebook UI.  In particular, 
if the notebook can independently issue Ctrl-C KeyboardInterrupt signals into the kernel, there is no longer 
a need to worry about what happens when it hangs waiting for input from a serial connection.  

Other known projects that have implemented a Jupyter Micropython kernel are:
* https://github.com/adafruit/jupyter_micropython_kernel
* https://github.com/willingc/circuitpython_kernel
* https://github.com/TDAbboud/mpkernel
* https://github.com/takluyver/ubit_kernel
* https://github.com/jneines/nodemcu_kernel
* https://github.com/zsquareplusc/mpy-repl-tool

In my defence, this is not an effect of not-invented-here syndrome; I did not discover most of these 
other projects until I had mostly written this one.  

I do think that for robustness it is important to expose the full processes 
of making connections.  For my purposes this is more robust and contains debugging (of the 
serial connections) capability through its %lsmagic functions.

Other known projects to have made Jupyter-like or secondary interfaces to Micropython:
* https://github.com/nickzoic/mpy-webpad
* https://github.com/BetaRavener/uPyLoader

The general approach of all of these is to make use of the Ctrl-A 
paste mode with its Ctrl-D end of message signals.  
The problem with this mode is it was actually designed for 
automatic testing rather than supporting an interactive REPL (Read Execute Print Loop) system
(citation required), so there can be reliability issues to do with 
accidentally escaping from this mode or not being able to detect the state 
of being in it.  

For example, you can't safely do a Ctrl-B to leave the paste mode and then a 
Ctrl-A to re-enter paste mode cleanly, because a Ctrl-B in the non-paste mode 
will reboot the device.  


