# lin_pump.py - LIN Pump Handler for Grundfos UPM4 series
# Communicates with LIN-enabled circulator pumps via LIN1-1.1 FrSet module
# Implements VDMA 24226 LIN Circulator Profile (4 unconditional frames)
#
# Communication approach: one-shot master TX/RX with cyclic SET_PUMP keepalive
# Based on proven protocol from test_LIN_pump_v0_1.py

import time

# Control mode constants
MODE_CC = 0  # Constant Curve
MODE_CP = 1  # Constant Pressure
MODE_PP = 2  # Proportional Pressure

# Control mode name mapping
MODE_NAMES = {MODE_CC: 'cc', MODE_CP: 'cp', MODE_PP: 'pp'}
MODE_FROM_NAME = {'cc': MODE_CC, 'cp': MODE_CP, 'pp': MODE_PP}

# LIN frame IDs per VDMA 24226
FRAME_SET_PUMP = 0x01       # Master TX: control setpoint, mode, on/off
FRAME_STATUS_GET = 0x02     # Master RX: RPM, head, flow, temp
FRAME_ADVANCED_GET = 0x03   # Master RX: power, voltage indicator
FRAME_MANU_SPECIFIC = 0x04  # Master RX: vendor-specific (Grundfos)

# LIN1-1.1 FrSet parameter addresses (v0.78 firmware)
P_MODULE    = 0    # Module identification string
P_LIN_ID    = 6    # LIN frame ID for current operation
P_LIN_N     = 8    # Received byte count (Variant D: resets on read)
P_LIN_BUF   = 10   # 8-byte frame data buffer (read/write)
P_TIME_UPD  = 12   # Cycle time: 0=stop, 1=send once, >1=cyclic (ms)
P_RXF_POP   = 14   # Pop one entry from RX FIFO (returns 16-bit word)
P_LIN_PAUSE = 16   # Min inter-packet pause in ms (VDMA requires >=20ms)
P_BAUDRATE  = 18   # LIN baudrate
P_V_24      = 38   # 24V power supply voltage reading

# Timing constants
V24_MIN = 8.0               # Minimum supply voltage for pump (V)
V24_WAIT_S = 30             # Max time to wait for power (s)
FRAME_INTERVAL = 0.025      # Min interval between frames (s)
PUMP_RESPONSE_MS = 500      # Timeout waiting for slave response (ms)


class LinPumpHandler:
    """Handler for LIN-bus communication with Grundfos UPM4 circulator pumps.

    Uses LIN1-1.1 FrSet module with one-shot master TX/RX protocol:
    - SET_PUMP (ID 1): Cyclic master TX at 200ms to keep pump alive
    - Status_GET (ID 2): Periodic one-shot master RX for pump status
    - ADVANCED_GET (ID 3): Periodic one-shot master RX for power data
    - MANU_SPECIFIC (ID 4): Periodic one-shot master RX for vendor data
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
        # SET_PUMP is sent cyclically; track if we need to update the data
        self._set_pump_dirty = True

    def init_module(self):
        """Configure LIN1-1.1 module: verify presence, wait for power,
        set baudrate and pause, drain FIFO, start cyclic SET_PUMP.

        Returns:
            bool: True if module configured successfully
        """
        try:
            print("Initializing LIN1-1.1 module at slot %d..." % self.slot)

            # Verify module is present
            module_id = self.fr.read(P_MODULE, slot=self.slot)
            if module_id is None:
                print("LIN1-1.1 module not found at slot %d" % self.slot)
                return False
            print("Found module: %s" % module_id)

            # Wait for V_24 supply voltage (pump needs power)
            if not self._wait_power():
                print("ERROR: No power on V_24 line!")
                return False

            # Set baudrate
            self.fr.write(P_BAUDRATE, self.baudrate, slot=self.slot)
            time.sleep(0.2)
            baud_readback = self.fr.read(P_BAUDRATE, slot=self.slot)
            print("Baudrate: %s (requested %d)" % (baud_readback, self.baudrate))

            # Set minimum inter-packet pause (VDMA requires >=20ms)
            self.fr.write(P_LIN_PAUSE, 20, slot=self.slot)
            time.sleep(0.05)

            # Drain any stale data from RX FIFO
            self._drain_fifo()

            # Send initial SET_PUMP with CommandON=0 (pump off for safety)
            self.command_on = 0
            self._send_set_pump_once()

            # Start cyclic SET_PUMP at 200ms to prevent pump fallback
            self._start_cyclic_set_pump()

            self.initialized = True
            self._comm_errors = 0
            print("LIN1-1.1 module initialized successfully")
            return True

        except Exception as e:
            print("LIN1-1.1 init failed: %s" % e)
            self.initialized = False
            return False

    def _wait_power(self):
        """Wait for V_24 supply voltage to reach minimum threshold.

        Returns:
            bool: True if voltage is sufficient
        """
        v24 = self.fr.read(P_V_24, slot=self.slot)
        if v24 is not None and v24 >= V24_MIN:
            print("V_24 = %.1fV - OK" % v24)
            return True

        print("V_24 = %.1fV - waiting..." % (v24 if v24 is not None else 0))
        t0 = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), t0) < V24_WAIT_S * 1000:
            time.sleep(0.5)
            v24 = self.fr.read(P_V_24, slot=self.slot)
            if v24 is not None and v24 >= V24_MIN:
                print("V_24 = %.1fV - OK" % v24)
                return True

        v24 = self.fr.read(P_V_24, slot=self.slot)
        print("TIMEOUT! V_24 = %.1fV (need >= %.1fV)" % (
            v24 if v24 is not None else 0, V24_MIN))
        return False

    def _drain_fifo(self):
        """Clear stale entries from RX FIFO."""
        for _ in range(32):
            rxf = self.fr.read(P_RXF_POP, slot=self.slot)
            if rxf is None or rxf == 0:
                break

    def _lin_set_id(self, lin_id):
        """Select LIN frame ID for next operation."""
        self.fr.write(P_LIN_ID, lin_id & 0x3F, slot=self.slot)
        time.sleep(0.02)

    def _lin_write_data(self, data_bytes):
        """Write 8-byte frame data to LIN buffer."""
        self.fr.write(P_LIN_BUF, bytearray(data_bytes), slot=self.slot)
        time.sleep(0.02)

    def _lin_send_once(self):
        """Trigger a single LIN frame transmission."""
        self.fr.write(P_TIME_UPD, 1, slot=self.slot)
        time.sleep(0.02)

    def _lin_master_tx(self, lin_id, data_bytes):
        """Send data as master TX (header + data from master)."""
        self._lin_set_id(lin_id)
        self._lin_write_data(data_bytes)
        self._lin_send_once()
        time.sleep(FRAME_INTERVAL)

    def _lin_master_rx(self, lin_id, timeout_ms=PUMP_RESPONSE_MS):
        """Send header (master RX) and wait for slave response.

        Args:
            lin_id: LIN frame ID to request
            timeout_ms: Max wait time for response

        Returns:
            tuple: (n, data) where n is byte count (negative if CRC error),
                   data is raw bytes. Returns (None, None) on timeout.
        """
        self._lin_set_id(lin_id)
        # Variant D: clear stale LIN_N before triggering send
        self.fr.read(P_LIN_N, slot=self.slot)
        self._lin_send_once()

        t0 = time.ticks_ms()
        while True:
            n = self.fr.read(P_LIN_N, slot=self.slot)
            if n is not None and n != 0:
                data = self.fr.read(P_LIN_BUF, slot=self.slot)
                return (n, data)
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return (None, None)
            time.sleep(0.02)

    def _send_set_pump_once(self):
        """Encode and send a single SET_PUMP frame."""
        frame_data = self.encode_set_pump()
        self._lin_master_tx(FRAME_SET_PUMP, frame_data)

    def _stop_cyclic(self):
        """Stop cyclic SET_PUMP transmission."""
        self.fr.write(P_TIME_UPD, 0, slot=self.slot)
        time.sleep(0.02)

    def _start_cyclic_set_pump(self, frame_data=None):
        """Start cyclic SET_PUMP transmission at 200ms interval.
        Optionally accepts pre-encoded frame data to avoid re-encoding."""
        self._lin_set_id(FRAME_SET_PUMP)
        if frame_data is None:
            frame_data = self.encode_set_pump()
        self._lin_write_data(frame_data)
        # Set cyclic period - module auto-repeats at this interval
        self.fr.write(P_TIME_UPD, 200, slot=self.slot)
        time.sleep(0.02)

    def _update_cyclic_set_pump(self):
        """Update the SET_PUMP data for ongoing cyclic transmission.
        Only writes new data to the buffer; the module continues cycling."""
        self._lin_set_id(FRAME_SET_PUMP)
        self._lin_write_data(self.encode_set_pump())

    def update(self):
        """Main update cycle - called from main loop each iteration.

        1. Sync control parameters from config
        2. Update cyclic SET_PUMP data if changed
        3. Handle startup sequence
        4. Batch all pending reads in a single stop/restart cycle
        """
        if not self.initialized:
            return

        try:
            # Sync control parameters from config manager
            self._sync_from_config()

            # Handle startup sequence
            if not self._startup_done:
                self._handle_startup()

            # Update SET_PUMP data if parameters changed
            if self._set_pump_dirty:
                self._update_cyclic_set_pump()
                self._set_pump_dirty = False

            now = time.time()

            # Collect pending reads to batch them in a single stop/restart
            pending = []
            if now - self._last_status_read >= 0.5:
                pending.append(FRAME_STATUS_GET)
            if now - self._last_advanced_read >= 2.0:
                pending.append(FRAME_ADVANCED_GET)
            if now - self._last_manu_read >= 5.0:
                pending.append(FRAME_MANU_SPECIFIC)

            if pending:
                self._do_pending_reads(pending, now)

        except Exception as e:
            self._comm_errors += 1
            if self._comm_errors % 10 == 1:
                print("LIN update error (%d): %s" % (self._comm_errors, e))

    def _sync_from_config(self):
        """Sync control parameters from config manager.
        Marks SET_PUMP data dirty if anything changed."""
        sp = self.config_manager.get_param('pump_setpoint') or 0.0
        if sp != self.setpoint:
            self.setpoint = sp
            self._set_pump_dirty = True

        mode_val = self.config_manager.get_param('pump_control_mode')
        if mode_val is not None and mode_val != self.control_mode:
            self.control_mode = mode_val
            self._set_pump_dirty = True

        cmd = self.config_manager.get_param('pump_command_on')
        if cmd is not None and cmd != self.command_on:
            self.command_on = cmd
            self._set_pump_dirty = True

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
        elif self.command_on != 0:
            # Force pump off during startup — persist to config so a reboot
            # doesn't restart the pump before ReadyForOperation is confirmed
            self.command_on = 0
            self._set_pump_dirty = True
            self.config_manager.set_param('pump_command_on', 0)

    def _do_pending_reads(self, frame_ids, now):
        """Batch one-shot master RX reads in a single stop/restart cycle.

        Stops cyclic SET_PUMP once, performs all pending reads, then
        restarts cyclic once. Saves SPI overhead vs. individual stop/restart.

        Args:
            frame_ids: list of FRAME_* constants to read
            now: current time.time() value (avoids redundant syscalls)
        """
        # Stop cyclic SET_PUMP once for all reads
        self._stop_cyclic()

        for frame_id in frame_ids:
            n, data = self._lin_master_rx(frame_id)
            got_data = n is not None and n != 0 and data is not None

            if frame_id == FRAME_STATUS_GET:
                self._last_status_read = now
                if got_data:
                    self.decode_status_get(data, abs(n), crc_ok=(n > 0))
                    self._comm_errors = 0
                else:
                    self._comm_errors += 1
            elif frame_id == FRAME_ADVANCED_GET:
                self._last_advanced_read = now
                if got_data:
                    self.decode_advanced_get(data, abs(n))
            elif frame_id == FRAME_MANU_SPECIFIC:
                self._last_manu_read = now
                if got_data:
                    self.decode_manu_specific(data, abs(n))

        # Restart cyclic SET_PUMP once after all reads
        self._start_cyclic_set_pump()

    # --- Frame encoding ---

    def encode_set_pump(self):
        """Encode SET_PUMP frame (ID 1, 8 bytes) from current control parameters.

        VDMA 24226 byte layout:
            Byte 0: Setpoint_SET [7:0] (lower 8 bits of 10-bit value)
            Byte 1: [CommandON:7][RotDir:6][ControlMode:5-2][Setpoint:1-0]
            Bytes 2-7: 0x00 (reserved)

        Returns:
            bytearray: 8-byte SET_PUMP frame
        """
        # Quantize setpoint: 0-100% with 0.1 resolution -> raw 0-1000
        raw = int(min(max(self.setpoint, 0.0), 100.0) * 10)

        data = bytearray(8)
        data[0] = raw & 0xFF                          # Setpoint [7:0]
        data[1] = ((raw >> 8) & 0x03)                 # Setpoint [9:8]
        data[1] |= (self.control_mode & 0x0F) << 2   # ControlMode [5:2]
        data[1] |= (self.rotation_dir & 0x01) << 6   # RotationDirection [6]
        data[1] |= (self.command_on & 0x01) << 7      # CommandON [7]
        # Bytes 2-7: reserved, fill with 0x00
        return data

    # --- Frame decoding ---

    def decode_status_get(self, data, n_bytes, crc_ok=True):
        """Decode Status_GET frame (ID 2) using byte-level access.

        Matches proven test file decode: byte-by-byte field extraction
        with raw values (no scaling factors applied to RPM/head/flow).

        Args:
            data: raw frame data (bytes or bytearray)
            n_bytes: number of valid bytes received
            crc_ok: True if CRC was valid
        """
        if data is None or n_bytes < 2:
            return

        # Bytes 0-1: setpoint, control mode, rotation, operational status
        sp_raw = data[0] | ((data[1] & 0x03) << 8)
        self.status['actual_setpoint'] = round(sp_raw / 10.0, 1)
        self.status['control_mode'] = (data[1] >> 2) & 0x0F
        self.status['control_mode_name'] = MODE_NAMES.get(
            self.status['control_mode'], '?')
        self.status['rotation_direction'] = (data[1] >> 6) & 0x01
        self.status['operational_status'] = (data[1] >> 7) & 0x01

        # Byte 2: flags
        if n_bytes >= 3:
            self.status['ready_for_operation'] = data[2] & 0x01
            self.status['warning'] = (data[2] >> 1) & 0x01
            self.status['error'] = (data[2] >> 2) & 0x01
            self.status['final_error'] = (data[2] >> 3) & 0x01

        # Bytes 2-3: RPM (bits 20-29 = upper nibble of byte 2 + lower 6 of byte 3)
        if n_bytes >= 4:
            rpm = ((data[2] >> 4) & 0x0F) | ((data[3] & 0x3F) << 4)
            self.status['rpm'] = rpm

        # Bytes 3-4: Head (bits 30-37 = upper 2 of byte 3 + lower 6 of byte 4)
        if n_bytes >= 5:
            head = ((data[3] >> 6) & 0x03) | ((data[4] & 0x3F) << 2)
            self.status['head'] = head  # cm H2O, raw value

        # Bytes 4-6: Flow (bits 38-51 = upper 2 of byte 4 + byte 5 + lower 4 of byte 6)
        if n_bytes >= 7:
            flow = ((data[4] >> 6) & 0x03) | (data[5] << 2) | (
                (data[6] & 0x0F) << 10)
            self.status['flow'] = flow

        # Bytes 6-7: FluidTemp (bits 52-62) and OperationalLimitReached (bit 63)
        if n_bytes >= 8:
            temp_raw = ((data[6] >> 4) & 0x0F) | ((data[7] & 0x7F) << 4)
            self.status['fluid_temp_raw'] = temp_raw
            # Apply VDMA offset: factor 0.1, offset -20
            self.status['fluid_temp'] = round(temp_raw * 0.1 - 20.0, 1)
            self.status['limit_reached'] = (data[7] >> 7) & 0x01

        self.status['crc_ok'] = crc_ok

    def decode_advanced_get(self, data, n_bytes):
        """Decode ADVANCED_GET frame (ID 3) using byte-level access.

        Args:
            data: raw frame data
            n_bytes: number of valid bytes received
        """
        if data is None or n_bytes < 2:
            return

        # Bytes 0-1: Power (14 bits = byte 0 + lower 6 of byte 1)
        power = data[0] | ((data[1] & 0x3F) << 8)
        self.status['power'] = power  # raw Watts

        # Bytes 1-2: PowerOnIndicator (4 bits spanning byte boundary)
        if n_bytes >= 3:
            pon = ((data[1] >> 6) & 0x03) | ((data[2] & 0x03) << 2)
            self.status['power_on_indicator'] = pon

        # Bytes 2-3: Mains voltage (7 bits)
        if n_bytes >= 4:
            voltage = ((data[2] >> 2) & 0x3F) | ((data[3] & 0x01) << 6)
            self.status['mains_voltage'] = voltage

        # Byte 7: ResponseError (bit 63)
        if n_bytes >= 8:
            self.status['response_error'] = (data[7] >> 7) & 0x01

    def decode_manu_specific(self, data, n_bytes):
        """Decode MANU_SPECIFIC frame (ID 4) - Grundfos-specific.

        Best-effort decode of vendor-specific data. Stores raw bytes
        for diagnostics since format varies between pump models.

        Args:
            data: raw frame data
            n_bytes: number of valid bytes received
        """
        if data is None or n_bytes < 2:
            return

        # Best-effort Grundfos decode
        if n_bytes >= 2:
            kv_raw = data[0] | (data[1] << 8)
            self.status['kv'] = round(kv_raw * 0.01, 2)

        if n_bytes >= 4:
            low_flow_raw = data[2] | (data[3] << 8)
            self.status['low_flow_threshold'] = round(low_flow_raw * 0.1, 1)

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
            self._set_pump_dirty = True

    def set_control_mode(self, mode):
        """Set pump control mode.

        Args:
            mode: Mode string ('cc', 'cp', 'pp') or int (0, 1, 2)
        """
        if isinstance(mode, str):
            mode_int = MODE_FROM_NAME.get(mode.lower())
            if mode_int is None:
                print("Unknown control mode: %s" % mode)
                return
        else:
            mode_int = int(mode)
            if mode_int not in MODE_NAMES:
                print("Invalid control mode: %d" % mode_int)
                return

        success, msg = self.config_manager.set_param('pump_control_mode', mode_int)
        if success:
            self.control_mode = mode_int
            self._set_pump_dirty = True

    def set_command_on(self, on):
        """Set pump on/off command.

        Args:
            on: True/1 to enable pump, False/0 to disable
        """
        val = 1 if on else 0
        success, msg = self.config_manager.set_param('pump_command_on', val)
        if success:
            self.command_on = val
            self._set_pump_dirty = True

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
        """Send immediate pump off command (safety shutdown).
        Stops cyclic transmission, sends stop command, restarts cyclic with OFF."""
        self.command_on = 0
        self.setpoint = 0.0
        self._set_pump_dirty = True
        if self.initialized:
            try:
                # Stop any cyclic transmission
                self._stop_cyclic()
                # Send stop command immediately
                self._send_set_pump_once()
                # Restart cyclic with OFF command
                self._start_cyclic_set_pump()
            except Exception as e:
                print("Emergency stop write failed: %s" % e)
