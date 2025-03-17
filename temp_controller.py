import time

class TemperatureController:

	def __init__(self, config_manager):
		self.config = config_manager
		self.temp_history = []
		self.max_history_len = 60
		self.error_history = []
		self.max_error_len = 10
		self.last_control_time = 0
		self.integral_error = 0
		self.last_error = 0
		self.min_control_interval = 1.0
		self.p_value = None
		self.i_value = None
		self.d_value = None

	def add_temp_to_history(self, timestamp, temp):
		if len(self.temp_history) >= self.max_history_len:
			self.temp_history.pop(0)
		self.temp_history.append((timestamp, temp))

	def add_error_to_history(self, error):
		if len(self.error_history) >= self.max_error_len:
			self.error_history.pop(0)
		self.error_history.append(error)

	def calculate_control_action(self, current_temp, setpoint, dt):
		if current_temp is None or setpoint is None:
			return (False, 0)
		if current_temp > self.config.get_param('max_temp'):
			return (False, 0)
		error = setpoint - current_temp
		self.add_temp_to_history(time.time(), current_temp)
		self.add_error_to_history(error)
		self.integral_error += error * dt
		max_integral = 20.0
		self.integral_error = max(-max_integral, min(max_integral, self.integral_error))
		derivative = (error - self.last_error) / dt if dt > 0 else 0
		hysteresis = self.config.get_param('hysteresis')
		trend = self.calculate_trend()
		should_heat = False
		if abs(error) > hysteresis:
			should_heat = error > 0
		elif trend < -0.1:
			should_heat = error >= -hysteresis / 2
		elif trend > 0.1:
			should_heat = error > hysteresis / 2
		else:
			should_heat = error > 0
		if should_heat:
			if trend > 0.5:
				should_heat = False
		elif trend < -0.5:
			should_heat = True
		self.last_error = error
		return (should_heat, abs(error))

	def calculate_trend(self):
		if len(self.temp_history) < 2:
			return 0
		times = [(t - self.temp_history[0][0]) / 60.0 for t, _ in self.temp_history]
		temps = [t for _, t in self.temp_history]
		n = len(times)
		sum_x = sum(times)
		sum_y = sum(temps)
		sum_xy = sum((x * y for x, y in zip(times, temps)))
		sum_xx = sum((x * x for x in times))
		try:
			slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
			return slope
		except:
			return 0

	def get_control_stats(self):
		return {'trend': self.calculate_trend(), 'integral_error': self.integral_error, 'last_error': self.last_error, 'error_history': list(self.error_history), 'temp_history': list(self.temp_history)}

	def reset(self):
		self.temp_history.clear()
		self.error_history.clear()
		self.integral_error = 0
		self.last_error = 0
		self.last_control_time = 0

	def calculate_soft_pid_output(self, current_temp, setpoint, dt):
		if current_temp is None or setpoint is None:
			return 0.0
		kp = self.config.get_param('pid_kp_std')
		ti = self.config.get_param('pid_ti_std')
		td = self.config.get_param('pid_td_std')
		if kp is None or kp <= 0:
			kp = 1.0
		if ti is None or ti <= 0:
			ti = 100.0
		if td is None:
			td = 0.0
		pid_min = self.config.get_param('pid_min_volts') or 0.0
		pid_max = self.config.get_param('pid_max_volts') or 10.0
		error = setpoint - current_temp
		self.add_temp_to_history(time.time(), current_temp)
		self.add_error_to_history(error)
		p_term = kp * error
		if dt > 0:
			derivative = (error - self.last_error) / dt
		else:
			derivative = 0
		d_term = kp * td * derivative
		self.integral_error += error * dt
		i_term = kp * self.integral_error / ti
		if i_term > pid_max:
			i_term = pid_max
			self.integral_error = i_term * ti / kp
		elif i_term < pid_min:
			i_term = pid_min
			self.integral_error = i_term * ti / kp
		output = p_term + i_term + d_term
		self.p_value = p_term
		self.i_value = i_term
		self.d_value = d_term
		output = max(pid_min, min(pid_max, output))
		self.last_error = error
		return output