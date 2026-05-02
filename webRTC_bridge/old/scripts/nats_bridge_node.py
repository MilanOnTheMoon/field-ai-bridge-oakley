#!/usr/bin/env python3

import rospy
import asyncio

# import the top‑level class from our package
from nats_bridge import nats_bridge

def main(args=None):
    rospy.init_node('nats_bridge', anonymous=False)
    node = nats_bridge()
    try:
        rospy.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node._stopping = True
        try:
            if node.nats_client is not None and not node.nats_client.is_closed:
                # Close NATS client if possible
                try:
                    asyncio.get_event_loop().run_until_complete(node.nats_client.close())
                except Exception:
                    pass
        except Exception:
            pass

if __name__ == '__main__':
    main()
