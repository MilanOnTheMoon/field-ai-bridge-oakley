[![Bridge](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build.yml)[![DrawIO](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/drawio-export.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/drawio-export.yml)

# fieldai-bridge

- Docker image with ros1 node that bridges NATS to ROS1 (FieldAI topics)
- Docker compose file that brings up all the different required codes
  - NATS to ROS1 bridge
  - NATS listener

```bash
git clone --recursive git@github.com:tii-firefighting/fieldai-bridge.git
```

## Network Setup

![network_diagram](images/export/network-Page-1.svg)

Communications between the FMO (ground station software) and the agents is via a [NATS messaging system](https://en.wikipedia.org/wiki/NATS_Messaging), which is then bridged on the agent side into the correct language (ROS1/ROS2/mavlink, etc).
This is typically packaged as a docker file that can be easily deployed to each agent.

The supplied docker compose file also starts the containers for the NATS backbone and authentication. 

## Configuration
### IP Forwarding
Make sure IP forwarding is enabled
```
echo "net.ipv4.ip_forward = 1" | sudo tee -a /etc/sysctl.conf
```

### Tailscale Log In
```
docker exec -it tailscale-tailscale-1 tailscale up
```

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
HOSTNAME=$(hostname) docker compose up --build -d

```
