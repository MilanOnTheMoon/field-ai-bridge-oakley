cmake_minimum_required(VERSION 3.0.2)
project(nats_bridge)

# add_compile_options(-std=c++11)

find_package(catkin REQUIRED COMPONENTS
  roscpp
  rospy
  std_msgs
  sensor_msgs
  nav_msgs
)

catkin_python_setup()

catkin_package(
  CATKIN_DEPENDS roscpp rospy std_msgs sensor_msgs nav_msgs
)

include_directories(
  ${catkin_INCLUDE_DIRS}
)

# install the executable node script(s)
install(PROGRAMS
  scripts/*
  DESTINATION ${CATKIN_PACKAGE_BIN_DESTINATION}
)

# install launch files if present
install(DIRECTORY launch
        DESTINATION ${CATKIN_PACKAGE_SHARE_DESTINATION})
