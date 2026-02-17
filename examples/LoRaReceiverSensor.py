"""
LoRa receiver that drives a stable outdoor sensor emulation output.

Receives temperature readings over LoRa and smoothly updates the analog
output pin so a boiler controller sees a steady NTC-like resistance.
The output persists across soft resets via RTC memory and survives power
cycles via event-driven flash saves (no periodic writes).
"""

from time import sleep
from sensor_output import StableSensorOutput

_LOOP_MS = 200   # main-loop period – matches app_config['loop']


def _parse_temperature(payload):
    """Extract a temperature float from a LoRa payload.

    Accepts either a raw UTF-8 float string (e.g. b'12.5') or a
    simple key:value format (e.g. b'T:12.5').  Returns None on failure.
    """
    try:
        text = payload.decode().strip()
        if ':' in text:
            text = text.split(':')[-1].strip()
        return float(text)
    except Exception:
        return None


def receive(lora, sensor_cfg=None, ntc_cfg=None):
    """Main loop: receive LoRa packets and drive the sensor output.

    Parameters
    ----------
    lora : SX127x
        Initialised LoRa radio instance.
    sensor_cfg : dict | None
        Keyword arguments forwarded to ``StableSensorOutput``.
        If None, defaults from config.py are used.
    ntc_cfg : dict | None
        NTC thermistor parameters.
    """
    # Build sensor output from config dicts
    kwargs = dict(sensor_cfg) if sensor_cfg else {}
    if ntc_cfg:
        kwargs['ntc'] = ntc_cfg
    pin = kwargs.pop('pin', 25)
    sensor = StableSensorOutput(pin, **kwargs)

    print("LoRa Receiver + Sensor Output (pin {})".format(pin))
    print("  restored value: {:.4f}".format(sensor.current_value))

    while True:
        if lora.received_packet():
            lora.blink_led()
            payload = lora.read_payload()

            temp = _parse_temperature(payload)
            if temp is not None:
                sensor.set_temperature(temp)
                print("rx temp: {:.1f} C  target: {:.4f}".format(
                    temp, sensor.target_value))
            else:
                print("rx (ignored): {}".format(payload))

        # Advance slew one tick – always call, even when no new packet
        sensor.update()

        sleep(_LOOP_MS / 1000)
