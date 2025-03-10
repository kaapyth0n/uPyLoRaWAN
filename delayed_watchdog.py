"""
Delayed Watchdog for Raspberry Pi Pico

This module implements a delayed watchdog activation mechanism.
Instead of starting the hardware watchdog immediately, it schedules
its activation after a configurable delay (e.g., 30 minutes).

This solves the problem of the Pico's short maximum watchdog timeout
(8388 ms) while still providing protection against hangs.

Usage:
    import delayed_watchdog
    
    # Optional: Configure parameters
    delayed_watchdog.configure(activation_delay_ms=1800000, watchdog_timeout_ms=8000)
    
    # Schedule the watchdog to start after the delay
    delayed_watchdog.schedule()
    
    # Cancel the scheduled watchdog activation if boot completes successfully
    delayed_watchdog.cancel()
"""

import machine
import gc

# Configuration
_activation_delay_ms = 1800000  # 30 minutes by default
_watchdog_timeout_ms = 8388     # ~8 seconds (max allowed is 8388 ms)
_timer = None
_watchdog = None
_activated = False
_debug = False

def _log(message):
    """Print debug message if debug mode is enabled"""
    if _debug:
        print(f"[DelayedWDT] {message}")
    
def _watchdog_callback(timer):
    """Callback that activates the hardware watchdog after the delay period"""
    global _watchdog, _activated
    
    try:
        _log("Activation timer triggered - starting hardware watchdog")
        
        # Ensure watchdog isn't already running
        if _activated:
            _log("Watchdog already activated")
            return
        
        # Initialize the hardware watchdog with configured timeout
        timeout = min(_watchdog_timeout_ms, 8388)  # Enforce maximum allowed value
        _watchdog = machine.WDT(timeout=timeout)
        _activated = True
        _log(f"Hardware watchdog activated with {timeout}ms timeout")
        
        # Force garbage collection to free memory
        gc.collect()
    except Exception as e:
        print(f"Error activating watchdog: {e}")

def configure(activation_delay_ms=None, watchdog_timeout_ms=None, debug=None):
    """Configure watchdog parameters
    
    Args:
        activation_delay_ms: Delay before activating watchdog (default 30 minutes)
        watchdog_timeout_ms: Watchdog timeout once activated (default 8000 ms)
        debug: Enable debug logging (default False)
    """
    global _activation_delay_ms, _watchdog_timeout_ms, _debug
    
    if activation_delay_ms is not None:
        _activation_delay_ms = max(60000, activation_delay_ms)  # Minimum 1 minute
        
    if watchdog_timeout_ms is not None:
        _watchdog_timeout_ms = min(watchdog_timeout_ms, 8388)  # Maximum 8388 ms
        
    if debug is not None:
        _debug = debug
        
    _log(f"Configured: delay={_activation_delay_ms}ms, timeout={_watchdog_timeout_ms}ms")

def schedule():
    """Schedule the watchdog to activate after the configured delay"""
    global _timer, _activated
    
    if _activated:
        _log("Watchdog already activated, can't schedule")
        return False
        
    try:
        # Cancel any existing timer
        cancel()
        
        # Create and initialize a new timer
        _timer = machine.Timer()
        _timer.init(period=_activation_delay_ms, 
                   mode=machine.Timer.ONE_SHOT, 
                   callback=_watchdog_callback)
        
        _log(f"Watchdog scheduled to activate in {_activation_delay_ms/1000} seconds")
        return True
    except Exception as e:
        print(f"Error scheduling watchdog: {e}")
        return False

def cancel():
    """Cancel the scheduled watchdog activation"""
    global _timer
    
    if _timer:
        try:
            _timer.deinit()
            _log("Scheduled activation cancelled")
            return True
        except Exception as e:
            print(f"Error cancelling watchdog timer: {e}")
    return False

def is_active():
    """Check if the watchdog has been activated"""
    global _activated
    return _activated

def feed():
    """Feed the watchdog if it's active"""
    global _watchdog, _activated
    
    if not _activated or not _watchdog:
        return False
        
    try:
        _watchdog.feed()
        return True
    except:
        return False

# Run garbage collection to free memory
gc.collect()