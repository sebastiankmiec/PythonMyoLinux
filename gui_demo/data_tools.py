#
# PyQt5 imports
#
from PyQt5.QtWidgets import (QListWidget, QListWidgetItem, QProgressDialog, QTabWidget, QFileDialog, QMessageBox,
                             QWidget, QLabel, QHBoxLayout, QVBoxLayout, QCheckBox, QFrame, QMainWindow, QPushButton,
                             QGridLayout, QSizePolicy, QGroupBox, QTextEdit, QLineEdit, QErrorMessage, QProgressBar)

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


# Old backend:
# from PyQt5.QtChart import QLineSeries, QValueAxis


########################################################################################################################
#
# Custom PyQt5 events (emitted by DataTools)
#
########################################################################################################################

# Used by MyoDataWorker
class DataTabUpdate(QObject):
    connectUpdate       = pyqtSignal([bytes, int, int])
    disconnectUpdate    = pyqtSignal([bytes])

########################################################################################################################


class DataTools(QWidget):
    """
        A top level widget containing all other widgets used for the "Data Tools" tab.
    """

    def __init__(self, on_device_connected, on_device_disconnected, is_data_tools_open):
        super().__init__()

        self.myo_devices = []
        self.first_myo = None  # Currently connected myo devices, and associated ports
        self.first_port = None
        self.second_myo = None
        self.second_port = None
        self.is_data_tools_open = is_data_tools_open

        self.first_myo_data = []  # Data collected by event handlers
        self.second_myo_data = []

        self.progress_bars = []  # Progress bars, used when searching for Myo armband devies
        self.search_threads = []  # Background threads that scan for advertising packets from advertising
        self.myo_counts = []  # The number of Myo devices found, via a given communication port

        # Emitted signals
        self.data_tab_signals = DataTabUpdate()
        self.data_tab_signals.connectUpdate.connect(on_device_connected)
        self.data_tab_signals.disconnectUpdate.connect(on_device_disconnected)

        # States
        self.ports_searching = {}
        self.gt_helper_open = False  # Ground truth helper

        # Configurable
        self.start_time = time.time()
        self.data_directory = None
        self.increments = 100  # Number of progress bar increments (when searching for Myo devices)
        self.worker_check_period = 1  # seconds

        self.init_ui()

    def init_ui(self):

        # DataTools top layout
        self.setContentsMargins(5, 15, 5, 5)
        data_collection_layout = QGridLayout()
        data_collection_layout.setSpacing(15)

        #
        # Myo dongle and device discovery
        #
        com_port_button = QPushButton("Find COM Ports")
        com_port_button.clicked.connect(self.find_ports)
        data_collection_layout.addWidget(com_port_button, 0, 0, Qt.AlignBottom)
        self.ports_found = QListWidget()  # Populated with found dongles and devices
        self.ports_found.itemPressed.connect(self.serial_port_clicked)
        data_collection_layout.addWidget(self.ports_found, 1, 0, 1, 1)

        #
        # EMG Data Visualization
        #
        # EMG data plots
        self.myo_1_layouts = [pg.GraphicsLayoutWidget() for x in range(8)]
        self.myo_2_layouts = [pg.GraphicsLayoutWidget() for x in range(8)]
        self.myo_1_charts = [None for x in range(8)]
        self.myo_2_charts = [None for x in range(8)]
        self.top_tab = QTabWidget()  # Top-level tab container

        # Old backend
        # self.myo_1_charts = [QChartView() for x in range(8)]               # EMG data plots
        # self.myo_2_charts = [QChartView() for x in range(8)]

        #
        # Helper function used below
        #
        def initialize_plots(charts_list, layouts_list, top_tab, device_num):
            """
                A helper function that initializes all plots (for both devices, and all channels)

            :param charts_list: A list of None -> becomes a list of PlotItem
            :param layouts_list: A list of GraphicsLayoutWidget
            :param top_tab: A top level tab per device
            :param device_num: The device number (1/2)
            """

            # Custom y-axis for EMG plots
            def custom_y_ticks(*args):
                return [(200.0, [-128, 0, 127]), (100.0, [-80, -40, 40, 80])]

            #
            # Channels 1-8 subtabs
            #
            for i, chart in enumerate(charts_list):
                brush = pg.functions.mkBrush(255, 255, 255)
                layouts_list[i].setBackgroundBrush(brush)

                # Add widget to tab
                top_tab.addTab(layouts_list[i], "Ch. " + str(i + 1))

                # Add plot to new widget
                temp_plot = pg.PlotItem()
                layouts_list[i].addItem(row=0, col=0, rowspan=1, colspan=1, item=temp_plot)
                charts_list[i] = temp_plot
                temp_plot.setMenuEnabled(False)

                # Customize plot
                charts_list[i].setXRange(0, NUM_GUI_SAMPLES, padding=0.075)
                charts_list[i].setYRange(-150, 150, padding=0)  # EMG values are signed 8-bit
                charts_list[i].showGrid(True, True, 0.6)
                layouts_list[i].ci.setContentsMargins(10, 10, 40, 20)

                left_axis = charts_list[i].getAxis("left")
                left_axis.tickValues = custom_y_ticks
                left_axis.setPen(color="333")

                bottom_axis = charts_list[i].getAxis("bottom")
                labelStyle = {'color': '#000', 'font-size': '12pt', "font-style": "italic", "font-weight": "bold"}
                bottom_axis.setLabel(text="Sample Number", **labelStyle)
                bottom_axis.setPen(color="333")

                charts_list[i].setTitle(title="Device {} - Channel {} - EMG Amplitude".format(device_num, i + 1),
                                        size="15pt", bold=True, color="000088")

        # Plot formatting (device one)
        self.myo_1_tab = QTabWidget()  # Myo device 1 tab
        self.myo_1_tab.setStyleSheet("font-weight: normal;")
        initialize_plots(self.myo_1_charts, self.myo_1_layouts, self.myo_1_tab, 1)

        # Plot formatting (device two)
        self.myo_2_tab = QTabWidget()
        self.myo_2_tab.setStyleSheet("font-weight: normal;")
        initialize_plots(self.myo_2_charts, self.myo_2_layouts, self.myo_2_tab, 2)

        self.top_tab.setStyleSheet("font-weight: bold;")

        # Plot layout
        data_collection_layout.addWidget(self.top_tab, 0, 1, 4, 1)
        data_collection_layout.setRowStretch(0, 1)
        data_collection_layout.setRowStretch(1, 20)
        data_collection_layout.setRowStretch(2, 5)
        data_collection_layout.setRowStretch(3, 1)
        data_collection_layout.setColumnStretch(0, 4)
        data_collection_layout.setColumnStretch(1, 6)

        #
        # Data Saving Options
        #
        self.data_gen_box = QGroupBox()  # Data Saving Options layout
        self.data_gen_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        top_layout = QVBoxLayout()
        top_layout.setSpacing(12)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # Data Generation Box
        inner_box = QGroupBox()
        inner_box.setObjectName("DataInnerBox")
        inner_box.setStyleSheet("QGroupBox#DataInnerBox { border: 1px solid gray; background-color: #cccccc;"
                                "                             border-radius: 7px;}")
        box_title = QLabel("Data Generation")
        box_title.setStyleSheet("font-weight: bold; font-size: 14pt;")
        top_layout.addWidget(box_title)
        top_layout.addWidget(inner_box)
        top_inner_layout = QVBoxLayout()
        top_inner_layout.setSpacing(10)
        top_inner_layout.setContentsMargins(10, 10, 10, 10)

        # "Save" and "GT Helper" buttons
        buttons_layout = QHBoxLayout()
        path_layout = QHBoxLayout()  # Line to enter path

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        separator.setLineWidth(2)

        path_title = QLabel("Output Directory")
        path_title.setStyleSheet("font-weight: bold")
        top_inner_layout.addWidget(path_title)  # Line to enter path
        self.save_path = QLineEdit()
        path_layout.addWidget(self.save_path)

        file_browser_button = QPushButton("...")  # File explorer button
        file_browser_button.clicked.connect(self.file_browser_clicked)
        path_layout.addWidget(file_browser_button)

        self.save_data_button = QPushButton("Save")  # Save button
        self.save_data_button.clicked.connect(self.save_clicked)

        self.gt_helper_button = QPushButton("GT Helper")  # Ground truth button
        self.gt_helper_button.clicked.connect(self.gt_helper_clicked)
        self.gt_helper = GroundTruthHelper(close_function=self.gt_helper_closed)

        top_inner_layout.addLayout(path_layout)
        top_inner_layout.addWidget(separator)
        top_inner_layout.addLayout(buttons_layout)
        buttons_layout.addWidget(self.save_data_button)
        buttons_layout.addWidget(self.gt_helper_button)
        inner_box.setLayout(top_inner_layout)
        self.data_gen_box.setLayout(top_layout)
        data_collection_layout.addWidget(self.data_gen_box, 2, 0, 2, 1)
        self.setLayout(data_collection_layout)

    def stop_data_tools_workers(self):
        """
            Stops all workers related to the "Data Tools" tab.
        """

        #
        # Wait on Myo search workers to complete
        #
        waiting_on_search = True
        while waiting_on_search:

            waiting_on_search = False
            for worker in self.search_threads:
                if not worker.complete:
                    worker.running = False
                    waiting_on_search = True
                    break

            if waiting_on_search:
                time.sleep(self.worker_check_period)

        #
        # Stop data workers
        #
        waiting_on_search = True
        while waiting_on_search:

            waiting_on_search = False
            num_widgets = self.ports_found.count()

            for idx in range(num_widgets):

                # Ignore port widgets (only interested in Myo device rows)
                list_widget = self.ports_found.item(idx)
                if hasattr(list_widget, "port_idx"):
                    continue

                myo_widget = self.ports_found.itemWidget(list_widget)

                if not (myo_widget.worker is None):
                    if not myo_widget.worker.complete:
                        myo_widget.worker.running = False
                        waiting_on_search = True
                        break

            if waiting_on_search:
                time.sleep(self.worker_check_period)

        #
        # Stop GT Helper
        #
        if not (self.gt_helper.worker is None):
            self.gt_helper.stop_videos()

            while not (self.gt_helper.worker.complete):
                time.sleep(self.worker_check_period)

        if self.gt_helper_open:
            self.gt_helper.close()

    def get_current_label(self):
        """
            Passes the current ground truth label of the movement being performed from GT helper to data workers.

        :return: [int] Ground truth label of current movement
        """
        if self.gt_helper_open:
            return self.gt_helper.get_current_label()
        else:
            return -1

    def gt_helper_closed(self):
        self.gt_helper_open = False

    def file_browser_clicked(self):
        """
            File explorer button clicked.
        """

        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly)
        self.data_directory = dialog.getExistingDirectory(self, 'Choose Directory', curdir)

        if exists(curdir):
            self.save_path.setText(self.data_directory)

    def save_clicked(self):
        """
            Save button clicked.
        """

        if (((self.data_directory is None) or (not exists(self.data_directory))) and
                (not exists(self.save_path.text()))):
            self.warn_user("Invalid path selected.")
            return
        else:
            self.data_directory = self.save_path.text()

        if (self.first_myo != None) or (self.second_myo != None):
            self.warn_user("Please disconnect Myo devices first.")
            return

        #
        # Helper function that saves one data point to a file descriptor (for a file containing a single device)
        #
        def write_single(data, fd):

            # See "create_emg_event" for details:
            base_time = self.start_time
            cur_time = data[0]
            index = data[1]
            emg_list = data[2]
            orient_list = data[3]
            accel_list = data[4]
            gyro_list = data[5]
            label = data[6]

            # Write to file descriptor
            fd.write("{:.4f},{},{},{},{},{},{},{},{},{},{},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},"
                     "{:.4f},{:.4f}\n".format(
                cur_time - base_time, index, label,
                emg_list[0], emg_list[1], emg_list[2], emg_list[3], emg_list[4],
                emg_list[5], emg_list[6], emg_list[7],
                orient_list[0], orient_list[1], orient_list[2], orient_list[3],
                accel_list[0], accel_list[1], accel_list[2],
                gyro_list[0], gyro_list[1], gyro_list[2]
            ))

        if (len(self.first_myo_data) == 0) and (len(self.second_myo_data) == 0):
            self.warn_user("No data available to save.")

        # Multiple myo devices to save data from
        elif (len(self.first_myo_data) != 0) and (len(self.second_myo_data) != 0):

            full_path_1 = join(self.data_directory, FILENAME_1)
            full_path_2 = join(self.data_directory, FILENAME_2)
            full_path_all = join(self.data_directory, FILENAME_all)
            first_myo_data = copy.deepcopy(self.first_myo_data)
            sec_myo_data = copy.deepcopy(self.second_myo_data)

            # File descriptors for 3 created files
            fd_1 = open(full_path_1, "w")
            fd_2 = open(full_path_2, "w")
            fd_all = open(full_path_all, "w")

            # Headers
            fd_1.write(
                "Time, Index, Label, EMG_1, EMG_2, EMG_3, EMG_4, EMG_5, EMG_6, EMG_7, EMG_8, OR_W, OR_X, OR_Y, OR_Z,"
                "ACC_1, ACC_2, ACC_3, GYRO_1, GYRO_2, GYRO_3\n")
            fd_2.write(
                "Time, Index, Label, EMG_1, EMG_2, EMG_3, EMG_4, EMG_5, EMG_6, EMG_7, EMG_8, OR_W, OR_X, OR_Y, OR_Z,"
                "ACC_1, ACC_2, ACC_3, GYRO_1, GYRO_2, GYRO_3\n")
            fd_all.write("Time_1, Time_2, Label, D1_EMG_1, D1_EMG_2, D1_EMG_3, D1_EMG_4, D1_EMG_5, D1_EMG_6, D1_EMG_7,"
                         " D1_EMG_8, D1_OR_W, D1_OR_X, D1_OR_Y, D1_OR_Z, D1_ACC_1, D1_ACC_2, D1_ACC_3, D1_GYRO_1,"
                         " D1_GYRO_2, D1_GYRO_3,"
                         " D2_EMG_1, D2_EMG_2, D2_EMG_3, D2_EMG_4, D2_EMG_5, D2_EMG_6, D2_EMG_7, D2_EMG_8, D2_OR_W,"
                         " D2_OR_X, D2_OR_Y, D2_OR_Z, D2_ACC_1, D2_ACC_2, D2_ACC_3, D2_GYRO_1, D2_GYRO_2, D2_GYRO_3\n")

            # Find
            #   1) Time of which both devices are recording,
            #   2) Time of which the first device stops recording
            max_first = float("-inf")
            min_last = float("inf")

            if max_first < first_myo_data[0][0]:
                max_first = first_myo_data[0][0]
            if max_first < sec_myo_data[0][0]:
                max_first = sec_myo_data[0][0]
            if min_last > first_myo_data[len(first_myo_data) - 1][0]:
                min_last = first_myo_data[len(first_myo_data) - 1][0]
            if min_last > sec_myo_data[len(sec_myo_data) - 1][0]:
                min_last = sec_myo_data[len(sec_myo_data) - 1][0]

            # Define time of first data point (using a buffer period)
            start_time = max_first + BUFFER_PERIOD
            if start_time > min_last:
                self.warn_user("Less than {} seconds worth of data collected.".format(BUFFER_PERIOD))
                fd_1.close()
                fd_2.close()
                fd_all.close()
                return

            #
            # Save data to individual files, and find start indices
            #
            min_first_dist = float("inf")
            min_sec_dist = float("inf")
            first_idx = None
            sec_idx = None

            for i, data in enumerate(first_myo_data):
                time = data[0]
                if abs(start_time - time) < min_first_dist:
                    min_first_dist = abs(start_time - time)
                    first_idx = i
                write_single(data, fd_1)
            for i, data in enumerate(sec_myo_data):
                time = data[0]
                if abs(start_time - time) < min_sec_dist:
                    min_sec_dist = abs(start_time - time)
                    sec_idx = i
                    write_single(data, fd_2)

            #
            # Attempt to create a file with data synchronized file (using timestamps)
            #
            second_offset = sec_idx  # Index to data of second device

            for first_offset, data in enumerate(first_myo_data):
                if first_offset < first_idx:
                    continue
                if second_offset >= len(sec_myo_data):
                    break

                #
                # See "create_emg_event" for details:
                #
                base_time = self.start_time  # Single data point (device one)
                cur_time = data[0]
                emg_list = data[2]
                orient_list = data[3]
                accel_list = data[4]
                gyro_list = data[5]
                label_one = data[6]  # Label, as per device one (not device two)

                cur_sec_data = sec_myo_data[second_offset]  # Single data point (device two)
                cur_time_2 = cur_sec_data[0]

                # Time since opening of GUI program
                first_delta_time = cur_time - base_time
                sec_delta_time = cur_time_2 - base_time

                #
                # If the second device is lagging, let the second device catch up
                #       ---> By finding a more recent second device data point
                #
                if first_delta_time - sec_delta_time > COPY_THRESHOLD:
                    while first_delta_time - sec_delta_time > COPY_THRESHOLD:
                        second_offset += 1
                        if second_offset >= len(sec_myo_data):
                            break

                        cur_sec_data = sec_myo_data[second_offset]
                        cur_time_2 = cur_sec_data[0]
                        sec_delta_time = cur_time_2 - base_time

                if second_offset >= len(sec_myo_data):
                    break
                else:
                    cur_sec_data = sec_myo_data[second_offset]  # Update single data point
                    cur_time_2 = cur_sec_data[0]
                    emg_list_2 = cur_sec_data[2]
                    orient_list_2 = cur_sec_data[3]
                    accel_list_2 = cur_sec_data[4]
                    gyro_list_2 = cur_sec_data[5]
                    sec_delta_time = cur_time_2 - base_time

                #
                # If second data is ahead, let the first device catch up
                #       ---> By finding a more recent first device data point
                #
                if sec_delta_time - first_delta_time > COPY_THRESHOLD:
                    continue

                # Write to file descriptor
                fd_all.write("{:.4f},{:.4f},{},{},{},{},{},{},{},{},{},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},"
                             "{:.4f},{:.4f},{:.4f},{:.4f},{},{},{},{},{},{},{},{},{:.4f},{:.4f},{:.4f},{:.4f},{:.4f},"
                             "{:.4f},{:.4f},{:.4f},{:.4f},{:.4f}\n".
                    format(
                    first_delta_time, sec_delta_time, label_one,
                    emg_list[0], emg_list[1], emg_list[2], emg_list[3], emg_list[4],
                    emg_list[5], emg_list[6], emg_list[7],
                    orient_list[0], orient_list[1], orient_list[2], orient_list[3],
                    accel_list[0], accel_list[1], accel_list[2],
                    gyro_list[0], gyro_list[1], gyro_list[2],

                    emg_list_2[0], emg_list_2[1], emg_list_2[2], emg_list_2[3], emg_list_2[4],
                    emg_list_2[5], emg_list_2[6], emg_list_2[7],
                    orient_list_2[0], orient_list_2[1], orient_list_2[2], orient_list_2[3],
                    accel_list_2[0], accel_list_2[1], accel_list_2[2],
                    gyro_list_2[0], gyro_list_2[1], gyro_list_2[2]
                )
                )
                second_offset += 1

            fd_1.close()
            fd_2.close()
            fd_all.close()

            self.update = QMessageBox()
            self.update.setText("Saved data from two Myo devices.")
            self.update.show()

        # Only a single Myo device to save data from (simpler)
        else:

            full_path = join(self.data_directory, SINGLE_MYO_FILENAME)

            # Select data from valid device
            data_ref = None
            if len(self.first_myo_data) == 0:
                data_ref = copy.deepcopy(self.second_myo_data)
            else:
                data_ref = copy.deepcopy(self.first_myo_data)

            # Create file, write header
            fd = open(full_path, "w")
            fd.write(
                "Time, Index, Label, EMG_1, EMG_2, EMG_3, EMG_4, EMG_5, EMG_6, EMG_7, EMG_8, OR_W, OR_X, OR_Y, OR_Z,"
                "ACC_1, ACC_2, ACC_3, GYRO_1, GYRO_2, GYRO_3\n")

            # Save data points
            for data in data_ref:
                write_single(data, fd)
            fd.close()

            self.update = QMessageBox()
            self.update.setText("Saved data from one Myo device.")
            self.update.show()

    def gt_helper_clicked(self):
        if not self.gt_helper_open:
            self.gt_helper_open = True
            self.gt_helper.show()

    def find_ports(self):
        """
            Find available serial USB interfaces (character device files, /dev/tty*), corresponding to Myo dongles.
        """

        #
        # If a port is searching for Myo devices, wait
        #
        port_searching = False
        for port in self.ports_searching.keys():
            if self.ports_searching[port]:
                port_searching = True
                break

        if port_searching:
            self.warn_user("A port is currently searching for devices.")
            return

        self.myo_counts.clear()
        self.ports_found.clear()
        self.progress_bars.clear()

        expec_manufac = "Bluegiga"
        expec_name = "Low Energy Dongle"

        ports_found = 0
        for port in comports():

            #
            # If this is a Bluegiga - Low Energy Dongle
            #
            port_attr = port.__dict__
            if not (
                    ("manufacturer" in port_attr.keys()) and
                    (("product" in port_attr.keys()) or ("description" in port_attr.keys())) and
                    ("device" in port_attr.keys())
            ):
                continue

            if not (
                    (expec_manufac in port_attr["manufacturer"]) or
                    ((expec_name in port_attr["product"]) and (expec_name in port_attr["description"]))
            ):
                continue

            # Styling
            port_list_entry = QListWidgetItem(port_attr["device"])

            port_list_entry.setIcon(QIcon(join(abspath(__file__).replace("data_tools.py", ""), "icons/sp.png")))
            port_list_entry.port_idx = ports_found
            port_list_entry.port = port_attr["device"]
            self.ports_found.insertItem(ports_found, port_list_entry);
            ports_found += 1
            self.myo_counts.append(0)  # No Myo devices found for this newly found port yet

    def serial_port_clicked(self, e):
        """
            On a click event (may not be a port), search for Myo devices using this port.
        :param e: A click event on a port (ideally).
        """

        try:
            index = e.port_idx  # Port number
            port = e.port  # /dev/ttyXYZ
        except:
            return

        #
        # Port is already searching
        #
        if port in self.ports_searching:
            if self.ports_searching[port]:
                self.warn_user("This port is already searching for devices.")
                return

        #
        # First, clear Myo devices previously found on this port
        #
        list_index = 0
        for i in range(index):
            list_index += 1
            list_index += self.myo_counts[i]

        for j in range(self.myo_counts[index]):
            self.ports_found.takeItem(list_index + 1)

        #
        # Add a progress bar message
        #
        progress = QProgressDialog("Searching for Myo armbands...", "Cancel", 0, self.increments)
        progress.setWindowTitle("In Progress")
        progress.show()
        progress.setValue(0)
        progress.setCancelButton(None)
        self.progress_bars.append(progress)

        #
        # Create background thread to search for Myo devices
        #
        self.myo_counts[index] = 0
        self.ports_searching[port] = True
        worker = MyoSearchWorker(port, progress, partial(self.devices_found,
                                                         thread_idx=len(self.search_threads),
                                                         port=port,
                                                         myo_count_index=index), self.increments)
        self.search_threads.append(worker)
        QThreadPool.globalInstance().start(worker)

    def devices_found(self, thread_idx=None, port=None, myo_count_index=None):
        """
            After searching for devices (see serial_port_clicked) is complete, an event is emitted and this
                function is called.

        :param thread_idx: Index in list of threads
        :param port: Port used to find devices.
        :param myo_count_index: Index to list storing number of Myo devices found for a given port
        :return:
        """
        self.ports_searching[port] = False

        if len(self.search_threads[thread_idx].myo_found) == 0:
            return

        # Find index to insert found Myo results
        list_index = 0
        for i in range(myo_count_index):
            list_index += 1
            list_index += self.myo_counts[i]

        # For each myo found
        for i, device in enumerate(self.search_threads[thread_idx].myo_found):
            temp_widget = QListWidgetItem()
            temp_widget.setBackground(Qt.gray)

            #
            # Holds relevant information about Myo found, and reacts to user actions
            #
            widget = MyoFoundWidget(port, device, self.connection_made, self.connection_dropped,
                                        self.get_current_label, partial(self.battery_update,
                                                                    device_address=device["sender_address"]),
                                        self.data_tab_signals, self.is_data_tools_open
                                    )

            # Add to list of Myo dongles and devices found
            temp_widget.setSizeHint(widget.sizeHint())
            self.ports_found.insertItem(list_index + i + 1, temp_widget)
            self.ports_found.setItemWidget(temp_widget, widget)
            self.myo_counts[myo_count_index] += 1

    def battery_update(self, battery_level, device_address):
        """
            This function is called after a data worker receives a battery service response from a Myo device.
                --> Updates the ports found list with accurate battery levels.

        :param battery_level: [int] The current battery level of some Myo device.
        :param device_address: [bytes] The MAC address of the corresponding Myo device.
        """

        num_widgets = self.ports_found.count()
        for idx in range(num_widgets):

            # Ignore port widgets (only interested in Myo device rows)
            list_widget = self.ports_found.item(idx)
            if hasattr(list_widget, "port_idx"):
                continue

            myo_widget = self.ports_found.itemWidget(list_widget)

            if myo_widget.myo_device["sender_address"].endswith(device_address):
                myo_widget.battery_level.setValue(battery_level)

    def connection_dropped(self, address):
        """
                Prior to disconnecting from a Myo device, this function is called to ensure a disconnect is valid.

        :param address: Address of Myo device.
        """
        if self.first_myo is None:

            if (self.second_myo != None) and (self.second_myo == address):
                self.second_myo = None
                self.second_port = None
                self.top_tab.removeTab(0)

                # Old backend:
                # for i in range(len(self.myo_1_charts)):
                #    self.myo_2_charts[i].chart().removeAllSeries()
            else:
                return self.warn_user("An unexpected error has occured.")

        else:
            if self.first_myo == address:
                self.first_myo = None
                self.first_port = None
                self.top_tab.removeTab(0)

                # Old backend:
                # for i in range(len(self.myo_1_charts)):
                #    self.myo_1_charts[i].chart().removeAllSeries()

            elif self.second_myo != None:
                if (self.second_myo != None) and (self.second_myo == address):
                    self.second_myo = None
                    self.second_port = None
                    self.top_tab.removeTab(1)

                    # Old backend:
                    # for i in range(len(self.myo_1_charts)):
                    #    self.myo_2_charts[i].chart().removeAllSeries()
                else:
                    return self.warn_user("An unexpected error has occured.")

    def connection_made(self, address, port):
        """
            Prior to connecting to a Myo device, this function is called to ensure a connection can be made.

        :param address: Address of Myo device.
        :param port: Communication port to be used for connection.
        :return: (top_tab_idx, obj, index, charts, myo_data)

            Where:
                top_tab_idx: Regers to the index of the top most tab open (Myo Device 1 or 2)
                obj: Allows MyoFoundWidget to determine which tab it controls
                index: Refers to index of channel tab open
                charts: Refers to one of two chart objects that should be filled with EMG data visualizations
                myo_data: Refers to a list that should be filled with incoming EMG/IMU data
        """

        if self.first_myo is None:

            if self.second_myo != None:

                if self.second_myo == address:
                    return self.warn_user("The device you attempted to connect to is already connected.")
                elif port == self.second_port:
                    return self.warn_user("The device you attempted to connect to, requires a port that is already"
                                          " in use.")

            self.first_myo = address
            self.first_port = port
            self.top_tab.addTab(self.myo_1_tab, "Myo Device 1")

            return (
                self.top_tab.currentIndex, None, self.myo_1_tab.currentIndex, self.myo_1_charts, self.first_myo_data)

        else:
            if self.second_myo != None:
                return self.warn_user("This GUI only currently supports up to two Myo devices.")
            elif self.first_myo == address:
                return self.warn_user("The device you attempted to connect to is already connected.")
            elif port == self.first_port:
                return self.warn_user("The device you attempted to connect to, requires a port that is already in use.")
            else:
                self.second_myo = address
                self.second_port = port

                self.top_tab.addTab(self.myo_2_tab, "Myo Device 2")

                return (self.top_tab.currentIndex, self.first_myo, self.myo_2_tab.currentIndex, self.myo_2_charts,
                        self.second_myo_data)

    def warn_user(self, message):
        """
            Generates a pop-up warning message

        :param message: The text to display
        """
        self.warning = QErrorMessage()
        self.warning.showMessage(message)
        self.warning.show()


########################################################################################################################
########################################################################################################################
########################################################################################################################
#
# (DataTools) Widgets Used
#
########################################################################################################################
########################################################################################################################
########################################################################################################################

class MyoFoundWidget(QWidget):
    """
        A Widget for a Myo found list entry, that provides the ability to connect/disconnect.
    """

    def __init__(self, port, myo_device, connect_notify, disconnect_notify, get_current_label, battery_notify,
                    data_tab_signals, is_data_tools_open):
        """

        :param port: The port used to find this device.
        :param myo_device: The hardware (MAC) address of this device.
        :param connect_notify: A function called prior to connection attempts.
        :param disconnect_notify: A function called prior to disconnect attempts.
        :param get_current_label: A function that returns the current ground truth label.
        :param battery_notify: A function called on battery update evenets.
        """
        super().__init__()

        self.myo_device = myo_device
        self.chart_list = None
        self.tab_open = None
        self.port = port
        self.connect_notify = connect_notify
        self.disconnect_notify = disconnect_notify
        self.get_current_label = get_current_label
        self.battery_notify = battery_notify
        self.data_tab_signals = data_tab_signals
        self.is_data_tools_open = is_data_tools_open

        # States
        self.connected = False
        self.worker = None

        # Configurable parameters
        self.num_trim_samples = 400  # On unexpected disconnect, or user-initiated disconnect, trim this many samples
        #       from the list of all collected data thus far.
        self.init_UI()

    def init_UI(self):

        # Layout
        topLayout = QVBoxLayout()
        infoLayout = QHBoxLayout()
        infoLayout.setSpacing(5)

        # Myo armband icon
        lbl = QLabel(self)
        orig = QPixmap(join(abspath(__file__).replace("data_tools.py", ""), "icons/myo.png"))
        new = orig.scaled(QSize(45, 45), Qt.KeepAspectRatio)
        lbl.setPixmap(new)

        #
        # Format the Myo hardware (MAC) into a readable form
        #
        infoLayout.addWidget(lbl)
        formatted_address = ""
        length = len(self.myo_device["sender_address"].hex())

        for i, ch in enumerate(self.myo_device["sender_address"].hex()):
            formatted_address += ch
            if ((i - 1) % 2 == 0) and (i != length - 1):
                formatted_address += "-"

        vline = QFrame()
        vline.setFrameShape(QFrame.VLine)
        vline.setFrameShadow(QFrame.Sunken)
        vline2 = QFrame()
        vline2.setFrameShape(QFrame.VLine)
        vline2.setFrameShadow(QFrame.Sunken)

        #
        # Myo armband address, signal strength
        #
        addr_label = QLabel(formatted_address)
        infoLayout.addWidget(addr_label)
        infoLayout.addWidget(vline)
        rssi_label = QLabel(str(self.myo_device["rssi"]) + " dBm")
        infoLayout.addWidget(rssi_label)
        infoLayout.addWidget(vline2)
        infoLayout.setStretchFactor(rssi_label, 3)
        infoLayout.setStretchFactor(addr_label, 6)

        #
        # Battery Level
        #
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

        self.top_tab_open = connection_contents[0]
        self.prev_tab = connection_contents[1]
        self.tab_open = connection_contents[2]
        self.chart_list = connection_contents[3]
        self.data_list = connection_contents[4]

        #
        # Begin the process of connecting and collecting data
        #
        if self.worker is None:
            # Data to be collected
            self.measurements_list = [[] for x in range(8)]
            self.data_indices = []
            self.plotted_data = [None for x in range(8)]

            # Create background worker
            self.worker = MyoDataWorker(self.port, self.myo_device, self.measurements_list, self.data_indices,
                                        self.on_axes_update, self.on_new_data, self.data_list, self.on_worker_started,
                                        self.on_worker_stopped, self.connect_failed, self.on_discon_occurred,
                                        self.battery_notify, self.create_event, self.get_current_label,
                                        self.data_tab_signals, self.is_data_tools_open)

            self.worker.setAutoDelete(False)  # We reuse this worker

        QThreadPool.globalInstance().start(self.worker)

    def create_event(self):
        """
                Determines if data updates should be sent to this MyoFoundWidget object, based on which top tab is open.

            :return: [bool] Should data updates be sent to this widget?
        """
        if self.prev_tab is None:
            idx = 0
        else:
            idx = 1
        return self.top_tab_open() == idx

    def on_worker_started(self):
        """
            Once the background data worker starts, this function is called.
                > This function sets up the EMG plots for updates, and allows the user to disconnect (if they wish).
        :return:
        """

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

        # Update states
        self.enable_text.setText("Disable: ")
        self.connected = True
        self.enable_box.setEnabled(True)

    def on_discon_occurred(self):
        """
            If a Myo device disconnects unexpectedly, this function is called.
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

        self.warning = QErrorMessage()
        self.warning.showMessage("Myo armband device disconnected unexpectedly.")
        self.warning.show()

        self.disconnect_notify(self.myo_device["sender_address"].hex())
        self.enable_box.setEnabled(True)

    def connect_failed(self):
        """
            A function called upon connection failure, from the background data worker.
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
        GroundTruthHelper is opened upon pressing "GT Helper".
            > This window plays videos and provides ground truth, in order to provide a simple data collection interface.
    """

    #
    # Used to cleanup background worker thread (on exit)
    #
    class Exit(QObject):
        exitClicked = pyqtSignal()

    def closeEvent(self, event):
        self.close_event.exitClicked.emit()

    def __init__(self, parent=None, close_function=None):
        """
        :param parent: Parent widget
        :param close_function: A function called upon user exit of the GroundTruthHelper window.
        """
        super().__init__()

        self.close_event = self.Exit()
        if close_function is not None:
            self.close_event.exitClicked.connect(close_function)
        self.close_event.exitClicked.connect(self.pause_videos)

        # Each video path has the following format:
        #   -> (1, 2, 3):
        #       1: Path relative to video_dir
        #       2: Minimum video number in specified path
        #       3. Maximum video number in specified path
        #
        self.video_dir = "../gesture_videos"
        self.video_path_template = [
            ("arrows/exercise_a/a{}.mp4", 12),
            ("arrows/exercise_b/b{}.mp4", 17),
            ("arrows/exercise_c/c{}.mp4", 23)
        ]

        # States
        self.playing = False
        self.all_video_paths = None
        self.worker = None
        self.unpausing = False
        self.pausing = False
        self.shutdown = False

        self.init_ui()

    def init_ui(self):
        self.setGeometry(0, 0, 1024, 768)

        #
        # Contains all widgets within this main window
        #
        top_level_widget = QWidget(self)
        self.setCentralWidget(top_level_widget)
        top_layout = QGridLayout()
        top_layout.setContentsMargins(10, 10, 10, 10)
        top_layout.setSpacing(12)

        #
        # Top Text
        #
        self.status_label = QLabel("Waiting to Start...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 18pt; "
                                        "   color: red;")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.progress_label = QLabel("0.0s (1 / 1)")
        self.progress_label.setStyleSheet(" font-size: 16pt; color: black;")
        self.progress_label.setAlignment(Qt.AlignCenter)

        #
        # Video box
        #
        self.setWindowTitle("Ground Truth Helper")
        self.video_player   = QMediaPlayer(None, QMediaPlayer.VideoSurface)
        video_widget        = QVideoWidget()

        #
        # Description Box
        #
        description_box = QGroupBox()
        description_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        description_box.setContentsMargins(0, 0, 0, 0)
        desc_layout = QVBoxLayout()
        desc_layout.setContentsMargins(0, 0, 0, 0)
        desc_layout.setSpacing(0)

        self.desc_title = QLabel("No Movement")
        self.desc_title.setStyleSheet("border: 4px solid gray; font-weight: bold; font-size: 14pt;")
        self.desc_title.setAlignment(Qt.AlignCenter)
        self.desc_explain = QTextEdit("No description available.")
        self.desc_explain.setStyleSheet("border: 4px solid gray; font-size: 12pt; border-color: black;")
        self.desc_explain.setReadOnly(True)

        desc_layout.addWidget(self.desc_title)
        desc_layout.addWidget(self.desc_explain)
        desc_layout.setStretchFactor(self.desc_title, 1)
        desc_layout.setStretchFactor(self.desc_explain, 9)
        description_box.setLayout(desc_layout)

        #
        # Start, Pause, Stop Buttons
        #
        start_stop_box = QGroupBox()
        start_stop_box.setContentsMargins(0, 0, 0, 0)
        start_stop_box.setObjectName("StartBox")
        start_box_layout = QGridLayout()

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

        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)

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

        #
        # Training Session Parameters
        #
        parameters_box = QGroupBox()
        parameters_box.setTitle("Collection Parameters")
        parameters_box.setObjectName("CollecParamBox")
        parameters_box.setStyleSheet(
            "QGroupBox#CollecParamBox { border: 1px solid gray; border-radius: 7px; margin-top: 0.5em;"
            "                              font-weight: bold; }"
            "QGroupBox#CollecParamBox::title { subcontrol-origin: margin; left: 9px; }")
        parameters_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top_param_layout = QGridLayout()

        rep_title = QLabel("Number of Repetitions")
        self.num_reps = QLineEdit("6")
        top_param_layout.addWidget(rep_title, 0, 0)
        top_param_layout.addWidget(self.num_reps, 0, 2, 1, 2)
        top_param_layout.setSpacing(0)

        collect_title = QLabel("(<b>Collect</b>\\<b>Rest</b>) Duration")
        self.collect_entry = QLineEdit("5.0")
        self.rest_entry = QLineEdit("3.0")
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

        #
        # Positions and sizes of all widgets in grid layout
        #
        top_layout.addWidget(self.status_label, 0, 0)
        top_layout.addWidget(self.progress_label, 0, 1)
        top_layout.addWidget(video_widget, 1, 0)
        top_layout.addWidget(description_box, 1, 1)
        top_layout.addWidget(start_stop_box, 2, 0)
        top_layout.addWidget(parameters_box, 2, 1)
        top_layout.setRowStretch(0, 7)
        top_layout.setRowStretch(1, 100)
        top_layout.setRowStretch(2, 10)
        top_layout.setColumnStretch(0, 66)
        top_layout.setColumnStretch(1, 33)

        #
        # Set widget to contain window contents
        #
        top_level_widget.setLayout(top_layout)
        self.video_player.setVideoOutput(video_widget)
        self.video_player.setMuted(True)

    def enable_video_buttons(self, state_play, state_pause, state_stop):
        """
            A helper function to set the current states of the play/pause/stop buttons.

        :param state_play: [bool] Enable/disable play button.
        :param state_pause: [bool] Enable/disable pause button.
        :param state_stop: [bool] Enable/disable stop button.
        :return:
        """
        self.play_button.setEnabled(state_play)
        self.pause_button.setEnabled(state_pause)
        self.stop_button.setEnabled(state_stop)

    def start_videos(self):
        """
            A function called when the "Start" button is pressed.
                > Either
                    i. Starts the background worker thread to play video, update text fields and more
                    ii. Unpauses the background worker, in order to continue doing the aforesaid.
        """

        # Disable play/pause/stop buttons until it is safe
        self.enable_video_buttons(False, False, False)

        # If any button click is still being processed
        if (self.unpausing) or (self.pausing) or (self.shutdown):
            return

        if self.playing:
            self.enable_video_buttons(False, True, True)
            return

        if self.worker is not None:
            self.worker.force_unpause()
            return

        #
        # Check for valid inputs
        #
        def throw_error_message(self, message):
            # Re-enable video buttons
            self.enable_video_buttons(True, False, False)

            # Display warning
            self.warning = QErrorMessage()
            self.warning.showMessage(message)
            self.warning.show()
            return None

        def acquire_var(self, text, widget_name, func):
            try:
                temp = func(text)
            except:
                # Re-enable video buttons
                self.enable_video_buttons(True, False, False)

                # Display warning
                if func == float:
                    return throw_error_message(self, "Please set a valid float for \"{}\".".format(widget_name))
                else:
                    return throw_error_message(self, "Please set a valid integer for \"{}\".".format(widget_name))
            return temp

        if ((acquire_var(self, self.collect_entry.text(), "Collect Duration", float) is None) or
                (acquire_var(self, self.collect_entry.text(), "Rest Duration", float) is None) or
                (acquire_var(self, self.num_reps.text(), "Number of Repetitions", int) is None)):
            return

        self.collect_duration = acquire_var(self, self.collect_entry.text(), "Collect Duration", float)
        self.rest_duration = acquire_var(self, self.rest_entry.text(), "Rest Duration", float)
        self.repetitions = acquire_var(self, self.num_reps.text(), "Rest Duration", int)

        if (not self.ex_a_check.isChecked()) and (not self.ex_b_check.isChecked()) and (
                not self.ex_c_check.isChecked()):
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
                # Re-enable video buttons
                self.enable_video_buttons(True, False, False)

                # Display warning
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
                                        self.collect_duration, self.rest_duration, self.repetitions,
                                        self.on_worker_started, self.on_worker_unpaused, self.on_worker_paused,
                                        self.on_worker_stopped)
        QThreadPool.globalInstance().start(self.worker)

    def on_worker_started(self):
        """
            This function is called when the background worker has started.
        """
        self.playing = True
        self.enable_video_buttons(False, True, True)

    def on_worker_unpaused(self):
        """
             This function is called when the background worker has unpaused.
         """
        self.playing = True
        self.enable_video_buttons(False, True, True)
        self.unpausing = False

    def on_worker_paused(self):
        """
            This function is called when the background worker has paused.
        """
        self.playing = False
        self.pausing = False
        self.enable_video_buttons(True, False, True)

    def on_worker_stopped(self):
        """
            This function is called when the background worker has finished execution of run().
        """
        self.playing = False
        self.shutdown = False
        self.worker = None

        # Update GUI appearance
        self.status_label.setText("Waiting to Start...")
        self.status_label.setStyleSheet(" font-weight: bold; font-size: 18pt; "
                                        "   color: red;")
        self.progress_label.setText("0.0s (1 / 1)")
        self.desc_title.setText("No Movement")
        self.desc_explain.setText("No description available.")
        self.current_movement.setText("")

        self.enable_video_buttons(True, False, False)

    def pause_videos(self):
        """
            This function is called when the user presses "Pause".
                > The background worker pauses the playback of video, and updating of text fields.
                > The ground truth labels also become invalid.
        """
        if (not self.playing) or (self.pausing) or (self.shutdown):
            return
        self.enable_video_buttons(False, False, False)
        self.pausing = True

        # Pause the background worker
        self.worker.force_pause()

    def stop_videos(self):
        """
            This function is called when the user presses "Stop".
                > The background worker finishes executing the run() function as a result of being "stopped".
        """
        if ((not self.playing) and (self.worker is None)) or (self.shutdown):
            return
        self.enable_video_buttons(False, False, False)
        self.shutdown = True

        # Force the background worker to leave run()
        self.worker.force_stop()

    def check_video_paths(self):
        """
            Determines if an exercise has all videos necessary for playback, upon pressing "Start".

        :return: [bool, bool, bool]

                > Where each bool determines if exercise A/B/C has all videos available.
        """

        exercises_found = [True, True, True]
        self.all_video_paths = [("A", []), ("B", []), ("C", [])]

        def create_exercise_paths(self, ex_label):
            ex_index = ord(ex_label) - ord('A')
            found_videos = True
            path_template = join(self.video_dir, self.video_path_template[ex_index][0])
            max_idx = self.video_path_template[ex_index][1]
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
    # Used for data logging, by TopLevel
    #
    def get_current_label(self):
        """
        :return: [int] Ground truth label for current movement
        """
        if (self.worker is None) or (not self.playing):
            return -1
        else:
            if self.worker.current_label is None:
                return -1
            else:
                return self.worker.current_label


########################################################################################################################
########################################################################################################################
########################################################################################################################
#
# Custom PyQt5 events (used by QRunnables)
#
########################################################################################################################
########################################################################################################################
########################################################################################################################

# MyoSearchWorker
class MyoSearch(QObject):
    searchComplete = pyqtSignal()


# Used by MyoDataWorker
class DataWorkerUpdate(QObject):
    axesUpdate = pyqtSignal()
    dataUpdate = pyqtSignal()
    workerStarted = pyqtSignal()
    workerStopped = pyqtSignal()
    connectFailed = pyqtSignal()
    disconOccurred = pyqtSignal()
    batteryUpdate = pyqtSignal([int])


# Used by GroundTruthWorker
class GTWorkerUpdate(QObject):
    workerStarted = pyqtSignal()
    workerUnpaused = pyqtSignal()
    workerPaused = pyqtSignal()
    workerStopped = pyqtSignal()


########################################################################################################################
########################################################################################################################
########################################################################################################################
#
# (DataTools) Background Workers
#
########################################################################################################################
########################################################################################################################
########################################################################################################################

class MyoDataWorker(QRunnable):
    """
        A background Qt thread that:
            1) Connects to a device (if possible)
            2) Establishes data to be received
            3) Collects data from a Myo armband device
            4) Passes data to MyoFoundWidget for plotting
            5) Optionally, disconnects on a second press, halting the receipt of data
    """

    def __init__(self, port, myo_device, series_list, indices_list, axes_callback, data_call_back, data_list,
                 on_worker_started, on_worker_stopped, on_connect_failed, on_discon_occurred, battery_notify,
                 create_event, get_current_label, data_tab_signals, is_data_tools_open):
        """
        :param port: Port used to create MyoFoundWidget widget.
        :param myo_device: Address of Myo device to interact with.
        :param series_list: A list of series that hold data, corresponding to the charts.
        :param indices_list: A list of sample indices, corresponding to the charts.
        :param axes_callback: Called when chart axes need an update.
        :param data_call_back: A function called on receipt of EMG data.
        :param data_list: A list of all data collected from this device.
        :param on_worker_started: A function called when this background worker starts.
        :param on_worker_stopped: A function called when this background worker exits run().
        :param on_connect_failed: A function called when this background worker fails to connect to a Myo device.
        :param on_discon_occurred: A function called when the corresponding Myo device disconnects unexpectedly.
        :param battery_notify: A function called on receipt of battery level update.
        :param create_event: A function that determines whether to push data updates, based on open tabs.
        :param get_current_label: A function that returns the current ground truth label being collected.
        """
        super().__init__()
        self.port = port
        self.myo_device = myo_device
        self.series_list = series_list
        self.indices_list = indices_list
        self.data_list = data_list
        self.update = DataWorkerUpdate()
        self.create_event = create_event
        self.get_current_label = get_current_label
        self.data_tab_signals = data_tab_signals
        self.is_data_tools_open = is_data_tools_open

        # Signals
        self.update.axesUpdate.connect(axes_callback)
        self.update.dataUpdate.connect(data_call_back)
        self.update.workerStarted.connect(on_worker_started)
        self.update.workerStopped.connect(on_worker_stopped)
        self.update.connectFailed.connect(on_connect_failed)
        self.update.disconOccurred.connect(on_discon_occurred)
        self.update.batteryUpdate.connect(battery_notify)

        # Configurable parameters
        self.scan_period = 0.2  # seconds
        self.update_period = 4
        self.emg_sample_rate = 200  # 200 hz

        # States
        self.running = False
        self.samples_count = 0
        self.complete = False

        # Timestamp states
        self.reset_period = 200
        self.cur_sample = 0
        self.base_time = None

    def run(self):
        # State setup
        self.dongle = MyoDongle(self.port)
        self.running = True
        self.complete = False
        self.update.workerStarted.emit()

        # Connect
        self.dongle.clear_state()
        connect_success = self.dongle.connect(self.myo_device)
        if not connect_success:
            self.update.connectFailed.emit()
            return

        # Attempt to update battery level
        level = self.dongle.read_battery_level()
        if not (level is None):
            self.update.batteryUpdate.emit(level)
        self.data_tab_signals.connectUpdate.emit(self.myo_device["sender_address"], self.myo_device["rssi"], level)

        # Enable IMU/EMG readings and callback functions
        self.dongle.set_sleep_mode(False)
        self.dongle.enable_imu_readings()
        self.dongle.enable_emg_readings()
        self.dongle.add_joint_emg_imu_handler(self.create_emg_event)

        disconnect_occurred = False
        while self.running and (not disconnect_occurred):
            disconnect_occurred = self.dongle.scan_for_data_packets_conditional(self.scan_period)

        self.data_tab_signals.disconnectUpdate.emit(self.myo_device["sender_address"])
        if disconnect_occurred:
            self.dongle.clear_state()
            self.update.disconOccurred.emit()
        else:
            self.dongle.clear_state()
            self.update.workerStopped.emit()

        self.complete = True

    def create_emg_event(self, emg_list, orient_w, orient_x, orient_y, orient_z,
                         accel_1, accel_2, accel_3, gyro_1, gyro_2, gyro_3, sample_num):
        """
            On receipt of a data packet from a Myo device, triggered by "scan_for_data_packets", this function is
            called.
        :param emg_list: A list of 8 EMG readings.
        :param orient_w/x/y/z: Magnetometer readings, corresponding to a unit quaternion.
        :param accel_1/2/3: Accelerometer readings.
        :param gyro_1/2/3: Gyroscope readings.
        :param sample_num: [int] 1/2 : Sample 1 or 2 (data is sent in pairs)
        """

        if self.running:

            if self.cur_sample % self.reset_period == 0:
                self.base_time = time.time()
                self.cur_sample = 0

            time_received = self.base_time + self.cur_sample * (1 / self.emg_sample_rate)
            self.cur_sample += 1

            # Is this tab corresponding to this worker open
            create_events   = self.create_event()
            create_events  &= self.is_data_tools_open()

            # Request an axes update for the charts
            if (self.samples_count != 0) and (self.samples_count % NUM_GUI_SAMPLES == 0):
                self.start_range = self.samples_count
                for i in range(len(self.series_list)):
                    self.series_list[i].clear()
                    # self.series_list[i].removePoints(0, NUM_GUI_SAMPLES-1)
                self.indices_list.clear()

                if create_events:
                    self.update.axesUpdate.emit()

            # Update chart data
            for i in range(len(self.series_list)):
                # self.series_list[i].append(self.samples_count, emg_list[i])
                self.series_list[i].append(emg_list[i])
            self.indices_list.append(self.samples_count)

            if create_events:
                if self.samples_count % self.update_period == 0:
                    self.update.dataUpdate.emit()

            # Accelerometer values are multipled by the following constant (and are in units of g)
            MYOHW_ACCELEROMETER_SCALE = 2048.0

            # Gyroscope values are multipled by the following constant (and are in units of deg/s)
            MYOHW_GYROSCOPE_SCALE = 16.0

            # Orientation values are multipled by the following constant (units of a unit quaternion)
            MYOHW_ORIENTATION_SCALE = 16384.0

            #
            # Update list of all data collected (with correct rescaling)
            #
            current_label = self.get_current_label()  # Grabbed from GT Helper

            self.data_list.append((time_received, self.samples_count, emg_list,
                                   [orient_w / MYOHW_ORIENTATION_SCALE, orient_x / MYOHW_ORIENTATION_SCALE,
                                    orient_y / MYOHW_ORIENTATION_SCALE, orient_z / MYOHW_ORIENTATION_SCALE],
                                   [accel_1 / MYOHW_ACCELEROMETER_SCALE, accel_2 / MYOHW_ACCELEROMETER_SCALE,
                                    accel_3 / MYOHW_ACCELEROMETER_SCALE],
                                   [gyro_1 / MYOHW_GYROSCOPE_SCALE, gyro_2 / MYOHW_GYROSCOPE_SCALE,
                                    gyro_3 / MYOHW_GYROSCOPE_SCALE],
                                   current_label))

            # Update list of all data collected (without scaling)
            #
            # self.data_list.append((time.time(), self.samples_count, emg_list, [orient_w, orient_x, orient_y, orient_z],
            #                       [accel_1, accel_2, accel_3],
            #                       [gyro_1, gyro_2, gyro_3]))
            self.samples_count += 1


class MyoSearchWorker(QRunnable):
    """
        A background Qt thread that:
            1) Searches for Myo devices
            2) Updates a progress bar
            3) Emits an event upon completion
    """

    def __init__(self, cur_port, progress_bar, finished_callback, increments):
        """
        :param cur_port: A communication port to search for Myo devices on.
        :param progress_bar: A progress bar to update.
        :param finished_callback: A callback function, called after searching is complete.
        :param increments: Number of increments to progress bar.
        """
        super().__init__()
        self.cur_port = cur_port
        self.progress_bar = progress_bar
        self.finish = MyoSearch()
        self.finish.searchComplete.connect(finished_callback)

        # States
        self.complete = False
        self.running = False

        #
        # Configurable
        #
        self.increments = increments  # Progress bar increments
        self.time_to_search = 3  # In seconds
        self.currrent_increment = 0

    def run(self):
        self.complete = False
        self.running = True

        while self.currrent_increment <= self.increments:

            if self.currrent_increment == 0:
                self.myo_dongle = MyoDongle(self.cur_port)
                self.myo_dongle.clear_state()
                self.myo_found = []

                # Create a (Python) background thread to perform the scanning of packets
                def helper_func():
                    self.myo_found.extend(self.myo_dongle.discover_myo_devices(self.time_to_search))

                self.background_thread = threading.Thread(target=helper_func)
                self.background_thread.start()

            self.currrent_increment += 1

            # Done searching!
            if self.currrent_increment > self.increments:
                self.background_thread.join()  # Wait for work completion

                if self.running:
                    self.finish.searchComplete.emit()

            else:
                # Inter-thread communication (GUI thread will make the call to update the progress bar):
                QMetaObject.invokeMethod(self.progress_bar, "setValue",
                                         Qt.QueuedConnection, Q_ARG(int, self.currrent_increment))
                time.sleep(self.time_to_search / self.increments)

        # Clear Myo device states and disconnect
        self.myo_dongle.clear_state()
        self.complete = True
        self.running = False
        QMetaObject.invokeMethod(self.progress_bar, "close", Qt.QueuedConnection)


class GroundTruthWorker(QRunnable):
    """
        A background worker that controls playback of videos and text field updates, for the GT Helper.
    """

    def __init__(self, status_label, progress_label, desc_title, desc_explain, cur_movement, video_player,
                 all_video_paths, collect_duration, rest_duration, num_reps, on_worker_started, on_worker_unpaused,
                 on_worker_paused, on_worker_stopped):
        """
        :param status_label: A QLabel displaying a message of what the GT Helper is currently performing.
        :param progress_label:  A QLabel displaying the current progress of data collection.
        :param desc_title: A QLabel displaying the name of current movement.
        :param desc_explain: A QLabel describing how to perform the current movement.
        :param cur_movement: A QLabel displaying the current exercise and movement number.
        :param video_player: A QMediaPlayer, to show videos of gestures performed.
        :param all_video_paths: An object containing paths to all selected videos (based on exercises checked off).
        :param collect_duration: Duration of gesture data collection.
        :param rest_duration: Duration of rest data collection.
        :param num_reps: Number of repetitions to be performed per movement.
        :param on_worker_started: A callback function used once this background worker has started.
        :param on_worker_unpaused: A callback function used once this background worker has unpaused.
        :param on_worker_paused: A callback function used once this background worker has paused.
        :param on_worker_stopped: A callback function used once this background worker has stopped.
        """
        super().__init__()

        self.status_label = status_label
        self.progress_label = progress_label
        self.desc_title = desc_title
        self.desc_explain = desc_explain
        self.cur_movement = cur_movement
        self.video_player = video_player
        self.all_video_paths = all_video_paths
        self.collect_duration = collect_duration
        self.rest_duration = rest_duration
        self.num_reps = num_reps

        self.num_class_A = 12
        self.num_class_B = 17

        # Signals
        self.update = GTWorkerUpdate()
        self.update.workerStarted.connect(on_worker_started)
        self.update.workerUnpaused.connect(on_worker_unpaused)
        self.update.workerPaused.connect(on_worker_paused)
        self.update.workerStopped.connect(on_worker_stopped)

        # Used to update time remaining
        self.timer = QTimer()
        self.timer.timeout.connect(self.timer_update)
        self.timer_interval = 100  # units of ms
        self.state_end_event = self.StateComplete()
        self.state_end_event.stateEnded.connect(self.stop_state)

        # On video load or video completion, this is triggered
        self.video_player.mediaStatusChanged.connect(self.media_status_changed)

        # Configurable parameters
        self.preparation_period = 20.0

        # State variables
        self.current_rep = 0
        self.state_time_remain = 0  # seconds
        self.video_playing = False
        self.stopped = False
        self.paused = False
        self.current_label = None
        self.complete = False

    # On finish of repetition/rest/prepation
    class StateComplete(QObject):
        stateEnded = pyqtSignal()

    # Qt5, QMediaPlayer enum
    # > "Defines the status of a media player's current media."
    class MediaStatus(Enum):
        UnknownMediaStatus = 0
        NoMedia = 1
        LoadingMedia = 2
        LoadedMedia = 3
        StalledMedia = 4
        BufferingMedia = 5
        BufferedMedia = 6
        EndOfMedia = 7
        InvalidMedia = 8

    def run(self):

        # Re-enable video buttons
        self.complete = False
        self.update.workerStarted.emit()

        for exercise in self.all_video_paths:

            if self.stopped:
                break

            ex_label = exercise[0]
            video_paths = exercise[1]

            for movement_num, video_path in enumerate(video_paths):

                if self.stopped:
                    break
                #
                # Setup for current movement
                #
                self.current_rep = 0
                QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                            Q_ARG(str, "{} s ({}/{})".format(self.preparation_period, self.current_rep,
                                                                                self.num_reps)))
                QMetaObject.invokeMethod(self.cur_movement, "setText", Qt.QueuedConnection,
                                            Q_ARG(str, "Exercise {} - Movement {} of {}".format(ex_label, movement_num + 1,
                                                                                   len(video_paths))
                                                )
                                         )

                current_description = MOVEMENT_DESC[ex_label][movement_num + 1]
                QMetaObject.invokeMethod(self.desc_title, "setText", Qt.QueuedConnection,
                                            Q_ARG(str, current_description[0]))
                QMetaObject.invokeMethod(self.desc_explain, "setText",
                                         Qt.QueuedConnection, Q_ARG(str, current_description[1]))

                #
                # Preparation period
                #
                QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                         Q_ARG(str, "Preparing for repetition 1..." ))
                QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                         Q_ARG(str, "font-weight: bold; font-size: 18pt; color: blue;"))
                self.play_video(video_path, self.preparation_period)
                self.current_label = None

                while self.video_playing or (self.paused and not self.stopped):
                    time.sleep(self.timer_interval / 1000)

                if self.stopped:
                    break

                #
                # Collecting\resting periods
                #
                for i in range(self.num_reps):

                    # Collect
                    self.current_rep = i + 1
                    QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                             Q_ARG(str, "Collecting for repetition {}...".format(self.current_rep)))
                    QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                             Q_ARG(str, "font-weight: bold; font-size: 18pt; color: green;"))
                    self.play_video(video_path, self.collect_duration)
                    self.set_current_label(ex_label, movement_num + 1)

                    while self.video_playing or (self.paused and not self.stopped):
                        time.sleep(self.timer_interval / 1000)

                    if self.stopped:
                        break

                    # Rest
                    if self.current_rep != self.num_reps:
                        QMetaObject.invokeMethod(self.status_label, "setText", Qt.QueuedConnection,
                                                    Q_ARG(str, "Resting before repetition {}...".format(self.current_rep + 1)))
                        QMetaObject.invokeMethod(self.status_label, "setStyleSheet", Qt.QueuedConnection,
                                                 Q_ARG(str, "font-weight: bold; font-size: 18pt; color: orange;"))
                        self.play_video(video_path, self.rest_duration)
                        self.current_label = 0

                        while self.video_playing or (self.paused and not self.stopped):
                            time.sleep(self.timer_interval / 1000)
                    else:
                        self.current_label = None

                    if self.stopped:
                        break

        #
        # If user pressed stop
        #
        if self.stopped:
            self.update.workerStopped.emit()
        self.complete = True

    def play_video(self, video_path, period):
        """
            Prepare video for playback, media_status_changed is called when loading finishes.

        :param video_path: Path to video
        :param period: Time to play video
        """
        self.video_playing = True
        self.state_time_remain = period
        abs_path = QFileInfo(video_path).absoluteFilePath()
        QMetaObject.invokeMethod(self.video_player, "setMedia", Qt.QueuedConnection,
                                 Q_ARG(QMediaContent, QMediaContent(QUrl.fromLocalFile(abs_path))))

    def media_status_changed(self, state):
        """
            This function is called when the media player's media finishes loading/playing/etc.
        :param state: State corresponding to media player update
        """
        if state == self.MediaStatus.LoadedMedia.value:
            QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)
            self.timer.start(self.timer_interval)
        elif state == self.MediaStatus.EndOfMedia.value:
            if self.state_time_remain > self.timer_interval / 1000:
                QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)

    def timer_update(self):
        """
            This function is called every "self.timer_interval" seconds, upon timer completion.
        """
        self.state_time_remain = max(0, self.state_time_remain - self.timer_interval / 1000)

        QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                 Q_ARG(str, "{}s ({} / {})".format("{0:.1f}".format(self.state_time_remain),
                                                           self.current_rep, self.num_reps)))

        if self.state_time_remain == 0:
            self.timer.stop()
            self.state_end_event.stateEnded.emit()

    def set_current_label(self, ex_label, movement_num):
        """
            Computes the ground truth label
        :param ex_label: [str] Exercise "A/B/C"
        :param movement_num: [int] Movement number
        """
        if ex_label == "A":
            self.current_label = movement_num
        elif ex_label == "B":
            self.current_label = movement_num + self.num_class_A
        else:
            self.current_label = movement_num + self.num_class_A + self.num_class_B

    def stop_state(self):
        """
            Upon completion of a repetition/rest/prepation state, this function is called.
        """

        QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)
        self.video_playing = False

    def force_stop(self):
        """
            GroundTruthHelper calls this function to stop this background worker thread.
        """
        self.timer.stop()
        QMetaObject.invokeMethod(self.video_player, "stop", Qt.QueuedConnection)
        self.video_playing = False
        self.stopped = True

    def force_pause(self):
        """
            GroundTruthHelper calls this function to pause this background worker thread.
        """
        self.timer.stop()
        QMetaObject.invokeMethod(self.video_player, "pause", Qt.QueuedConnection)
        self.paused = True

        # Re-enable video buttons
        self.update.workerPaused.emit()

    def force_unpause(self):
        """
            GroundTruthHelper calls this function to unpause this background worker thread.
        """
        self.timer.start(self.timer_interval)
        QMetaObject.invokeMethod(self.video_player, "play", Qt.QueuedConnection)
        self.paused = False

        # Re-enable video buttons
        self.update.workerUnpaused.emit()
