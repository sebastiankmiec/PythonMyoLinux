# PythonMyoLinux
This repository contains the following:
1. A Python (3.5) package to collect sEMG and IMU measurements from Myo armband devices, featuring:
   1. An implementation of the Bluegiga API (BGAPI).
   2. Use of GAP and GATT client to:
      * Discover, and connect to devices.
      * Discover and subscribe to available services.
   3. Use of Myo specific commands.
  
2. A GUI demonstration.

![image](https://drive.google.com/uc?export=view&id=1G40KBpmYx6hCCASe5zwHfsd21CBqkGtE)

# Setup & Usage
First perform the following:
```
git clone https://github.com/sebastiankmiec/PythonMyoLinux.git
cd PythonMyoLinux
conda create -n myo_env python=3.5
conda activate myo_env
```

#### 1. Python package
```
conda install pyserial
python main.py
```

#### 2. GUI demonstration
```
pip install .
pip install PyQt5
pip install PyQtChart
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
