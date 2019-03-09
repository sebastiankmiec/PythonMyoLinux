#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QProgressDialog, QTabWidget, QFileDialog, QMessageBox,
                             QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame, QMainWindow, QPushButton,
                             QGridLayout, QSizePolicy, QGroupBox, QTextEdit, QLineEdit, QErrorMessage, QProgressBar,
                             QSpacerItem)

from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtCore import (QSize, QThreadPool, Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal, QTimer, QUrl,\
                            QFileInfo)
from PyQt5.QtMultimediaWidgets import QVideoWidget
import pyqtgraph as pg
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

#
# Miscellaneous imports
#
import threading
from enum import Enum
import time
from functools import partial
from os.path import curdir, exists, join, abspath
import copy
from serial.tools.list_ports import comports

#
# Submodules in this repository
#
from pymyolinux import MyoDongle
from movements import *
from param import *


class MyoConnectedWidget(QWidget):

    def __init__(self, address, rssi, battery):
        super().__init__()
        self.address = address
        self.init_ui(address, rssi, battery)

    def init_ui(self, address, rssi, battery):

        infoLayout = QHBoxLayout()
        infoLayout.setSpacing(5)

        # Myo armband icon
        lbl = QLabel(self)
        orig = QPixmap(join(abspath(__file__).replace("online_test.py", ""), "icons/myo.png"))
        new = orig.scaled(QSize(30, 30), Qt.KeepAspectRatio)
        lbl.setPixmap(new)

        #
        # Format the Myo hardware (MAC) into a readable form
        #
        infoLayout.addWidget(lbl)
        formatted_address = ""
        length = len(address.hex())

        for i, ch in enumerate(address.hex()):
            formatted_address += ch
            if ((i - 1) % 2 == 0) and (i != length - 1):
                formatted_address += "-"

        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        # vline2 = QFrame()
        # vline2.setFrameShape(QFrame.VLine)
        # vline2.setFrameShadow(QFrame.Sunken)

        #
        # Myo armband address, signal strength
        #
        addr_label = QLabel(formatted_address)
        addr_label.setContentsMargins(5, 0, 0, 0)
        cur_font = addr_label.font()
        cur_font.setPointSize(10)
        addr_label.setFont(cur_font)
        infoLayout.addWidget(addr_label)
        infoLayout.addWidget(vline)
        #rssi_label = QLabel(str(rssi) + " dBm")
        #infoLayout.addWidget(rssi_label)
        #infoLayout.addWidget(vline2)
        #infoLayout.setStretchFactor(rssi_label, 3)
        infoLayout.setStretchFactor(addr_label, 4)

        #
        # Battery Level
        #
        self.battery_level = QProgressBar()
        self.battery_level.setMinimum(0)
        self.battery_level.setMaximum(100)
        self.battery_level.setValue(battery)
        infoLayout.addWidget(self.battery_level)
        infoLayout.setStretchFactor(self.battery_level, 2)

        self.setLayout(infoLayout)


class OnlineTesting(QWidget):

    def __init__(self):
        super().__init__()

        self.init_ui()

    def init_ui(self):

        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(15)

        #
        # Top "message box" / time remaining
        #
        message_layout  = QHBoxLayout()
        self.status_label = QLabel("Waiting for Preparation...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 16pt; "
                                        "   color: red;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.progress_label = QLabel("0.0s (1 / 1)")
        self.progress_label.setStyleSheet(" font-size: 14pt; color: black;")
        self.progress_label.setAlignment(Qt.AlignCenter)
        message_layout.addWidget(self.status_label)
        message_layout.addWidget(self.progress_label)
        message_layout.setStretch(0, 66)
        message_layout.setStretch(1, 33)
        top_layout.addLayout(message_layout)


        #
        # Video player
        #
        video_layout        = QHBoxLayout()
        self.video_player   = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        video_widget        = QVideoWidget()
        self.video_player.setVideoOutput(video_widget)

        video_layout.addWidget(video_widget)

        descrip_layout      = QVBoxLayout()
        self.desc_title = QLabel("No Movement")
        self.desc_title.setStyleSheet("border: 4px solid gray; font-weight: bold; font-size: 14pt;")
        self.desc_title.setAlignment(Qt.AlignCenter)
        self.desc_explain = QTextEdit("No description available.")
        self.desc_explain.setStyleSheet("border: 4px solid gray; font-size: 12pt; border-color: black;")
        self.desc_explain.setReadOnly(True)
        descrip_layout.addWidget(self.desc_title)
        descrip_layout.addWidget(self.desc_explain)
        video_layout.addLayout(descrip_layout)

        video_layout.setStretch(0, 66)
        video_layout.setStretch(1, 33)
        top_layout.addLayout(video_layout)

        #
        # Preparation Box
        #
        parameters_box = QGroupBox()
        parameters_box.setTitle("Preparation Phase")
        parameters_box.setObjectName("CollecParamBox")
        parameters_box.setStyleSheet(
            "QGroupBox#CollecParamBox { border: 1px solid gray; border-radius: 7px; margin-top: 1.6em;"
            "                              font-weight: bold; background-color: #dddddd;}"
            "QGroupBox#CollecParamBox::title { subcontrol-origin: margin; subcontrol-position: top center; "
            " border: 1px solid gray; border-radius: 7px;}")
        font = parameters_box.font()
        font.setPointSize(14)
        parameters_box.setFont(font)
        parameters_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top_layout.addWidget(parameters_box)

        prep_layout = QGridLayout()
        prep_layout.setHorizontalSpacing(15)
        parameters_box.setLayout(prep_layout)

        #
        # Preparation Box: Model Selection
        #
        model_button = QPushButton("Select Model")
        model_button.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(model_button, 0, 0, 1, 2)

        hline = QFrame()
        hline.setFrameShape(QFrame.HLine)
        hline.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline, 1, 0, 1, 2)

        name_title = QLabel("Name")
        prep_layout.addWidget(name_title, 2, 0)
        samples_title = QLabel("Samples")
        prep_layout.addWidget(samples_title, 3, 0)

        self.model_name = QLineEdit()
        self.model_name.setReadOnly(True)
        prep_layout.addWidget(self.model_name, 2, 1)
        self.samples_field = QLineEdit()
        self.samples_field.setReadOnly(True)
        prep_layout.addWidget(self.samples_field, 3, 1)

        # Note: No copy constructors for Qt5 objects...
        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        vline2 = QFrame()
        vline2.setFrameShape(QFrame.VLine)
        vline2.setFrameShadow(QFrame.Sunken)
        vline3 = QFrame()
        vline3.setFrameShape(QFrame.VLine)
        vline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(vline, 0, 2, 4, 1)

        #
        # Preparation Box: Generate Noise Model
        #
        noise_button = QPushButton("Collect Noise")
        noise_button.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(noise_button, 0, 3)
        collect_title = QLabel("Duration")
        collect_title.setAlignment(Qt.AlignCenter | Qt.AlignBottom)

        hline2 = QFrame()
        hline2.setFrameShape(QFrame.HLine)
        hline2.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline2, 1, 3)
        prep_layout.addWidget(collect_title, 2, 3)

        self.noise_duration = QLineEdit("15.0")
        self.noise_duration.setAlignment(Qt.AlignCenter)
        prep_layout.addWidget(self.noise_duration, 3, 3)
        prep_layout.addWidget(vline2, 0, 4, 4, 1)

        #
        # Preparation Box: Devices Connected
        #
        connected_title  = QLabel("Devices Connected")
        connected_title.setAlignment(Qt.AlignCenter)
        connected_title.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(connected_title, 0, 5)
        self.devices_connected = QListWidget()
        self.devices_connected.verticalScrollBar().setDisabled(True)

        hline3 = QFrame()
        hline3.setFrameShape(QFrame.HLine)
        hline3.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline3, 1, 5)

        prep_layout.addWidget(self.devices_connected, 2, 5, 2, 1)
        prep_layout.addWidget(vline3, 0, 6, 4, 1)

        #
        # Online Testing Parameters
        #
        test_title      = QLabel("Test Parameters")
        test_title.setAlignment(Qt.AlignCenter)
        test_title.setStyleSheet("font-weight: bold")
        prep_layout.addWidget(test_title, 0, 7, 1, 2)

        hline4 = QFrame()
        hline4.setFrameShape(QFrame.HLine)
        hline4.setFrameShadow(QFrame.Sunken)
        prep_layout.addWidget(hline4, 1, 7, 1, 2)

        self.pred_min_duration  = QLineEdit("2.0")
        self.pred_max_duration  = QLineEdit("4.0")
        self.min_title          = QLabel("<b>(Min)</b> Duration")
        self.max_title          = QLabel("<b>(Max)</b> Duration")

        prep_layout.addWidget(self.min_title, 2, 7)
        prep_layout.addWidget(self.max_title, 3, 7)
        prep_layout.addWidget(self.pred_min_duration, 2, 8)
        prep_layout.addWidget(self.pred_max_duration, 3, 8)

        #
        # Preparation Phase formatting
        #
        prep_layout.setRowStretch(0, 3)
        prep_layout.setRowStretch(1, 1)
        prep_layout.setRowStretch(2, 4)
        prep_layout.setRowStretch(3, 4)

        prep_layout.setColumnStretch(0, 1)
        prep_layout.setColumnStretch(1, 3)
        prep_layout.setColumnStretch(2, 1)
        prep_layout.setColumnStretch(3, 2)
        prep_layout.setColumnStretch(4, 1)
        prep_layout.setColumnStretch(5, 6)
        prep_layout.setColumnStretch(6, 1)
        prep_layout.setColumnStretch(7, 1)
        prep_layout.setColumnStretch(8, 3)

        #
        # Overall formatting
        #
        top_layout.setStretch(0, 1)
        top_layout.setStretch(1, 15)
        top_layout.setStretch(2, 4)

        self.setLayout(top_layout)

    def device_connected(self, address, rssi, battery):

        new_device = MyoConnectedWidget(address, rssi, battery)
        temp_widget = QListWidgetItem()
        temp_widget.setBackground(Qt.gray)
        size_hint = new_device.sizeHint()
        size_hint.setHeight(36)
        temp_widget.setSizeHint(size_hint)
        self.devices_connected.addItem(temp_widget)
        self.devices_connected.setItemWidget(temp_widget, new_device)

    def device_disconnected(self, address):

        num_widgets = self.devices_connected.count()

        for idx in range(num_widgets):
            # Ignore port widgets (only interested in Myo device rows)
            list_widget = self.devices_connected.item(idx)
            myo_widget  = self.devices_connected.itemWidget(list_widget)

            if myo_widget.address.endswith(address):
                self.devices_connected.takeItem(idx)
                break