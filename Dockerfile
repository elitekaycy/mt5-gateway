# 1. Update the base image to the Bookworm tag
FROM ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm AS base

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
  xvfb \
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

# Pre-install the display-less Wine components (Mono, Python, the MT5 Python libs)
# into a template prefix baked into the image. WINEPREFIX is the /config volume,
# which shadows anything built into it, so a fresh volume would otherwise re-install
# all of this (~10 min) on every first boot. The boot instead seeds /config/.wine
# from this template with a fast copy. MT5 itself (a GUI installer) is still
# installed at runtime. Built as uid 911 (abc) to match the runtime user. Kept
# before the app COPY (it only needs requirements.txt) so app-code changes don't
# bust this layer's cache.
ENV WINE_TEMPLATE=/opt/wine-template
COPY app/requirements.txt /tmp/requirements.txt
RUN mkdir -p "$WINE_TEMPLATE" && chown -R abc:abc "$WINE_TEMPLATE"
USER abc
# The Python installer needs an X display even in /quiet mode, and there is none
# during `docker build`, so run the installs under a virtual framebuffer (Xvfb).
RUN set -eux; \
  export HOME="$WINE_TEMPLATE" WINEPREFIX="$WINE_TEMPLATE" WINEARCH=win64 \
    WINEDEBUG=-all WINEDLLOVERRIDES=mscoree=d DISPLAY=:99; \
  Xvfb :99 -screen 0 1024x768x16 >/dev/null 2>&1 & xvfb_pid=$!; sleep 2; \
  wineboot -i; wineserver -w; \
  wget -qO /tmp/mono.msi https://dl.winehq.org/wine/wine-mono/8.0.0/wine-mono-8.0.0-x86.msi; \
  wine msiexec /i /tmp/mono.msi /qn; wineserver -w; \
  wget -qO /tmp/python.exe https://www.python.org/ftp/python/3.9.13/python-3.9.13-amd64.exe; \
  wine /tmp/python.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0; wineserver -w; \
  wine python -m pip install --no-cache-dir -r /tmp/requirements.txt; wineserver -w; \
  kill "$xvfb_pid" 2>/dev/null || true; \
  rm -f /tmp/mono.msi /tmp/python.exe
USER root

# App code last, so editing it rebuilds in seconds (the template layer above stays
# cached). Includes broker_servers.json, the baked broker-address table.
COPY app /app

EXPOSE 3000 5000 5001 8001 18812
VOLUME /config
