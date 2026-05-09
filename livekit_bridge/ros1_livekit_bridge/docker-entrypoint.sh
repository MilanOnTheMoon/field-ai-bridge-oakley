#!/bin/bash
# Entrypoint for the ROS1 → LiveKit bridge container.
#
# Responsibilities:
#   1. Source the ROS env so rospy / sensor_msgs are importable.
#   2. exec main.py — config comes from YAML, not flags.
#
# Note: this container does NOT start a roscore. The bridge and the
# publisher are deliberately split; bring up `roscore` separately (in a
# terminal, in its own container, or on the robot) and point both
# config.yaml files at it via `ros_master_uri`.
set -euo pipefail

# ROS Noetic's setup.bash dereferences $ROS_MASTER_URI without guarding
# for it being unset under `set -u`. Provide a default so the source
# succeeds; main.py overwrites it from the YAML config anyway.
export ROS_MASTER_URI="${ROS_MASTER_URI:-http://localhost:11311}"

source /opt/ros/noetic/setup.bash

exec python3 -u main.py "$@"
