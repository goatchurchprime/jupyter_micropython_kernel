import serial, socket, serial.tools.list_ports, select

# this should take account of the operating system
def guessserialport():  
    return sorted([x[0]  for x in serial.tools.list_ports.grep("")])


class DeviceConnector:
    def __init__(self, sres):
        self.workingserial = None
        self.workingsocket = None
        self.sres = sres

    def workingserialreadall(self):  # usually used to clear the incoming buffer
        pass
    def serialconnect(self, portname, baudrate):
        pass
    def socketconnect(self, ipnumber, portnumber):
        pass
    def sendtofile(self, destinationfilename, bappend, cellcontents):
        pass
    def enterpastemode(self):
        pass
