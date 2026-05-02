
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
