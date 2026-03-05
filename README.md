
# fieldai-bridge

- Docker image with ros1 node that bridges NATS to ROS1 (FieldAI topics)
- Docker compose file that brings up all the different required codes
  - NATS to ROS1 bridge
  - NATS listener

```bash
git clone --recursive git@github.com:tii-firefighting/fieldai-bridge.git
```

![network_diagram](images/export/network-Page-1.svg)

## Debugging

See https://github.com/daniel-robotics/ros_python_pkg for example ros package setup

```bash
# Run a ros noetic instance
docker run -it --network=host osrf/ros:noetic-desktop

# Build container
docker build -t fieldai-nats-bridge:latest . 

# Run container
docker run -it --network=host fieldai-nats-bridge:latest
source devel/setup.bash && roslaunch nats_bridge nats_bridge.launch

# Start via docker compose (for deployment)
docker compose up --build
```