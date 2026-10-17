// SPDX-License-Identifier: Apache-2.0
// openbook-test-dhcpd: the smallest DHCP server the QEMU Wi-Fi test needs (scripts/audio-net-qemu.sh). It runs in
// the access point's network namespace on the second simulated radio and leases one address to whoever asks:
// 192.168.77.<10 + n> in 192.168.77.0/24, router and DNS 192.168.77.1, one hour. DISCOVER -> OFFER,
// REQUEST -> ACK; nothing else. Test equipment only: never part of an image.
//
// usage: openbook-test-dhcpd IFACE          (static, built with the NDK: scripts/audio-net-qemu.sh payload)
#include <arpa/inet.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

#define SERVER "192.168.77.1"

struct dhcp {
    uint8_t op, htype, hlen, hops;
    uint32_t xid;
    uint16_t secs, flags;
    uint32_t ciaddr, yiaddr, siaddr, giaddr;
    uint8_t chaddr[16], sname[64], file[128];
    uint8_t magic[4], options[312];
} __attribute__((packed));

static int put(uint8_t *o, int at, uint8_t code, int len, const void *v) {
    o[at] = code;
    o[at + 1] = (uint8_t)len;
    memcpy(o + at + 2, v, len);
    return at + 2 + len;
}

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: openbook-test-dhcpd IFACE\n"); return 2; }
    int s = socket(AF_INET, SOCK_DGRAM, 0), one = 1;
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    setsockopt(s, SOL_SOCKET, SO_BROADCAST, &one, sizeof one);
    if (setsockopt(s, SOL_SOCKET, SO_BINDTODEVICE, argv[1], strlen(argv[1]) + 1)) { perror("bindtodevice"); return 1; }
    struct sockaddr_in a = {.sin_family = AF_INET, .sin_port = htons(67)};
    if (bind(s, (struct sockaddr *)&a, sizeof a)) { perror("bind"); return 1; }
    printf("openbook-test-dhcpd: serving 192.168.77.0/24 on %s\n", argv[1]);
    fflush(stdout);
    uint8_t macs[8][6];
    int nmacs = 0;
    for (;;) {
        struct dhcp m;
        ssize_t n = recv(s, &m, sizeof m, 0);
        if (n < 240 || m.op != 1 || memcmp(m.magic, "\x63\x82\x53\x63", 4)) continue;
        int type = 0;
        for (int i = 0; i + 1 < (int)sizeof m.options && m.options[i] != 255;) {
            if (m.options[i] == 0) { i++; continue; }
            if (m.options[i] == 53) type = m.options[i + 2];
            i += 2 + m.options[i + 1];
        }
        if (type != 1 && type != 3) continue;  // DISCOVER, REQUEST
        int k = 0;
        while (k < nmacs && memcmp(macs[k], m.chaddr, 6)) k++;
        if (k == nmacs && nmacs < 8) memcpy(macs[nmacs++], m.chaddr, 6);
        char ip[32];
        snprintf(ip, sizeof ip, "192.168.77.%d", 10 + k);
        struct dhcp r = m;
        r.op = 2;
        r.hops = 0;
        r.secs = 0;
        r.ciaddr = 0;
        inet_pton(AF_INET, ip, &r.yiaddr);
        inet_pton(AF_INET, SERVER, &r.siaddr);
        memset(r.options, 0, sizeof r.options);
        uint8_t reply = type == 1 ? 2 : 5;  // OFFER, ACK
        uint32_t server, mask, lease = htonl(3600);
        inet_pton(AF_INET, SERVER, &server);
        inet_pton(AF_INET, "255.255.255.0", &mask);
        int at = put(r.options, 0, 53, 1, &reply);
        at = put(r.options, at, 54, 4, &server);
        at = put(r.options, at, 51, 4, &lease);
        at = put(r.options, at, 1, 4, &mask);
        at = put(r.options, at, 3, 4, &server);
        at = put(r.options, at, 6, 4, &server);
        r.options[at++] = 255;
        struct sockaddr_in to = {.sin_family = AF_INET, .sin_port = htons(68)};
        to.sin_addr.s_addr = htonl(INADDR_BROADCAST);
        sendto(s, &r, sizeof r - sizeof r.options + at, 0, (struct sockaddr *)&to, sizeof to);
        printf("openbook-test-dhcpd: %s %s\n", reply == 2 ? "OFFER" : "ACK", ip);
        fflush(stdout);
    }
}
