# 1. Update the base image to the Bookworm tag
FROM ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm@sha256:c6129530811450448ab760064b27e111fb3351fc3222af652f605a48eb518ed7 AS base

ENV TITLE=MetaTrader
ENV WINEARCH=win64
ENV WINEPREFIX="/config/.wine"
ENV DISPLAY=:0
# 2. Fix for Debian 12 Python PEP 668 (allows global pip install in container)
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Ensure the directory exists with correct permissions
RUN mkdir -p /config/.wine && \
  chown -R abc:abc /config/.wine && \
  chmod -R 755 /config/.wine

# 3. Standard update (Backports removal logic is deleted as it's unnecessary here)
RUN apt-get update && apt-get upgrade -y

# 4. Install required packages
# Added 'gnupg' and 'software-properties-common' for secure key handling
# Changed 'netcat' to 'netcat-openbsd' for better stability
RUN apt-get install -y \
  dos2unix \
  python3-pip \
  wget \
  python3-pyxdg \
  netcat-openbsd \
  gnupg \
  software-properties-common \
  && pip3 install --upgrade pip

# 5. MODERN WineHQ Key Handling (apt-key is deprecated)
# This downloads the key, de-armors it, and places it in a dedicated keyring
RUN mkdir -p /etc/apt/keyrings && \
  wget -qO- https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq.gpg && \
  echo "deb [signed-by=/etc/apt/keyrings/winehq.gpg] https://dl.winehq.org/wine-builds/debian/ bookworm main" > /etc/apt/sources.list.d/winehq.list

# 6. Add i386 architecture and install Wine 10.0
RUN dpkg --add-architecture i386 && \
  apt-get update && \
  apt-cache madison winehq-stable && \
  apt-get install --install-recommends -y \
  winehq-stable=10.0.0.0~bookworm-1 \
  wine-stable=10.0.0.0~bookworm-1 \
  wine-stable-amd64=10.0.0.0~bookworm-1 \
  wine-stable-i386=10.0.0.0~bookworm-1 \
  && apt-mark hold winehq-stable wine-stable wine-stable-amd64 wine-stable-i386 \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Stage 2: Final image
FROM base

# Copy application files and scripts
COPY app /app
COPY VERSION /VERSION
# Broker directory for headless env login (defaults/servers.dat is gitignored;
# provide it before build). The dir always has README.md so this COPY succeeds
# whether or not servers.dat is present.
COPY defaults/ /defaults/
COPY scripts /scripts
RUN dos2unix /scripts/*.sh && \
  chmod +x /scripts/*.sh

COPY /root /
RUN touch /var/log/mt5_setup.log && \
  chown abc:abc /var/log/mt5_setup.log && \
  chmod 644 /var/log/mt5_setup.log

EXPOSE 3000 5001
VOLUME /config
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -fsS http://localhost:5001/health/ready || exit 1
