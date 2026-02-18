# lin_pump.py - LIN Pump Handler for Grundfos UPM4 series
# Communicates with LIN-enabled circulator pumps via LIN1-1.1 FrSet module
# Implements VDMA 24226 LIN Circulator Profile (4 unconditional frames)

import time

# Control mode constants
MODE_CC = 0  # Constant Curve
MODE_CP = 1  # Constant Pressure
MODE_PP = 2  # Proportional Pressure

# Control mode name mapping
MODE_NAMES = {MODE_CC: 'cc', MODE_CP: 'cp', MODE_PP: 'pp'}
MODE_FROM_NAME = {'cc': MODE_CC, 'cp': MODE_CP, 'pp': MODE_PP}

# LIN frame IDs per VDMA 24226
FRAME_SET_PUMP = 1       # Master write: control setpoint, mode, on/off
FRAME_STATUS_GET = 2     # Slave response: RPM, head, flow, temp
FRAME_ADVANCED_GET = 3   # Slave response: power, voltage indicator
FRAME_MANU_SPECIFIC = 4  # Slave response: vendor-specific (Grundfos)

# LIN1-1.1 FrSet parameter addresses
LIN_PARAM_ID = 6         # Set LIN frame ID for packet table entry
LIN_PARAM_N = 8          # Set number of packet table entries
LIN_PARAM_BUF = 10       # Read/write 8-byte frame data + 4-byte metadata
LIN_PARAM_TIME = 12      # Set cycle time per entry (ms)
LIN_PARAM_RXF_POP = 14   # Pop received frames from FIFO
LIN_PARAM_PAUSE = 16     # Pause/resume cyclic sending
LIN_PARAM_BAUDRATE = 18  # Set baudrate


class LinPumpHandler:
    """Handler for LIN-bus communication with Grundfos UPM4 circulator pumps.

    Uses LIN1-1.1 FrSet module to exchange VDMA 24226 frames:
    - SET_PUMP (ID 1): Write setpoint, control mode, on/off
    - Status_GET (ID 2): Read RPM, head, flow, fluid temp
    - ADVANCED_GET (ID 3): Read power input, power-on indicator
    - MANU_SPECIFIC (ID 4): Read vendor-specific data (Grundfos Kv, low flow)
    """

    def __init__(self, fr, config_manager, slot=8, baudrate=19200):
        """Initialize LIN pump handler.

        Args:
            fr: FrSet interface instance
            config_manager: ConfigurationManager instance for pump parameters
            slot: FrSet slot number for LIN1-1.1 module (default 8)
            baudrate: LIN bus baudrate (default 19200 per VDMA 24226)
        """
        self.fr = fr
        self.config_manager = config_manager
        self.slot = slot
        self.baudrate = baudrate

        # Current control parameters (written to SET_PUMP frame)
        self.setpoint = 0.0       # 0-100% with 0.1 resolution
        self.control_mode = MODE_CC
        self.rotation_dir = 0     # 0 = default direction
        self.command_on = 0       # 0 = off, 1 = on

        # Parsed pump status from received frames
        self.status = {}

        # Module state
        self.initialized = False
        self._startup_done = False
        self._last_status_read = 0
        self._last_advanced_read = 0
        self._last_manu_read = 0
        self._comm_errors = 0

    def init_module(self):
        """Configure LIN1-1.1 module: baudrate, packet table entries, cycle times.

        Packet table layout:
        - Entry 0: ID 1 (SET_PUMP), master write, 100ms cycle
        - Entry 1: ID 2 (Status_GET), slave read, 100ms cycle
        - Entry 2: ID 3 (ADVANCED_GET), slave read, 250ms cycle
        - Entry 3: ID 4 (MANU_SPECIFIC), slave read, 1000ms cycle

        Returns:
            bool: True if module configured successfully
        """
        try:
            print(f"Initializing LIN1-1.1 module at slot {self.slot}...")

            # Verify module is present
            module_id = self.fr.read(0, slot=self.slot)
            if module_id is None:
                print(f"LIN1-1.1 module not found at slot {self.slot}")
                return False
            print(f"Found module: {module_id}")

            # Pause cyclic sending during configuration
            self.fr.write(LIN_PARAM_PAUSE, 1, slot=self.slot)
            time.sleep_ms(50)

            # Set baudrate to 19200 (VDMA 24226 standard)
            self.fr.write(LIN_PARAM_BAUDRATE, self.baudrate, slot=self.slot)
            time.sleep_ms(50)

            # Set number of packet table entries to 4
            self.fr.write(LIN_PARAM_N, 4, slot=self.slot)
            time.sleep_ms(50)

            # Configure packet table entries
            # Entry 0: SET_PUMP (ID 1), master write, 100ms
            self._configure_packet_entry(0, FRAME_SET_PUMP, is_write=True, cycle_ms=100)

            # Entry 1: Status_GET (ID 2), slave read, 100ms
            self._configure_packet_entry(1, FRAME_STATUS_GET, is_write=False, cycle_ms=100)

            # Entry 2: ADVANCED_GET (ID 3), slave read, 250ms
            self._configure_packet_entry(2, FRAME_ADVANCED_GET, is_write=False, cycle_ms=250)

            # Entry 3: MANU_SPECIFIC (ID 4), slave read, 1000ms
            self._configure_packet_entry(3, FRAME_MANU_SPECIFIC, is_write=False, cycle_ms=1000)

            # Write initial SET_PUMP frame with CommandON=0 (pump off for safety)
            self.command_on = 0
            self._write_set_pump()

            # Resume cyclic sending
            self.fr.write(LIN_PARAM_PAUSE, 0, slot=self.slot)
            time.sleep_ms(100)

            self.initialized = True
            self._comm_errors = 0
            print("LIN1-1.1 module initialized successfully")
            return True

        except Exception as e:
            print(f"LIN1-1.1 init failed: {e}")
            self.initialized = False
            return False

    def _configure_packet_entry(self, entry_idx, frame_id, is_write, cycle_ms):
        """Configure a single packet table entry in LIN1-1.1 module.

        Args:
            entry_idx: Packet table entry index (0-3)
            frame_id: LIN frame ID (1-4)
            is_write: True for master write, False for slave read
            cycle_ms: Cycle time in milliseconds
        """
        # Select the packet table entry by writing entry index
        # Then set frame ID, direction, and cycle time
        # LIN1-1.1 uses LIN_ID parameter to configure each entry sequentially

        # Build entry configuration:
        # High byte: entry index, Low byte: frame_id | (direction << 6)
        direction_bit = 0x00 if is_write else 0x40  # bit 6 = direction (0=write, 1=read)
        entry_config = (entry_idx << 8) | (frame_id & 0x3F) | direction_bit
        self.fr.write(LIN_PARAM_ID, entry_config, slot=self.slot)
        time.sleep_ms(20)

        # Set cycle time for this entry
        cycle_config = (entry_idx << 16) | (cycle_ms & 0xFFFF)
        self.fr.write(LIN_PARAM_TIME, cycle_config, slot=self.slot)
        time.sleep_ms(20)

    def update(self):
        """Main update cycle - called from main loop each iteration.

        1. Load control parameters from config
        2. Encode and write SET_PUMP frame
        3. Read and decode response frames from FIFO
        4. Handle startup sequence (send OFF first, check ready, then enable)
        """
        if not self.initialized:
            return

        try:
            # Sync control parameters from config manager
            self._sync_from_config()

            # Handle startup sequence
            if not self._startup_done:
                self._handle_startup()

            # Write SET_PUMP frame with current control parameters
            self._write_set_pump()

            # Read received frames from FIFO
            self._read_responses()

        except Exception as e:
            self._comm_errors += 1
            if self._comm_errors % 10 == 1:
                print(f"LIN update error ({self._comm_errors}): {e}")

    def _sync_from_config(self):
        """Sync control parameters from config manager."""
        self.setpoint = self.config_manager.get_param('pump_setpoint') or 0.0
        mode_val = self.config_manager.get_param('pump_control_mode')
        if mode_val is not None:
            self.control_mode = mode_val
        cmd = self.config_manager.get_param('pump_command_on')
        if cmd is not None:
            self.command_on = cmd

    def _handle_startup(self):
        """Handle pump startup sequence.

        Startup requires:
        1. Send CommandON=0 (pump off)
        2. Wait for ReadyForOperation flag
        3. Then allow CommandON=1 if requested
        """
        # Check if pump reports ReadyForOperation
        if self.status.get('ready_for_operation'):
            self._startup_done = True
            print("LIN pump ready for operation")
        else:
            # Force pump off during startup
            self.command_on = 0

    def _write_set_pump(self):
        """Encode and write SET_PUMP frame (ID 1) to LIN1-1.1 module."""
        frame_data = self.encode_set_pump()

        # Write frame data to LIN_buf for entry 0 (SET_PUMP)
        # Prepend entry index byte so module knows which entry this data is for
        buf = bytearray(1) + frame_data
        buf[0] = 0  # entry index 0
        self.fr.write(LIN_PARAM_BUF, buf, slot=self.slot)

    def _read_responses(self):
        """Read and decode response frames from LIN1-1.1 FIFO."""
        # Pop frames from RxF FIFO - each pop returns one frame
        # Try to read up to 4 frames per cycle
        for _ in range(4):
            try:
                raw = self.fr.packet(LIN_PARAM_RXF_POP, b'\x00', n=12, slot=self.slot)
                if raw is None or len(raw) < 12:
                    break

                # Frame format from LIN1-1.1:
                # Bytes 0-7: frame data (8 bytes)
                # Byte 8: frame ID
                # Byte 9: status/flags
                # Bytes 10-11: timestamp or reserved
                frame_data = raw[0:8]
                frame_id = raw[8] & 0x3F  # lower 6 bits = LIN ID
                frame_status = raw[9]

                # Check if frame is valid (status byte indicates success)
                if frame_status & 0x80:  # error flag
                    continue

                # Decode based on frame ID
                if frame_id == FRAME_STATUS_GET:
                    self.decode_status_get(frame_data)
                elif frame_id == FRAME_ADVANCED_GET:
                    self.decode_advanced_get(frame_data)
                elif frame_id == FRAME_MANU_SPECIFIC:
                    self.decode_manu_specific(frame_data)

            except Exception:
                break

    # --- Frame encoding ---

    def encode_set_pump(self):
        """Encode SET_PUMP frame (ID 1, 8 bytes) from current control parameters.

        Bit layout (LSB-first byte order):
            Bits [0:9]   = Setpoint_SET (10 bits, factor 0.1, 0-100%)
            Bits [10:13] = ControlMode_SET (4 bits: 0=CC, 1=CP, 2=PP)
            Bits [14]    = RotationDirection_SET (1 bit)
            Bits [15]    = CommandON_SET (1 bit)
            Bits [16:63] = Reserved (0xFF fill)

        Returns:
            bytearray: 8-byte SET_PUMP frame
        """
        # Quantize setpoint: 0-100% with 0.1 resolution -> 0-1000
        sp_raw = int(min(max(self.setpoint, 0.0), 100.0) * 10) & 0x3FF

        # Pack bits 0-15 into two bytes (little-endian)
        mode_bits = (self.control_mode & 0x0F) << 10
        rot_bit = (self.rotation_dir & 0x01) << 14
        cmd_bit = (self.command_on & 0x01) << 15

        word0 = sp_raw | mode_bits | rot_bit | cmd_bit

        data = bytearray(8)
        data[0] = word0 & 0xFF
        data[1] = (word0 >> 8) & 0xFF
        # Bytes 2-7: reserved, fill with 0xFF per VDMA spec
        data[2] = 0xFF
        data[3] = 0xFF
        data[4] = 0xFF
        data[5] = 0xFF
        data[6] = 0xFF
        data[7] = 0xFF

        return data

    # --- Frame decoding ---

    def decode_status_get(self, data):
        """Decode Status_GET frame (ID 2, 8 bytes) into status dict.

        Bit layout (LSB-first):
            Bits [0:9]   = ActualSetpoint (10b, factor 0.1, %)
            Bits [10:13] = ControlMode (4b)
            Bits [14]    = RotationDirection (1b)
            Bits [15]    = OperationalStatus (1b)
            Bits [16]    = ReadyForOperation (1b)
            Bits [17]    = WarningPresent (1b)
            Bits [18]    = ErrorPresent (1b)
            Bits [19]    = FinalErrorPresent (1b)
            Bits [20:29] = EstimatedRPM (10b, factor 10, rpm)
            Bits [30:37] = EstimatedHead (8b, factor 10, cm H2O -> m H2O)
            Bits [38:51] = EstimatedFlow (14b, factor 10, l/h)
            Bits [52:62] = FluidTemp (11b, factor 0.1, offset -20, °C)
            Bits [63]    = OperationalLimitReached (1b)

        Args:
            data: 8-byte frame data
        """
        if len(data) < 8:
            return

        # Convert bytes to a 64-bit integer (little-endian)
        val = 0
        for i in range(8):
            val |= data[i] << (i * 8)

        # Extract bit fields
        actual_setpoint = (val & 0x3FF) * 0.1               # bits 0-9
        control_mode = (val >> 10) & 0x0F                     # bits 10-13
        rotation_dir = (val >> 14) & 0x01                     # bit 14
        operational_status = (val >> 15) & 0x01               # bit 15
        ready_for_op = (val >> 16) & 0x01                     # bit 16
        warning = (val >> 17) & 0x01                          # bit 17
        error = (val >> 18) & 0x01                            # bit 18
        final_error = (val >> 19) & 0x01                      # bit 19
        rpm = ((val >> 20) & 0x3FF) * 10                      # bits 20-29, factor 10
        head_raw = (val >> 30) & 0xFF                         # bits 30-37
        head_cm = head_raw * 10                               # factor 10, in cm H2O
        flow = ((val >> 38) & 0x3FFF) * 0.1                   # bits 38-51, factor 10 -> l/h
        fluid_temp_raw = (val >> 52) & 0x7FF                  # bits 52-62
        fluid_temp = fluid_temp_raw * 0.1 - 20.0             # factor 0.1, offset -20
        limit_reached = (val >> 63) & 0x01                    # bit 63

        # Update status dict
        self.status['actual_setpoint'] = round(actual_setpoint, 1)
        self.status['control_mode'] = control_mode
        self.status['control_mode_name'] = MODE_NAMES.get(control_mode, '?')
        self.status['rotation_direction'] = rotation_dir
        self.status['operational_status'] = operational_status
        self.status['ready_for_operation'] = ready_for_op
        self.status['warning'] = warning
        self.status['error'] = error
        self.status['final_error'] = final_error
        self.status['rpm'] = rpm
        self.status['head'] = head_cm
        self.status['flow'] = round(flow, 1)
        self.status['fluid_temp'] = round(fluid_temp, 1)
        self.status['limit_reached'] = limit_reached

        self._last_status_read = time.time()
        self._comm_errors = 0  # Reset error counter on successful read

    def decode_advanced_get(self, data):
        """Decode ADVANCED_GET frame (ID 3, 8 bytes).

        Bit layout (LSB-first):
            Bits [0:13]  = EstimatedPowerInput (14b, factor 0.2, W)
            Bits [14:17] = PowerOnIndicator (4b)
            Bits [18:62] = Reserved
            Bit  [63]    = ResponseError

        Args:
            data: 8-byte frame data
        """
        if len(data) < 8:
            return

        val = 0
        for i in range(8):
            val |= data[i] << (i * 8)

        power_raw = val & 0x3FFF                              # bits 0-13
        power = power_raw * 0.2                               # factor 0.2, in Watts
        power_on_indicator = (val >> 14) & 0x0F               # bits 14-17
        response_error = (val >> 63) & 0x01                   # bit 63

        self.status['power'] = round(power, 1)
        self.status['power_on_indicator'] = power_on_indicator
        self.status['response_error'] = response_error

        self._last_advanced_read = time.time()

    def decode_manu_specific(self, data):
        """Decode MANU_SPECIFIC frame (ID 4, 8 bytes) - Grundfos-specific.

        Best-effort decode of vendor-specific data.
        Format may vary between pump models. Common Grundfos fields:
            Bits [0:15]  = Kv value (16b, factor 0.01)
            Bits [16:31] = Low flow threshold (16b, factor 0.1, l/h)

        Args:
            data: 8-byte frame data
        """
        if len(data) < 8:
            return

        val = 0
        for i in range(8):
            val |= data[i] << (i * 8)

        # Grundfos-specific fields (best-effort, may not apply to all models)
        kv_raw = val & 0xFFFF
        kv = kv_raw * 0.01
        low_flow_raw = (val >> 16) & 0xFFFF
        low_flow = low_flow_raw * 0.1

        self.status['kv'] = round(kv, 2)
        self.status['low_flow_threshold'] = round(low_flow, 1)

        self._last_manu_read = time.time()

    # --- Public control API ---

    def get_status(self):
        """Return current parsed pump status dict for MQTT publishing.

        Returns:
            dict: Pump status values with physical units
        """
        return self.status

    def set_setpoint(self, value):
        """Set pump setpoint (0-100%).

        Args:
            value: Setpoint percentage (float, 0.0-100.0)
        """
        value = min(max(float(value), 0.0), 100.0)
        success, msg = self.config_manager.set_param('pump_setpoint', value)
        if success:
            self.setpoint = value

    def set_control_mode(self, mode):
        """Set pump control mode.

        Args:
            mode: Mode string ('cc', 'cp', 'pp') or int (0, 1, 2)
        """
        if isinstance(mode, str):
            mode_int = MODE_FROM_NAME.get(mode.lower())
            if mode_int is None:
                print(f"Unknown control mode: {mode}")
                return
        else:
            mode_int = int(mode)
            if mode_int not in MODE_NAMES:
                print(f"Invalid control mode: {mode_int}")
                return

        success, msg = self.config_manager.set_param('pump_control_mode', mode_int)
        if success:
            self.control_mode = mode_int

    def set_command_on(self, on):
        """Set pump on/off command.

        Args:
            on: True/1 to enable pump, False/0 to disable
        """
        val = 1 if on else 0
        success, msg = self.config_manager.set_param('pump_command_on', val)
        if success:
            self.command_on = val

    def is_comm_ok(self):
        """Check if LIN communication is working.

        Returns:
            bool: True if recent frames were received successfully
        """
        if not self.initialized:
            return False
        now = time.time()
        # Consider communication OK if we got a status frame within last 5 seconds
        return (now - self._last_status_read) < 5

    def emergency_stop(self):
        """Send immediate pump off command (safety shutdown)."""
        self.command_on = 0
        self.setpoint = 0.0
        if self.initialized:
            try:
                self._write_set_pump()
            except Exception as e:
                print(f"Emergency stop write failed: {e}")
