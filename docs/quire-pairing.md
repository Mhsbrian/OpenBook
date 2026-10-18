# Quire: pairing a second computer (design, for review before it is built)

As of 2026-10-18. Part of Q4 (ANAL-218). Status: **design only**. Nothing here is implemented: the issue requires the Checker's review (ANAL-217) first. `docs/quire.md` §4 links here.

## 1. What it is for

Some people keep their agents on another machine: a desktop with Claude Code signed in, a workstation with a GPU. Some laptops can't run the Linux environment at all, either because the hardware has no virtualization or because it is off in the firmware. For both, Quire core on OpenBook should be able to use the `quired` on a second computer on the same network, as if it were in the Linux environment.

Quire core is the ACP client either way. Only the transport changes, from vsock to an encrypted LAN connection. On the computer, `quired serve` routes sessions to its agents exactly as it does in the guest (`docs/quire.md` §6).

## 2. What is at stake

`quired` runs agent CLIs as the person's user on that computer. Agents have the person's full access, and asking first is the agent's choice (`docs/quire.md` §5.2). **Whoever can talk to a listening `quired` can make code run on that computer.** So the channel has to:

1. let nobody but the paired OpenBook connect, even an attacker on the same Wi-Fi who can see, drop and inject packets;
2. let OpenBook be sure it reached the computer the person paired, not an impostor that would then see prompts, screenshots and answers;
3. keep the content confidential and intact;
4. be easy to set up once, without accounts, a cloud service or typing a long key.

## 3. Threats

| Attacker | Can | Must not be able to |
|---|---|---|
| Passive, on the LAN | read every packet | read content; learn anything that helps later |
| Active, on the LAN (ARP or mDNS spoofing, rogue access point) | drop, change, inject and replay; pose as either side | pair with either side; finish a session; get a guess at the pairing code to try offline |
| A device on the LAN that never paired | connect to the port | get past the handshake; tell paired from unpaired by timing; run anything |
| Someone who stole the OpenBook laptop | use the paired key | keep access once the person revokes the device on the computer |
| A malicious or compromised `quired` | send any ACP content | change OpenBook's settings without the broker's consent (Q6, `docs/quire.md` §5.3), or read secure windows |

Out of scope: an attacker who already runs code as the person on either machine.

## 4. Design

### 4.1 Off unless the person starts it

- Nothing listens until the person runs `quired serve --listen ADDR:PORT` on the computer. The default port is 7691. It is never a system service that starts by itself.
- The vsock listener in the Linux environment is unchanged and separate.
- In listen mode, the session root defaults to `~/Quire`, not `$HOME`. A remote client's sessions stay in that folder unless the person passes `--root`.
- MCP servers named by the client are refused, as in the guest.

### 4.2 Identities

- Each side has a long-term key pair. The computer keeps an ECDSA P-256 key in `~/.config/quired/identity.key` (0600). Quire keeps its key in Android Keystore, non-exportable.
- Each side wraps its key in a self-signed X.509 certificate. Certificates are not checked against any CA. **A peer is identified only by the SHA-256 of its SubjectPublicKeyInfo (its pin).**
- Why P-256: Android Keystore and Go's `crypto/tls` both handle it natively, so neither side needs crypto outside its standard library.

### 4.3 The channel: TLS 1.3 with both pins

- Every connection is TLS 1.3 only, with ALPN `quire-acp/1` and mutual authentication. Both sides present their certificates.
- After the handshake, each side checks the peer's pin against its list of paired peers. There is no plaintext mode and no fallback.
- Go: `tls.Config{MinVersion: tls.VersionTLS13, ClientAuth: tls.RequireAnyClientCert, VerifyPeerCertificate: pins}`. Android: an `SSLSocket` with a TrustManager that pins and a KeyManager over the Keystore key.
- ACP's newline-delimited JSON runs inside, unchanged.
- **An unpaired client** is refused after the TLS handshake, with the same alert and timing as a bad certificate. `quired` logs the attempt with the peer's pin.

### 4.4 Pairing: a 6-digit code compared on both screens

Pairing is the one moment when neither side knows the other's pin. It uses short-authentication-string comparison with a commitment (SAS-MCA, the scheme behind Bluetooth's numeric comparison). It needs only what TLS already gives.

1. On the computer, the person runs `quired pair`. For 5 minutes it accepts **one** unpinned client. It advertises `_quire._tcp` over mDNS, with the computer's name and the first 4 bytes of its pin in the TXT record.
2. In Quire, the person chooses **Pair a computer** and picks the computer from the list, or types its address.
3. The two sides complete a TLS 1.3 handshake with their certificates, unverified for now. Both derive `E = TLS-Exporter("EXPORTER-quire-pairing-v1", "", 32)`. E binds both certificates and the session keys.
4. Inside the channel:
   - **Commit:** the computer picks a 32-byte nonce `Nb` and sends `Cb = SHA-256("quire-commit" ‖ Nb)`.
   - **Nonce:** Quire picks `Na` and sends it.
   - **Reveal:** the computer sends `Nb`. Quire checks it against `Cb`.
5. Both compute `SAS = SHA-256("quire-sas" ‖ E ‖ Na ‖ Nb)`, truncated to 20 bits and shown as 6 digits.
6. **Both screens show the 6 digits.** The person confirms on both: Quire's dialog, and `quired pair`'s prompt.
7. Each side stores the other's pin only once both have confirmed and each has told the other so over the channel. Otherwise nothing is stored.

**Why the commitment.** An attacker in the middle has two TLS sessions with two different exporters, and needs the 6 digits to match on both screens. Without `Cb`, it could choose its own nonces after seeing the others, and search 2^20 values offline in under a second. With the commitment, each side's nonce is fixed before the attacker learns the other's. It gets one random try per pairing: about one chance in a million, and the person sees a failed or mismatched pairing.

**Why not a code typed on the other screen.** A short code typed into Quire and used as a pre-shared key (Noise `NNpsk0`, or TLS-PSK) is open to offline guessing. An active attacker who poses as the computer once can test every code afterwards. A PAKE (SPAKE2, CPace) fixes that, but Go and Android would each need group arithmetic their standard libraries don't expose. SAS-MCA gives the same guarantee with the person's eyes and stock TLS.

### 4.5 Limits and revocation

- `quired pair` serves one pairing and then exits. A wrong confirmation, a mismatch or a timeout ends it.
- Unpaired connections are rate-limited: 5 per minute per address, with backoff.
- On the computer, `quired pair --list` and `quired pair --forget ID` manage pairings. Pins live in `~/.config/quired/paired.json` (0600). In Quire, **Settings › Quire › Paired computers › Forget** does the same.
- Forgetting a device takes effect at the next handshake. Open sessions from that device are closed at once.
- Each session start is logged on the computer with the device name and folder. A desktop notification is optional.

### 4.6 What Quire shows

- The note names where the agent runs: "Claude Code · on the desktop".
- If the paired computer can't be reached, Quire says so. It doesn't fall back silently to another computer or to the cloud.
- If the computer's pin changes, Quire refuses and asks the person to pair again. That happens on a reinstall, or when someone is posing as the computer.

## 5. Where it plugs in

- **`quired`:**
  - `serve --listen` (TLS) beside `--vsock`, `--unix` and `--stdio`;
  - `pair`;
  - a `paired.json` store.

  `internal/serve` doesn't change: it only sees an `io.Reader` and an `io.Writer`.
- **Quire core:**
  - `Connectors.PairedComputer` (today it only reports "none paired");
  - the pairing dialog;
  - a Keystore key;
  - a pinned `SSLSocket` that feeds `AgentHost`, as the Terminal bridge does for the Linux environment.
- **Order:** the Linux environment first, then a paired computer (`Connectors.statuses`). On a laptop without KVM, Quire's message already names pairing as the fallback (`agents_no_kvm`, `agents_not_paired`).

## 6. Tests required before it ships

1. **A MITM simulation.** A relay between Quire's code and `quired pair` that runs two TLS sessions and plays every strategy it can within the protocol. Pairing must never complete with matching digits, except by the 2^-20 chance (checked statistically, with the code shortened to 8 bits for the test).
2. **Unpaired or forgotten clients.** An unpaired client and a forgotten client are both refused after the handshake, with identical alert and timing, and nothing reaches `internal/serve`.
3. **A changed pin.** Quire refuses to connect and says why.
4. **The pairing window.** It closes after one pairing, after 5 minutes, and after a mismatch.
5. **No plaintext.** No TLS version below 1.3, and no connection without ALPN `quire-acp/1`.
6. **Rate limits** hold.
7. **No secrets in logs.** Neither side logs key material, exporters or nonces; pins are logged truncated.
8. **The Q1 contract still holds** over the TLS transport: the session-root rule, refused MCP servers, deny-by-default permission answers.

## 7. Questions for the review

1. Is SAS-MCA over the TLS 1.3 exporter sound as specified, in particular the binding of `E` to both certificates and the order of commit, nonce and reveal?
2. Is 20 bits (6 digits) enough for a one-shot pairing, or should it be 7–8 digits?
3. Should listen mode require an explicit interface rather than an address, to avoid listening on a public network by mistake?
4. Is `~/Quire` the right default root for remote clients, given that agents run with the person's full access anyway (§5.2)?

## Sources

- Vaudenay, "Secure Communications over Insecure Channels Based on Short Authenticated Strings", CRYPTO 2005 (SAS-MCA).
- Bluetooth Core Specification, Secure Simple Pairing, Numeric Comparison (the commitment and nonce order used in §4.4).
- RFC 8446 §7.5 (TLS 1.3 exporters); RFC 5705 (keying material exporters).
- RFC 9382 (SPAKE2) and draft-irtf-cfrg-cpace (CPace), the PAKE alternatives considered in §4.4.
