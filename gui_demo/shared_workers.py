#
# PyQt5 imports
#
from PyQt5.QtCore import (Qt, QRunnable, QMetaObject, Q_ARG, QObject, pyqtSignal)

#
# Imports for online prediction tasks
#
from scipy.signal import butter, lfilter
import numpy as np

try:
    import cPickle as pickle
except:
    import pickle

#
# Miscellaneous imports
#
import time

#
# Submodules in this repository
#
from movements import *
from param import *


########################################################################################################################
########################################################################################################################
########################################################################################################################
#
# Custom PyQt5 events (used by QRunnables)
#
########################################################################################################################
########################################################################################################################
########################################################################################################################

# Used by NoiseCollectionWorker
class NoiseUpdates(QObject):
    workerStarted   = pyqtSignal()
    collectComplete = pyqtSignal()
    modelReady      = pyqtSignal()

########################################################################################################################
########################################################################################################################
########################################################################################################################

class NoiseCollectionWorker(QRunnable):
    """
        Collects noise data, processes it, and creates a noise model, used by signal detection.
    """

    def __init__(self, myo_data, noise_duration, noise_increments, progress_bar, progress_label, on_worker_started,
                        on_collect_complete, on_model_ready):
        """
        :param myo_data: A MyoData object, holding all data collected from both Myo armbands
        :param noise_duration: The duration to collect noise data for
        :param noise_increments: How many increments for the noise collection progress bar
        :param progress_bar: The noise collection progress bar
        :param progress_label: A QLineEdit text field, containing the remaining amount of time
        :param on_worker_started: A function called on the start of noise data collection
        :param on_collect_complete: A function called on completion of noise data collection
        :param on_model_ready: A function called on completion of noise model creation
        """
        super().__init__()

        self.myo_data           = myo_data
        self.noise_duration     = noise_duration
        self.noise_increments   = noise_increments
        self.progress_bar       = progress_bar
        self.progress_label     = progress_label

        # Configurable
        self.buffer_time    = 1     # Add a buffer to account for startup of this background thread

        # States
        self.start_time         = time.time() + self.buffer_time
        self.currrent_increment = 0

        self.worker_updates = NoiseUpdates()
        self.worker_updates.workerStarted.connect(on_worker_started)
        self.worker_updates.collectComplete.connect(on_collect_complete)
        self.worker_updates.modelReady.connect(on_model_ready)

        # To be filled via run()
        self.smooth_avg = None
        self.smooth_std = None
        self.noise_mean = None
        self.noise_cov  = None

    def run(self):
        #
        # Wait for data collection to finish
        #
        time.sleep(self.buffer_time)
        while (time.time() - self.start_time) < self.noise_duration:
            QMetaObject.invokeMethod(self.progress_bar, "setValue", Qt.QueuedConnection,
                                     Q_ARG(int, self.currrent_increment))


            time_remaining = "{0:.1f}".format(self.noise_duration - (time.time() - self.start_time)) + " s"
            QMetaObject.invokeMethod(self.progress_label, "setText", Qt.QueuedConnection,
                                     Q_ARG(str, time_remaining))

            time.sleep(self.noise_duration / self.noise_increments)
            self.currrent_increment += 1

        end_time = time.time()
        self.worker_updates.collectComplete.emit()

        #
        # Extract data in time window
        #
        first_myo_data  = self.myo_data.band_1
        second_myo_data = self.myo_data.band_2
        data_mapping    = self.myo_data.data_mapping

        # Find start/end indices of first dataset
        first_data_indices  = [None, None]
        default_final       = len(first_myo_data.timestamps)

        for i, data_time in enumerate(first_myo_data.timestamps):
            if first_data_indices[0] is None:
                if data_time > self.start_time:
                    first_data_indices[0] = i
            if first_data_indices[1] is None:
                if data_time > end_time:
                    first_data_indices[1] = i
                    break

        if first_data_indices[1] is None:
            first_data_indices[1] = default_final

        noise_samples = []
        for first_idx in range(first_data_indices[0], first_data_indices[1]):
            if ((data_mapping[first_idx] != self.myo_data.invalid_map) and
                    (data_mapping[first_idx] < len(second_myo_data.timestamps))):
                first_emg   = [x[first_idx] for x in first_myo_data.emg]
                sec_idx     = data_mapping[first_idx]
                second_emg  = [x[sec_idx] for x in second_myo_data.emg]
                noise_samples.append(first_emg + second_emg)

        #
        # Fit a noise model
        #
        noise_samples   = np.array(noise_samples)
        self.noise_mean = np.mean(noise_samples, axis=0)
        self.noise_cov  = np.cov(noise_samples, rowvar=False)

        # Apply sixth-order digital butterworth lowpass filter with 50 Hz cutoff frequency to rectified signal (first)
        fs              = 200
        nyquist         = 0.5 * fs
        cutoff          = 50
        order           = 6
        b, a            = butter(order, cutoff / nyquist, btype='lowpass')
        noise_samples   = np.abs(noise_samples)
        filt_data       = lfilter(b, a, noise_samples, axis=0)

        self.smooth_avg  = np.mean(filt_data, axis=0)
        self.smooth_std  = np.std(filt_data, axis=0)

        self.worker_updates.modelReady.emit()

