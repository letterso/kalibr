import numpy as np
import aslam_cv as acv
import sm

from .RosbagDatasetReader import RosbagTopicReader
from .RosbagDatasetReader import decode_image_message


class BagImageDatasetReaderIterator(object):
  def __init__(self, dataset, indices=None):
    self.dataset = dataset
    if indices is None:
      self.indices = np.arange(dataset.numImages())
    else:
      self.indices = indices
    self.iter = self.indices.__iter__()

  def __iter__(self):
    return self

  def next(self):
    # required for python 2.x compatibility
    idx = next(self.iter)
    return self.dataset.getImage(idx)

  def __next__(self):
    idx = next(self.iter)
    return self.dataset.getImage(idx)


class BagImageDatasetReader(object):
  def __init__(self, bagfile, imagetopic, bag_from_to=None, perform_synchronization=False, bag_freq=None):
    self.bagfile = bagfile
    self.topic = imagetopic
    self.perform_synchronization = perform_synchronization
    self.timestamp_corrector = sm.DoubleTimestampCorrector()
    self.reader = RosbagTopicReader(
      bagfile,
      imagetopic,
      perform_synchronization=perform_synchronization,
      timestamp_corrector=self.timestamp_corrector,
    )
    self.index = self.reader.index
    self.indices = self.reader.indices

    if bag_from_to:
      self.indices = self.truncateIndicesFromTime(self.indices, bag_from_to)

    if bag_freq:
      self.indices = self.truncateIndicesFromFreq(self.indices, bag_freq)

  def sortByTime(self, indices):
    return sorted(indices, key=lambda idx: self.index[idx].header_time_nsec)

  def truncateIndicesFromTime(self, indices, bag_from_to):
    valid_indices = self.reader.truncate_indices_from_time(indices, bag_from_to, sm.logWarn)
    sm.logWarn(
        "BagImageDatasetReader: truncated {0} / {1} images (from-to).".format(len(indices) - len(valid_indices), len(indices)))
    return valid_indices

  def truncateIndicesFromFreq(self, indices, freq):
    if freq < 0.0:
      raise RuntimeError("Frequency {0} Hz is smaller 0".format(freq))

    timestamp_last = -1
    valid_indices = []
    for idx in indices:
      timestamp = self.index[idx].header_time_nsec / 1.0e9
      if timestamp_last < 0.0:
        timestamp_last = timestamp
        valid_indices.append(idx)
        continue
      if (timestamp - timestamp_last) >= 1.0 / freq:
        timestamp_last = timestamp
        valid_indices.append(idx)
    sm.logWarn(
      "BagImageDatasetReader: truncated {0} / {1} images (frequency)".format(len(indices) - len(valid_indices), len(indices)))
    return valid_indices

  def __iter__(self):
    return self.readDataset()

  def readDataset(self):
    return BagImageDatasetReaderIterator(self, self.indices)

  def readDatasetShuffle(self):
    indices = self.indices
    np.random.shuffle(indices)
    return BagImageDatasetReaderIterator(self, indices)

  def numImages(self):
    return len(self.indices)

  def getImage(self, idx):
    timestamp = self.reader.timestamp_for_record(idx, acv.Time)
    img_data = decode_image_message(self.reader.message(idx))
    return (timestamp, img_data)
