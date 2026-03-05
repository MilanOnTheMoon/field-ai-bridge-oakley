
# docker build -t fieldai-nats-bridge:latest . 

FROM osrf/ros:noetic-desktop

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

SHELL ["/bin/bash", "-c"]

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    tmux \
    && pip3 install -r requirements.txt  \
    && rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-rosdep \
    python3-rosinstall \
    python3-rosinstall-generator \
    python3-wstool \
    build-essential

# Copy workspace over
WORKDIR /ros1_ws
COPY nats_bridge ./src/nats_bridge

# Build
RUN source /opt/ros/$ROS_DISTRO/setup.bash && \
    catkin_make

# CMD and ENTRYPOINT
# CMD source devel/setup.bash && roslaunch nats_bridge nats_bridge.launch
CMD ["/bin/bash"]
