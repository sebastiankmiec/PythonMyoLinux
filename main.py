from pymyolinux.core.myo import MyoDongle


def imu_data_handler(orient_w, orient_x, orient_y, orient_z, accel_1, accel_2, accely_3, gyro_1, gyro_2, gyro_3):

    # Accelerometer values are multipled by the following constant (and are in units of g)
    MYOHW_ACCELEROMETER_SCALE = 2048.0

    # Gyroscope values are multipled by the following constant (and are in units of deg/s)
    MYOHW_GYROSCOPE_SCALE = 16.0

    # Orientation values are multipled by the following constant (units of a unit quaternion)
    MYOHW_ORIENTATION_SCALE = 16384.0

    print("-------------------------------------------------------------------------------------------")
    print((orient_w, orient_x, orient_y, orient_z, accel_1, accel_2, accely_3, gyro_1, gyro_2, gyro_3))
    print((orient_w / MYOHW_ORIENTATION_SCALE, orient_x / MYOHW_ORIENTATION_SCALE, orient_y / MYOHW_ORIENTATION_SCALE,
                orient_z / MYOHW_ORIENTATION_SCALE, accel_1 / MYOHW_ACCELEROMETER_SCALE,
                accel_2 / MYOHW_ACCELEROMETER_SCALE, accely_3 / MYOHW_ACCELEROMETER_SCALE,
                gyro_1 / MYOHW_GYROSCOPE_SCALE, gyro_2 / MYOHW_GYROSCOPE_SCALE, gyro_3 / MYOHW_GYROSCOPE_SCALE))


if __name__ == "__main__":
    device_1 = MyoDongle("/dev/ttyACM0")
    device_1.clear_state()
    print("\n")

    myo_devices = device_1.discover_myo_devices()
    if len(myo_devices) > 0:
        device_1.connect(myo_devices[0])
    print("\n")

    device_1.add_imu_handler(imu_data_handler)
    #device_1.add_emg_handler(nothing)
    device_1.enable_imu_readings()
    #device_1.enable_emg_readings()

    device_1.scan_for_data_packets()