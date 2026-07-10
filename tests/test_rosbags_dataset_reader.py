from __future__ import annotations

import builtins
import importlib
import sys
import types
from pathlib import Path

import cv2
import numpy as np
import pytest
from rosbags.interfaces import (
    Qos,
    QosDurability,
    QosHistory,
    QosLiveliness,
    QosReliability,
    QosTime,
)
from rosbags.rosbag1 import Reader as Rosbag1Reader
from rosbags.rosbag1 import Writer as Rosbag1Writer
from rosbags.rosbag2 import Writer as Rosbag2Writer
from rosbags.typesys import Stores, get_typestore

REPO_ROOT = Path(__file__).resolve().parents[1]
KALIBR_COMMON = REPO_ROOT / "aslam_offline_calibration" / "kalibr" / "python" / "kalibr_common"


class FakeTime:
    def __init__(self, secs, nsecs=None):
        if nsecs is None:
            total_ns = int(round(float(secs) * 1_000_000_000))
            self.secs = total_ns // 1_000_000_000
            self.nsecs = total_ns % 1_000_000_000
        else:
            self.secs = int(secs)
            self.nsecs = int(nsecs)

    def toSec(self):
        return self.secs + self.nsecs / 1_000_000_000.0


class FakeTimestampCorrector:
    def correctTimestamp(self, header_time, receive_time):
        self.header_time = header_time
        self.receive_time = receive_time

    def getLocalTime(self, header_time):
        return header_time


def import_dataset_modules(monkeypatch):
    package = types.ModuleType("kalibr_common")
    package.__path__ = [str(KALIBR_COMMON)]
    monkeypatch.setitem(sys.modules, "kalibr_common", package)
    monkeypatch.setitem(sys.modules, "aslam_cv", types.SimpleNamespace(Time=FakeTime))
    monkeypatch.setitem(
        sys.modules,
        "sm",
        types.SimpleNamespace(
            DoubleTimestampCorrector=FakeTimestampCorrector,
            logWarn=lambda msg: None,
        ),
    )
    for name in [
        "kalibr_common.RosbagDatasetReader",
        "kalibr_common.ImageDatasetReader",
        "kalibr_common.ImuDatasetReader",
    ]:
        sys.modules.pop(name, None)
    image_module = importlib.import_module("kalibr_common.ImageDatasetReader")
    imu_module = importlib.import_module("kalibr_common.ImuDatasetReader")
    return image_module, imu_module


def stamp_cls(typestore):
    return typestore.types["builtin_interfaces/msg/Time"]


def header_cls(typestore):
    return typestore.types["std_msgs/msg/Header"]


def vector3_cls(typestore):
    return typestore.types["geometry_msgs/msg/Vector3"]


def image_cls(typestore):
    return typestore.types["sensor_msgs/msg/Image"]


def compressed_image_cls(typestore):
    return typestore.types["sensor_msgs/msg/CompressedImage"]


def imu_cls(typestore):
    return typestore.types["sensor_msgs/msg/Imu"]


def make_header(typestore, timestamp_ns, seq=0):
    Time = stamp_cls(typestore)
    Header = header_cls(typestore)
    stamp = Time(sec=timestamp_ns // 1_000_000_000, nanosec=timestamp_ns % 1_000_000_000)
    try:
        return Header(seq=seq, stamp=stamp, frame_id="frame")
    except TypeError:
        return Header(stamp=stamp, frame_id="frame")


def make_image(typestore, timestamp_ns, image):
    Image = image_cls(typestore)
    return Image(
        header=make_header(typestore, timestamp_ns),
        height=image.shape[0],
        width=image.shape[1],
        encoding="mono8",
        is_bigendian=0,
        step=image.shape[1],
        data=np.asarray(image, dtype=np.uint8).reshape(-1),
    )


def make_compressed_image(typestore, timestamp_ns, image):
    CompressedImage = compressed_image_cls(typestore)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return CompressedImage(
        header=make_header(typestore, timestamp_ns),
        format="png",
        data=np.frombuffer(encoded.tobytes(), dtype=np.uint8),
    )


def make_imu(typestore, timestamp_ns, gyro, accel):
    Imu = imu_cls(typestore)
    Vector3 = vector3_cls(typestore)
    covariance = np.zeros(9, dtype=np.float64)
    return Imu(
        header=make_header(typestore, timestamp_ns),
        orientation=typestore.types["geometry_msgs/msg/Quaternion"](0.0, 0.0, 0.0, 1.0),
        orientation_covariance=covariance,
        angular_velocity=Vector3(*gyro),
        angular_velocity_covariance=covariance,
        linear_acceleration=Vector3(*accel),
        linear_acceleration_covariance=covariance,
    )


def write_ros2_bag(path, image_topic="/cam/image_raw", imu_topic="/imu"):
    typestore = get_typestore(Stores.ROS2_FOXY)
    image_type = image_cls(typestore).__msgtype__
    imu_type = imu_cls(typestore).__msgtype__
    with Rosbag2Writer(path, version=9) as writer:
        image_conn = writer.add_connection(image_topic, image_type, typestore=typestore)
        imu_conn = writer.add_connection(imu_topic, imu_type, typestore=typestore)
        image2 = make_image(
            typestore,
            2_000_000_000,
            np.array([[5, 6], [7, 8]], dtype=np.uint8),
        )
        writer.write(
            image_conn,
            2_000_000_000,
            typestore.serialize_cdr(image2, image_type),
        )
        image1 = make_image(
            typestore,
            1_000_000_000,
            np.array([[1, 2], [3, 4]], dtype=np.uint8),
        )
        writer.write(
            image_conn,
            1_000_000_000,
            typestore.serialize_cdr(image1, image_type),
        )
        imu_msg = make_imu(
            typestore,
            1_500_000_000,
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
        )
        writer.write(
            imu_conn,
            1_500_000_000,
            typestore.serialize_cdr(imu_msg, imu_type),
        )
    return path


def write_ros1_bag(path, image_topic="/cam/image_raw", images=None, header_timestamps=None):
    typestore = get_typestore(Stores.ROS1_NOETIC)
    image_type = image_cls(typestore).__msgtype__
    if images is None:
        images = [np.array([[9, 8], [7, 6]], dtype=np.uint8)]
    if header_timestamps is None:
        header_timestamps = [idx * 1_000_000_000 for idx in range(1, len(images) + 1)]
    with Rosbag1Writer(path) as writer:
        image_conn = writer.add_connection(image_topic, image_type, typestore=typestore)
        for idx, (image_data, header_timestamp_ns) in enumerate(
            zip(images, header_timestamps), start=1
        ):
            receive_timestamp_ns = idx * 1_000_000_000
            image = make_image(typestore, header_timestamp_ns, image_data)
            writer.write(
                image_conn,
                receive_timestamp_ns,
                typestore.serialize_ros1(image, image_type),
            )
    return path


def qos_profile(reliability):
    zero = QosTime(0, 0)
    return Qos(
        QosHistory.KEEP_LAST,
        10,
        reliability,
        QosDurability.VOLATILE,
        zero,
        zero,
        QosLiveliness.AUTOMATIC,
        zero,
        False,
    )


class NativeRosTime:
    def __init__(self, secs, nsecs):
        self.secs = secs
        self.nsecs = nsecs

    def to_sec(self):
        return self.secs + self.nsecs / 1_000_000_000.0


class NativeRosbagIndexEntry:
    def __init__(self, position):
        self.position = position


class NativeRosbag:
    def __init__(self, _path):
        stamp = NativeRosTime(1, 0)
        message = types.SimpleNamespace(
            _type="sensor_msgs/Image",
            header=types.SimpleNamespace(stamp=stamp),
            height=2,
            width=2,
            encoding="mono8",
            is_bigendian=0,
            step=2,
            data=b"\x09\x08\x07\x06",
        )
        self.messages = [("/cam/image_raw", message, stamp)]

    def _get_connections(self, topics):
        return [object()] if topics == "/cam/image_raw" else []

    def _get_indexes(self, connections):
        if connections:
            yield [NativeRosbagIndexEntry(0)]

    def _read_message(self, position):
        return self.messages[position]

    def close(self):
        pass


def test_ros1_reader_uses_native_rosbag_when_rosbags_is_unavailable(monkeypatch):
    rosbag_module = types.ModuleType("rosbag")
    rosbag_module.Bag = NativeRosbag
    monkeypatch.setitem(sys.modules, "rosbag", rosbag_module)

    original_import = builtins.__import__

    def import_without_rosbags(name, *args, **kwargs):
        if name == "rosbags" or name.startswith("rosbags."):
            raise ImportError("rosbags is intentionally unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_rosbags)
    image_module, _ = import_dataset_modules(monkeypatch)

    images = image_module.BagImageDatasetReader("native.bag", "/cam/image_raw")
    stamp, image = images.getImage(images.indices[0])

    assert stamp.toSec() == pytest.approx(1.0)
    assert image.tolist() == [[9, 8], [7, 6]]


def test_ros2_reader_sorts_by_header_time_and_reads_images_and_imu(tmp_path, monkeypatch):
    image_module, imu_module = import_dataset_modules(monkeypatch)
    bag = write_ros2_bag(tmp_path / "ros2_bag")

    images = image_module.BagImageDatasetReader(str(bag), "/cam/image_raw")
    assert images.numImages() == 2
    first_stamp, first_image = images.getImage(images.indices[0])
    assert first_stamp.toSec() == pytest.approx(1.0)
    assert first_image.tolist() == [[1, 2], [3, 4]]

    imu = imu_module.BagImuDatasetReader(str(bag), "/imu")
    stamp, omega, alpha = imu.getMessage(imu.indices[0])
    assert stamp.toSec() == pytest.approx(1.5)
    assert omega.tolist() == [1.0, 2.0, 3.0]
    assert alpha.tolist() == [4.0, 5.0, 6.0]


def test_reader_rejects_missing_topic_before_reading_other_streams(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    bag = write_ros2_bag(tmp_path / "ros2_bag")

    with pytest.raises(RuntimeError, match="Could not find topic /missing"):
        image_module.BagImageDatasetReader(str(bag), "/missing")


def test_reader_index_does_not_retain_deserialized_messages(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    bag = write_ros2_bag(tmp_path / "ros2_bag")

    images = image_module.BagImageDatasetReader(str(bag), "/cam/image_raw")

    assert images.numImages() == 2
    assert all(not hasattr(record, "msg") for record in images.index)


def test_lazy_reader_distinguishes_messages_with_equal_receive_timestamps(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    typestore = get_typestore(Stores.ROS2_FOXY)
    bag = tmp_path / "same_receive_time_bag"
    image_type = image_cls(typestore).__msgtype__
    with Rosbag2Writer(bag, version=9) as writer:
        connection = writer.add_connection("/cam/image_raw", image_type, typestore=typestore)
        second = make_image(
            typestore,
            2_000_000_000,
            np.array([[5, 6], [7, 8]], dtype=np.uint8),
        )
        first = make_image(
            typestore,
            1_000_000_000,
            np.array([[1, 2], [3, 4]], dtype=np.uint8),
        )
        writer.write(connection, 3_000_000_000, typestore.serialize_cdr(second, image_type))
        writer.write(connection, 3_000_000_000, typestore.serialize_cdr(first, image_type))

    images = image_module.BagImageDatasetReader(str(bag), "/cam/image_raw")

    _, first_image = images.getImage(images.indices[0])
    _, second_image = images.getImage(images.indices[1])
    assert first_image.tolist() == [[1, 2], [3, 4]]
    assert second_image.tolist() == [[5, 6], [7, 8]]


def test_lazy_reader_distinguishes_ros2_connections_on_the_same_topic(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    typestore = get_typestore(Stores.ROS2_FOXY)
    bag = tmp_path / "multi_connection_bag"
    image_type = image_cls(typestore).__msgtype__
    with Rosbag2Writer(bag, version=9) as writer:
        first_connection = writer.add_connection(
            "/cam/image_raw",
            image_type,
            typestore=typestore,
            offered_qos_profiles=[qos_profile(QosReliability.RELIABLE)],
        )
        second_connection = writer.add_connection(
            "/cam/image_raw",
            image_type,
            typestore=typestore,
            offered_qos_profiles=[qos_profile(QosReliability.BEST_EFFORT)],
        )
        second = make_image(
            typestore,
            2_000_000_000,
            np.array([[5, 6], [7, 8]], dtype=np.uint8),
        )
        first = make_image(
            typestore,
            1_000_000_000,
            np.array([[1, 2], [3, 4]], dtype=np.uint8),
        )
        writer.write(
            first_connection,
            3_000_000_000,
            typestore.serialize_cdr(second, image_type),
        )
        writer.write(
            second_connection,
            3_000_000_000,
            typestore.serialize_cdr(first, image_type),
        )

    raw_bag = next(bag.glob("*.db3"))
    images = image_module.BagImageDatasetReader(str(raw_bag), "/cam/image_raw")

    _, first_image = images.getImage(images.indices[0])
    _, second_image = images.getImage(images.indices[1])
    assert first_image.tolist() == [[1, 2], [3, 4]]
    assert second_image.tolist() == [[5, 6], [7, 8]]


def test_rosbags_ros1_reader_streams_sequential_access_without_rescanning(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    bag = write_ros1_bag(
        tmp_path / "ros1.bag",
        images=[
            np.array([[1, 2], [3, 4]], dtype=np.uint8),
            np.array([[5, 6], [7, 8]], dtype=np.uint8),
        ],
    )
    calls = []
    original_messages = Rosbag1Reader.messages

    def counting_messages(self, connections=(), start=None, stop=None):
        calls.append((start, stop))
        for item in original_messages(self, connections, start, stop):
            yield item

    monkeypatch.setattr(Rosbag1Reader, "messages", counting_messages)
    images = image_module.BagImageDatasetReader(str(bag), "/cam/image_raw")

    for idx in images.indices:
        images.getImage(idx)

    assert calls == [(None, None), (None, None)]


def test_rosbags_ros1_reader_does_not_rescan_for_reversed_header_order(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    images_data = [np.full((2, 2), value, dtype=np.uint8) for value in range(12)]
    bag = write_ros1_bag(
        tmp_path / "reversed_headers.bag",
        images=images_data,
        header_timestamps=[timestamp * 1_000_000_000 for timestamp in range(12, 0, -1)],
    )
    calls = []
    original_messages = Rosbag1Reader.messages

    def counting_messages(self, connections=(), start=None, stop=None):
        calls.append((start, stop))
        for item in original_messages(self, connections, start, stop):
            yield item

    monkeypatch.setattr(Rosbag1Reader, "messages", counting_messages)
    images = image_module.BagImageDatasetReader(str(bag), "/cam/image_raw")

    decoded_values = [images.getImage(idx)[1][0, 0] for idx in images.indices]

    assert decoded_values == list(reversed(range(12)))
    assert all(start is None for start, _ in calls)


def test_ros1_reader_reads_standard_image_without_ros_python(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    bag = write_ros1_bag(tmp_path / "ros1.bag")

    images = image_module.BagImageDatasetReader(str(bag), "/cam/image_raw")
    stamp, image = images.getImage(images.indices[0])

    assert stamp.toSec() == pytest.approx(1.0)
    assert image.tolist() == [[9, 8], [7, 6]]


def test_reader_decodes_compressed_images(tmp_path, monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    typestore = get_typestore(Stores.ROS2_FOXY)
    bag = tmp_path / "compressed_bag"
    compressed_type = compressed_image_cls(typestore).__msgtype__
    with Rosbag2Writer(bag, version=9) as writer:
        conn = writer.add_connection("/cam/compressed", compressed_type, typestore=typestore)
        msg = make_compressed_image(
            typestore,
            1_000_000_000,
            np.array([[10, 11], [12, 13]], dtype=np.uint8),
        )
        writer.write(conn, 1_000_000_000, typestore.serialize_cdr(msg, compressed_type))

    images = image_module.BagImageDatasetReader(str(bag), "/cam/compressed")
    _, image = images.getImage(images.indices[0])

    assert image.tolist() == [[10, 11], [12, 13]]


def test_reader_decodes_nv12_luma_plane_with_row_padding(monkeypatch):
    image_module, _ = import_dataset_modules(monkeypatch)
    msg = types.SimpleNamespace(
        __msgtype__="sensor_msgs/msg/Image",
        encoding="nv12",
        height=2,
        width=4,
        step=6,
        is_bigendian=0,
        data=np.array(
            [
                1,
                2,
                3,
                4,
                90,
                91,
                5,
                6,
                7,
                8,
                92,
                93,
                128,
                128,
                128,
                128,
                128,
                128,
            ],
            dtype=np.uint8,
        ),
    )

    image = image_module.decode_image_message(msg)

    assert image.tolist() == [[1, 2, 3, 4], [5, 6, 7, 8]]
