"""
OpenPMU WaveMU
Waveform Merging Unit Simulator: Plays back Wave / FLAC soundfiles 
containing continuous point on wave (CPOW) sampled vales (SV) in 
OpenPMU's XML format. Allows relay of recorded waveforms, construction 
of arbitrary waveforms, and simulation of OpenPMU's ADC.

Copyright (C) 2021  OpenPMU

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import os
import time
from datetime import datetime, timedelta
import numpy as np
import socket
from lxml import etree
import base64
import soundfile as sf

SCRIPT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))

# convert from dict to xml value
# if no conversion needed, delete it from the expression
dictTypeConvert = lambda key: {'Frame': str,
                               'Fs': str,
                               'n': str,
                               'Channels': str,
                               'Payload': base64.standard_b64encode,
                               'bits': str,
                               }.get(key, lambda x: x)


class WaveMU():
    def __init__(self, waveFilePath, channels=2, ip="127.0.0.1", port=48001):

        self.waveFilePath = waveFilePath
        self.channels = channels

        self.interval = 0.01  # seconds
        self.Fs = 12800
        self.n = int(self.Fs * self.interval)
        self.ADCRange = 2 ** 15 - 1
        self.bits = 16

        self.ip = ip
        self.port = port

        self.stopThread = False
        self.xmlTemplate = etree.parse(os.path.join(SCRIPT_DIRECTORY, "OpenPMU_SV.xml"))
        
        print("Length of file: ", self.getLength(), "seconds")

    def run(self):
        self.stopThread = False
        
        timeStart = datetime.now()

        socketOut = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        socketFwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)    
        # basic information
        resultDict = dict()
        resultDict["Fs"] = self.Fs
        resultDict["n"] = self.n
        resultDict["Channels"] = self.channels
        resultDict["bits"] = self.bits

        # frame count
        frame = 0
        # time information for cos function
        intervalDelta = timedelta(seconds=self.interval)
        
        print(intervalDelta)
        
        SVgen = self.readWaveFileGen(self.waveFilePath)
        
        # Hold off until top of second (check for rollover)
        startTime = datetime.now()
        while startTime.second == datetime.now().second:
            time.sleep(0.0001)
        
        while not self.stopThread:
            now = datetime.now()
            resultDict["Time"] = now.time().strftime("%H:%M:%S") + ".%03d" % (frame * self.interval * 1000)
            resultDict["Date"] = now.date().strftime("%Y-%m-%d")
            resultDict["Frame"] = frame

            try:
                payload = next(SVgen)
            except:
                self.stop()
                break
            
            for i in range(self.channels):
                Channel_i = "Channel_%d" % i
                resultDict[Channel_i] = dict()
                resultDict[Channel_i]["Payload"] = np.ascontiguousarray(payload[i, :])

            xml = self.toXML(resultDict)
            # print(xml)
            socketOut.sendto(xml, (self.ip, self.port))
            socketFwd.sendto(xml, ("127.0.0.1", 48005))    
            
            elapsedTime = round((datetime.now() - timeStart).total_seconds(), 3)
            
            frame += 1
            if (frame == int(1 / self.interval)):
                frame = 0
                print('.')
                print(elapsedTime, ' ', end='', flush=True)
            else:
                print('.', end='', flush=True)

            # delay some time, this is not accurate
            s = (intervalDelta - (datetime.now() - now)).total_seconds()
            # print("sleep - ", s)
            # print(frame)
            # print(round((datetime.now() - timeStart).total_seconds(), 3))
            time.sleep(s if s > 0 else 0)

    def stop(self):
        self.stopThread = True

    # convert from python dictionary to a XML string
    def toXML(self, resultDict):
        level0 = self.xmlTemplate.getroot()

        try:
            for level1 in list(level0):
                tag1 = level1.tag
                if tag1 in resultDict.keys():
                    if tag1.startswith("Channel_"):
                        for level2 in list(level1):
                            tag2 = level2.tag
                            if tag2 in resultDict[tag1].keys():
                                # print(resultDict[tag1][tag2])
                                level2.text = dictTypeConvert(tag2)(resultDict[tag1][tag2])

                    else:
                        level1.text = dictTypeConvert(tag1)(resultDict[tag1])
                else:
                    level0.remove(level1)
        except KeyError as e:
            print("XML tag error: ", e)
        xml = etree.tostring(level0, encoding="utf-8")
        return xml
    
    # Generator for reading wavefile. Returns next block of sampled values each call.
    def readWaveFileGen(self, waveFilePath):
        
        for block in sf.blocks(waveFilePath, blocksize=128, overlap=0, dtype='int16'):
            yield block.T.byteswap()
            
    # Calculate the length of the wavefile in seconds    
    def getLength(self):
       
        with sf.SoundFile(self.waveFilePath) as wf:
            try:
                length = wf.frames / wf.samplerate    
            except Exception as e:
                print(e)      
                
        return length 


if __name__ == "__main__":
    
    waveFilePath = "example.flac"
    
    NewWaveMU = WaveMU(waveFilePath, ip="127.0.0.1", port=48001)
    NewWaveMU.run()

