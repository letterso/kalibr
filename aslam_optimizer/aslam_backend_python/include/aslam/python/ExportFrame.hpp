#ifndef ASLAM_PYTHON_EXPORT_FRAME_HPP
#define ASLAM_PYTHON_EXPORT_FRAME_HPP

#include <sstream>

#include <aslam/Frame.hpp>

namespace aslam {
namespace python {

template<int D>
void exportKeypoint() {
  using namespace boost::python;
  using namespace aslam;

  typedef aslam::Keypoint<D> keypoint_t;

  std::stringstream str;
  str << "Keypoint" << D;

  class_<keypoint_t, bases<KeypointBase> >(str.str().c_str(), init<>()).def(
      "measurement", &keypoint_t::measurement,
      return_value_policy<copy_const_reference>()).def(
      "y", &keypoint_t::y, return_value_policy<copy_const_reference>()).def(
      "setMeasurement", &keypoint_t::setMeasurement).def("octave",
                                                         &keypoint_t::octave)
      .def("setOctave", &keypoint_t::setOctave).def(
      "inverseMeasurementCovariance", &keypoint_t::inverseMeasurementCovariance,
      return_value_policy<copy_const_reference>()).def(
      "invR", &keypoint_t::invR, return_value_policy<copy_const_reference>())
      .def("setInverseMeasurementCovariance",
           &keypoint_t::setInverseMeasurementCovariance).def(
      "setInverseCovariance", &keypoint_t::setInverseCovariance).def(
      "landmark", &keypoint_t::landmark, return_internal_reference<>());
}

template<typename CAMERA_GEOMETRY_T>
void exportFrame(const std::string & name) {
  using namespace boost::python;
  using namespace aslam;

  typedef CAMERA_GEOMETRY_T geometry_t;
  typedef Frame<geometry_t> frame_t;
  typedef typename frame_t::keypoint_t keypoint_t;

  keypoint_t & (frame_t::*keypoint)(size_t) = &frame_t::keypoint;
  void (frame_t::*addKeypointPtr)(
      const keypoint_t & keypoint) = &frame_t::addKeypoint;

  class_<frame_t, boost::shared_ptr<frame_t>, bases<FrameBase> >(name.c_str(),
                                                                 init<>()).def(
      "geometry", &frame_t::geometryPtr).def("setGeometry",
                                             &frame_t::setGeometry).def(
      "clearKeypoints", &frame_t::clearKeypoints).def(
      "keypoint", keypoint, return_internal_reference<>()).def("addKeypoint",
                                                               addKeypointPtr);
}

}  // namespace python
}  // namespace aslam

#endif /* ASLAM_PYTHON_EXPORT_FRAME_HPP */
