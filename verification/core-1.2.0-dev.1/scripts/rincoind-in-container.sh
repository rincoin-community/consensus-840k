#!/usr/bin/env bash
# Runs the unmodified official v1.1.0-rc1 x86_64 release binary (built for Ubuntu 24.04) inside a local
# Ubuntu 24.04 image, because this host (Debian 12) has an older glibc. Host networking, same paths, same user.
BASE=/path/to/workdir
exec docker run --rm -i --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$BASE":"$BASE" -w "$BASE" rincoin-builder:linux-x86_64-ubuntu24 \
  "$BASE/A-release/bin/rincoind" "$@"
