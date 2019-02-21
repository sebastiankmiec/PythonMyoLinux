from pymyolinux.core.bluegiga import BlueGigaProtocol
from pymyolinux.util.packet_def import *
from pymyolinux.util.event import Event
import struct


class MyoDongle():
    """
        Represents a single Myo dongle, that leverages the Bluegiga API.
    """

    #
    # Connection parameters
    #
    default_latency = 0     # This parameter configures the slave latency. Slave latency defines how many connection
                            # intervals a slave device can skip.

    default_timeout = 64    # How long the devices can be out of range before the connection is closed (units of 10ms).
                            # Range: 10 - 3200

    # Range: 6 - 3200 (in units of 1.25ms).
    #   Note: Lower implies faster data transfer, but potentially less reliable data exchanges.
    #
    default_conn_interval_min   = 6     # Time between consecutive connection events (a connection interval).
                                        # (E.g. a data exchange before going back to an idle state to save power)
    default_conn_interval_max   = 6

    #
    # GATT parameters
    #
    MIN_HANDLE      = 0x1
    MAX_HANDLE      = 0xffff
    PRIMARY_SERVICE = b'\x00\x28'

    def __init__(self, com_port):
        """
            DESC

        :param com_port: Refers to a path to a character device file, for a usb to BLE controller serial interface.
                            e.g. /dev/ttyACM0
        """
        self.ble = BlueGigaProtocol(com_port)

        # Filled via "discover_primary_services()"
        self.handles        = {}
        self.imu_enabled    = False
        self.emg_enabled    = False
        self.sleep_disabled = False

    def clear_state(self, timeout=2):

        if not (self.ble.connection is None):

            #
            # Disable IMU readings
            #
            if self.imu_enabled:
                # Unsubscribe
                self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                              self.handles["imu_descriptor"],
                                                                              disable_notifications),
                                   BlueGigaProtocol.ble_rsp_attclient_attribute_write)

                resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
                if not resp_received:
                    raise RuntimeError("GATT procedure (write completion to CCCD) response timed out.")

            #
            # Disable EMG readings
            #
            if self.emg_enabled:
                for emg_num in range(4):
                    self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                                  self.handles["emg_descriptor_" +
                                                                                               str(emg_num)],
                                                                                  disable_notifications),
                                       BlueGigaProtocol.ble_rsp_attclient_attribute_write)

                    resp_received = self.ble.read_packets_conditional(
                        BlueGigaProtocol.ble_evt_attclient_procedure_completed)
                    if not resp_received:
                        raise RuntimeError("GATT procedure (write completion to CCCD, emg {}) response timed out.".
                                           format(emg_num))

            if self.imu_enabled or self.emg_enabled:
                mode_command_payload = struct.pack('<5B', Myo_Commands.myohw_command_set_mode.value,
                                                   3,  # Payload size
                                                   EMG_Modes.myohw_emg_mode_none.value,
                                                   IMU_Modes.myohw_imu_mode_none.value,
                                                   Classifier_Modes.myohw_classifier_mode_disabled.value)

                self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                              self.handles["command_characteristic"],
                                                                              mode_command_payload),
                                   BlueGigaProtocol.ble_rsp_attclient_attribute_write)

                resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
                if not resp_received:
                    raise RuntimeError("GATT procedure (write completion) response timed out.")

            if self.sleep_disabled:
                sleep_mode              = Sleep_Modes.myohw_sleep_mode_normal.value
                mode_command_payload    = struct.pack('<3B', Myo_Commands.myohw_command_set_sleep_mode.value,
                                                        1,  # Payload size
                                                        sleep_mode)

                self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                    self.handles["command_characteristic"],
                                    mode_command_payload),
                                    BlueGigaProtocol.ble_rsp_attclient_attribute_write)

                resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
                if not resp_received:
                    raise RuntimeError("GATT procedure (write completion) response timed out.")

        self.emg_enabled    = False
        self.imu_enabled    = False
        self.sleep_disabled = False

        # Disable dongle advertisement
        self.transmit_wait(self.ble.ble_cmd_gap_set_mode(GAP_Discoverable_Modes.gap_non_discoverable.value,
                                                            GAP_Connectable_Modes.gap_non_connectable.value),
                                BlueGigaProtocol.ble_rsp_gap_set_mode)

        # Disconnect any connected devices
        max_num_connections = 8
        for i in range(max_num_connections):
            self.transmit_wait(self.ble.ble_cmd_connection_disconnect(i),
                                    BlueGigaProtocol.ble_rsp_connection_disconnect)
            if self.ble.disconnecting:
                # Need to wait for disconnect response
                resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_connection_disconnected,
                                                                        timeout)
                if not resp_received:
                    raise RuntimeError("Disconnect response timed out.")

        # Stop scanning
        self.transmit_wait(self.ble.ble_cmd_gap_end_procedure(), BlueGigaProtocol.ble_rsp_gap_end_procedure)
        self.handles    = {}

    def discover_myo_devices(self, timeout=2):
        # Scan for advertising packets
        self.transmit_wait(self.ble.ble_cmd_gap_discover(GAP_Discover_Mode.gap_discover_observation.value),
                                BlueGigaProtocol.ble_rsp_gap_discover)
        self.ble.read_packets(timeout)

        # Stop scanning
        self.transmit_wait(self.ble.ble_cmd_gap_end_procedure(), BlueGigaProtocol.ble_rsp_gap_end_procedure)

        return self.ble.myo_devices

    def connect(self, myo_device_found, timeout=2):
        if self.ble.connection is not None:
            raise RuntimeError("BLE connection is not None.")

        # Attempt to connect
        self.transmit_wait(self.ble.ble_cmd_gap_connect_direct(myo_device_found["sender_address"],
                                                myo_device_found["address_type"],
                                                self.default_conn_interval_min, self.default_conn_interval_max,
                                                self.default_timeout, self.default_latency),
                                BlueGigaProtocol.ble_rsp_gap_connect_direct)

        # Need to wait for conenction response
        resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_connection_status, timeout)
        if not resp_received:
            return False
        return True

    def discover_primary_services(self, timeout=10):
        if self.ble.connection is None:
            raise RuntimeError("BLE connection is None.")

        #
        # Find primary service groups
        #
        self.transmit_wait(self.ble.ble_cmd_attclient_read_by_group_type(self.ble.connection["connection"],
                                                                            self.MIN_HANDLE, self.MAX_HANDLE,
                                                                            self.PRIMARY_SERVICE),
                                BlueGigaProtocol.ble_rsp_attclient_read_by_group_type)

        resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed,
                                                                timeout)
        if not resp_received:
            raise RuntimeError("GATT procedure completion response timed out.")

        #
        # For each service group:
        #   -> Find available attributes
        #
        for service in self.ble.services_found:
            self.transmit_wait(self.ble.ble_cmd_attclient_find_information(self.ble.connection["connection"],
                                                                            service["start"], service["end"]),
                                    BlueGigaProtocol.ble_rsp_attclient_find_information)

            resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed,
                                                               timeout)
            if not resp_received:
                raise RuntimeError("GATT procedure completion response timed out.")

    def transmit(self, packet_contents):
        self.ble.transmit_packet(packet_contents)

    def transmit_wait(self, packet_contents, event, timeout=2):
        self.ble.transmit_packet(packet_contents)
        resp_received = self.ble.read_packets_conditional(event, timeout)
        if not resp_received:
            raise RuntimeError("Response timed out for the transmitted command.")

    def add_imu_handler(self, handler):
        """
            On receiving an IMU data packet.
        :param handler: A function to be called with the following signature:
                            ---> myfunc_data_handler_123(orient_w, orient_x, orient_y, orient_z, accel_1,
                                                                accel_2, accely_3, gyro_1, gyro_2, gyro_3)
        """
        if not self.imu_enabled:
            raise RuntimeError("IMU readings are not enabled.")
        self.ble.imu_event += handler

    def enable_imu_readings(self, timeout=2):
        if self.ble.connection is None:
            raise RuntimeError("BLE connection is None.")

        #
        # Ensure handles have been discovered
        #
        self.check_handles()

        self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                        self.handles["imu_descriptor"],
                                                                        enable_notifications),
                                BlueGigaProtocol.ble_rsp_attclient_attribute_write)

        resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
        if not resp_received:
            raise RuntimeError("GATT procedure (write completion to CCCD) response timed out.")


        #
        # Need to go one step further, by issuing a command to set "Myo device mode"
        #
        emg_mode                = EMG_Modes.myohw_emg_mode_send_emg.value if self.emg_enabled else \
                                    EMG_Modes.myohw_emg_mode_none.value

        mode_command_payload    = struct.pack('<5B', Myo_Commands.myohw_command_set_mode.value,
                                                3, # Payload size
                                                emg_mode, IMU_Modes.myohw_imu_mode_send_data.value,
                                                Classifier_Modes.myohw_classifier_mode_disabled.value)

        self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                        self.handles["command_characteristic"],
                                                                        mode_command_payload),
                           BlueGigaProtocol.ble_rsp_attclient_attribute_write)

        resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
        if not resp_received:
            raise RuntimeError("GATT procedure (write completion) response timed out.")

        self.imu_enabled = True

    def add_emg_handler(self, handler):
        """
            On receiving an EMG data packet.
        :param handler: A function to be called with the following signature:
                            ---> myfunc_data_handler_123(emg_list, sample_num)
        """
        if not self.emg_enabled:
            raise RuntimeError("EMG readings are not enabled.")
        self.ble.emg_event += handler

    def enable_emg_readings(self):
        if self.ble.connection is None:
            raise RuntimeError("BLE connection is None.")

        #
        # Ensure handles have been discovered
        #
        self.check_handles()

        for emg_num in range(4):
            self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                            self.handles["emg_descriptor_" +
                                                                                         str(emg_num)],
                                                                            enable_notifications),
                                    BlueGigaProtocol.ble_rsp_attclient_attribute_write)

            resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
            if not resp_received:
                raise RuntimeError("GATT procedure (write completion to CCCD, emg {}) response timed out.".
                                        format(emg_num))

        #
        # Need to go one step further, by issuing a command to set "Myo device mode"
        #
        imu_mode                = IMU_Modes.myohw_imu_mode_send_data.value if self.imu_enabled else \
                                    IMU_Modes.myohw_imu_mode_none.value

        mode_command_payload    = struct.pack('<5B', Myo_Commands.myohw_command_set_mode.value,
                                                3, # Payload size
                                                EMG_Modes.myohw_emg_mode_send_emg.value, imu_mode,
                                                Classifier_Modes.myohw_classifier_mode_disabled.value)

        self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                        self.handles["command_characteristic"],
                                                                        mode_command_payload),
                           BlueGigaProtocol.ble_rsp_attclient_attribute_write)

        resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
        if not resp_received:
            raise RuntimeError("GATT procedure (write completion) response timed out.")

        self.emg_enabled        = True

    def add_joint_emg_imu_handler(self, handler):
        """
              On receiving an EMG data packet, use the latest IMU packet.
              :param handler: A function to be called with the following signature:
                                  ---> myfunc_data_handler_123(emg_list, orient_w, orient_x, orient_y, orient_z, accel_1,
                                                                        accel_2, accel_3, gyro_1, gyro_2, gyro_3,
                                                                        sample_num)
        """
        if not self.imu_enabled:
            raise RuntimeError("IMU readings are not enabled.")
        if not self.emg_enabled:
            raise RuntimeError("EMG readings are not enabled.")
        self.ble.joint_emg_imu_event += handler

    def read_battery_level(self):
        if self.ble.connection is None:
            raise RuntimeError("BLE connection is None.")

        #
        # Ensure handles have been discovered
        #
        self.check_handles()

        #
        # Issue a command to read Myo device battery level
        #
        self.transmit_wait(self.ble.ble_cmd_attclient_read_by_handle(self.ble.connection["connection"],
                                                                      self.ble.battery_handle),
                                BlueGigaProtocol.ble_evt_attclient_attribute_value)

        return self.ble.battery_level

    def set_sleep_mode(self, device_can_sleep):
        if self.ble.connection is None:
            raise RuntimeError("BLE connection is None.")

        #
        # Ensure handles have been discovered
        #
        self.check_handles()

        #
        # Issue a command to set "Myo device sleep mode"
        #
        sleep_mode = Sleep_Modes.myohw_sleep_mode_normal.value if device_can_sleep else \
            Sleep_Modes.myohw_sleep_mode_never_sleep.value

        mode_command_payload = struct.pack('<3B', Myo_Commands.myohw_command_set_sleep_mode.value,
                                               1,  # Payload size
                                               sleep_mode)

        self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                      self.handles["command_characteristic"],
                                                                      mode_command_payload),
                           BlueGigaProtocol.ble_rsp_attclient_attribute_write)

        resp_received = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
        if not resp_received:
            raise RuntimeError("GATT procedure (write completion) response timed out.")

        self.sleep_disabled = not device_can_sleep

    def scan_for_data_packets(self, time=10):
        self.ble.read_packets(time)

    def scan_for_data_packets_conditional(self, time=10):
        disconnect_occurred = self.ble.read_packets_conditional(BlueGigaProtocol.ble_evt_connection_disconnected, time)
        return disconnect_occurred

    # Helper functions
    def check_handles(self):
        # Need to be able to activate notifications via writing to descriptor handles
        #
        if len(self.handles.keys()) == 0:
            self.discover_primary_services()
            if len(self.ble.attributes_found) == 0:
                raise RuntimeError("No attributes found, ensure discover_primary_services() was called.")
            self.fill_handles()

    def fill_handles(self):
        imu_uuid        = get_full_uuid(HW_Services.IMUDataCharacteristic.value)
        command_uuid    = get_full_uuid(HW_Services.CommandCharacteristic.value)
        emg_uuid_0      = get_full_uuid(HW_Services.EmgData0Characteristic.value)
        emg_uuid_1      = get_full_uuid(HW_Services.EmgData1Characteristic.value)
        emg_uuid_2      = get_full_uuid(HW_Services.EmgData2Characteristic.value)
        emg_uuid_3      = get_full_uuid(HW_Services.EmgData3Characteristic.value)
        battery_uuid    = HW_Services.BatteryLevelCharacteristic.value

        for attribute in self.ble.attributes_found:
            if attribute["uuid"].endswith(imu_uuid):
                # Assumption:
                #       > Client Characteristic Configuration Descriptor comes right after characteristic attribute.
                self.ble.imu_handle             = attribute["chrhandle"]
                self.handles["imu_descriptor"]  = attribute["chrhandle"] + 1

            elif attribute["uuid"].endswith(command_uuid):
                self.handles["command_characteristic"] = attribute["chrhandle"]

            elif attribute["uuid"].endswith(emg_uuid_0):
                self.ble.emg_handle_0               = attribute["chrhandle"]
                self.handles["emg_descriptor_0"]    = attribute["chrhandle"] + 1
            elif attribute["uuid"].endswith(emg_uuid_1):
                self.ble.emg_handle_1               = attribute["chrhandle"]
                self.handles["emg_descriptor_1"]    = attribute["chrhandle"] + 1
            elif attribute["uuid"].endswith(emg_uuid_2):
                self.ble.emg_handle_2               = attribute["chrhandle"]
                self.handles["emg_descriptor_2"]    = attribute["chrhandle"] + 1
            elif attribute["uuid"].endswith(emg_uuid_3):
                self.ble.emg_handle_3               = attribute["chrhandle"]
                self.handles["emg_descriptor_3"]    = attribute["chrhandle"] + 1

            elif attribute["uuid"].endswith(battery_uuid):
                self.ble.battery_handle = attribute["chrhandle"]

        if "imu_descriptor" not in self.handles:
            raise RuntimeError("Unable to find IMU attribute, in device's GATT database.")
        if "command_characteristic" not in self.handles:
            raise RuntimeError("Unable to find command attribute, in device's GATT database.")
        if "emg_descriptor_0" not in self.handles:
            raise RuntimeError("Unable to find EMG attribute 0, in device's GATT database.")
        if "emg_descriptor_1" not in self.handles:
            raise RuntimeError("Unable to find EMG attribute 1, in device's GATT database.")
        if "emg_descriptor_2" not in self.handles:
            raise RuntimeError("Unable to find EMG attribute 2, in device's GATT database.")
        if "emg_descriptor_3" not in self.handles:
            raise RuntimeError("Unable to find EMG attribute 3, in device's GATT database.")
