#!/usr/bin/python3

import pigpio
import time
from queue import Queue
from threading import Thread
from audio_helpers import SoundDeviceStream, ConversationStream
from array import array
from random import random
import logging

class FishDeviceStream(SoundDeviceStream):
    def __init__(self, fish, **kwargs):
        super().__init__(**kwargs)
        self.fish = fish
        self.UPDATE_SAMPLES = 400
        self.UPDATE_INTERVAL = self.UPDATE_SAMPLES / self._sample_rate
        self.MOUTH_THRESH = 250
        self.audioFifo = Queue()
        self.mouthThread = Thread(target=self.mouthMover)
        self.mouthThread.daemon = True
        self.mouthThread.start()

    def write(self, buf):
        samples = array('h', buf)
        for i in range(0, len(samples), self.UPDATE_SAMPLES):
            self.audioFifo.put(samples[i:i+self.UPDATE_SAMPLES])
        super().write(buf)

    def mouthMover(self):
        while True:
            before = time.time()
            if self.audioFifo.qsize() == 0:
                self.fish.resetMotors()
            samples = self.audioFifo.get()
            self.fish.randMouth = max(samples) - min(samples) > self.MOUTH_THRESH
            elapsed = time.time() - before
            sleepTime = self.UPDATE_INTERVAL - elapsed
            time.sleep(max(sleepTime, 0))

class FishConversationStream(ConversationStream):
    def __init__(self, fish, **kwargs):
        super().__init__(**kwargs)
        self.fish = fish
    
    def start_recording(self):
        self.fish.changeHead(True)
        super().start_recording()

    def stop_recording(self):
        self.fish.resetMotors()
        super().stop_recording()
            
class Fish():
    def __init__(self):
        self.PWM_FREQ = 250000 - 100 # little less than 250khz
        self.ENABLE_PINS = [12,13]
        self.DIR_PINS = [5,6]
        self.BUTTON_PIN = 26
        self.INDICATOR_PIN = 19
        self.randMouth = False
        self.pi = pigpio.pi()

        for pin in self.ENABLE_PINS:
            self.pi.set_mode(pin, pigpio.OUTPUT)
        for pin in self.DIR_PINS:
            self.pi.set_mode(pin, pigpio.OUTPUT)

        self.pi.set_mode(self.BUTTON_PIN, pigpio.INPUT)
        self.pi.set_pull_up_down(self.BUTTON_PIN, pigpio.PUD_UP)
        self.resetMotors()
        self.mouthThread = Thread(target=self.mouthRandomizer)
        self.mouthThread.daemon = True
        self.mouthThread.start()

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        self.resetMotors()
        self.setIndicator(False)
        logging.info("Motors disabled")

    def mouthRandomizer(self):
        while True:
            if self.randMouth:
                self.changeMouth(random() > 0.5)
                time.sleep(0.06)
            else:
                self.changeMouth(False)
                time.sleep(0.05)

    def getTriggerButton(self):
        return not self.pi.read(self.BUTTON_PIN)

    def setIndicator(self, on):
        self.pi.write(self.INDICATOR_PIN, on)

    def motorSpeed(self, motor, speed):
        self.pi.hardware_PWM(self.ENABLE_PINS[motor], self.PWM_FREQ, speed * 10000)

    def motorDir(self, motor, direction):
        self.pi.write(self.DIR_PINS[motor], direction)

    def resetMotors(self):
        self.randMouth = False
        self.motorSpeed(0, 0)
        self.motorSpeed(1, 0)
        self.motorDir(0, 0)
        self.motorDir(1, 0)
        self.headOut = False
        self.mouthOpen = False

    def changeMouth(self, wantOpen):
        if self.mouthOpen and not wantOpen:
            logging.info("Mouth In")
            self.motorDir(1, 1)
            self.motorSpeed(1, 100)
            time.sleep(0.005)
            self.motorSpeed(1, 0)
            self.mouthOpen = False
        elif not self.mouthOpen and wantOpen:
            logging.info("Mouth Out")
            self.motorDir(1, 0)
            self.motorSpeed(1, 100)
            time.sleep(0.14)
            self.motorSpeed(1, 80)
            self.mouthOpen = True

    def changeHead(self, wantOut):
        if self.headOut and not wantOut:
            logging.info("Head In")
            self.motorDir(0, 1)
            self.motorSpeed(0, 50)
            time.sleep(0.11)
            self.motorSpeed(0, 0)
            self.headOut = False
        elif not self.headOut and wantOut:
            logging.info("Head Out")
            self.motorDir(0, 0)
            self.motorSpeed(0, 100)
            time.sleep(0.23)
            self.motorSpeed(0, 30)
            self.headOut = True
