from enum import Enum
import copy
from pymyolinux.core.packet_def import *

#######
###     Handlers used by BlueGigaProtocol
#######

class HW_Services(Enum):
    ControlService = b"\x00\x01" # Myo info service

def add_myo_device(sender_obj, rssi, packet_type, sender, address_type, bond, data):

    # Is this a Myo advertising control service packet
    #
    control_uuid = get_full_uuid(HW_Services.ControlService.value)
    if data.endswith(control_uuid):
        myo_connection = {"sender_address": sender, "address_type": address_type, "rssi": rssi}

        if myo_connection not in sender_obj.myo_devices:
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
    sender_obj.disconnecting = False

def empty_handler(sender_obj, **kwargs):
    pass

#######
### Helper Functions
#######

# See "https://github.com/thalmiclabs/myo-bluetooth/blob/master/myohw.h" as a reference
def get_full_uuid(short_uuid):
    new_uuid = copy.deepcopy(MYO_SERVICE_BASE_UUID)
    new_uuid[12] = short_uuid[1]
    new_uuid[13] = short_uuid[0]
    return new_uuid