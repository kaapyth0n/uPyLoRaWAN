import time

class TemperatureController:
    """Advanced temperature controller with trend analysis"""
    
    def __init__(self, config_manager):
        """Initialize temperature controller
        
        Args:
            config_manager: Reference to configuration manager
        """
        self.config = config_manager
        self.temp_history = []  # Replace deque with a list
        self.max_history_len = 60  # Store up to 60 readings manually
        self.error_history = []  # Same change for error history
        self.max_error_len = 10  # Store up to 10 errors manually
        self.last_control_time = 0
        self.integral_error = 0
        self.last_error = 0
        self.min_control_interval = 1.0  # Minimum time between control decisions

        # Add public variables for PID components
        self.p_value = None
        self.i_value = None
        self.d_value = None

        # Filtered temperature for slow thermal systems
        self.filtered_temp = None         # Current filtered temperature value
        self.last_filter_time = 0         # Timestamp of last filter update

    def add_temp_to_history(self, timestamp, temp):
        """Add a temperature reading to the history"""
        if len(self.temp_history) >= self.max_history_len:
            self.temp_history.pop(0)  # Remove the oldest entry
        self.temp_history.append((timestamp, temp))
    
    def add_error_to_history(self, error):
        """Add an error value to the history"""
        if len(self.error_history) >= self.max_error_len:
            self.error_history.pop(0)  # Remove the oldest entry
        self.error_history.append(error)
        
    def calculate_control_action(self, current_temp, setpoint, dt):
        """Calculate control action using advanced algorithm
        
        Args:
            current_temp (float): Current temperature reading
            setpoint (float): Target temperature
            dt (float): Time since last control action
            
        Returns:
            tuple: (should_heat (bool), error_magnitude (float))
        """
        if current_temp is None or setpoint is None:
            return False, 0
            
        # Basic safety checks
        if current_temp > self.config.get_param('max_temp'):
            return False, 0
            
        # Calculate basic error
        error = setpoint - current_temp
        
        # Store history
        self.add_temp_to_history(time.time(), current_temp)
        self.add_error_to_history(error)
        
        # Calculate integral error with anti-windup
        self.integral_error += error * dt
        max_integral = 20.0  # Prevent excessive integral term
        self.integral_error = max(-max_integral, min(max_integral, self.integral_error))
        
        # Calculate derivative term
        derivative = (error - self.last_error) / dt if dt > 0 else 0
        
        # Get control parameters
        hysteresis = self.config.get_param('hysteresis')
        
        # Calculate temperature trend
        trend = self.calculate_trend()
        
        # Decision logic
        should_heat = False
        
        # Simple hysteresis control
        if abs(error) > hysteresis:
            should_heat = error > 0
        else:
            # Use trend information for fine control
            if trend < -0.1:  # Temperature falling
                should_heat = error >= -hysteresis/2
            elif trend > 0.1:  # Temperature rising
                should_heat = error > hysteresis/2
            else:  # Stable temperature
                should_heat = error > 0
                
        # Additional checks based on trend and history
        if should_heat:
            # Check if heating too aggressive
            if trend > 0.5:  # Temperature rising too fast
                should_heat = False
        else:
            # Check if cooling too aggressive
            if trend < -0.5:  # Temperature falling too fast
                should_heat = True
                
        self.last_error = error
        return should_heat, abs(error)
        
    def calculate_trend(self):
        """Calculate temperature trend from history
        
        Returns:
            float: Temperature change rate (°C/minute)
        """
        if len(self.temp_history) < 2:
            return 0
            
        # Calculate linear regression slope
        times = [(t - self.temp_history[0][0])/60.0 for t, _ in self.temp_history]
        temps = [t for _, t in self.temp_history]
        
        n = len(times)
        sum_x = sum(times)
        sum_y = sum(temps)
        sum_xy = sum(x * y for x, y in zip(times, temps))
        sum_xx = sum(x * x for x in times)
        
        try:
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x * sum_x)
            return slope
        except:
            return 0
            
    def get_control_stats(self):
        """Get control statistics
        
        Returns:
            dict: Control statistics
        """
        return {
            'trend': self.calculate_trend(),
            'integral_error': self.integral_error,
            'last_error': self.last_error,
            'error_history': list(self.error_history),
            'temp_history': list(self.temp_history)
        }
        
    def reset(self):
        """Reset controller state"""
        self.temp_history.clear()
        self.error_history.clear()
        self.integral_error = 0
        self.last_error = 0
        self.last_control_time = 0
        self.filtered_temp = None
        self.last_filter_time = 0

    def update_filtered_temp(self, current_temp, dt):
        """Update the filtered (low-pass) temperature value

        Implements a first-order low-pass filter (exponential moving average):
            filtered = alpha * current + (1 - alpha) * filtered
        where alpha = dt / (tau + dt)

        Args:
            current_temp (float): Current raw temperature reading
            dt (float): Time since last update (seconds)

        Returns:
            float: Filtered temperature value, or current_temp if filtering disabled
        """
        if current_temp is None:
            return self.filtered_temp

        tau = self.config.get_param('temp_filter_tau')

        # If filtering is disabled (tau=0), just return current temp
        if tau is None or tau <= 0:
            self.filtered_temp = current_temp
            return current_temp

        # Initialize filter on first call
        if self.filtered_temp is None:
            self.filtered_temp = current_temp
            self.last_filter_time = time.time()
            return current_temp

        # Calculate filter coefficient
        # alpha approaches 1 as dt >> tau (fast response to changes)
        # alpha approaches 0 as dt << tau (slow response, more filtering)
        alpha = dt / (tau + dt)

        # Apply exponential moving average filter
        self.filtered_temp = alpha * current_temp + (1 - alpha) * self.filtered_temp
        self.last_filter_time = time.time()

        return self.filtered_temp

    def get_effective_temp(self, current_temp, dt):
        """Get the effective temperature for control calculations

        Returns filtered temperature if filtering is enabled (temp_filter_tau > 0),
        otherwise returns the raw current temperature.

        Args:
            current_temp (float): Current raw temperature reading
            dt (float): Time since last update (seconds)

        Returns:
            float: Temperature to use for control calculations
        """
        tau = self.config.get_param('temp_filter_tau')

        if tau is not None and tau > 0:
            return self.update_filtered_temp(current_temp, dt)
        else:
            return current_temp

    def calculate_soft_pid_output(self, current_temp, setpoint, dt):
        """Calculate software PID output using standard form parameters

        Uses filtered temperature if temp_filter_tau > 0, which helps with
        slow thermal systems that have significant oscillation or noise.

        Args:
            current_temp (float): Current temperature reading (will be filtered if enabled)
            setpoint (float): Target temperature
            dt (float): Time since last control action

        Returns:
            float: Output value (0-max_volts)
        """
        if current_temp is None or setpoint is None:
            return 0.0

        # Get effective temperature (filtered if enabled)
        effective_temp = self.get_effective_temp(current_temp, dt)

        # Get PID parameters - standard form
        kp = self.config.get_param('pid_kp_std')
        ti = self.config.get_param('pid_ti_std')
        td = self.config.get_param('pid_td_std')

        # Safety checks for parameters
        if kp is None or kp <= 0:
            kp = 1.0  # Default value
        if ti is None or ti <= 0:
            ti = 100.0  # Prevent division by zero
        if td is None:
            td = 0.0  # Default to no derivative action

        # Get min/max voltage limits
        pid_min = self.config.get_param('pid_min_volts') or 0.0
        pid_max = self.config.get_param('pid_max_volts') or 10.0

        # Calculate error using effective (possibly filtered) temperature
        error = setpoint - effective_temp
        
        # Store history
        self.add_temp_to_history(time.time(), current_temp)
        self.add_error_to_history(error)
        
        # Calculate proportional term
        p_term = kp * error
        
        # Calculate derivative term
        if dt > 0:
            # Use error difference for derivative calculation
            derivative = (error - self.last_error) / dt
        else:
            derivative = 0
        
        d_term = kp * td * derivative
        
        # Calculate integral term with dynamic anti-windup
        # Limit integral based on available control range after P contribution
        
        # Update integral with error contribution
        self.integral_error += error * dt
        
        # Calculate integral term
        i_term = kp * self.integral_error / ti
        
        # Apply limits to integral term
        if i_term > pid_max:
            i_term = pid_max
            # Recalculate integral_error to match limited i_term
            self.integral_error = i_term * ti / kp
        elif i_term < pid_min:
            i_term = pid_min
            # Recalculate integral_error to match limited i_term
            self.integral_error = i_term * ti / kp
        
        # Calculate final output
        output = p_term + i_term + d_term
        
        # Store the PID components as public variables for MQTT reporting
        self.p_value = p_term
        self.i_value = i_term
        self.d_value = d_term
        
        # Apply global limits
        output = max(pid_min, min(pid_max, output))
        
        # Store last error for next derivative calculation
        self.last_error = error

        return output

    def calculate_direct_sensor_output(self, current_temp, setpoint, dt,
                                        min_r, max_r, current_r, rate_limit, invert):
        """Calculate PID-controlled resistance output for direct_sensor mode

        Uses PID to control resistance output directly for unknown NTC/PTC sensors.
        Unlike ntc10k mode which adjusts simulated temperature, this mode outputs
        resistance directly as the PID control variable.

        Uses filtered temperature if temp_filter_tau > 0, which helps with
        slow thermal systems that have significant oscillation or noise.

        Args:
            current_temp (float): Current flow temperature reading (will be filtered if enabled)
            setpoint (float): Target flow temperature
            dt (float): Time since last control action (seconds)
            min_r (float): Minimum resistance bound (Ohms)
            max_r (float): Maximum resistance bound (Ohms)
            current_r (float): Current resistance output (Ohms)
            rate_limit (float): Maximum resistance change per update (Ohms)
            invert (int): 0=NTC (normal), 1=PTC (inverted control direction)

        Returns:
            float: New resistance value (clamped and rate-limited)
        """
        # Handle invalid inputs by returning current resistance
        if current_temp is None or setpoint is None or current_r is None:
            return current_r if current_r is not None else (min_r + max_r) / 2

        # Get effective temperature (filtered if enabled)
        effective_temp = self.get_effective_temp(current_temp, dt)

        # Get PID parameters from config (reuse soft_pid parameters)
        kp = self.config.get_param('pid_kp_std')
        ti = self.config.get_param('pid_ti_std')
        td = self.config.get_param('pid_td_std')

        # Safety checks for parameters
        if kp is None or kp <= 0:
            kp = 1.0
        if ti is None or ti <= 0:
            ti = 100.0
        if td is None:
            td = 0.0

        # Calculate error using effective (possibly filtered) temperature
        error = setpoint - effective_temp

        # Invert error for PTC sensors (inverted control direction)
        if invert:
            error = -error

        # Store history for trend analysis
        self.add_temp_to_history(time.time(), current_temp)
        self.add_error_to_history(error)

        # Calculate proportional term
        p_term = kp * error

        # Calculate derivative term
        if dt > 0:
            derivative = (error - self.last_error) / dt
        else:
            derivative = 0
        d_term = kp * td * derivative

        # Update integral with error contribution
        self.integral_error += error * dt

        # Calculate integral term
        i_term = kp * self.integral_error / ti

        # Calculate midpoint of resistance range
        midpoint = (min_r + max_r) / 2
        output_range = (max_r - min_r) / 2

        # Limit integral term to prevent windup beyond output range
        if i_term > output_range:
            i_term = output_range
            self.integral_error = i_term * ti / kp
        elif i_term < -output_range:
            i_term = -output_range
            self.integral_error = i_term * ti / kp

        # Calculate PID output as offset from midpoint
        pid_output = p_term + i_term + d_term

        # Store PID components for reporting
        self.p_value = p_term
        self.i_value = i_term
        self.d_value = d_term

        # Calculate new resistance: midpoint + pid_output
        # For NTC: error > 0 (too cold) -> pid_output > 0 -> decrease resistance
        # The control direction depends on how the boiler interprets outdoor sensor
        new_r = midpoint + pid_output

        # Apply rate limiting
        if rate_limit > 0 and current_r is not None:
            delta = new_r - current_r
            if abs(delta) > rate_limit:
                new_r = current_r + (rate_limit if delta > 0 else -rate_limit)

        # Clamp to bounds
        new_r = max(min_r, min(max_r, new_r))

        # Store last error for next derivative calculation
        self.last_error = error

        return new_r