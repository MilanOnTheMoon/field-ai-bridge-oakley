
# docker build -t fieldai-webrtc-bridge:latest . 
# docker run -it fieldai-webrtc-bridge:latest 

FROM osrf/ros:melodic-desktop

ARG DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

SHELL ["/bin/bash", "-c"]

# Base packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    git tmux wget \
    curl gnupg lsb-release \
    build-essential \
    python-pip && \
    git config --global url."https://github.com/".insteadOf git://github.com/

# ROS Requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
        python-rosdep \
        python-rosinstall \
        python-rosinstall-generator \
        python-wstool \
        python-catkin-tools
    
# Create ROS1 workspaceCopy workspace over
RUN mkdir -p /ros1_ws/src
WORKDIR /ros1_ws

# ROS1 to webRTC bridge
RUN apt-get install ros-melodic-webrtc-ros -y

# NATS Bridge
COPY webrtc_launch ./src/webrtc_launch

# Build
RUN source /opt/ros/$ROS_DISTRO/setup.bash && \
    catkin build

# CMD and ENTRYPOINT
CMD source devel/setup.bash && roslaunch webrtc_launch webrtc.launch
# CMD ["/bin/bash"]
