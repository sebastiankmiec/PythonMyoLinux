#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame, QMainWindow, QPushButton,
                                QGridLayout, QSizePolicy, QGroupBox, QTextEdit, QLineEdit, QErrorMessage, QProgressBar)
from PyQt5.QtGui import QPixmap, QFontMetrics, QPalette
from PyQt5.QtCore import Qt, QSize, QThreadPool, QObject, pyqtSignal, QUrl, QThread
from PyQt5.QtMultimedia import QMediaPlayer
from PyQt5.QtMultimediaWidgets import QVideoWidget
import pyqtgraph as pg
from os.path import join, exists
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
from backgroundworker import MyoDataWorker, GroundTruthWorker


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
        self.connect_notify     = connect_notify
        self.disconnect_notify  = disconnect_notify

        # Configurable parameters
        self.num_trim_samples = 400     # On unexpected disconnect, or user-initiated disconnect, trim this many samples
                                        #       from the list of all collected data thus far.

        # States
        self.connected          = False
        self.worker             = None

        self.initUI()

    def initUI(self):

        topLayout       = QVBoxLayout()
        infoLayout      = QHBoxLayout()
        infoLayout.setSpacing(5)

        # Myo armband icon
        lbl     = QLabel(self)
        orig    = QPixmap(join(abspath(__file__).replace("widgets.py", ""), "icons/myo.png"))
        new     = orig.scaled(QSize(45, 45), Qt.KeepAspectRatio)
        lbl.setPixmap(new)

        #
        # Format the Myo hardware (MAC) into a readable form
        #
        infoLayout.addWidget(lbl)
        formatted_address   = ""
        length              = len(self.myo_device["sender_address"].hex())

        for i, ch in enumerate(self.myo_device["sender_address"].hex()):
            formatted_address += ch
            if ((i-1) % 2 == 0) and (i != length-1):
                formatted_address += "-"

        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        vline2 = QFrame()
        vline2.setFrameShape(QFrame.VLine)
        vline2.setFrameShadow(QFrame.Sunken)

        # Myo armband address, signal strength
        addr_label = QLabel(formatted_address)
        infoLayout.addWidget(addr_label)
        infoLayout.addWidget(vline)
        rssi_label = QLabel(str(self.myo_device["rssi"]) + " dBm")
        infoLayout.addWidget(rssi_label)
        infoLayout.addWidget(vline2)
        infoLayout.setStretchFactor(rssi_label, 3)
        infoLayout.setStretchFactor(addr_label, 6)

        # Battery Level
        self.battery_level = QProgressBar()
        self.battery_level.setMinimum(0)
        self.battery_level.setMaximum(100)
        self.battery_level.setValue(100)
        infoLayout.addWidget(self.battery_level)
        infoLayout.setStretchFactor(self.battery_level, 2)

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
        topLayout.addLayout(infoLayout)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        topLayout.addWidget(line)
        topLayout.addLayout(enableLayout)
        self.setLayout(topLayout)

    def connect_with_myo(self):
        """
            On a click event to the "Enable/Disable: " checkbox, this function is called and:
                1) Connects to a device (if possible)
                2) Establishes data to be received
                3) Collects data from a Myo armband device
                4) Optionally, disconnects on a second press, halting the receipt of data

        :return: None
        """
        self.enable_box.setEnabled(False)

        # Must be a second click => disconnect
        if self.connected:
            self.worker.running = False
            return

        #
        # See if it is possible to make a connection (at most 2 devices, 1 per port, can be connected)
        #
        connection_contents = self.connect_notify(self.myo_device["sender_address"].hex(), self.port)
        if connection_contents is None:
            self.enable_box.setCheckState(Qt.Unchecked)
            self.enable_box.setEnabled(True)
            return

        self.top_tab_open   = connection_contents[0]
        self.prev_tab       = connection_contents[1]
        self.tab_open       = connection_contents[2]
        self.chart_list     = connection_contents[3]
        self.data_list      = connection_contents[4]

        # Old backend:
        #
        # self.measurements_list = [QLineSeries() for x in range(8)]
        #
        # Add a legend to each chart, and connect data (series) to charts
        # for i, series in enumerate(self.measurements_list):
        #    self.chart_list[i].chart().legend().setVisible(False)
        #    self.chart_list[i].chart().addSeries(series)
        #
        # Add axes to each chart
        # self.xaxis_list = [QValueAxis() for x in range(8)]
        # self.yaxis_list = [QValueAxis() for x in range(8)]

        # for i, series in enumerate(self.measurements_list):
        #    series.attachAxis(self.xaxis_list[i])
        #    series.attachAxis(self.yaxis_list[i])

        #
        # Begin the process of connecting and collecting data
        #
        if self.worker is None:

            # Data to be collected
            self.measurements_list  = [[] for x in range(8)]
            self.data_indices       = []
            self.plotted_data       = [None for x in range(8)]

            # Create background worker
            self.worker = MyoDataWorker(self.port, self.myo_device, self.measurements_list, self.data_indices,
                                            self.on_axes_update, self.on_new_data, self.data_list, self.on_worker_started,
                                            self.on_worker_stopped, self.connect_failed, self.on_discon_occurred,
                                            self.battery_level, self.create_event)

            self.worker.setAutoDelete(False) # We reuse this worker

        QThreadPool.globalInstance().start(self.worker)

    def create_event(self):
        if self.prev_tab is None:
            idx = 0
        else:
            idx = 1
        return self.top_tab_open() == idx

    def on_worker_started(self):
        # Update states
        self.enable_text.setText("Disable: ")
        self.connected = True

        #
        # Prepare EMG visualization
        #
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
        self.enable_box.setEnabled(True)

    def on_discon_occurred(self):
        self.connected = False
        self.enable_text.setText("Enable: ")
        self.enable_box.setCheckState(Qt.Unchecked)

        # Trim potentially useless data
        num_samples = len(self.data_list)
        if self.num_trim_samples >= num_samples:
            self.data_list = []
        else:
            self.data_list = self.data_list[:num_samples - self.num_trim_samples]

        self.warning = QErrorMessage()
        self.warning.showMessage("Myo armband device disconnected unexpectedly.")
        self.warning.show()

        self.disconnect_notify(self.myo_device["sender_address"].hex())
        self.enable_box.setEnabled(True)

    def connect_failed(self):
        """
            A helper function to disconnect from a Myo device.
        :return: None
        """
        self.connected = False
        self.enable_text.setText("Enable: ")
        self.enable_box.setCheckState(Qt.Unchecked)

        self.warning = QErrorMessage()
        self.warning.showMessage("Unable to connect to Myo armband device.")
        self.warning.show()

        self.disconnect_notify(self.myo_device["sender_address"].hex())
        self.enable_box.setEnabled(True)

    def on_worker_stopped(self):
        """
            A helper function to disconnect from a Myo device.
        :return: None
        """
        self.connected = False
        self.enable_text.setText("Enable: ")
        self.enable_box.setCheckState(Qt.Unchecked)

        # Trim potentially useless data
        num_samples = len(self.data_list)
        if self.num_trim_samples >= num_samples:
            self.data_list = []
        else:
            self.data_list = self.data_list[:num_samples - self.num_trim_samples]

        # Old backend:
        #
        # for i in range(len(self.measurements_list)):
        #    self.chart_list[i].chart().removeAxis(self.xaxis_list[i])
        #    self.chart_list[i].chart().removeAxis(self.yaxis_list[i])

        self.disconnect_notify(self.myo_device["sender_address"].hex())
        self.enable_box.setEnabled(True)

    def on_new_data(self):
        """
            On each new data sample collected, this function is triggered by a ChartUpdate event, specifically,
                a dataUpdate signal.

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


class GroundTruthHelper(QMainWindow):
    """

    """
    def __init__(self, parent=None, close_function=None):
        """

        :param parent:
        :param close_function:
        """
        super(GroundTruthHelper, self).__init__(parent)

        self.close_event = self.Exit()
        if close_function is not None:
            self.close_event.exitClicked.connect(close_function)


        # Each video path has the following format:
        #   -> (1, 2, 3):
        #       1: Path relative to video_dir
        #       2: Minimum video number in specified path
        #       3. Maximum video number in specified path
        #
        self.video_dir              = "../gesture_videos"
        self.video_path_template    = [
                                        ("arrows/exercise_a/a{}.mp4", 12),
                                        ("arrows/exercise_b/b{}.mp4", 17),
                                        ("arrows/exercise_c/c{}.mp4", 23)
                                    ]
        self.sleep_period           = 2 # seconds

        # States
        self.playing            = False
        self.all_video_paths    = None
        self.worker             = None

        self.initUI()

    def initUI(self):
        self.setGeometry(0, 0, 1024, 768)

        # Contains all widgets within this main window
        top_level_widget = QWidget(self)
        self.setCentralWidget(top_level_widget)
        top_layout = QGridLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(12)

        # Top Text
        self.status_label   = QLabel("Waiting to Start...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 18pt; "
                                        "   color: red;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.progress_label = QLabel("0.0s (1 / 1)")
        self.progress_label.setStyleSheet(" font-size: 16pt; color: black;")
        self.progress_label.setAlignment(Qt.AlignCenter)

        # Video box
        self.setWindowTitle("Ground Truth Helper")
        self.video_player = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        videoWidget = QVideoWidget()

        # Description Box
        description_box = QGroupBox()
        description_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        description_box.setContentsMargins(0, 0, 0, 0)
        desc_layout     = QVBoxLayout()
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.setSpacing(0)

        self.desc_title      = QLabel("No Movement")
        self.desc_title.setStyleSheet("border: 4px solid gray; font-weight: bold; font-size: 14pt;")
        self.desc_title.setAlignment(Qt.AlignCenter)
        self.desc_explain    = QTextEdit("No description available.")
        self.desc_explain.setStyleSheet("border: 4px solid gray; font-size: 12pt; border-color: black;")
        self.desc_explain.setReadOnly(True)

        desc_layout.addWidget(self.desc_title)
        desc_layout.addWidget(self.desc_explain)
        desc_layout.setStretchFactor(self.desc_title, 1)
        desc_layout.setStretchFactor(self.desc_explain, 9)
        description_box.setLayout(desc_layout)

        # Start, Pause, Stop Buttons
        start_stop_box      = QGroupBox()
        start_stop_box.setContentsMargins(0, 0, 0, 0)
        start_stop_box.setObjectName("StartBox")
        #start_stop_box.setStyleSheet("QGroupBox#StartBox { border: 2px solid gray; border-radius: 10px;"
        #                             "                       border-color: black;}")
        start_box_layout    = QGridLayout()

        self.current_movement = QLabel("")
        self.current_movement.setAlignment(Qt.AlignCenter)
        self.current_movement.setStyleSheet("background-color: #cccccc; border: 1px solid gray; font-size: 14pt;"
                                            "   font-weight: bold;")
        start_box_layout.addWidget(self.current_movement, 0, 1, 1, 3)

        self.play_button = QPushButton()
        self.play_button.setText("Start")
        self.play_button.setStyleSheet("font-weight: bold;")
        self.play_button.clicked.connect(self.start_videos)
        self.pause_button = QPushButton()
        self.pause_button.setText("Pause")
        self.pause_button.setStyleSheet("font-weight: bold;")
        self.pause_button.clicked.connect(self.pause_videos)
        self.stop_button = QPushButton()
        self.stop_button.setText("Stop")
        self.stop_button.setStyleSheet("font-weight: bold;")
        self.stop_button.clicked.connect(self.stop_videos)
        start_box_layout.addWidget(self.play_button, 2, 1)
        start_box_layout.addWidget(self.pause_button, 2, 2)
        start_box_layout.addWidget(self.stop_button, 2, 3)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setLineWidth(2)
        start_box_layout.addWidget(separator, 1, 1, 1, 3)

        start_stop_box.setLayout(start_box_layout)
        start_box_layout.setColumnStretch(0, 10)
        start_box_layout.setColumnStretch(1, 10)
        start_box_layout.setColumnStretch(2, 10)
        start_box_layout.setColumnStretch(3, 10)
        start_box_layout.setColumnStretch(4, 10)
        start_box_layout.setRowStretch(0, 1)
        start_box_layout.setRowStretch(1, 1)
        start_box_layout.setRowStretch(2, 1)

        # Training Session Parameters
        parameters_box = QGroupBox()
        parameters_box.setTitle("Collection Parameters")
        parameters_box.setObjectName("CollecParamBox")
        parameters_box.setStyleSheet("QGroupBox#CollecParamBox { border: 1px solid gray; border-radius: 7px; margin-top: 0.5em;"
                                     "                              font-weight: bold; }"
                                     "QGroupBox#CollecParamBox::title { subcontrol-origin: margin; left: 9px; }")
        parameters_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top_param_layout    = QGridLayout()

        rep_title       = QLabel("Number of Repetitions")
        self.num_reps   = QLineEdit("6")
        top_param_layout.addWidget(rep_title, 0, 0)
        top_param_layout.addWidget(self.num_reps, 0, 2, 1, 2)
        top_param_layout.setSpacing(0)

        collect_title   = QLabel("(<b>Collect</b>\\<b>Rest</b>) Duration")
        self.collect_entry   = QLineEdit("5.0")
        self.rest_entry      = QLineEdit("5.0")
        top_param_layout.addWidget(collect_title, 1, 0)
        top_param_layout.addWidget(self.collect_entry, 1, 2)
        top_param_layout.addWidget(self.rest_entry, 1, 3)

        ex_label = QLabel("Exercise (<b>A</b>\\<b>B</b>\\<b>C</b>)")
        check_layout = QHBoxLayout()
        check_layout.setSpacing(0)
        check_layout.setContentsMargins(0, 0, 0, 0)

        self.ex_a_check = QCheckBox()
        self.ex_a_check.setChecked(True)
        self.ex_b_check = QCheckBox()
        self.ex_b_check.setChecked(True)
        self.ex_c_check = QCheckBox()
        self.ex_c_check.setChecked(True)
        check_layout.addWidget(self.ex_a_check)
        check_layout.addWidget(self.ex_b_check)
        check_layout.addWidget(self.ex_c_check)
        top_param_layout.addWidget(ex_label, 2, 0)
        top_param_layout.addLayout(check_layout, 2, 2, 1, 2)
        top_param_layout.setColumnStretch(0, 5)
        top_param_layout.setColumnStretch(1, 1)
        top_param_layout.setColumnStretch(2, 3)
        top_param_layout.setColumnStretch(3, 3)
        parameters_box.setLayout(top_param_layout)

        # Positions and sizes of all widgets in grid layout
        top_layout.addWidget(self.status_label, 0, 0)
        top_layout.addWidget(self.progress_label, 0, 1)
        top_layout.addWidget(videoWidget, 1, 0)
        top_layout.addWidget(description_box, 1, 1)
        top_layout.addWidget(start_stop_box, 2, 0)
        top_layout.addWidget(parameters_box, 2, 1)
        top_layout.setRowStretch(0, 7)
        top_layout.setRowStretch(1, 100)
        top_layout.setRowStretch(2, 10)
        top_layout.setColumnStretch(0, 66)
        top_layout.setColumnStretch(1, 33)

        # Set widget to contain window contents
        top_level_widget.setLayout(top_layout)
        self.video_player.setVideoOutput(videoWidget)
        self.video_player.setMuted(True)

    def start_videos(self):

        if self.playing:
            return

        if self.worker is not None:
            self.worker.force_unpause()
            time.sleep(self.sleep_period)
            self.playing = True
            return

        #
        # Check for valid inputs
        #
        def throw_error_message(self, message):
            self.warning = QErrorMessage()
            self.warning.showMessage(message)
            self.warning.show()
            return None

        def acquire_var(self, text, widget_name, func):
            try:
                temp = func(text)
            except:
                if func == float:
                    return throw_error_message(self, "Please set a valid float for \"{}\".".format(widget_name))
                else:
                    return throw_error_message(self, "Please set a valid integer for \"{}\".".format(widget_name))
            return temp

        if ((acquire_var(self, self.collect_entry.text(), "Collect Duration", float) is None) or
                (acquire_var(self, self.collect_entry.text(), "Rest Duration", float) is None) or
                (acquire_var(self, self.num_reps.text(), "Number of Repetitions", int) is None)):
            return

        self.collect_duration   = acquire_var(self, self.collect_entry.text(), "Collect Duration", float)
        self.rest_duration      = acquire_var(self, self.rest_entry.text(), "Rest Duration", float)
        self.repetitions        = acquire_var(self, self.num_reps.text(), "Rest Duration", int)

        if (not self.ex_a_check.isChecked()) and (not self.ex_b_check.isChecked()) and (not self.ex_c_check.isChecked()):
            return throw_error_message(self, "Please select at least one exercise.")

        if self.collect_duration < 1.0:
            return throw_error_message(self, "Please select a collect duration >= 1.0s.")
        if self.rest_duration < 1.0:
            return throw_error_message(self, "Please select a rest duration >= 1.0s.")
        if self.repetitions < 1:
            return throw_error_message(self, "Please select a number of repetitions >= 1.")

        #
        # Attempt to find all videos
        #
        exercises_found = self.check_video_paths()

        def missing_exer(self, ex_found, ex_label):
            if not ex_found:
                self.warning = QErrorMessage()
                self.warning.showMessage("Unable to find videos for Exercise {}.".format(ex_label))
                self.warning.show()
            return ex_found

        if ((not missing_exer(self, exercises_found[0], "A")) or (not missing_exer(self, exercises_found[1], "B")) or
                (not missing_exer(self, exercises_found[2], "C"))):
            return

        #
        # Start playing videos, and updating text fields, via background thread
        #
        self.worker = GroundTruthWorker(self.status_label, self.progress_label, self.desc_title, self.desc_explain,
                                            self.current_movement, self.video_player, self.all_video_paths,
                                            self.collect_duration, self.rest_duration, self.repetitions)
        QThreadPool.globalInstance().start(self.worker)
        time.sleep(self.sleep_period)

        self.playing = True

    def pause_videos(self):
        if not self.playing:
            return

        self.worker.force_pause()
        time.sleep(self.sleep_period)
        self.playing = False

    def stop_videos(self):
        if not self.playing:
            return

        self.worker.force_stop()
        time.sleep(self.sleep_period)
        self.worker  = None
        self.playing = False

    def check_video_paths(self):
        """

        :return:
        """

        exercises_found         = [True, True, True]
        self.all_video_paths    = [("A", []), ("B", []), ("C", [])]

        def create_exercise_paths(self, ex_label):
            ex_index        = ord(ex_label) - ord('A')
            found_videos    = True
            path_template   = join(self.video_dir, self.video_path_template[ex_index][0])
            max_idx         = self.video_path_template[ex_index][1]
            ex_path_created = []

            for i in range(1, max_idx + 1):
                full_path = path_template.format(i)
                ex_path_created.append(full_path)

                if not exists(full_path):
                    found_videos = False
                    break

            self.all_video_paths[ex_index][1].extend(ex_path_created)
            return found_videos

        if self.ex_a_check.isChecked():
            exercises_found[0] = create_exercise_paths(self, "A")
        if self.ex_b_check.isChecked():
            exercises_found[1] = create_exercise_paths(self, "B")
        if self.ex_c_check.isChecked():
            exercises_found[2] = create_exercise_paths(self, "C")

        return exercises_found

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
        if self.worker is None:
            return 0
        else:
            if self.worker.current_label is None:
                return 0
            else:
                return self.worker.current_label