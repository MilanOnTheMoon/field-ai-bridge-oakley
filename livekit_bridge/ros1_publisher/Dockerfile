# ROS1 image publisher. Standalone counterpart of ros1_livekit_bridge/.
FROM ros:noetic-ros-base

# - libgl1        : opencv-python wheel needs libGL.so.1
# - libglib2.0-0  : opencv-python wheel needs libgthread-2.0.so.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# uv: single static binary, no Python install of its own. Replaces pip
# here because it resolves and installs in a fraction of the time.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# ros:noetic ships only Python 3.8, but our PyPI deps need 3.9+. Pull
# in a parallel Python 3.10 via uv (python-build-standalone). rospy /
# sensor_msgs are pure Python so they import fine under 3.10 once
# setup.bash adds /opt/ros/noetic/lib/python3/dist-packages to
# PYTHONPATH (the entrypoint already does this, and venvs honor it).
ENV UV_PYTHON_INSTALL_DIR=/opt/uv-python
RUN uv python install 3.10

# Install Python deps first so editing source doesn't bust the dep layer.
COPY pyproject.toml .
RUN uv venv --python 3.10 /opt/venv
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install --no-cache -r pyproject.toml

# Source + bundled assets. `polaris_image.jpg` is bundled so
# `image_path:` works headlessly inside the container.
COPY image_publisher.py main.py config.yaml docker-entrypoint.sh polaris_image.jpg ./
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD []
