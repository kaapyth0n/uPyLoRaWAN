import time
import gc
import math
def celsius_to_resistance(temp):
    try:
        R25 = 10000.0
        B = 3950.0
        T0 = 298.15
        temp_k = temp + 273.15
        resistance = R25 * pow(2.718281828, B * (1/temp_k - 1/T0))
        return max(100, min(100000, resistance))
    except:
        return 10000
def validate_temperature(temp):
    if temp is None:
        return False, "Temperature is None"
    try:
        temp = float(temp)
    except:
        return False, "Invalid temperature format"
    if temp < -55:
        return False, f"Temperature too low: {temp}"
    if temp > 125:
        return False, f"Temperature too high: {temp}"
    if math.isnan(temp):
        return False, "Temperature is NaN"
    return True, "Temperature valid"
def memory_stats():
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    total = free + alloc
    return {
        'free': free,
        'allocated': alloc,
        'total': total,
        'percent_used': (alloc * 100) / total
    }
def format_time(timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    try:
        time_tuple = time.localtime(timestamp)
        return "{:02d}:{:02d}:{:02d}".format(
            time_tuple[3],
            time_tuple[4],
            time_tuple[5]
        )
    except:
        return "??:??:??"
def format_uptime(seconds):
    try:
        minutes = seconds // 60
        hours = minutes // 60
        days = hours // 24
        if days > 0:
            return f"{days}d {hours%24}h"
        elif hours > 0:
            return f"{hours}h {minutes%60}m"
        else:
            return f"{minutes}m {seconds%60}s"
    except:
        return "??"
def calc_temperature_stats(temp_history):
    if not temp_history:
        return {
            'min': None,
            'max': None,
            'avg': None,
            'trend': 0
        }
    try:
        temps = [t[1] for t in temp_history]
        return {
            'min': min(temps),
            'max': max(temps),
            'avg': sum(temps) / len(temps),
            'trend': calc_trend(temp_history)
        }
    except:
        return {
            'min': None,
            'max': None,
            'avg': None,
            'trend': 0
        }
def calc_trend(history, window=300):
    try:
        current_time = time.time()
        filtered = [(t, v) for t, v in history
                   if current_time - t <= window]
        if len(filtered) < 2:
            return 0
        times = [(t - filtered[0][0])/60.0 for t, _ in filtered]
        values = [v for _, v in filtered]
        n = len(times)
        sum_x = sum(times)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(times, values))
        sum_xx = sum(x * x for x in times)
        try:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            return slope
        except:
            return 0
    except:
        return 0
def clamp(value, min_value, max_value):
    return max(min_value, min(max_value, value))
def force_reconnect(sta_if, ssid, password):
    try:
        if sta_if.isconnected():
            sta_if.disconnect()
        sta_if.active(False)
        time.sleep(1)
        sta_if.active(True)
        sta_if.connect(ssid, password)
    except Exception as e:
        pass