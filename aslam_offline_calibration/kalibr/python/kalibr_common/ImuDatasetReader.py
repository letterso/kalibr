import sm
import numpy as np
import aslam_cv as acv

from .RosbagDatasetReader import RosbagTopicReader
from .RosbagDatasetReader import read_imu_message


class BagImuDatasetReaderIterator(object):
    def __init__(self,dataset,indices=None):
        self.dataset = dataset
        if indices is None:
            self.indices = np.arange(dataset.numMessages())
        else:
            self.indices = indices
        self.iter = self.indices.__iter__()
    def __iter__(self):
        return self
    def next(self):
        # required for python 2.x compatibility
        idx = next(self.iter)
        return self.dataset.getMessage(idx)
    def __next__(self):
        idx = next(self.iter)
        return self.dataset.getMessage(idx)


class BagImuDatasetReader(object):
    def __init__(self, bagfile, imutopic, bag_from_to=None, perform_synchronization=False):
        self.bagfile = bagfile
        self.topic = imutopic
        self.perform_synchronization = perform_synchronization
        self.timestamp_corrector = sm.DoubleTimestampCorrector()
        self.reader = RosbagTopicReader(
            bagfile,
            imutopic,
            perform_synchronization=perform_synchronization,
            timestamp_corrector=self.timestamp_corrector,
        )
        self.index = self.reader.index
        self.indices = self.reader.indices

        if bag_from_to:
            self.indices = self.truncateIndicesFromTime(self.indices, bag_from_to)

    def sortByTime(self, indices):
        return sorted(indices, key=lambda idx: self.index[idx].header_time_nsec)

    def truncateIndicesFromTime(self, indices, bag_from_to):
        valid_indices = self.reader.truncate_indices_from_time(indices, bag_from_to, sm.logWarn)
        sm.logWarn("BagImuDatasetReader: truncated {0} / {1} messages.".format(len(indices)-len(valid_indices), len(indices)))
        return valid_indices

    def __iter__(self):
        return self.readDataset()

    def readDataset(self):
        return BagImuDatasetReaderIterator(self, self.indices)

    def readDatasetShuffle(self):
        indices = self.indices
        np.random.shuffle(indices)
        return BagImuDatasetReaderIterator(self,indices)

    def numMessages(self):
        return len(self.indices)

    def getMessage(self,idx):
        timestamp = self.reader.timestamp_for_record(idx, acv.Time)
        omega, alpha = read_imu_message(self.reader.message(idx))
        return (timestamp, omega, alpha)
