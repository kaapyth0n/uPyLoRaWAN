import machine
import gc
_activation_delay_ms = 1800000
_watchdog_timeout_ms = 8388
_timer = None
_watchdog = None
_activated = False
def _watchdog_callback(timer):
    global _watchdog, _activated
    try:
        if _activated:
            return
        timeout = min(_watchdog_timeout_ms, 8388)
        _watchdog = machine.WDT(timeout=timeout)
        _activated = True
        gc.collect()
    except Exception as e:
        pass

def configure(activation_delay_ms=None, watchdog_timeout_ms=None, debug=None):
    global _activation_delay_ms, _watchdog_timeout_ms, _debug
    if activation_delay_ms is not None:
        _activation_delay_ms = max(60000, activation_delay_ms)
    if watchdog_timeout_ms is not None:
        _watchdog_timeout_ms = min(watchdog_timeout_ms, 8388)
    if debug is not None:
        _debug = debug

def schedule():
    global _timer, _activated
    if _activated:
        return False
    try:
        cancel()
        _timer = machine.Timer()
        _timer.init(period=_activation_delay_ms, mode=machine.Timer.ONE_SHOT, callback=_watchdog_callback)
        return True
    except Exception as e:
        return False

def cancel():
    global _timer
    if _timer:
        try:
            _timer.deinit()
            return True
        except Exception as e:
            pass
    return False

def is_active():
    global _activated
    return _activated

def feed():
    global _watchdog, _activated
    if not _activated or not _watchdog:
        return False
    try:
        _watchdog.feed()
        return True
    except:
        return False
gc.collect()