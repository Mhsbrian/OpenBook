# SPDX-License-Identifier: Apache-2.0
# openbook-seeder: seeds OpenBook's release torrents from a read-only releases folder (docs/RELEASE.md §4).
# Transmission 4 with its RPC on the container's own loopback only; the one thing this container exposes is the
# BitTorrent peer port. It seeds a release only when its release.json says "public": true.
FROM alpine:3.24
RUN apk add --no-cache transmission-daemon curl jq tini \
 && adduser -D -H -u 10001 -s /sbin/nologin seeder \
 && mkdir -p /state /status /releases \
 && chown seeder:seeder /state /status
COPY entrypoint.sh /usr/local/bin/openbook-seeder
ENV PEER_PORT=51413 \
    SEED_UP_KBPS=0 \
    PEER_LIMIT=200 \
    SYNC_SECONDS=60 \
    SEED_UNPUBLISHED=0
USER 10001:10001
VOLUME ["/state", "/status"]
EXPOSE 51413/tcp 51413/udp
HEALTHCHECK --interval=60s --timeout=10s --start-period=180s --retries=3 CMD ["/usr/local/bin/openbook-seeder", "health"]
ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/openbook-seeder"]
CMD ["run"]
