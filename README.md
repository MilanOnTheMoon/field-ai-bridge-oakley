[![NATS Bridge](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_nats-bridge.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_nats-bridge.yml)\
[![WebRTC Bridge](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_webrtc-bridge.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_webrtc-bridge.yml)\
[![DrawIO](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/drawio-export.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/drawio-export.yml)

# fieldai-bridge

- Docker image with ros1 node that bridges NATS to ROS1 (FieldAI topics)
- Docker compose file that brings up all the different required codes
  - NATS to ROS1 bridge
  - ROS1 to webRTC bridge

```bash
git clone --recursive git@github.com:tii-firefighting/fieldai-bridge.git
```

## Network Setup

![network_diagram](images/export/network-Page-1.svg)

Communications between the FMO (ground station software) and the agents is via a [NATS messaging system](https://en.wikipedia.org/wiki/NATS_Messaging), which is then bridged on the agent side into the correct language (ROS1/ROS2/mavlink, etc).
This is typically packaged as a docker file that can be easily deployed to each agent.

The supplied docker compose file also starts the containers for the NATS backbone and authentication. 

## Configuration

```bash
docker compose -f   NATS_bridge/compose.yaml up --build 
docker compose -f webRTC_bridge/compose.yaml up --build 
```

## Debugging

See https://github.com/daniel-robotics/ros_python_pkg for example ros package setup

```bash
# Run a ros noetic instance
docker run -it --network=host osrf/ros:noetic-desktop

```
