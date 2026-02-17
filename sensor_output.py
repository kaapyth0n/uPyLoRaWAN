"""
Stable outdoor sensor (NTC thermistor) emulation output.

Provides a glitch-free analog output representing the resistance of an
outdoor temperature sensor for a boiler controller.  Designed to maintain
output stability across LoRa radio mode changes and software restarts
*without* periodic flash writes.

Persistence strategy
--------------------
1. RTC user memory  - written on every update; survives soft resets and
                      deep-sleep wake-ups with zero flash wear.
2. Flash file       - written ONLY when the normalised value drifts by
                      more than ``significant_change`` from the last save.
                      Outdoor temperature changes slowly, so in practice
                      this means a handful of writes per hour at most.
3. On boot the restore order is:  RTC → flash → default temperature.

Hardware output
---------------
* ESP32 DAC (8-bit true analog on GPIO 25 / 26)  - preferred, no ripple.
* Fallback: hardware PWM at a configurable frequency, intended to be
  smoothed by an external RC low-pass filter.

Both backends are driven entirely by hardware peripherals, so the output
is unaffected by CPU activity (LoRa mode switches, GC pauses, ISRs).
"""

import machine
import struct
import math

try:
    from machine import DAC
    _HAS_DAC = True
except ImportError:
    _HAS_DAC = False


# ── NTC defaults (typical 10 kΩ outdoor sensor) ─────────────────────────

NTC_DEFAULTS = {
    'r_nominal': 10000,    # Ω at t_nominal
    't_nominal': 25.0,     # °C
    'beta':      3435,     # K
    'r_min':     500,      # Ω clamp  (≈ very hot)
    'r_max':     100000,   # Ω clamp  (≈ very cold)
}

_PERSIST_FILE  = '/sensor_state.dat'
_RTC_OFFSET    = 0
_RTC_MAGIC     = b'\xa5\xb4'


class StableSensorOutput:
    """Emulates an outdoor NTC sensor with a rock-stable analog output.

    Parameters
    ----------
    pin : int
        GPIO number for the output.  On ESP32, GPIO 25 gives a true DAC.
    use_dac : bool | None
        True → force DAC, False → force PWM, None → auto-detect.
    pwm_freq : int
        PWM carrier frequency (Hz).  Only used when DAC is unavailable.
        Choose a frequency well above your RC filter cutoff.
    default_temp_c : float
        Assumed outdoor temperature when no persisted state exists.
    slew_max : float
        Maximum change in normalised output (0–1) per ``update()`` call.
        Controls how fast the output can ramp; prevents sudden jumps that
        the boiler controller might interpret as a sensor fault.
    significant_change : float
        Minimum normalised-value drift since the last flash save before a
        new flash write is triggered.  This is the *only* mechanism that
        touches flash, and it is event-driven, never periodic.
    ntc : dict | None
        NTC curve parameters.  Keys: r_nominal, t_nominal, beta, r_min,
        r_max.  Defaults to a standard 10 kΩ sensor.
    persist_file : str
        Path for the flash persistence file.
    """

    def __init__(self, pin, *, use_dac=None, pwm_freq=1000,
                 default_temp_c=5.0, slew_max=0.005,
                 significant_change=0.02, ntc=None,
                 persist_file=_PERSIST_FILE):

        self._ntc = ntc if ntc is not None else dict(NTC_DEFAULTS)
        self._persist_file = persist_file
        self._slew_max = slew_max
        self._sig_change = significant_change
        self._last_flash_val = None

        # ── output backend ────────────────────────────────────────────
        self._dac = None
        self._pwm = None

        if use_dac is True or (use_dac is None and _HAS_DAC):
            try:
                self._dac = DAC(machine.Pin(pin))
            except Exception:
                self._dac = None

        if self._dac is None:
            p = machine.Pin(pin)
            self._pwm = machine.PWM(p)
            self._pwm.freq(pwm_freq)

        # ── restore persisted value ───────────────────────────────────
        restored = self._restore_rtc()
        if restored is None:
            restored = self._restore_flash()

        if restored is not None:
            self._current = restored
            self._target  = restored
        else:
            val = self.temp_to_normalised(default_temp_c)
            self._current = val
            self._target  = val

        # Drive the pin *immediately* so there is never a moment where
        # the output floats or sits at zero.
        self._hw_write(self._current)

    # ── public API ────────────────────────────────────────────────────

    def set_temperature(self, temp_c):
        """Set the target output from a temperature in °C."""
        self._target = self.temp_to_normalised(temp_c)

    def set_resistance(self, ohms):
        """Set the target output from a resistance in Ω."""
        self._target = self._resistance_to_normalised(ohms)

    def set_normalised(self, value):
        """Set the target output directly (0.0 … 1.0)."""
        self._target = max(0.0, min(1.0, value))

    def update(self):
        """Advance the output one slew step toward the target.

        Call this once per main-loop iteration.  The slew limiter ensures
        that even if the target jumps (new LoRa packet with a very
        different temperature), the actual output ramps smoothly.

        Returns True if the output value changed.
        """
        diff = self._target - self._current
        if abs(diff) < 1e-5:
            return False

        if abs(diff) > self._slew_max:
            self._current += self._slew_max if diff > 0 else -self._slew_max
        else:
            self._current = self._target

        self._hw_write(self._current)
        self._save_rtc(self._current)

        # Flash: only on meaningful drift, never periodic.
        if (self._last_flash_val is None
                or abs(self._current - self._last_flash_val) >= self._sig_change):
            self._save_flash(self._current)
            self._last_flash_val = self._current

        return True

    def force_set(self, temp_c):
        """Immediately set output (no slew).  Useful at startup."""
        val = self.temp_to_normalised(temp_c)
        self._current = val
        self._target  = val
        self._hw_write(val)
        self._save_rtc(val)
        self._save_flash(val)
        self._last_flash_val = val

    @property
    def current_value(self):
        """Current normalised output (0.0 … 1.0)."""
        return self._current

    @property
    def target_value(self):
        """Target normalised output (0.0 … 1.0)."""
        return self._target

    # ── NTC model ─────────────────────────────────────────────────────

    def temp_to_resistance(self, temp_c):
        """Beta-equation:  temperature (°C) → resistance (Ω)."""
        ntc = self._ntc
        inv_t  = 1.0 / (temp_c + 273.15)
        inv_t0 = 1.0 / (ntc['t_nominal'] + 273.15)
        return ntc['r_nominal'] * math.exp(ntc['beta'] * (inv_t - inv_t0))

    def temp_to_normalised(self, temp_c):
        """Temperature (°C) → normalised output value (0.0 … 1.0)."""
        r = self.temp_to_resistance(temp_c)
        return self._resistance_to_normalised(r)

    def _resistance_to_normalised(self, ohms):
        """Map resistance to 0..1 on a log scale for even resolution."""
        ntc = self._ntc
        ohms = max(ntc['r_min'], min(ntc['r_max'], ohms))
        log_min = math.log(ntc['r_min'])
        log_max = math.log(ntc['r_max'])
        # 1.0 = low resistance (hot) → high output voltage
        # 0.0 = high resistance (cold) → low output voltage
        return 1.0 - (math.log(ohms) - log_min) / (log_max - log_min)

    # ── hardware output ───────────────────────────────────────────────

    def _hw_write(self, value):
        value = max(0.0, min(1.0, value))
        if self._dac is not None:
            self._dac.write(int(value * 255))
        else:
            self._pwm.duty_u16(int(value * 65535))

    # ── RTC memory (survives soft reset & deep sleep, no flash wear) ──

    def _save_rtc(self, value):
        try:
            rtc = machine.RTC()
            payload = _RTC_MAGIC + struct.pack('<f', value)
            buf = bytearray(rtc.memory())
            needed = _RTC_OFFSET + len(payload)
            if len(buf) < needed:
                buf.extend(b'\x00' * (needed - len(buf)))
            buf[_RTC_OFFSET:_RTC_OFFSET + len(payload)] = payload
            rtc.memory(bytes(buf))
        except Exception:
            pass

    def _restore_rtc(self):
        try:
            data = machine.RTC().memory()
            end = _RTC_OFFSET + 6
            if len(data) >= end:
                chunk = data[_RTC_OFFSET:end]
                if chunk[:2] == _RTC_MAGIC:
                    val = struct.unpack('<f', chunk[2:6])[0]
                    if 0.0 <= val <= 1.0:
                        return val
        except Exception:
            pass
        return None

    # ── flash persistence (event-driven, NOT periodic) ────────────────

    def _save_flash(self, value):
        try:
            with open(self._persist_file, 'wb') as f:
                f.write(_RTC_MAGIC + struct.pack('<f', value))
        except Exception:
            pass

    def _restore_flash(self):
        try:
            with open(self._persist_file, 'rb') as f:
                data = f.read(6)
            if len(data) == 6 and data[:2] == _RTC_MAGIC:
                val = struct.unpack('<f', data[2:6])[0]
                if 0.0 <= val <= 1.0:
                    self._last_flash_val = val
                    return val
        except Exception:
            pass
        return None
