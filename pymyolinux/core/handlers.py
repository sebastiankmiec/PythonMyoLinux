from enum import Enum
import copy

# See "https://github.com/thalmiclabs/myo-bluetooth/blob/master/myohw.h" as a reference
MYO_SERVICE_BASE_UUID = bytearray(b"\x42\x48\x12\x4a\x7f\x2c\x48\x47\xb9\xde\x04\xa9\x00\x00\x06\xd5")

#######
###     Handlers used by BlueGigaProtocol
#######

class HW_Services(Enum):
    ControlService = b"\x00\x01" # Myo info service

def add_myo_address(sender_obj, rssi, packet_type, sender, address_type, bond, data):

    # Is this a Myo advertising control service packet
    #
    control_uuid = get_full_uuid(HW_Services.ControlService.value)
    if data.endswith(control_uuid):
        myo_connection = {"sender_address": sender, "address_type": address_type}

        if myo_connection not in sender_obj.myo_addresses:
            sender_obj.myo_addresses.append(myo_connection)

def add_connection(sender_obj, result, connection_handle):
    sender_obj.connection = {"result": result, "connection_handle": connection_handle}

#######
### Helper Functions
#######

# See "https://github.com/thalmiclabs/myo-bluetooth/blob/master/myohw.h" as a reference
def get_full_uuid(short_uuid):
    new_uuid = copy.deepcopy(MYO_SERVICE_BASE_UUID)
    new_uuid[12] = short_uuid[1]
    new_uuid[13] = short_uuid[0]
    return new_uuid