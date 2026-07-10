from __future__ import print_function

import os
from collections import namedtuple

import cv2
import numpy as np

NSEC_PER_SEC = 1000000000
_MAX_PENDING_MESSAGES = 4


def _stamp_to_nsec(stamp):
    sec = getattr(stamp, "sec", getattr(stamp, "secs", 0))
    nsec = getattr(stamp, "nanosec", getattr(stamp, "nsec", getattr(stamp, "nsecs", 0)))
    return int(sec) * NSEC_PER_SEC + int(nsec)


def _nsec_to_sec_nsec(timestamp_nsec):
    return int(timestamp_nsec // NSEC_PER_SEC), int(timestamp_nsec % NSEC_PER_SEC)


def _message_type(msg):
    return getattr(msg, "__msgtype__", getattr(msg, "_type", ""))


def _normalize_msgtype(msgtype):
    return msgtype.replace("/msg/", "/")


RosbagMessageRecord = namedtuple(
    "RosbagMessageRecord", ["header_time_nsec", "receive_time_nsec", "locator"]
)


def _correct_timestamp(timestamp_corrector, header_time_nsec, receive_time_nsec):
    if timestamp_corrector is not None:
        timestamp_corrector.correctTimestamp(header_time_nsec / 1.0e9, receive_time_nsec / 1.0e9)


class _NativeRosbagTopicReader(object):
    def __init__(self, rosbag_module, bagfile, topic, timestamp_corrector):
        self.bagfile = bagfile
        self.topic = topic
        self.timestamp_corrector = timestamp_corrector
        self.bag = rosbag_module.Bag(bagfile)

        try:
            connections = list(self.bag._get_connections(topics=topic))
            if not connections:
                raise RuntimeError("Could not find topic {0} in {1}.".format(topic, bagfile))

            records = []
            for connection_index in self.bag._get_indexes(connections):
                for entry in connection_index:
                    _, msg, receive_stamp = self.bag._read_message(entry.position)
                    if not hasattr(msg, "header"):
                        raise RuntimeError(
                            "Message on topic {0} has no header timestamp.".format(topic)
                        )
                    header_time_nsec = _stamp_to_nsec(msg.header.stamp)
                    receive_time_nsec = _stamp_to_nsec(receive_stamp)
                    _correct_timestamp(timestamp_corrector, header_time_nsec, receive_time_nsec)
                    records.append(
                        RosbagMessageRecord(header_time_nsec, receive_time_nsec, entry.position)
                    )

            if not records:
                raise RuntimeError("Could not find topic {0} in {1}.".format(topic, bagfile))
            self.index = sorted(records, key=lambda record: record.header_time_nsec)
        except Exception:
            self.close()
            raise

    def message(self, record):
        return self.bag._read_message(record.locator)[1]

    def close(self):
        if self.bag is not None:
            self.bag.close()
            self.bag = None


class _RosbagsTopicReader(object):
    def __init__(self, bagfile, topic, timestamp_corrector):
        try:
            from pathlib import Path

            from rosbags.highlevel import AnyReader
            from rosbags.typesys import Stores, get_typestore
        except ImportError:
            raise RuntimeError(
                "Reading {0} requires either ROS1 rosbag or the standalone "
                "rosbags dependency.".format(bagfile)
            )

        bagpath = Path(bagfile)
        store = Stores.ROS1_NOETIC if bagpath.suffix == ".bag" else Stores.LATEST
        self.bagpath = bagpath
        self._reader_type = AnyReader
        self._default_typestore = get_typestore(store)
        self.reader = AnyReader([bagpath], default_typestore=self._default_typestore)
        self.connections = []
        self._message_stream = None
        self._stream_order = 0
        self._stream_occurrences = {}
        self._pending_messages = {}
        self._ros1_reader = None

        try:
            self.reader.open()
            self.connections = [
                connection for connection in self.reader.connections if connection.topic == topic
            ]
            if not self.connections:
                raise RuntimeError("Could not find topic {0} in {1}.".format(topic, bagfile))

            if not self.reader.is2:
                self._ros1_reader = self.reader.readers[0]
            connection_indices = {
                connection.id: idx for idx, connection in enumerate(self.connections)
            }
            ros1_entry_offsets = {}
            receive_occurrences = {}
            records = []
            for connection, receive_time_nsec, rawdata in self.reader.messages(
                connections=self.connections
            ):
                msg = self.reader.deserialize(rawdata, connection.msgtype)
                if not hasattr(msg, "header"):
                    raise RuntimeError(
                        "Message on topic {0} has no header timestamp.".format(topic)
                    )
                header_time_nsec = _stamp_to_nsec(msg.header.stamp)
                occurrence = receive_occurrences.get(receive_time_nsec, 0)
                receive_occurrences[receive_time_nsec] = occurrence + 1
                ros1_locator = None
                if self._ros1_reader is not None:
                    entry_offset = ros1_entry_offsets.get(connection.id, 0)
                    ros1_entry_offsets[connection.id] = entry_offset + 1
                    ros1_locator = (
                        connection_indices[connection.id],
                        self._ros1_reader.indexes[connection.id][entry_offset],
                    )
                _correct_timestamp(timestamp_corrector, header_time_nsec, receive_time_nsec)
                records.append(
                    RosbagMessageRecord(
                        header_time_nsec,
                        receive_time_nsec,
                        (occurrence, len(records), ros1_locator),
                    )
                )

            if not records:
                raise RuntimeError("Could not find topic {0} in {1}.".format(topic, bagfile))
            self.index = sorted(records, key=lambda record: record.header_time_nsec)
        except Exception:
            self.close()
            raise

    def message(self, record):
        expected_occurrence, expected_order = record.locator[:2]
        identity = (record.receive_time_nsec, expected_occurrence)
        if identity in self._pending_messages:
            connection, rawdata = self._pending_messages.pop(identity)
            return self.reader.deserialize(rawdata, connection.msgtype)

        if (
            expected_order < self._stream_order
            or expected_order - self._stream_order > _MAX_PENDING_MESSAGES
        ):
            return self._read_direct(record)

        if self._message_stream is None:
            self._message_stream = iter(self.reader.messages(connections=self.connections))

        while True:
            try:
                connection, receive_time_nsec, rawdata = next(self._message_stream)
            except StopIteration:
                return self._read_direct(record)

            occurrence = self._stream_occurrences.get(receive_time_nsec, 0)
            self._stream_occurrences[receive_time_nsec] = occurrence + 1
            current_identity = (receive_time_nsec, occurrence)
            self._stream_order += 1
            if current_identity == identity:
                return self.reader.deserialize(rawdata, connection.msgtype)
            self._pending_messages[current_identity] = (connection, rawdata)
            if self._stream_order > expected_order:
                return self._read_direct(record)

    def _read_direct(self, record):
        expected_occurrence = record.locator[0]
        if self._ros1_reader is not None:
            return self._read_ros1_entry(record)

        with self._reader_type([self.bagpath], default_typestore=self._default_typestore) as reader:
            connections = [
                connection
                for connection in reader.connections
                if connection.topic == self.connections[0].topic
            ]
            messages = reader.messages(
                connections=connections,
                start=record.receive_time_nsec,
                stop=record.receive_time_nsec + 1,
            )
            for occurrence, (actual_connection, _, rawdata) in enumerate(messages):
                if occurrence == expected_occurrence:
                    return reader.deserialize(rawdata, actual_connection.msgtype)
        raise RuntimeError(
            "Could not read indexed message on topic {0} at {1} ns.".format(
                self.connections[0].topic, record.receive_time_nsec
            )
        )

    def _read_ros1_entry(self, record):
        connection_idx, entry = record.locator[2]
        connection = self.connections[connection_idx]
        original_index = self._ros1_reader.indexes[connection.id]
        self._ros1_reader.indexes[connection.id] = [entry]
        try:
            actual_connection, receive_time_nsec, rawdata = next(
                self._ros1_reader.messages(connections=[connection])
            )
        finally:
            self._ros1_reader.indexes[connection.id] = original_index

        if receive_time_nsec != record.receive_time_nsec:
            raise RuntimeError(
                "Indexed message time changed from {0} to {1} ns.".format(
                    record.receive_time_nsec, receive_time_nsec
                )
            )
        return self.reader.deserialize(rawdata, actual_connection.msgtype)

    def close(self):
        if self.reader is not None:
            if self._message_stream is not None:
                close_stream = getattr(self._message_stream, "close", None)
                if close_stream is not None:
                    close_stream()
                self._message_stream = None
            self._pending_messages.clear()
            if getattr(self.reader, "isopen", False):
                self.reader.close()
            self.reader = None


class RosbagTopicReader(object):
    def __init__(self, bagfile, topic, perform_synchronization=False, timestamp_corrector=None):
        if topic is None:
            raise RuntimeError(
                "Please pass in a topic name referring to the stream in the bag file\n{0}".format(
                    bagfile
                )
            )

        self.bagfile = bagfile
        self.topic = topic
        self.perform_synchronization = perform_synchronization
        self.timestamp_corrector = timestamp_corrector
        self._reader = self._open_backend()
        self.index = self._reader.index
        self.indices = np.arange(len(self.index))

    def _open_backend(self):
        if os.path.splitext(self.bagfile)[1].lower() == ".bag":
            try:
                import rosbag
            except ImportError:
                rosbag = None
            if rosbag is not None:
                return _NativeRosbagTopicReader(
                    rosbag,
                    self.bagfile,
                    self.topic,
                    self.timestamp_corrector if self.perform_synchronization else None,
                )

        return _RosbagsTopicReader(
            self.bagfile,
            self.topic,
            self.timestamp_corrector if self.perform_synchronization else None,
        )

    def truncate_indices_from_time(self, indices, bag_from_to, log_warn):
        timestamps = [self.index[idx].header_time_nsec / 1.0e9 for idx in indices]
        bagstart = min(timestamps)
        baglength = max(timestamps) - bagstart

        if bag_from_to[0] >= bag_from_to[1]:
            raise RuntimeError("Bag start time must be bigger than end time.")
        if bag_from_to[0] < 0.0:
            log_warn("Bag start time of {0} s is smaller 0".format(bag_from_to[0]))
        if bag_from_to[1] > baglength:
            log_warn(
                "Bag end time of {0} s is bigger than the total length of {1} s".format(
                    bag_from_to[1], baglength
                )
            )

        valid_indices = []
        for idx, timestamp in zip(indices, timestamps):
            if timestamp >= (bagstart + bag_from_to[0]) and timestamp <= (
                bagstart + bag_from_to[1]
            ):
                valid_indices.append(idx)
        return valid_indices

    def timestamp_for_record(self, idx, time_factory):
        record = self.index[idx]
        if self.perform_synchronization and self.timestamp_corrector is not None:
            local_time = self.timestamp_corrector.getLocalTime(record.header_time_nsec / 1.0e9)
            return time_factory(local_time)
        secs, nsecs = _nsec_to_sec_nsec(record.header_time_nsec)
        return time_factory(secs, nsecs)

    def message(self, idx):
        return self._reader.message(self.index[idx])

    def close(self):
        if self._reader is not None:
            self._reader.close()
            self._reader = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _data_as_uint8(data):
    if isinstance(data, np.ndarray):
        return np.asarray(data, dtype=np.uint8).reshape(-1)
    try:
        return np.frombuffer(data, dtype=np.uint8)
    except (TypeError, ValueError):
        return np.asarray(data, dtype=np.uint8).reshape(-1)


def decode_image_message(msg):
    msgtype = _normalize_msgtype(_message_type(msg))

    if msgtype == "sensor_msgs/CompressedImage":
        encoded = _data_as_uint8(msg.data)
        img_data = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)
        if img_data is None:
            raise RuntimeError("Could not decode compressed image message.")
        if len(img_data.shape) > 2 and img_data.shape[2] == 3:
            img_data = cv2.cvtColor(img_data, cv2.COLOR_BGR2GRAY)
        return img_data

    if msgtype != "sensor_msgs/Image":
        raise RuntimeError(
            "Unsupported Image Type: '{}'\nSupported are: "
            "sensor_msgs/CompressedImage, sensor_msgs/Image".format(msgtype)
        )

    encoding = msg.encoding
    raw = _data_as_uint8(msg.data)
    height = int(msg.height)
    width = int(msg.width)
    step = int(msg.step)

    if encoding in ("16UC1", "mono16"):
        dtype = ">u2" if int(msg.is_bigendian) else "<u2"
        image_16u = np.frombuffer(raw.tostring(), dtype=dtype).reshape(height, step // 2)[:, :width]
        return (image_16u / 256).astype("uint8")

    if encoding in ("8UC1", "mono8"):
        return raw.reshape(height, step)[:, :width].copy()

    if encoding.lower() == "nv12":
        y_plane_size = height * step
        if step < width or raw.size < y_plane_size:
            raise RuntimeError(
                "Invalid NV12 image layout: width={0}, height={1}, step={2}, data={3}".format(
                    width, height, step, raw.size
                )
            )
        return raw[:y_plane_size].reshape(height, step)[:, :width].copy()

    if encoding in ("8UC3", "bgr8", "rgb8"):
        channels = 3
        image = raw.reshape(height, step)[:, : width * channels].reshape(height, width, channels)
        if encoding == "rgb8":
            return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    if encoding in ("8UC4", "bgra8"):
        channels = 4
        image = raw.reshape(height, step)[:, : width * channels].reshape(height, width, channels)
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)

    bayer_codes = {
        "bayer_rggb8": cv2.COLOR_BAYER_BG2GRAY,
        "bayer_bggr8": cv2.COLOR_BAYER_RG2GRAY,
        "bayer_gbrg8": cv2.COLOR_BAYER_GR2GRAY,
        "bayer_grbg8": cv2.COLOR_BAYER_GB2GRAY,
    }
    if encoding in bayer_codes:
        image = raw.reshape(height, step)[:, :width]
        return cv2.cvtColor(image, bayer_codes[encoding])

    raise RuntimeError(
        "Unsupported Image Encoding: '{}'\nSupported are: "
        "16UC1 / mono16, 8UC1 / mono8, nv12, 8UC3 / rgb8 / bgr8, 8UC4 / bgra8, "
        "bayer_rggb8, bayer_bggr8, bayer_gbrg8, bayer_grbg8".format(encoding)
    )


def read_imu_message(msg):
    msgtype = _normalize_msgtype(_message_type(msg))
    if msgtype != "sensor_msgs/Imu":
        raise RuntimeError(
            "Unsupported IMU Type: '{}'\nSupported is: sensor_msgs/Imu".format(msgtype)
        )

    omega = np.array(
        [
            msg.angular_velocity.x,
            msg.angular_velocity.y,
            msg.angular_velocity.z,
        ]
    )
    alpha = np.array(
        [
            msg.linear_acceleration.x,
            msg.linear_acceleration.y,
            msg.linear_acceleration.z,
        ]
    )
    return omega, alpha
