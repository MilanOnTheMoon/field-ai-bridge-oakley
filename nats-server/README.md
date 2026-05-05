
# NATS Server and Client

A server and client used for testings.
This will nominally not be used (as the NATS server will be hosted on `fire-base`), but can be used for testing.

## Debugging

Publish a message on the network
```bash
# Publish a NATS message to the network
docker exec -it nats-box nats pub --server=nats://localhost:4222 robomote.fire.location '{"lat
":47.39831624913856,"lon":8.54685815056169}'

# Print Messages
docker exec -it nats-box nats sub ">"
```
