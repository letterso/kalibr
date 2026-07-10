cmake_minimum_required(VERSION 3.16)
project(kalibr_standalone LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

set(KALIBR_STANDALONE_PYTHON_DIR ${CMAKE_BINARY_DIR}/python)
set(KALIBR_STANDALONE_BIN_DIR ${CMAKE_BINARY_DIR}/bin)

find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module NumPy)
find_package(Eigen3 REQUIRED)
find_package(OpenCV REQUIRED)
find_package(TBB REQUIRED)
list(APPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/aslam_optimizer/sparse_block_matrix/cmake")
find_package(SuiteSparse REQUIRED)

set(_boost_python_component "python${Python3_VERSION_MAJOR}${Python3_VERSION_MINOR}")
find_package(Boost REQUIRED COMPONENTS
  system
  serialization
  filesystem
  thread
  regex
  ${_boost_python_component}
)

execute_process(
  COMMAND ${Python3_EXECUTABLE} -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX') or '.so')"
  OUTPUT_VARIABLE PYTHON_EXTENSION_SUFFIX
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

include_directories(
  ${Boost_INCLUDE_DIRS}
  ${EIGEN3_INCLUDE_DIRS}
  ${OpenCV_INCLUDE_DIRS}
  ${CHOLMOD_INCLUDE_DIR}
  ${SUITESPARSE_INCLUDE_DIRS}
  ${Python3_INCLUDE_DIRS}
  ${Python3_NumPy_INCLUDE_DIRS}
  Schweizer-Messer/sm_common/include
  Schweizer-Messer/sm_boost/include
  Schweizer-Messer/sm_eigen/include
  Schweizer-Messer/sm_kinematics/include
  Schweizer-Messer/sm_logging/include
  Schweizer-Messer/sm_matrix_archive/include
  Schweizer-Messer/sm_opencv/include
  Schweizer-Messer/sm_property_tree/include
  Schweizer-Messer/sm_python/include
  Schweizer-Messer/sm_random/include
  Schweizer-Messer/sm_timing/include
  Schweizer-Messer/numpy_eigen/include
  Schweizer-Messer/numpy_eigen/include/numpy_eigen
  aslam_optimizer/sparse_block_matrix/include
  aslam_optimizer/aslam_backend/include
  aslam_optimizer/aslam_backend_expressions/include
  aslam_optimizer/aslam_backend_python/include
  aslam_cv/aslam_time/include
  aslam_cv/aslam_cameras/include
  aslam_cv/aslam_cameras_april/include
  aslam_cv/aslam_cv_backend/include
  aslam_cv/aslam_cv_backend_python/include
  aslam_cv/aslam_cv_error_terms/include
  aslam_cv/aslam_cv_python/include
  aslam_cv/aslam_cv_serialization/include
  aslam_cv/aslam_imgproc/include
  aslam_nonparametric_estimation/bsplines/include
  aslam_nonparametric_estimation/aslam_splines/include
  aslam_incremental_calibration/incremental_calibration/include
  aslam_incremental_calibration/incremental_calibration_python/include
  aslam_offline_calibration/ethz_apriltag2/include
  aslam_offline_calibration/kalibr/include
)

add_compile_definitions(__STRICT_ANSI__)

function(kalibr_add_python_module target package_dir)
  add_library(${target} MODULE ${ARGN})
  set_target_properties(${target} PROPERTIES
    PREFIX ""
    OUTPUT_NAME "lib${target}"
    SUFFIX "${PYTHON_EXTENSION_SUFFIX}"
    LIBRARY_OUTPUT_DIRECTORY "${KALIBR_STANDALONE_PYTHON_DIR}/${package_dir}"
  )
  target_link_libraries(${target} PRIVATE
    Python3::Module
    Boost::${_boost_python_component}
  )
endfunction()

function(kalibr_copy_python_package source_dir package_name)
  file(MAKE_DIRECTORY "${KALIBR_STANDALONE_PYTHON_DIR}/${package_name}")
  file(COPY "${source_dir}/" DESTINATION "${KALIBR_STANDALONE_PYTHON_DIR}/${package_name}")
endfunction()

function(kalibr_add_wrapper name source_script)
  set(wrapper "${KALIBR_STANDALONE_BIN_DIR}/${name}")
  set(_wrapper_content [=[
#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT}/python${PYTHONPATH:+:${PYTHONPATH}}"
export LD_LIBRARY_PATH="${ROOT}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
if [ -z "${MPLCONFIGDIR:-}" ]; then
  export MPLCONFIGDIR="/tmp/kalibr-matplotlib-${USER:-user}"
  mkdir -p "${MPLCONFIGDIR}" 2>/dev/null || true
fi
exec "@Python3_EXECUTABLE@" "@CMAKE_CURRENT_SOURCE_DIR@/@source_script@" "$@"
]=])
  string(CONFIGURE "${_wrapper_content}" _wrapper_content @ONLY)
  file(WRITE "${wrapper}" "${_wrapper_content}")
  file(CHMOD "${wrapper}" FILE_PERMISSIONS
    OWNER_READ OWNER_WRITE OWNER_EXECUTE
    GROUP_READ GROUP_EXECUTE
    WORLD_READ WORLD_EXECUTE
  )
endfunction()

add_library(sm_common Schweizer-Messer/sm_common/src/progress_info.cpp)
target_link_libraries(sm_common PUBLIC Boost::system)

add_library(sm_logging
  Schweizer-Messer/sm_logging/src/Formatter.cpp
  Schweizer-Messer/sm_logging/src/Logger.cpp
  Schweizer-Messer/sm_logging/src/LoggingEvent.cpp
  Schweizer-Messer/sm_logging/src/LoggingGlobals.cpp
  Schweizer-Messer/sm_logging/src/StdOutLogger.cpp
  Schweizer-Messer/sm_logging/src/Tokens.cpp
)
target_link_libraries(sm_logging PUBLIC sm_common Boost::system Boost::thread Boost::regex)

add_library(sm_random Schweizer-Messer/sm_random/src/random.cpp)
target_link_libraries(sm_random PUBLIC sm_common Boost::system)

add_library(sm_boost
  Schweizer-Messer/sm_boost/src/JobQueue.cpp
  Schweizer-Messer/sm_boost/src/portable_binary_iarchive.cpp
  Schweizer-Messer/sm_boost/src/portable_binary_oarchive.cpp
)
target_link_libraries(sm_boost PUBLIC sm_common Boost::system Boost::serialization Boost::thread)

add_library(sm_eigen Schweizer-Messer/sm_eigen/src/random.cpp)
target_link_libraries(sm_eigen PUBLIC sm_common sm_random Boost::system Boost::serialization)

file(GLOB SM_KINEMATICS_SRC CONFIGURE_DEPENDS Schweizer-Messer/sm_kinematics/src/*.cpp)
add_library(sm_kinematics ${SM_KINEMATICS_SRC})
target_link_libraries(sm_kinematics PUBLIC sm_common sm_eigen sm_boost sm_random
  Boost::system Boost::serialization Boost::filesystem)

add_library(sm_property_tree
  Schweizer-Messer/sm_property_tree/src/BoostPropertyTree.cpp
  Schweizer-Messer/sm_property_tree/src/BoostPropertyTreeImplementation.cpp
  Schweizer-Messer/sm_property_tree/src/BoostPropertyTreeSupport.cpp
  Schweizer-Messer/sm_property_tree/src/PropertyTree.cpp
  Schweizer-Messer/sm_property_tree/src/PropertyTreeImplementation.cpp
)
target_link_libraries(sm_property_tree PUBLIC sm_common Boost::system Boost::filesystem pthread)

add_library(sm_matrix_archive Schweizer-Messer/sm_matrix_archive/src/MatrixArchive.cpp)
target_link_libraries(sm_matrix_archive PUBLIC sm_common Boost::system Boost::filesystem pthread)

add_library(sm_timing
  Schweizer-Messer/sm_timing/src/NsecTimeUtilities.cpp
  Schweizer-Messer/sm_timing/src/Timer.cpp
)
target_link_libraries(sm_timing PUBLIC sm_common sm_random Boost::system)

add_library(sm_opencv INTERFACE)
target_link_libraries(sm_opencv INTERFACE sm_common Boost::system ${OpenCV_LIBS})

include(Schweizer-Messer/numpy_eigen/src/autogen_files.cmake)
list(TRANSFORM AUTOGEN_FILES PREPEND "Schweizer-Messer/numpy_eigen/")
kalibr_add_python_module(numpy_eigen numpy_eigen ${AUTOGEN_FILES})
target_link_libraries(numpy_eigen PRIVATE Boost::system)

add_library(sparse_block_matrix
  aslam_optimizer/sparse_block_matrix/src/matrix_structure.cpp
  aslam_optimizer/sparse_block_matrix/src/sparse_helper.cpp
  aslam_optimizer/sparse_block_matrix/src/marginal_covariance_cholesky.cpp
)
target_link_libraries(sparse_block_matrix PUBLIC sm_common sm_eigen ${SUITESPARSE_LIBRARIES} TBB::tbb)

add_library(aslam_time
  aslam_cv/aslam_time/src/time.cpp
  aslam_cv/aslam_time/src/duration.cpp
)
target_link_libraries(aslam_time PUBLIC Boost::system)

add_library(aslam_cameras
  aslam_cv/aslam_cameras/src/CameraGeometryBase.cpp
  aslam_cv/aslam_cameras/src/GlobalShutter.cpp
  aslam_cv/aslam_cameras/src/RollingShutter.cpp
  aslam_cv/aslam_cameras/src/NoMask.cpp
  aslam_cv/aslam_cameras/src/NoDistortion.cpp
  aslam_cv/aslam_cameras/src/RadialTangentialDistortion.cpp
  aslam_cv/aslam_cameras/src/EquidistantDistortion.cpp
  aslam_cv/aslam_cameras/src/FovDistortion.cpp
  aslam_cv/aslam_cameras/src/ImageMask.cpp
  aslam_cv/aslam_cameras/src/GridCalibrationTargetObservation.cpp
  aslam_cv/aslam_cameras/src/GridCalibrationTargetBase.cpp
  aslam_cv/aslam_cameras/src/GridCalibrationTargetCheckerboard.cpp
  aslam_cv/aslam_cameras/src/GridCalibrationTargetCirclegrid.cpp
  aslam_cv/aslam_cameras/src/GridDetector.cpp
  aslam_cv/aslam_cameras/src/Triangulation.cpp
  aslam_cv/aslam_cameras/src/FrameBase.cpp
  aslam_cv/aslam_cameras/src/KeypointBase.cpp
  aslam_cv/aslam_cameras/src/DescriptorBase.cpp
  aslam_cv/aslam_cameras/src/BackProjection.cpp
  aslam_cv/aslam_cameras/src/Landmark.cpp
  aslam_cv/aslam_cameras/src/Image.cpp
)
target_link_libraries(aslam_cameras PUBLIC sm_common sm_eigen sm_boost sm_kinematics
  sm_logging aslam_time sm_opencv sm_property_tree sm_random ${OpenCV_LIBS}
  Boost::system Boost::serialization Boost::filesystem)

add_library(aslam_imgproc aslam_cv/aslam_imgproc/src/UndistorterBase.cpp)
target_link_libraries(aslam_imgproc PUBLIC aslam_cameras Boost::system ${OpenCV_LIBS})

include(aslam_cv/aslam_cv_serialization/autogen_cameras.cmake)
list(TRANSFORM AUTOGEN_CAMERA_CPP_FILES PREPEND "aslam_cv/aslam_cv_serialization/")
add_library(aslam_cv_serialization
  ${AUTOGEN_CAMERA_CPP_FILES}
  aslam_cv/aslam_cv_serialization/src/FrameBaseSerialization.cpp
)
target_link_libraries(aslam_cv_serialization PUBLIC aslam_cameras aslam_time sm_boost
  sm_property_tree sm_eigen sm_kinematics sm_opencv sm_logging sm_random
  Boost::serialization Boost::system)

file(GLOB ETHZ_APRILTAG2_SRC CONFIGURE_DEPENDS aslam_offline_calibration/ethz_apriltag2/src/*.cc)
add_library(ethz_apriltag2 ${ETHZ_APRILTAG2_SRC})
target_link_libraries(ethz_apriltag2 PUBLIC Eigen3::Eigen ${OpenCV_LIBS})

add_library(aslam_cameras_april aslam_cv/aslam_cameras_april/src/GridCalibrationTargetAprilgrid.cpp)
target_link_libraries(aslam_cameras_april PUBLIC aslam_cameras ethz_apriltag2
  sm_common sm_logging sm_boost sm_eigen ${OpenCV_LIBS} Boost::serialization Boost::system)

file(GLOB ASLAM_BACKEND_SRC CONFIGURE_DEPENDS aslam_optimizer/aslam_backend/src/*.cpp)
add_library(aslam_backend ${ASLAM_BACKEND_SRC})
target_link_libraries(aslam_backend PUBLIC sparse_block_matrix sm_boost sm_random sm_timing
  sm_logging sm_property_tree Boost::system Boost::thread ${SUITESPARSE_LIBRARIES} TBB::tbb)

file(GLOB ASLAM_BACKEND_EXPRESSIONS_SRC CONFIGURE_DEPENDS
  aslam_optimizer/aslam_backend_expressions/src/*.cpp)
add_library(aslam_backend_expressions ${ASLAM_BACKEND_EXPRESSIONS_SRC})
target_link_libraries(aslam_backend_expressions PUBLIC aslam_backend sm_boost sm_random
  sm_kinematics sparse_block_matrix sm_timing Boost::system)

add_library(bsplines
  aslam_nonparametric_estimation/bsplines/src/BSpline.cpp
  aslam_nonparametric_estimation/bsplines/src/BSplinePose.cpp
)
target_link_libraries(bsplines PUBLIC sm_common sm_timing sm_eigen sm_kinematics sparse_block_matrix)

add_library(aslam_splines
  aslam_nonparametric_estimation/aslam_splines/src/BSplinePoseDesignVariable.cpp
  aslam_nonparametric_estimation/aslam_splines/src/BSplineExpressions.cpp
  aslam_nonparametric_estimation/aslam_splines/src/EuclideanBSplineDesignVariable.cpp
)
target_link_libraries(aslam_splines PUBLIC aslam_backend aslam_backend_expressions bsplines
  sparse_block_matrix sm_common sm_kinematics sm_timing Boost::system)

file(GLOB INCREMENTAL_CALIBRATION_SRC CONFIGURE_DEPENDS
  aslam_incremental_calibration/incremental_calibration/src/base/*.cpp
  aslam_incremental_calibration/incremental_calibration/src/exceptions/*.cpp
  aslam_incremental_calibration/incremental_calibration/src/statistics/*.cpp
  aslam_incremental_calibration/incremental_calibration/src/functions/*.cpp
  aslam_incremental_calibration/incremental_calibration/src/core/*.cpp
  aslam_incremental_calibration/incremental_calibration/src/algorithms/*.cpp
)
add_library(incremental_calibration ${INCREMENTAL_CALIBRATION_SRC})
target_link_libraries(incremental_calibration PUBLIC sm_eigen aslam_backend
  Boost::system Boost::thread TBB::tbb)

add_library(aslam_cv_backend
  aslam_cv/aslam_cv_backend/src/GridCalibrationTargetDesignVariableContainer.cpp
)
target_link_libraries(aslam_cv_backend PUBLIC sm_common sm_boost sm_kinematics sm_eigen
  sm_opencv sm_property_tree sm_logging sm_timing aslam_backend
  aslam_backend_expressions aslam_time aslam_cameras sparse_block_matrix Boost::system)

add_library(aslam_cv_error_terms INTERFACE)
target_link_libraries(aslam_cv_error_terms INTERFACE aslam_cv_backend aslam_splines)

add_library(kalibr_errorterms
  aslam_offline_calibration/kalibr/src/EuclideanError.cpp
  aslam_offline_calibration/kalibr/src/GyroscopeError.cpp
  aslam_offline_calibration/kalibr/src/AccelerometerError.cpp
)
target_link_libraries(kalibr_errorterms PUBLIC aslam_backend aslam_backend_expressions
  aslam_splines sm_kinematics)

kalibr_add_python_module(sm_python sm
  Schweizer-Messer/sm_python/src/module.cpp
  Schweizer-Messer/sm_python/src/export_rotational_kinematics.cpp
  Schweizer-Messer/sm_python/src/export_rotations.cpp
  Schweizer-Messer/sm_python/src/export_transformations.cpp
  Schweizer-Messer/sm_python/src/export_quaternion_algebra.cpp
  Schweizer-Messer/sm_python/src/export_homogeneous.cpp
  Schweizer-Messer/sm_python/src/exportTransformation.cpp
  Schweizer-Messer/sm_python/src/exportHomogeneousPoint.cpp
  Schweizer-Messer/sm_python/src/exportTimestampCorrector.cpp
  Schweizer-Messer/sm_python/src/exportPropertyTree.cpp
  Schweizer-Messer/sm_python/src/exportEigen.cpp
  Schweizer-Messer/sm_python/src/exportUncertainVector.cpp
  Schweizer-Messer/sm_python/src/exportMatrixArchive.cpp
  Schweizer-Messer/sm_python/src/export_kinematics_property_tree.cpp
  Schweizer-Messer/sm_python/src/export_eigen_property_tree.cpp
  Schweizer-Messer/sm_python/src/Logging.cpp
  Schweizer-Messer/sm_python/src/exportNsecTime.cpp
  Schweizer-Messer/sm_python/src/random.cpp
)
target_link_libraries(sm_python PRIVATE sm_common sm_kinematics sm_timing sm_logging
  sm_matrix_archive sm_property_tree sm_eigen Boost::system Boost::serialization)

kalibr_add_python_module(aslam_backend_python aslam_backend
  aslam_optimizer/aslam_backend_python/src/module.cpp
  aslam_optimizer/aslam_backend_python/src/Backend.cpp
  aslam_optimizer/aslam_backend_python/src/Optimizer.cpp
  aslam_optimizer/aslam_backend_python/src/OptimizerOptions.cpp
  aslam_optimizer/aslam_backend_python/src/OptimizationProblem.cpp
  aslam_optimizer/aslam_backend_python/src/DesignVariable.cpp
  aslam_optimizer/aslam_backend_python/src/ErrorTerm.cpp
  aslam_optimizer/aslam_backend_python/src/MEstimators.cpp
  aslam_optimizer/aslam_backend_python/src/JacobianContainer.cpp
  aslam_optimizer/aslam_backend_python/src/BackendExpressions.cpp
  aslam_optimizer/aslam_backend_python/src/CompressedColumnMatrix.cpp
  aslam_optimizer/aslam_backend_python/src/LinearSystemSolver.cpp
  aslam_optimizer/aslam_backend_python/src/ErrorTermTransformation.cpp
  aslam_optimizer/aslam_backend_python/src/TrustRegionPolicies.cpp
  aslam_optimizer/aslam_backend_python/src/SparseBlockMatrix.cpp
)
target_link_libraries(aslam_backend_python PRIVATE aslam_backend aslam_backend_expressions
  sparse_block_matrix sm_common sm_kinematics sm_timing Boost::thread)

kalibr_add_python_module(bsplines_python bsplines
  aslam_nonparametric_estimation/bsplines_python/src/SplinePython.cpp
  aslam_nonparametric_estimation/bsplines_python/src/BSplinePython.cpp
  aslam_nonparametric_estimation/bsplines_python/src/BSplinePosePython.cpp
)
target_link_libraries(bsplines_python PRIVATE bsplines sparse_block_matrix sm_common sm_kinematics)

kalibr_add_python_module(aslam_splines_python aslam_splines
  aslam_nonparametric_estimation/aslam_splines_python/src/spline_module.cpp
  aslam_nonparametric_estimation/aslam_splines_python/src/BSplineMotionError.cpp
  aslam_nonparametric_estimation/aslam_splines_python/src/SimpleSplineError.cpp
)
target_link_libraries(aslam_splines_python PRIVATE aslam_splines bsplines
  aslam_backend aslam_backend_expressions sm_common sm_kinematics
  sm_timing aslam_cameras aslam_time sm_property_tree sm_logging)

kalibr_add_python_module(aslam_cv_python aslam_cv
  aslam_cv/aslam_cv_python/src/module.cpp
  aslam_cv/aslam_cv_python/src/CameraGeometries.cpp
  aslam_cv/aslam_cv_python/src/CameraGeometry.cpp
  aslam_cv/aslam_cv_python/src/Time.cpp
  aslam_cv/aslam_cv_python/src/Frontend.cpp
  aslam_cv/aslam_cv_python/src/Frame.cpp
  aslam_cv/aslam_cv_python/src/CameraProjections.cpp
  aslam_cv/aslam_cv_python/src/CameraShutters.cpp
  aslam_cv/aslam_cv_python/src/GridCalibration.cpp
  aslam_cv/aslam_cv_python/src/Undistorters.cpp
  aslam_cv/aslam_cv_python/src/OmniUndistorter.cpp
  aslam_cv/aslam_cv_python/src/PinholeUndistorter.cpp
)
target_link_libraries(aslam_cv_python PRIVATE aslam_cv_serialization aslam_imgproc
  aslam_cameras aslam_time sm_kinematics Boost::serialization)

kalibr_add_python_module(aslam_cv_backend_python aslam_cv_backend
  aslam_cv/aslam_cv_backend_python/src/module.cpp
  aslam_cv/aslam_cv_backend_python/src/GridCalibration.cpp
)
target_link_libraries(aslam_cv_backend_python PRIVATE aslam_cv_backend aslam_backend
  aslam_backend_expressions aslam_splines
  aslam_cameras aslam_time)

kalibr_add_python_module(aslam_cameras_april_python aslam_cameras_april
  aslam_cv/aslam_cameras_april/src/module.cpp
)
target_link_libraries(aslam_cameras_april_python PRIVATE aslam_cameras_april)

kalibr_add_python_module(incremental_calibration_python incremental_calibration
  aslam_incremental_calibration/incremental_calibration_python/src/module.cpp
  aslam_incremental_calibration/incremental_calibration_python/src/OptimizationProblem.cpp
  aslam_incremental_calibration/incremental_calibration_python/src/IncrementalEstimator.cpp
  aslam_incremental_calibration/incremental_calibration_python/src/LinearSolver.cpp
)
target_link_libraries(incremental_calibration_python PRIVATE incremental_calibration
  aslam_backend sm_property_tree)

kalibr_add_python_module(kalibr_errorterms_python .
  aslam_offline_calibration/kalibr/src/module.cpp
)
target_link_libraries(kalibr_errorterms_python PRIVATE kalibr_errorterms)

kalibr_copy_python_package(Schweizer-Messer/numpy_eigen/src/numpy_eigen numpy_eigen)
kalibr_copy_python_package(Schweizer-Messer/sm_python/python/sm sm)
kalibr_copy_python_package(aslam_optimizer/aslam_backend_python/python/aslam_backend aslam_backend)
kalibr_copy_python_package(aslam_nonparametric_estimation/bsplines_python/python/bsplines bsplines)
kalibr_copy_python_package(aslam_nonparametric_estimation/aslam_splines_python/python/aslam_splines aslam_splines)
kalibr_copy_python_package(aslam_cv/aslam_cv_python/python/aslam_cv aslam_cv)
kalibr_copy_python_package(aslam_cv/aslam_cv_backend_python/python/aslam_cv_backend aslam_cv_backend)
kalibr_copy_python_package(aslam_cv/aslam_cameras_april/python/aslam_cameras_april aslam_cameras_april)
kalibr_copy_python_package(aslam_incremental_calibration/incremental_calibration_python/src/incremental_calibration incremental_calibration)
kalibr_copy_python_package(aslam_offline_calibration/kalibr/python/kalibr_common kalibr_common)
kalibr_copy_python_package(aslam_offline_calibration/kalibr/python/kalibr_camera_calibration kalibr_camera_calibration)
kalibr_copy_python_package(aslam_offline_calibration/kalibr/python/kalibr_imu_camera_calibration kalibr_imu_camera_calibration)
kalibr_copy_python_package(aslam_offline_calibration/kalibr/python/kalibr_rs_camera_calibration kalibr_rs_camera_calibration)
kalibr_copy_python_package(aslam_offline_calibration/kalibr/python/kalibr_errorterms kalibr_errorterms)

kalibr_add_wrapper(kalibr_calibrate_cameras aslam_offline_calibration/kalibr/python/kalibr_calibrate_cameras)
kalibr_add_wrapper(kalibr_calibrate_imu_camera aslam_offline_calibration/kalibr/python/kalibr_calibrate_imu_camera)
kalibr_add_wrapper(kalibr_calibrate_rs_cameras aslam_offline_calibration/kalibr/python/kalibr_calibrate_rs_cameras)
kalibr_add_wrapper(kalibr_bagextractor aslam_offline_calibration/kalibr/python/kalibr_bagextractor)
kalibr_add_wrapper(kalibr_visualize_calibration aslam_offline_calibration/kalibr/python/kalibr_visualize_calibration)
kalibr_add_wrapper(kalibr_visualize_distortion aslam_offline_calibration/kalibr/python/kalibr_visualize_distortion)
kalibr_add_wrapper(kalibr_create_target_pdf aslam_offline_calibration/kalibr/python/kalibr_create_target_pdf)
