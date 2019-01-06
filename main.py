from pymyolinux.core.myo import MyoDongle

if __name__ == "__main__":
    device_1 = MyoDongle("/dev/ttyACM0")
    device_1.clear_state()
    print("\n")

    myo_devices = device_1.discover_myo_devices()
    if len(myo_devices) > 0:
        device_1.connect(myo_devices[0])
    print("\n")