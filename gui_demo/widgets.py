#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame, QMainWindow, QPushButton,
                                QGridLayout, QSizePolicy)
from PyQt5.QtGui import QPixmap, QFontMetrics
from PyQt5.QtCore import Qt, QSize, QThreadPool, QObject, pyqtSignal, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaPlaylist, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
import pyqtgraph as pg
# from PyQt5.QtChart import QLineSeries, QValueAxis

#
# Miscellaneous imports
#
from os.path import join, abspath
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
        orig    = QPixmap(join(abspath(__file__).replace("widgets.py", ""), "icons/myo.png"))
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

        # Old backend:
        #
        #for i in range(len(self.measurements_list)):
        #    self.chart_list[i].chart().removeAxis(self.xaxis_list[i])
        #    self.chart_list[i].chart().removeAxis(self.yaxis_list[i])

        self.disconnect_notify(self.myo_device["sender_address"].hex())

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
        self.measurements_list  = [[] for x in range(8)]
        self.plotted_data       = [None for x in range(8)]
        self.data_indices       = []

        # Old backend:
        #
        # self.measurements_list = [QLineSeries() for x in range(8)]
        #
        # Add a legend to each chart, and connect data (series) to charts
        #for i, series in enumerate(self.measurements_list):
        #    self.chart_list[i].chart().legend().setVisible(False)
        #    self.chart_list[i].chart().addSeries(series)
        #
        # Add axes to each chart
        # self.xaxis_list = [QValueAxis() for x in range(8)]
        # self.yaxis_list = [QValueAxis() for x in range(8)]


        for i, series in enumerate(self.measurements_list):
            # self.chart_list[i].chart().addAxis(self.xaxis_list[i], Qt.AlignBottom)
            # self.chart_list[i].chart().addAxis(self.yaxis_list[i], Qt.AlignLeft)
            # self.xaxis_list[i].setRange(0, NUM_GUI_SAMPLES)
            # self.yaxis_list[i].setRange(-128, 127)  # EMG values are signed 8-bit
            # self.chart_list[i].setXRange(0, NUM_GUI_SAMPLES)

            # Generate an initial, empty plot --> update data later
            self.plotted_data[i] = self.chart_list[i].plot(self.data_indices, self.measurements_list[i],
                                                            pen=pg.functions.mkPen("08E", width=2),
                                                            symbol='o', symbolSize=SYMBOL_SIZE)

        #for i, series in enumerate(self.measurements_list):
        #    series.attachAxis(self.xaxis_list[i])
        #    series.attachAxis(self.yaxis_list[i])

        #
        # Begin the process of connecting and collecting data
        #
        self.worker = MyoDataWorker(self.port, self.myo_device, self.measurements_list, self.data_indices,
                                        self.on_axes_update, self.on_new_data, self.data_list)
        QThreadPool.globalInstance().start(self.worker)
        while not self.worker.running:
            time.sleep(self.sleep_period)

        # Update states
        self.enable_text.setText("Disable: ")
        self.connected          = True

    def on_new_data(self):
        """

            :return: None
        """

        if self.connected:
            tab_open = self.tab_open()

            # Update plot data
            for i, series in enumerate(self.measurements_list):
                if i == tab_open:
                    self.plotted_data[i].setData(self.data_indices, self.measurements_list[i])

    def on_axes_update(self):
        """
            After a set amount of data is collected, the axes of the charts needs to be updated, to focus on
                the most recent data.

                > This function is triggred by a ChartUpdate event, specifically, an axesUpdate signal.

        :return: None
        """

        if self.connected:
            tab_open = self.tab_open()

            # Update axes
            for i, series in enumerate(self.measurements_list):
                if i == tab_open:
                    self.chart_list[i].setXRange(self.worker.start_range,
                                                    self.worker.samples_count + NUM_GUI_SAMPLES, padding=0.075)

            # for i, series in enumerate(self.measurements_list):
            #
            #     # An optimization to prevent unnecessary rendering
            #     if i == tab_open:
            #
            #         # Remove old x-axis
            #         series.detachAxis(self.xaxis_list[i])
            #         self.chart_list[i].chart().removeAxis(self.xaxis_list[i])
            #         self.xaxis_list[i] = QValueAxis()
            #
            #         # Add new x-axis
            #         self.chart_list[i].chart().addAxis(self.xaxis_list[i], Qt.AlignBottom)
            #         self.xaxis_list[i].setRange(self.worker.samples_count, self.worker.samples_count +
            #                                         NUM_GUI_SAMPLES)
            #         series.attachAxis(self.xaxis_list[i])


class GroundTruthHelper(QWidget):
    def __init__(self, parent=None, close_function=None):
        #super(GroundTruthHelper, self).__init__(parent)
        super().__init__()

        self.close_event = self.Exit()
        if close_function is not None:
            self.close_event.exitClicked.connect(close_function)

        self.initUI()

    def initUI(self):
        self.setGeometry(0, 0, 1024, 768)

        self.grid   = QGridLayout()

        # Title
        gt_title  = QLabel("Ground Truth Helper")
        gt_title.setStyleSheet("font-weight: bold;")
        gt_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.grid.addWidget(gt_title, 0, 1, 1, 1)

        # Start button
        start_button   = QPushButton("Start")
        start_button.clicked.connect(self.start_videos)
        self.grid.addWidget(start_button, 1, 2, 1, 1)

        # Video Player
        self.player      = QMediaPlayer()
        playlist    = QMediaPlaylist(self.player)
        playlist.addMedia(QMediaContent(QUrl.fromLocalFile("/home/skmiec/Downloads/final/arrows/exercise_a/a1.mp4")))
        playlist.addMedia(QMediaContent(QUrl.fromLocalFile("/home/skmiec/Downloads/final/arrows/exercise_a/a2.mp4")))

        videoWidget = QVideoWidget()
        self.player.setVideoOutput(videoWidget)
        self.grid.addWidget(videoWidget, 2, 2, 1, 1)

        videoWidget.show()
        playlist.setCurrentIndex(1)
        #player.play()

        #self.grid.setRowStretch(0, 1)
        #self.grid.setRowStretch(1, 1)
        #self.grid.setColumnStretch(0, 1)
        #self.grid.setColumnStretch(1, 1)

        self.setLayout(self.grid)

    def start_videos(self):
        self.player.play()

    # def resizeEvent(self, e):
    #     """
    #         Resizes title text on resize event.
    #     :param e: A resize event
    #     :return: None
    #     """
    #     cur_font    = self.gt_title.font()
    #     metrics     = QFontMetrics(cur_font)
    #
    #     size    = metrics.size(0, self.gt_title.text())
    #     width   = self.gt_title.width() / (size.width() * 1.75)
    #     height  = self.gt_title.height() / (size.height() * 1.75)
    #
    #     factor  = (width + height) / 1.75
    #
    #     cur_font.setPointSizeF(cur_font.pointSizeF() * factor)
    #     self.gt_title.setFont(cur_font)

    #
    # Used by TopLevel widget
    #
    class Exit(QObject):
        exitClicked = pyqtSignal()
    def closeEvent(self, event):
        self.close_event.exitClicked.emit()

    #
    # Used for data logging
    #
    def get_current_label(self):
        pass