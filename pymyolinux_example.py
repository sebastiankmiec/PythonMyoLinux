from pymyolinux.core.myo import MyoDongle

def joint_event_handler(emg_list, orient_w, orient_x, orient_y, orient_z,
                                accel_1, accel_2, accel_3, gyro_1, gyro_2, gyro_3, sample_num):

    # Accelerometer values are multipled by the following constant (and are in units of g)
    MYOHW_ACCELEROMETER_SCALE = 2048.0

    # Gyroscope values are multipled by the following constant (and are in units of deg/s)
    MYOHW_GYROSCOPE_SCALE = 16.0

    # Orientation values are multipled by the following constant (units of a unit quaternion)
    MYOHW_ORIENTATION_SCALE = 16384.0

    print("-------------------------------------------------------------------------------------------")
    print((emg_list[0], emg_list[1], emg_list[2], emg_list[3], emg_list[4], emg_list[5], emg_list[6], emg_list[7]))
    #print((orient_w, orient_x, orient_y, orient_z, accel_1, accel_2, accel_3, gyro_1, gyro_2, gyro_3))
    print((orient_w / MYOHW_ORIENTATION_SCALE, orient_x / MYOHW_ORIENTATION_SCALE, orient_y / MYOHW_ORIENTATION_SCALE,
                orient_z / MYOHW_ORIENTATION_SCALE, accel_1 / MYOHW_ACCELEROMETER_SCALE,
                accel_2 / MYOHW_ACCELEROMETER_SCALE, accel_3 / MYOHW_ACCELEROMETER_SCALE,
                gyro_1 / MYOHW_GYROSCOPE_SCALE, gyro_2 / MYOHW_GYROSCOPE_SCALE, gyro_3 / MYOHW_GYROSCOPE_SCALE))


if __name__ == "__main__":
    device_1 = MyoDongle("/dev/ttyACM0")
    device_1.clear_state()

    myo_devices = device_1.discover_myo_devices()
    if len(myo_devices) > 0:
        device_1.connect(myo_devices[0])
    else:
        print("No devices found, exiting...")
        exit()

    #device_1.add_imu_handler()
    #device_1.add_emg_handler()
    device_1.enable_imu_readings()
    device_1.enable_emg_readings()
    device_1.add_joint_emg_imu_handler(joint_event_handler)

    # device_1.scan_for_data_packets_conditional()
    device_1.scan_for_data_packets(3)