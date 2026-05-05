[![NATS Bridge](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_nats-bridge.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_nats-bridge.yml)[![WebRTC Bridge](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_webrtc-bridge.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/build_webrtc-bridge.yml)[![DrawIO](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/drawio-export.yml/badge.svg)](https://github.com/tii-firefighting/fieldai-bridge/actions/workflows/drawio-export.yml)

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
# docker compose -f webRTC_bridge/compose.yaml up --build  # IGNORE THIS FOR NOW 
```

## Debugging
See individual folders for debugging in the `README.md` file.

But for a quick-start, in individual terminals:
1. Start the NATS server and client
    - `docker compose -f nats-server/compose.yaml up`
1. Echo all messages from the NATS server
    - `docker exec -it nats-box nats sub ">"`
1. Publish a message to the NATS server
    - `docker exec -it nats-box nats pub --server=nats://localhost:4222 robomote.fire.location '{"lat
":47.39831624913856,"lon":8.54685815056169}'`
    - You should see the message appear on the NATS server echo terminal - NATS is working correctly
1. Start the ROS1-NATS bridge
    - `docker compose -f   NATS_bridge/compose.yaml up --build`
    - You should see a `fieldai.node_heartbeat` message being published to NATS
    - --- Everything should work up until this point ---
1. Start streaming ROS1 data
    - (Parts to develop) You should see location / battery / etc. messages appear on the NATS server echo terminal
