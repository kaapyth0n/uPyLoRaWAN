import time
from . import simple

class MQTTClient(simple.MQTTClient):
    DELAY = 2

    def delay(self, i):
        time.sleep(self.DELAY)

    def reconnect(self):
        i = 0
        while 1:
            try:
                return super().connect(False)
            except OSError as e:
                i += 1
                self.delay(i)

    def publish(self, topic, msg, retain=False, qos=0):
        while 1:
            try:
                return super().publish(topic, msg, retain, qos)
            except OSError as e:
                pass
            self.reconnect()

    def wait_msg(self):
        while 1:
            try:
                return super().wait_msg()
            except OSError as e:
                pass
            self.reconnect()

    def check_msg(self, attempts=2):
        while attempts:
            self.sock.setblocking(False)
            try:
                return super().wait_msg()
            except OSError as e:
                pass
            self.reconnect()
            attempts -= 1