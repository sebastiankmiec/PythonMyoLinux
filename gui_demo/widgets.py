#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame)
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QSize, QThreadPool
from PyQt5.QtChart import QLineSeries, QValueAxis

#
# Miscellaneous imports
#
import time

#
# Submodules in this repository
#
from param import *
from backgroundworker import MyoDataWorker


class MyoFoundWidget(QWidget):
    """
        A Widget for a Myo found list entry, that provides the ability to connect/disconnect.
    """
    def __init__(self, port, myo_device, connect_notify, disconnect_notify):
        """
        :param port: The port used to find this device.
        :param myo_device: The hardware (MAC) address of this device.
        :param connect_notify: A function called prior to connection attempts.
        :param disconnect_notify: A function called prior to disconnect attempts.
        """
        super().__init__()

        self.myo_device         = myo_device
        self.chart_list         = None
        self.tab_open           = None
        self.port               = port
        self.connected          = False
        self.performing_action  = False

        self.connect_notify     = connect_notify
        self.disconnect_notify  = disconnect_notify
        self.sleep_period       = 1 # Seconds
        self.initUI()

    def initUI(self):

        topLayout       = QVBoxLayout()
        widgetLayout    = QHBoxLayout()

        # Myo armband icon
        lbl     = QLabel(self)
        orig    = QPixmap("icons/myo.png")
        new     = orig.scaled(QSize(45, 45), Qt.KeepAspectRatio)
        lbl.setPixmap(new)

        #
        # Format the Myo hardware (MAC) into a readable form
        #
        widgetLayout.addWidget(lbl)
        formatted_address   = ""
        length              = len(self.myo_device["sender_address"].hex())

        for i, ch in enumerate(self.myo_device["sender_address"].hex()):
            formatted_address += ch
            if ((i-1) % 2 == 0) and (i != length-1):
                formatted_address += "-"

        # Myo armband address, and signal strength
        widgetLayout.addWidget(QLabel("Myo Device - " + "\"" + formatted_address + "\"" + " (" +
                                    str(self.myo_device["rssi"]) + " dBm)"))
        widgetLayout.setAlignment(Qt.AlignRight)

        #
        # Connect / Disconnect options
        #
        enableLayout = QHBoxLayout()
        self.enable_text = QLabel("Enable: ")
        enableLayout.addWidget(self.enable_text)
        self.enable_box = QCheckBox()
        self.enable_box.clicked.connect(self.connect_with_myo)
        enableLayout.addWidget(self.enable_box)
        enableLayout.setAlignment(Qt.AlignRight)

        # For beauty
        topLayout.addLayout(widgetLayout)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        topLayout.addWidget(line)
        topLayout.addLayout(enableLayout)
        self.setLayout(topLayout)

    def disconnect_with_myo(self):
        """
            A helper function to disconnect from a Myo device.
        :return: None
        """
        self.connected          = False
        self.worker.running     = False
        self.enable_text.setText("Enable: ")
        self.enable_box.setCheckState(Qt.Unchecked)

        while not self.worker.exiting:
            time.sleep(self.sleep_period)

        for i in range(len(self.measurements_list)):
            self.chart_list[i].chart().removeAxis(self.xaxis_list[i])
            self.chart_list[i].chart().removeAxis(self.yaxis_list[i])

        self.disconnect_notify(self.myo_device["sender_address"].hex(), self.port)

    def connect_with_myo(self):
        """
            On a click event to the "Enable/Disable: " checkbox, this function is called and:
                1) Connects to a device (if possible)
                2) Establishes data to be received
                3) Collects data from a Myo armband device
                4) Optionally, disconnects on a second press, halting the receipt of data

        :return: None
        """

        # Must be a second click => disconnect
        if self.connected:
            self.disconnect_with_myo()
            return

        #
        # See if it is possible to make a connection (at most 2 devices, 1 per port, can be connected)
        #
        connection_contents = self.connect_notify(self.myo_device["sender_address"].hex(), self.port)
        if connection_contents is None:
            self.enable_box.setCheckState(Qt.Unchecked)
            return

        self.tab_open   = connection_contents[0]
        self.chart_list = connection_contents[1]
        self.data_list  = connection_contents[2]


        #
        # Prepare EMG visualization
        #
        self.data_list.clear()

        # Data to be collected
        self.samples_count = 0
        self.measurements_list = [QLineSeries() for x in range(8)]

        # Add a legend to each chart, and connect data (series) to charts
        for i, series in enumerate(self.measurements_list):
            self.chart_list[i].chart().legend().setVisible(False)
            self.chart_list[i].chart().addSeries(series)

        # Add axes to each chart
        self.xaxis_list = [QValueAxis() for x in range(8)]
        self.yaxis_list = [QValueAxis() for x in range(8)]

        for i, series in enumerate(self.measurements_list):
            self.chart_list[i].chart().addAxis(self.xaxis_list[i], Qt.AlignBottom)
            self.chart_list[i].chart().addAxis(self.yaxis_list[i], Qt.AlignLeft)
            self.xaxis_list[i].setRange(0, NUM_GUI_SAMPLES)
            self.yaxis_list[i].setRange(-128, 127)                          # EMG values are signed 8-bit values

        for i, series in enumerate(self.measurements_list):
            series.attachAxis(self.xaxis_list[i])
            series.attachAxis(self.yaxis_list[i])

        #
        # Begin the process of connecting and collecting data
        #
        self.worker = MyoDataWorker(self.port, self.myo_device, self.measurements_list,
                                                        self.joint_emg_imu_data_handler, self.data_list)
        QThreadPool.globalInstance().start(self.worker)
        while not self.worker.running:
            time.sleep(self.sleep_period)

        # Update states
        self.enable_text.setText("Disable: ")
        self.connected          = True

    def joint_emg_imu_data_handler(self):
        """
            After a set amount of data is collected, the axes of the charts needs to be updated, to focus on
                the most recent data.

        :return: None
        """

        if self.connected:
            tab_open = self.tab_open()
            for i, series in enumerate(self.measurements_list):

                # An optimization to prevent unnecessary rendering
                if i == tab_open:

                    # Remove old x-axis
                    series.detachAxis(self.xaxis_list[i])
                    self.chart_list[i].chart().removeAxis(self.xaxis_list[i])
                    self.xaxis_list[i] = QValueAxis()

                    # Add new x-axis
                    self.chart_list[i].chart().addAxis(self.xaxis_list[i], Qt.AlignBottom)
                    self.xaxis_list[i].setRange(self.worker.samples_count, self.worker.samples_count +
                                                    NUM_GUI_SAMPLES)
                    series.attachAxis(self.xaxis_list[i])
