# The terminal both images bake. The MetaQuotes installer only serves the newest build, and
# builds from 6274 on stop under Wine 10 with a false "debugger has been found" dialog (see
# docs/operations/image-size.md), so this takes build 6244 from a published image of ours.
FROM elitekaycy/mt5-gateway-api:0.3.19@sha256:28042a654f344edab30c7ef664e0b2f19e59134fb21c300e000809c0d93a37d1 AS terminal-source

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

# 3. Patch, install and clean in one stage, flattened below so that files replaced
# or deleted here stop costing image size. OS_PATCH_REV changes daily in the release
# build, so the cached layer is never reused with an older day's package versions: a
# stale cache shipped python3.11 deb12u8 after deb12u9 was out, and a week-keyed cache
# failed 0.3.25's scan on expat and libssh fixes released mid-week. Every release
# reinstalls the MT5 terminal anyway (MT5_LAYER_REV), so the daily key costs no extra rebuild.
ARG OS_PATCH_REV=0
ARG WINE_LAYER_REV=1
RUN echo "os patch rev: ${OS_PATCH_REV}" && apt-get update && apt-get upgrade -y

# 4. Install required packages. --no-install-recommends matters: python3-pip's
# recommends pulled in gcc, g++ and the Python headers. netcat is used by the base
# image's svc-kasmvnc; xvfb gives the template bake a display.
RUN apt-get update && apt-get install -y --no-install-recommends \
  dos2unix \
  wget \
  python3-pyxdg \
  netcat-openbsd \
  gnupg \
  xvfb

# 5. MODERN WineHQ Key Handling (apt-key is deprecated)
# This downloads the key, de-armors it, and places it in a dedicated keyring
RUN mkdir -p /etc/apt/keyrings && \
  wget -qO- https://dl.winehq.org/wine-builds/winehq.key | gpg --dearmor -o /etc/apt/keyrings/winehq.gpg && \
  echo "deb [signed-by=/etc/apt/keyrings/winehq.gpg] https://dl.winehq.org/wine-builds/debian/ bookworm main" > /etc/apt/sources.list.d/winehq.list

# 6. Add i386 architecture and install Wine 10.0. The KasmVNC base includes
# development/host utilities that this runtime never invokes; remove them to
# reduce both the attack surface and published image.
RUN test -n "$WINE_LAYER_REV" && \
  printf '%s\n' "$WINE_LAYER_REV" > /etc/mt5-gateway-wine-layer-rev && \
  dpkg --add-architecture i386 && \
  apt-get update && \
  apt-cache madison winehq-stable && \
  apt-get install --install-recommends -y \
  winehq-stable=10.0.0.0~bookworm-1 \
  wine-stable=10.0.0.0~bookworm-1 \
  wine-stable-amd64=10.0.0.0~bookworm-1 \
  wine-stable-i386=10.0.0.0~bookworm-1 \
  && apt-mark hold winehq-stable wine-stable wine-stable-amd64 wine-stable-i386 \
  && cd /kclient \
  && npm pkg set \
    overrides.jake.minimatch=3.1.4 \
    overrides.filelist.minimatch=5.1.8 \
    overrides.path-to-regexp=0.1.13 \
    'overrides[socket.io-parser]=4.2.7' \
    overrides.ws=8.21.0 \
    overrides.brace-expansion=1.1.20 \
    'overrides[engine.io]=6.6.10' \
    overrides.proxy-addr=2.0.8 \
    overrides.body-parser=1.20.9 \
  && npm install --omit=dev --ignore-scripts \
  && cd / \
  && apt-get purge -y docker-ce docker-ce-cli docker-buildx-plugin docker-compose-plugin containerd.io locales-all \
  && sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
  && locale-gen \
  && rm -rf /usr/lib/node_modules/npm /usr/include/node \
    /usr/sbin/ipp-usb \
    /etc/ssl/private/ssl-cert-snakeoil.key \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man

# Flatten: a plain layer cannot reclaim what lower layers hold, so the deletions and
# the rewrites from `apt-get upgrade` above only shrink the image once the system is
# copied into a single layer. FROM scratch drops the base image's config, so all of it
# is restated here; tests/test_image_variants.py pins this list.
FROM scratch AS system
COPY --from=base / /
ENV PATH=/lsiopy/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ENV HOME=/config
ENV LANGUAGE=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV TERM=xterm
ENV S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0
ENV S6_VERBOSITY=1
ENV S6_STAGE2_HOOK=/docker-mods
ENV VIRTUAL_ENV=/lsiopy
ENV DISPLAY=:0
ENV PERL5LIB=/usr/local/bin
ENV OMP_WAIT_POLICY=PASSIVE
ENV GOMP_SPINCOUNT=0
ENV START_DOCKER=false
ENV PULSE_RUNTIME_PATH=/defaults
ENV NVIDIA_DRIVER_CAPABILITIES=all
ENV TITLE=MetaTrader
ENV WINEARCH=win64
ENV WINEPREFIX=/config/.wine
ENV PIP_BREAK_SYSTEM_PACKAGES=1
ENTRYPOINT ["/init"]
EXPOSE 3001

# Stage 2: Final image
FROM system

# Copy runtime files and scripts
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

# Pre-install the Wine components (Python, the MT5 Python libs, and the
# MT5 terminal itself) into a template prefix baked into the image. WINEPREFIX is
# the /config volume, which shadows anything built into it, so a fresh volume
# would otherwise re-install all of this (~10 min) on every first boot. The boot
# instead seeds /config/.wine from this template with a fast copy, so a cold boot
# never runs an installer — including the MT5 GUI installer, which is the flaky
# one under Wine. Built as uid 911 (abc) to match the runtime user. Kept before
# the app COPY (it only needs requirements.txt) so app-code changes don't bust
# this layer's cache.
ENV WINE_TEMPLATE=/opt/wine-template
COPY app/requirements.txt /tmp/requirements.txt
RUN mkdir -p "$WINE_TEMPLATE" && chown -R abc:abc "$WINE_TEMPLATE"
USER abc
RUN /scripts/bake-wine-template.sh runtime

# Bake the MT5 terminal into the template as well, so a cold boot only copies it.
# These two pins apply when MT5_TERMINAL_SOURCE below is emptied to use the web
# installer. MetaQuotes rotates that stub, so its checksum is pinned: a rotation
# fails the build loudly (re-pin here, in Dockerfile.headless and mt5setup_sha256
# in scripts/02-common.sh).
ARG MT5_SETUP_URL=https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe
ARG MT5_SETUP_SHA256=a879492dd9d7b168d0538edd1c0dc5604ca43dc0951825b3501818e8b18f4c93
# Referenced by the RUN below so release CI can bust just this layer's cache
# (docker.yml passes the commit sha), while PR builds keep the default and stay
# cache-hit (mirrors WINE_LAYER_REV).
ARG MT5_LAYER_REV=1
# Set to 0 only to debug a build; a release must never ship an unverified terminal.
ARG MT5_VERIFY_TERMINAL=1
# Empty runs the installer above instead of copying the pinned terminal.
ARG MT5_TERMINAL_SOURCE="/mnt/terminal/Program Files/MetaTrader 5"
RUN --mount=type=bind,from=terminal-source,source=/opt/wine-template/drive_c,target=/mnt/terminal \
  test -n "$MT5_LAYER_REV" && /scripts/bake-wine-template.sh terminal
USER root

# App code last, so editing it rebuilds in seconds (the template layer above stays
# cached). Includes broker_servers.json, the baked broker-address table.
COPY app /app

EXPOSE 3000 5001
VOLUME /config
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD if [ -n "$API_KEY" ]; then \
    curl -fsS -H "Authorization: Bearer $API_KEY" http://localhost:5001/health/ready; \
  else \
    curl -fsS http://localhost:5001/health/ready; \
  fi
