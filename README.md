# Jupyter MicroPython Kernel

Jupyter kernel to interact with a MicroPython or CircuitPython board over its serial REPL.  
Note this is _highly_ experimental and still alpha/beta quality.  
Try it out but don't be surprised if it behaves in odd or unexpected ways!

## Installation

First install Jupyter: http://jupyter.org/install.html (the Python3 version)

Then clone this repository to a directory.

Install this library (in editable mode) into Python3

    pip3 install -e jupyter_micropython_kernel

(This creates a small file pointing to this directory in the python/../site-packages 
directory, and makes it possible to "git update" the library later as it gets improved)
    
Install the kernel into jupyter itself    

    python3 -m jupyter_micropython_kernel.install

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

    %%CONN /dev/ttyUSB0 115200
    
or something that matches the serial port and baudrate that 
you connect to your MicroPython/ESP8266 with.

You should now be able to execute MicroPython commands 
by running the cells.

(There is a micropythondemo.ipynb file in the directory you could 
look at with some of the features shown.)

If a cell is taking too long to interrupt, it may respond 
to a "Kernel" -> "Interrupt" command. s

To upload the contents of a cell to a file, put 

    %%FILE yourfilename.py 
    
as the first line of the cell

To do a soft reboot (when you need to clear out the modules 
and recover some memory) type:

    %%REBOOT

Note: Restarting the kernel does not actually reboot the device.  
Also, pressing the reset button will probably mess things up, because 
this interface relies on the ctrl-A non-echoing paste mode to do its stuff.


## Debugging

The system works by spawning off a new python executable that manages the 
interface to the serial line and accepts input-output through its stdin and
stdout.  

You can interact with this module directly by typing

    python -m jupyter_micropython_kernel.asyncmodule.py

It uses a prompt that looks like "[serPROMPT>"

You can type the same command "%%CONN ..." to make a connection.

When you are entering lines of code, the final line needs to be:

  %%D
  
To make the MicroPython device start executing the code that has been 
pasted.  While it is running, %%C will send it a ctrl-C keyboard 
interrupt.

