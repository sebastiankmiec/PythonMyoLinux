# PythonMyoLinux
This repository contains the following:
1. A Python (3.5) package to collect sEMG and IMU measurements from Myo armband devices, featuring:
   1. An implementation of the Bluegiga API (BGAPI)
   2. Use of GAP and GATT client to:
      * Discover, and connect to devices
      * Search for and subscribe to available services
   3. Use of Myo specific commands

&nbsp;

2. A GUI demonstration
   1. Overall system
![image](https://drive.google.com/uc?export=view&id=1CFbHmwnm0IA9_GXoSFw-ZrEctcZWsA-7)

   2. GUI tabs 
      1. Data Collection
![image](https://drive.google.com/uc?export=view&id=1lmxhSv5R_esBc0aPiKkVMWWlAkicxfSe)
      2. Online Training
![image](https://drive.google.com/uc?export=view&id=1VYAvod_qM05WB559Gb34QO3bI9qBqiNy)
      3. Online Prediction
![image](https://drive.google.com/uc?export=view&id=1DPZr0h6TVz1ReXGmWc4n6xWbzO1Ghpv1)

&nbsp;

The GUI demonstration currently supports up to two Myo armband devices over a BLED112 Bluetooth dongle(s), and is intended to be used on a Linux distribution. 

The GUI allows for collection of data with (crude) ground truth, as well as online training/testing. For refining of ground truth, and offline training/testing, please see the *NinaTools* respository.

&nbsp;

# Setup & Usage
First install the *pymyolinux* package
```
git clone https://github.com/sebastiankmiec/PythonMyoLinux.git
cd PythonMyoLinux
pip install .
```

&nbsp;

#### 1. *Pymyolinux* package demonstration
```
conda install -c conda-forge pyserial -y
python pymyolinux_example.py
```

&nbsp;

#### 2. GUI demonstration
Install remaining dependencies (first setup the *NinaTools* respository)
```
conda install -c conda-forge/label/cf201901 pyqt=5.6.0 pyqtgraph=0.10.0 -y
```

Distribution specific steps (for <b>CentOS 7 only</b>), to allow video playback
```
yum install gstreamer1.x86_64 gstreamer1-libav.x86_64 gstreamer1-plugins-bad-freeworld.x86_64 gstreamer1-plugins-good.x86_64 
yes | cp /lib64/gstreamer-1.0/* /path_to_miniconda/envs/testnina/lib/gstreamer-1.0/
```

To finally run the GUI demonstration
```
python gui_demo/gui_main.py
```

&nbsp;

# References
1. "Getting Started with Bluetooth Low Energy" by O'Reilly Media, Inc.
   * For a brief understanding of the Bluetooth stack, and Bluetooth core specification.
2. https://www.silabs.com/products/wireless/bluetooth/bluetooth-low-energy-modules/bled112-bluetooth-smart-dongle
   * See "Bluetooth Smart Software API Reference Manual for BLE Version 1.7", to understand BGAPI.
3. https://github.com/mjbrown/bgapi 
   * A major inspiration for this work.
3. https://github.com/thalmiclabs/myo-bluetooth
   * Contains Myo specific commands.
