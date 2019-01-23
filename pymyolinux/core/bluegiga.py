import struct
import serial
import time
from pymyolinux.util.event import Event
from pymyolinux.core.handlers import *

class BlueGigaProtocol():
    """
        An implementation of the Bluegiga API, following:
        "https://www.silabs.com/products/wireless/bluetooth/bluetooth-low-energy-modules/bled112-bluetooth-smart-dongle"
        --> See "Bluetooth Smart Software API Reference Manual for BLE Version 1.7" for details.
    """

    # Configurable
    debug = False

    # By default the BGAPI protocol assumes that UART flow control (RTS/CTS) is used to ensure reliable data
    # transmission and to prevent lost data because of buffer overflows.
    use_rts_cts         = True
    BLED112_BAUD_RATE   = 115200

    #
    # Myo device specific events
    #
    emg_event           = Event("On receiving an EMG data packet from the Myo device.", fire_type=0)
    imu_event           = Event("On receiving an IMU data packet from the Myo device.", fire_type=0)
    joint_emg_imu_event = Event("On receiving an IMU data packet from the Myo device. Use latest IMU event.",
                                    fire_type=0)

    # Non-empty events
    ble_evt_gap_scan_response                   = Event()
    ble_evt_connection_disconnected             = Event()
    ble_evt_connection_status                   = Event()
    ble_evt_attclient_group_found               = Event()
    ble_evt_attclient_procedure_completed       = Event()
    ble_evt_attclient_find_information_found    = Event()

    # Non-empty (response) events

    # Empty events
    ble_rsp_gap_set_mode                    = Event()
    ble_rsp_connection_disconnect           = Event()
    ble_rsp_gap_end_procedure               = Event()
    ble_rsp_gap_discover                    = Event()
    ble_rsp_attclient_read_by_group_type    = Event()
    ble_rsp_gap_connect_direct              = Event()
    ble_rsp_attclient_find_information      = Event()
    ble_rsp_attclient_attribute_write       = Event()
    ble_evt_attclient_attribute_value       = Event()

    # States
    read_buffer                 = b""
    expected_packet_length      = 0
    busy_reading                = False
    disconnecting               = False

    def __init__(self, com_port):

        self.com_port       = serial.Serial(port=com_port, baudrate=self.BLED112_BAUD_RATE, rtscts=self.use_rts_cts)
        self.is_packet_mode = not self.use_rts_cts

        # Filled by user of this object
        self.imu_handle         = None
        self.emg_handle_0       = None
        self.emg_handle_1       = None
        self.emg_handle_2       = None
        self.emg_handle_3       = None

        # Filled by event handlers
        self.myo_devices        = []
        self.services_found     = []
        self.attributes_found   = []
        self.connection         = None
        self.current_imu_read   = None

        # Event handlers
        self.ble_evt_gap_scan_response                  += add_myo_device
        self.ble_evt_connection_status                  += add_connection
        self.ble_evt_connection_disconnected            += device_disconnected
        self.ble_evt_attclient_group_found              += add_service_found
        self.ble_evt_attclient_procedure_completed      += service_finding_complete
        self.ble_evt_attclient_find_information_found   += add_attribute_found
        self.ble_evt_attclient_attribute_value          += on_receive_attribute_value

        # Empty handlers (solely to increment event fire count)
        empty_handler_events = [self.ble_rsp_gap_set_mode, self.ble_rsp_connection_disconnect,
                                    self.ble_rsp_gap_end_procedure, self.ble_rsp_gap_discover,
                                    self.ble_rsp_gap_connect_direct, self.ble_rsp_attclient_read_by_group_type,
                                    self.ble_rsp_attclient_find_information, self.ble_rsp_attclient_attribute_write]

        for empty_event in empty_handler_events:
            empty_event += empty_handler

    def transmit_packet(self, packet):
        """
            Given a bytes object, write to serial.

            Additionally, if in "packet mode" (from the API Reference Manual):

                "When using the BGAPI protocol without UART flow control over a simple 2-wire (TX and RX) UART interface
            and additional length byte needs to be added to the BGAPI packets, which tells the total length of the BGAPI
            packet excluding the length byte itself. This is used by the BGAPI protocol parser to identify the length of
            incoming commands and data and make sure they are fully received."

        :param packet: A bytes object.
        :return: None
        """

        # See comment above
        if self.is_packet_mode:
            packet = bytes([len(packet) & 0xFF]) + packet
        if self.debug:
            print('=>[ ' + ' '.join(['%02X' % b for b in packet]) + ' ]')

        self.com_port.write(packet)

    def read_packets(self, timeout=1):
        """
            Attempt to read bytes from communication port, with no intent of stopping early.

        :param timeout: Time spent reading
        :return: None
        """
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            self.busy_reading   = True
            time_spent          = time.time() - start_time
            time_left           = timeout - time_spent
            self.read_bytes(time_left)

    def read_packets_conditional(self, event, timeout=2):
        """
            Attempt to read bytes from communication port, prematurely stopping on occurence of an event.

        :param event: An event of interest (all events are defined at the start of BlueGigaProtocol)
        :param timeout: Time spent reading

        :return: Boolean, True => the event occurred
        """

        # Check if event has already occured
        if self.get_event_count(event) > 0:
            self.__eventcounter__[event] = 0
            return True

        start_time = time.time()
        while (time.time() - start_time) < timeout:
            self.busy_reading   = True
            time_spent          = time.time() - start_time
            time_left           = timeout - time_spent
            self.read_bytes(time_left)

            if self.get_event_count(event) > 0:
                self.__eventcounter__[event] = 0
                return True

        return False

    def get_event_count(self, event):
        """
            Returns the current event count of event, incremented by event handlers.

        :param event: An event of interest (all events are defined at the start of BlueGigaProtocol)
        :return: A count
        """

        if hasattr(self, "__eventcounter__"):
            if event in self.__eventcounter__:
                return self.__eventcounter__[event]
        return 0


    def read_bytes(self, timeout):
        """
            Attempts to read bytes from the communication port, and calls parse_byte() for processing.

        :param timeout: Time spent reading
        :return: Boolean, True => a byte was read, and it is not the last byte of a packet
        """
        self.com_port.timeout = timeout

        while True:
            byte_read = self.com_port.read(size=1)
            if len(byte_read) > 0:
                self.parse_byte(byte_read[0])

            # Timeout
            else:
                self.busy_reading = False

            # Either
            #   1. No bytes read
            #   2. Last byte of packet read
            if not self.busy_reading:
                break

        return self.busy_reading

    def parse_byte(self, byte_read):
        """
            Keeps track of bytes read. Upon completion of reading bytes from a packet, trigger an appropirate event.

        :param byte_read: A byte read via read_bytes().
        :return: None
        """

        """
            BGAPI packet format (from the API reference manual), as of 12/18/2018:
                        
            --------------------------------------------------------------------------------
            |Octet | Octet | Length | Description           | Notes                        |
            |      | bits  |        |                       |                              |
            -------------------------------------------------------------------------------|
            | 0    | 7     | 1 bit  | Message Type (MT)     | 0: Command/Response          |
            |      |       |        |                       | 1: Event                     |
            |      |       |        |                       |                              |
            -------------------------------------------------------------------------------|
            | ...  | 6:3   | 4 bits | Technology Type (TT)  | 0000: Bluetooth Smart        |
            |      |       |        |                       | 0001: Wi-Fi                  |      
            |      |       |        |                       |                              |
            --------------------------------------------------------------------------------
            | ...  | 2:0   | 3 bits | Length High (LH)      | Payload length (high bits)   |
            --------------------------------------------------------------------------------
            | 1    | 7:0   | 8 bits | Length Low (LL)       | Payload length (low bits)    |
            --------------------------------------------------------------------------------
            | 2    | 7:0   | 8 bits | Class ID (CID)        | Command class ID             |
            --------------------------------------------------------------------------------
            | 3    | 7:0   | 8 bits | Command ID (CMD)      | Command ID                   |
            --------------------------------------------------------------------------------
            | 4-n  | -     | 0-2048 | Payload (PL)          | Up to 2048 bytes of payload  |
            |      |       | Bytes  |                       |                              |
            --------------------------------------------------------------------------------
        """

        #
        # If valid Message/Technology Types
        #
        if (len(self.read_buffer) == 0 and
                (byte_read in [bluetooth_resp, bluetooth_event, wifi_resp, wifi_event])):
            self.read_buffer += bytes([byte_read])

        elif len(self.read_buffer) == 1:
            self.read_buffer            += bytes([byte_read])
            self.expected_packet_length  = packet_header_legnth + \
                                           (self.read_buffer[0] & packet_length_high_bits) + \
                                            self.read_buffer[1] # Payload length (low bits)

        elif len(self.read_buffer) > 1:
            self.read_buffer += bytes([byte_read])


        #
        # Read last byte of a packet, fire appropriate events
        #
        if self.expected_packet_length > 0 and len(self.read_buffer) == self.expected_packet_length:

            if self.debug:
                print('<=[ ' + ' '.join(['%02X' % b for b in self.read_buffer ]) + ' ]')

            packet_type, _, class_id, command_id = self.read_buffer[:packet_header_legnth]
            packet_payload = self.read_buffer[packet_header_legnth:]

            # Note: Part of this byte (and next byte "_") contains bits for payload length
            packet_type     = packet_type & packet_type_bits

            # Reset for next packet
            self.read_buffer = bytes([])


            #
            # (1) Bluetooth response packets
            #
            if packet_type == bluetooth_resp:

                #
                # Connection packets
                #
                if class_id == BGAPI_Classes.Connection.value:
                    if command_id == ble_rsp_connection_disconnect:
                        connection, result = struct.unpack('<BH', packet_payload[:3])
                        if result != disconnect_procedure_started:
                            if self.debug:
                                print("Failed to start disconnect procedure for connection {}.".format(connection))
                        else:
                            self.disconnecting = True
                            if self.debug:
                                print("Started disconnect procedure for connection {}.".format(connection))
                        self.ble_rsp_connection_disconnect(**{ 'connection': connection, 'result': result })

                #
                # GATT packets - discover services, acquire data
                #
                elif class_id == BGAPI_Classes.GATT.value:

                    if command_id == GATT_Response_Commands.ble_rsp_attclient_read_by_group_type.value:
                        connection, result = struct.unpack('<BH', packet_payload[:3])
                        self.ble_rsp_attclient_read_by_group_type(**{ 'connection': connection, 'result': result })

                    elif command_id == GATT_Response_Commands.ble_rsp_attclient_find_information.value:
                        connection, result = struct.unpack('<BH', packet_payload[:3])
                        if result != find_info_success:
                            if self.debug:
                                print("Error using find information command.")
                        self.ble_rsp_attclient_find_information(**{ 'connection': connection, 'result': result })

                    elif command_id == GATT_Response_Commands.ble_rsp_attclient_attribute_write.value:
                        connection, result = struct.unpack('<BH', packet_payload[:3])
                        if result != write_success:
                            raise("Write attempt was unsuccessful.")
                        self.ble_rsp_attclient_attribute_write(**{ 'connection': connection, 'result': result })

                #
                # GAP packets - advertise, observe, connect
                #
                elif class_id == BGAPI_Classes.GAP.value:

                    if command_id == GAP_Response_Commands.ble_rsp_gap_set_mode.value:
                        result = struct.unpack('<H', packet_payload[:2])[0]
                        if result != GAP_set_mode_success:
                            raise RuntimeError("Failed to set GAP mode.")
                        else:
                            if self.debug:
                                print("Successfully set GAP mode.")
                        self.ble_rsp_gap_set_mode(**{ 'result': result })

                    elif command_id == GAP_Response_Commands.ble_rsp_gap_discover.value:
                        result = struct.unpack('<H', packet_payload[:2])[0]
                        if result != GAP_start_procedure_success:
                            raise RuntimeError("Failed to start GAP discover procedure.")
                        self.ble_rsp_gap_discover(**{ 'result': result })

                    elif command_id == GAP_Response_Commands.ble_rsp_gap_connect_direct.value:
                        result, connection_handle = struct.unpack('<HB', packet_payload[:3])
                        if result != GAP_start_procedure_success:
                            raise RuntimeError("Failed to start GAP connection procedure.")
                        self.ble_rsp_gap_connect_direct(**{ 'result': result, 'connection_handle': connection_handle })

                    elif command_id == GAP_Response_Commands.ble_rsp_gap_end_procedure.value:
                        result = struct.unpack('<H', packet_payload[:2])[0]
                        if result != GAP_end_procedure_success:
                            if self.debug:
                                print("Failed to end GAP procedure.")
                        self.ble_rsp_gap_end_procedure(**{ 'result': result })


            #
            # (2) Bluetooth event packets
            #
            elif packet_type == bluetooth_event:

                #
                # Connection packets
                #
                if class_id == BGAPI_Classes.Connection.value:
                    if command_id == ble_evt_connection_status:
                        connection, flags, address, address_type, conn_interval, timeout, latency, bonding = struct.unpack('<BB6sBHHHB', packet_payload[:16])
                        args = { 'connection': connection, 'flags': flags, 'address': address, 'address_type': address_type, 'conn_interval': conn_interval, 'timeout': timeout, 'latency': latency, 'bonding': bonding }
                        print("Connected to a device with the following parameters:\n{}".format(args))
                        self.ble_evt_connection_status(**args)

                    elif command_id == ble_evt_connection_disconnected:
                        connection, reason = struct.unpack('<BH', packet_payload[:3])
                        if (self.connection is None) or (connection == self.connection["connection"]):
                            self.ble_evt_connection_disconnected(**{ 'connection': connection, 'reason': reason })

                #
                # GATT packets - discover services, acquire data
                #
                elif class_id == BGAPI_Classes.GATT.value:

                    if command_id == GATT_Event_Commands.ble_evt_attclient_procedure_completed.value:
                        connection, result, chrhandle = struct.unpack('<BHH', packet_payload[:5])
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            self.ble_evt_attclient_procedure_completed(**{ 'connection': connection, 'result': result, 'chrhandle': chrhandle })

                    elif command_id == GATT_Event_Commands.ble_evt_attclient_group_found.value:
                        connection, start, end, uuid_len = struct.unpack('<BHHB', packet_payload[:6])
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            uuid_data = packet_payload[6:]
                            self.ble_evt_attclient_group_found(**{ 'connection': connection, 'start': start, 'end': end, 'uuid': uuid_data })

                    elif command_id == GATT_Event_Commands.ble_evt_attclient_find_information_found.value:
                        connection, chrhandle, uuid_len = struct.unpack('<BHB', packet_payload[:4])
                        uuid_data = packet_payload[4:]
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            self.ble_evt_attclient_find_information_found(**{ 'connection': connection, 'chrhandle': chrhandle, 'uuid': uuid_data })

                    elif command_id == GATT_Event_Commands.ble_evt_attclient_attribute_value.value:
                        connection, atthandle, type, value_len = struct.unpack('<BHBB', packet_payload[:5])
                        if (self.connection is not None) and (connection == self.connection["connection"]):
                            value_data = packet_payload[5:]
                            self.ble_evt_attclient_attribute_value(**{ 'connection': connection, 'atthandle': atthandle, 'type': type, 'value': value_data })

                #
                # GAP packets - advertise, observe, connect
                #
                elif class_id == BGAPI_Classes.GAP.value:

                    if command_id == GAP_Event_Commands.ble_evt_gap_scan_response.value:
                        rssi, packet_type, sender, address_type, bond, data_len = struct.unpack('<bB6sBBB', packet_payload[:11])
                        data_data = packet_payload[11:]
                        self.ble_evt_gap_scan_response(**{ 'rssi': rssi, 'packet_type': packet_type, 'sender': sender, 'address_type': address_type, 'bond': bond, 'data': data_data })

                    elif command_id == GAP_Event_Commands.ble_evt_gap_mode_changed.value:
                        pass
                        #discover, connect = struct.unpack('<BB', packet_payload[:2])
                        #self.ble_evt_gap_mode_changed({ 'discover': discover, 'connect': connect })

            #
            # (3) Wifi response packet
            #
            elif packet_type == wifi_resp:
                pass

            #
            # (4) Wifi event packet
            #
            else:
                pass

            # Reset
            self.busy_reading = False


    #
    # Byte Array Packing Functions ---> Construct all necessary BGAPI messages
    #

    def ble_cmd_connection_disconnect(self, connection):
        """
            This command disconnects an active Bluetooth connection.
                -> When link is disconnected a Disconnected event is produced.
        :param connection: Connection handle to close
        :return: Bytes object
        """
        payload_length  = 1
        packet_class    = BGAPI_Classes.Connection.value
        message_id      = ble_cmd_connection_disconnect
        return struct.pack('<4BB', command_message, payload_length, packet_class, message_id, connection)

    def ble_cmd_attclient_read_by_group_type(self, connection, start, end, uuid):
        """
            This command reads the value of each attribute of a given type and in a given handle range.
                -> The command is typically used for primary (UUID: 0x2800) and secondary (UUID: 0x2801) service
                    discovery.
                -> Discovered services are reported by Group Found event.
                -> Finally when the procedure is completed a Procedure Completed event is generated.

        :param connection: Connection Handle
        :param start: First requested handle number
        :param end: Last requested handle number
        :param uuid: Group UUID to find
        :return: Bytes object
        """
        payload_length  = 6 + len(uuid)
        packet_class    = BGAPI_Classes.GATT.value
        message_id      = ble_cmd_attclient_read_by_group_type
        return struct.pack('<4BBHHB' + str(len(uuid)) + 's', command_message, payload_length, packet_class, message_id,
                                connection, start, end, len(uuid), bytes(i for i in uuid))

    def ble_cmd_attclient_find_information(self, connection, start, end):
        """
            This command is used to discover attribute handles and their types (UUIDs) in a given handle range.
            -> Causes attclient find_information_found and attclient procedure_completed

        :param connection: Connection handle
        :param start: First attribute handle
        :param end: Last attribute handle
        :return: Bytes object
        """
        payload_length  = 5
        packet_class    = BGAPI_Classes.GATT.value
        messaged_id     = ble_cmd_attclient_find_information
        return struct.pack('<4BBHH', command_message, payload_length, packet_class, messaged_id, connection, start, end)

    def ble_cmd_attclient_attribute_write(self, connection, atthandle, data):
        """
            This command can be used to write an attributes value on a remote device. In order to write the value of an
                attribute a Bluetooth connection must exist.
                -> A successful attribute write will be acknowledged by the remote device and this will generate an
                    event attclient_procedure_completed.

        :param connection: Connection handle
        :param atthandle: Attribute handle to write to
        :param data: Attribute value
        :return: Bytes object
        """
        payload_length  = 4 + len(data)
        packet_class    = BGAPI_Classes.GATT.value
        message_id      = ble_cmd_attclient_attribute_write
        return struct.pack('<4BBHB' + str(len(data)) + 's', command_message, payload_length, packet_class, message_id,
                                connection, atthandle, len(data), bytes(i for i in data))

    def ble_cmd_gap_set_mode(self, discover, connect):
        """
                This command configures the current GAP discoverability and connectability modes. It can be used to
                    enable advertisements and/or allow connection. The command is also meant to fully stop advertising.

        :param discover: GAP Discoverable Mode
        :param connect: GAP Connectable Mode
        :return: Bytes object
        """
        payload_length  = 2
        packet_class    = BGAPI_Classes.GAP.value
        message_id      = ble_cmd_gap_set_mode
        return struct.pack('<4BBB', command_message, payload_length, packet_class, message_id, discover, connect)

    def ble_cmd_gap_discover(self, mode):
        """
            This command starts the GAP discovery procedure to scan for advertising devices i.e. to perform a device
                discovery.
                -> Scanning parameters can be configured with the Set Scan Parameters command before issuing this
                    command.
                -> To cancel on an ongoing discovery process use the End Procedure command.

        :param mode: GAP Discover mode
        :return: Bytes object
        """
        payload_length  = 1
        packet_class    = BGAPI_Classes.GAP.value
        message_id      = ble_cmd_gap_discover
        return struct.pack('<4BB', command_message, payload_length, packet_class, message_id, mode)

    def ble_cmd_gap_connect_direct(self, address, addr_type, conn_interval_min, conn_interval_max, timeout, latency):
        """
            This command will start the GAP direct connection establishment procedure to a dedicated Bluetooth Smart
            device.
                1) The Bluetooth module will enter a state where it continuously scans for the connectable
                    advertisement packets from the remote device which matches the Bluetooth address gives as a
                    parameter.
                2) Upon receiving the advertisement packet, the module will send a connection request packet to the
                    target device to initiate a Bluetooth connection. A successful connection will be indicated by a
                    Status event.
            -> The connection establishment procedure can be cancelled with End Procedure command.

        :param address: Bluetooth address of the target device
        :param addr_type: Bluetooth address type
        :param conn_interval_min: Minimum Connection Interval (in units of 1.25ms). (Range: 6 - 3200)
        :param conn_interval_max: Minimum Connection Interval (in units of 1.25ms). (Range: 6 - 3200)
        :param timeout: Supervision Timeout (in units of 10ms). The Supervision Timeout defines how long the devices
                            can be out of range before the connection is closed. (Range: 10 - 3200)
        :param latency: This parameter configures the slave latency. Slave latency defines how many connection
                            intervals a slave device can skip. Increasing slave latency will decrease the energy
                            consumption of the slave in scenarios where slave does not have data to send at every
                            connection interval. (Range: 0 - 500)
        :return: Bytes object
        """
        payload_length  = 15
        packet_class    = BGAPI_Classes.GAP.value
        message_id      = ble_cmd_gap_connect_direct

        return struct.pack('<4B6sBHHHH', command_message, payload_length, packet_class, message_id,
                            bytes(i for i in address), addr_type, conn_interval_min, conn_interval_max, timeout,
                            latency)

    def ble_cmd_gap_end_procedure(self):
        """
            This command ends the current GAP discovery procedure and stop the scanning of advertising devices.
        :return: Bytes object
        """
        payload_length  = 0
        packet_class    = BGAPI_Classes.GAP.value
        message_id      = ble_cmd_gap_end_procedure

        return struct.pack('<4B', command_message, payload_length, packet_class, message_id)
