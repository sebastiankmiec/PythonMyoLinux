from pymyolinux.util.packet_def import *
import struct

#######
###     (BLE Event - Myo Specific) Handlers used by BlueGigaProtocol
#######

def on_receive_attribute_value(sender_obj, connection, atthandle, type, value):

    #
    # IMU
    #
    if atthandle == sender_obj.imu_handle:
        orient_w, orient_x, orient_y, orient_z, accel_1, accel_2, accel_3, gyro_1, gyro_2, gyro_3 =\
            struct.unpack('<10h', value)

        sender_obj.current_imu_read = {"orient_w" : orient_w, "orient_x": orient_x, "orient_y": orient_y,
                                        "orient_z": orient_z, "accel_1": accel_1, "accel_2": accel_2,
                                        "accel_3": accel_3, "gyro_1": gyro_1,
                                        "gyro_2": gyro_2, "gyro_3": gyro_3}

        # Trigger IMU event
        sender_obj.imu_event(orient_w = orient_w, orient_x = orient_x, orient_y = orient_y, orient_z = orient_z,
                                accel_1 = accel_1, accel_2 = accel_2, accel_3 = accel_3, gyro_1 = gyro_1,
                                gyro_2 = gyro_2, gyro_3 = gyro_3)

    #
    # EMG
    #
    elif ((atthandle == sender_obj.emg_handle_0) or (atthandle == sender_obj.emg_handle_1) or
          (atthandle == sender_obj.emg_handle_2) or (atthandle == sender_obj.emg_handle_3)):

        sample_0_1, sample_0_2, sample_0_3, sample_0_4, sample_0_5, sample_0_6, sample_0_7, sample_0_8, \
            sample_1_1, sample_1_2, sample_1_3, sample_1_4, sample_1_5, sample_1_6, sample_1_7, sample_1_8\
                = struct.unpack('<16b', value)

        # Trigger two EMG events
        sender_obj.emg_event(emg_list = [sample_0_1, sample_0_2, sample_0_3, sample_0_4, sample_0_5,
                                                        sample_0_6, sample_0_7, sample_0_8])
        sender_obj.emg_event(emg_list = [sample_1_1, sample_1_2, sample_1_3, sample_1_4, sample_1_5,
                                                        sample_1_6, sample_1_7, sample_1_8])

        # Trigger two joint IMU/EMG events:
        sender_obj.joint_emg_imu_event(emg_list = [sample_0_1, sample_0_2, sample_0_3, sample_0_4, sample_0_5,
                                                        sample_0_6, sample_0_7, sample_0_8],
                                                    **sender_obj.current_imu_read)
        sender_obj.joint_emg_imu_event(emg_list = [sample_1_1, sample_1_2, sample_1_3, sample_1_4, sample_1_5,
                                                        sample_1_6, sample_1_7, sample_1_8],
                                                    **sender_obj.current_imu_read)


#######
###     (BLE Response) Handlers used by BlueGigaProtocol
#######


#######
###     (BLE Event) Handlers used by BlueGigaProtocol
#######

def add_myo_device(sender_obj, rssi, packet_type, sender, address_type, bond, data):

    # Is this a Myo advertising control service packet
    #
    control_uuid = get_full_uuid(HW_Services.ControlService.value)
    if data.endswith(control_uuid):
        myo_connection = {"sender_address": sender, "address_type": address_type, "rssi": rssi}

        unique = True
        for device in sender_obj.myo_devices: # Note, device also has "rssi"
            if (
                    (myo_connection["sender_address"] == device["sender_address"]) and
                    (myo_connection["address_type"] == device["address_type"])
                ):
                unique = False
                break

        if unique:
            sender_obj.myo_devices.append(myo_connection)

def add_connection(sender_obj, connection, flags, address, address_type, conn_interval, timeout, latency, bonding):
    sender_obj.connection = {'connection': connection, 'flags': flags, 'address': address,
                                'address_type': address_type, 'conn_interval': conn_interval,
                                'timeout': timeout, 'latency': latency, 'bonding': bonding }

def device_disconnected(sender_obj, connection, reason):
    if reason == disconnect_due_local_user:
        print("Connection \"{}\" disconnected due to local user (disconnect issued).".format(connection))
    else:
        print("Connection \"{}\" disconnected due to uknown reason (resason = {}).".format(connection, reason))
    sender_obj.disconnecting    = False
    sender_obj.connection       = None
    sender_obj.services_found   = []
    sender_obj.attributes_found = []

def add_service_found(sender_obj, connection, start, end, uuid):
    sender_obj.services_found.append({'start': start, 'end': end, 'uuid': uuid })

def service_finding_complete(sender_obj, connection, result, chrhandle):
    if result != GAP_end_procedure_success:
        raise RuntimeError("Attribute protocol error code returned by remote device (result = {}).".format(result))

def add_attribute_found(sender_obj, connection, chrhandle, uuid):
    sender_obj.attributes_found.append({'chrhandle': chrhandle, 'uuid': uuid })

def empty_handler(sender_obj, **kwargs):
    pass
