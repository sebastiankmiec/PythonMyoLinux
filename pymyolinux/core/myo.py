from pymyolinux.core.bluegiga import BlueGigaProtocol
from pymyolinux.util.packet_def import *
from pymyolinux.util.event import Event
import struct


class MyoDongle():

    #
    # Connection parameters
    #
    default_latency = 0     # This parameter configures the slave latency. Slave latency defines how many connection
                            # intervals a slave device can skip.

    default_timeout = 64    # How long the devices can be out of range before the connection is closed.
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
        self.ble        = BlueGigaProtocol(com_port)

        # Filled via "discover_primary_services()"
        self.handles        = {}
        self.imu_enabled    = False
        self.emg_enabled    = False

    def clear_state(self, timeout=2):
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
                resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_connection_disconnected,
                                                                        timeout)
                if not resp_received:
                    raise RuntimeError("Disconnect response timed out.")

        # Stop scanning
        self.transmit_wait(self.ble.ble_cmd_gap_end_procedure(), BlueGigaProtocol.ble_rsp_gap_end_procedure)
        self.descriptors    = {}

    def discover_myo_devices(self, timeout=2):
        # Scan for advertising packets
        self.transmit_wait(self.ble.ble_cmd_gap_discover(GAP_Discover_Mode.gap_discover_observation.value),
                                BlueGigaProtocol.ble_rsp_gap_discover)
        self.ble.read_incoming(timeout)

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
        resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_connection_status, timeout)
        if not resp_received:
            raise RuntimeError("Connection response timed out.")

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

        resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed,
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

            resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed,
                                                               timeout)
            if not resp_received:
                raise RuntimeError("GATT procedure completion response timed out.")

    def transmit(self, packet_contents):
        self.ble.send_command(packet_contents)

    def transmit_wait(self, packet_contents, event, timeout=2):
        self.ble.send_command(packet_contents)
        resp_received = self.ble.read_incoming_conditional(event, timeout)
        if not resp_received:
            raise RuntimeError("Response timed out for the transmitted command.")

    def add_imu_handler(self, handler):
        """
            On receiving an IMU data packet.
        :param handler: A function to be called with the following signature:
                            ---> myfunc_data_handler_123(orient_w, orient_x, orient_y, orient_z, accel_1,
                                                                accel_2, accely_3, gyro_1, gyro_2, gyro_3)
        """
        self.ble.imu_event += handler

    def enable_imu_readings(self, timeout=2):
        if self.ble.connection is None:
            raise RuntimeError("BLE connection is None.")
        if len(self.ble.imu_event._getfunctionlist()) == 0:
            raise RuntimeError("No event handlers given to imu_event.")

        #
        # Need to be able to activate notifcations via writing to descriptor handles
        #
        if len(self.descriptors.keys()) == 0:
            self.discover_primary_services()
            if len(self.ble.attributes_found) == 0:
                raise RuntimeError("No attributes found, ensure discover_primary_services() was called.")
            self.fill_handles()

        self.transmit_wait(self.ble.ble_cmd_attclient_attribute_write(self.ble.connection["connection"],
                                                                        self.handles["imu_descriptor"], b"\x01\x00"),
                                BlueGigaProtocol.ble_rsp_attclient_attribute_write)

        resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
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

        resp_received = self.ble.read_incoming_conditional(BlueGigaProtocol.ble_evt_attclient_procedure_completed)
        if not resp_received:
            raise RuntimeError("GATT procedure (write completion) response timed out.")

        self.imu_enabled = True

    def scan_for_data_packets(self, time=10):
        self.ble.read_incoming(time)

    def fill_handles(self):
        imu_uuid        = get_full_uuid(HW_Services.IMUDataCharacteristic.value)
        command_uuid    = get_full_uuid(HW_Services.CommandCharacteristic.value)

        for attribute in self.ble.attributes_found:
            if attribute["uuid"].endswith(imu_uuid):
                # Assumption:
                #       > Client Characteristic Configuration Descriptor comes right after characteristic attribute.
                self.ble.imu_handle             = attribute["chrhandle"]
                self.handles["imu_descriptor"]  = attribute["chrhandle"] + 1

            elif attribute["uuid"].endswith(command_uuid):
                self.handles["command_characteristic"] = attribute["chrhandle"]

        if "imu_descriptor" not in self.handles:
            raise RuntimeError("Unable to find IMU attribute, in device's GATT database.")
        if "command_characteristic" not in self.handles:
            raise RuntimeError("Unable to find command attribute, in device's GATT database.")
