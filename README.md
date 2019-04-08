# PythonMyoLinux (In Progress)
This repository contains the following:
1. A Python (3.5) package to collect sEMG and IMU measurements from Myo armband devices, featuring:
   1. An implementation of the Bluegiga API (BGAPI)
   2. Use of GAP and GATT client to:
      * Discover, and connect to devices
      * Search for and subscribe to available services
   3. Use of Myo specific commands
  
2. A GUI demonstration.
   1. Overall system
![image](https://drive.google.com/uc?export=view&id=1CFbHmwnm0IA9_GXoSFw-ZrEctcZWsA-7)

   2. GUI tabs 
      1. Data Collection
![image](https://drive.google.com/uc?export=view&id=1lmxhSv5R_esBc0aPiKkVMWWlAkicxfSe)
      2. Online Prediction
![image](https://drive.google.com/uc?export=view&id=1DPZr0h6TVz1ReXGmWc4n6xWbzO1Ghpv1)

The GUI demonstration currently supports up to two Myo armband devices over a BLED112 Bluetooth dongle(s), and is intended to be used on a Linux distribution. 

Currently, the GUI allows for collection of data with (crude) ground truth. In the future, this package will provide ground truth correction; as well as online training and testing.

# Setup & Usage
First perform the following
```
git clone https://github.com/sebastiankmiec/PythonMyoLinux.git
cd PythonMyoLinux
conda create -n myo_env
conda activate myo_env
conda install -c conda-forge python=3.5
```

#### 1. Python package demonstration
```
conda install pyserial
python main.py
```

#### 2. GUI demonstration
Preliminary setup
```
pip install .
conda install -c conda-forge pyqt ffmpeg 
conda install -c conda-forge pyqtgraph
python gui_demo/main.py
```
Distribution specific steps (for <b>CentOS 7 only</b>)
```
yum install gstreamer1.x86_64 gstreamer1-libav.x86_64 gstreamer1-plugins-bad-freeworld.x86_64 gstreamer1-plugins-good.x86_64 
cp /lib64/gstreamer-1.0/* /path_to_miniconda/envs/myo_env/lib/gstreamer-1.0/
```

To finally run the GUI demonstration:
```
python gui_demo/main.py
```

# References
1. "Getting Started with Bluetooth Low Energy" by O'Reilly Media, Inc.
   * For a brief understanding of the Bluetooth stack, and Bluetooth core specification.
2. https://www.silabs.com/products/wireless/bluetooth/bluetooth-low-energy-modules/bled112-bluetooth-smart-dongle
   * See "Bluetooth Smart Software API Reference Manual for BLE Version 1.7", to understand BGAPI.
3. https://github.com/mjbrown/bgapi 
   * A major inspiration for this work.
3. https://github.com/thalmiclabs/myo-bluetooth
   * Contains Myo specific commands.
