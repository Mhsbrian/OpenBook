# Quire: pairing a second computer (design, for review before it is built)

As of 2026-10-19. Part of Q4 (ANAL-218). Status: **design only, revision 2**. Nothing here is implemented: the issue requires the Checker's review (ANAL-217) first. `docs/quire.md` §4 links here.

Revision 2 answers the Checker's Hold on revision 1 (ANAL-218, 2026-10-18):
- **Resumption skipped the pin check.** Go's `VerifyPeerCertificate` doesn't run on resumed connections, so a revoked client could resume. Now neither side resumes, and the live pin list is checked on every connection, resumed ones included (§4.3, §4.5).
- **The identity binding was wrong.** The TLS 1.3 exporter doesn't cover the client's certificate, and the commitment covered only the nonce. Now a canonical transcript with both pins goes into the exporter's context, the commitment and the code. Each side must have completed certificate proof of possession first, and the code's digits are defined (§4.4).
- The review's answers on the code's length, the listening address and the root are in §4.1, §4.4 and §7.

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
- ADDR must be a concrete local address. Listening on every address (`0.0.0.0`, `::`) takes a separate, explicit flag, `--listen-any`. mDNS advertises only on the network of the chosen address. An interface name is not required.
- The vsock listener in the Linux environment is unchanged and separate.
- In listen mode, the session root defaults to `~/Quire`, not `$HOME`. A remote client's sessions stay in that folder unless the person passes `--root`. `quired` says when it starts that this only organizes session folders: agents still run with the person's full access (`docs/quire.md` §5.2); it is not a sandbox.
- MCP servers named by the client are refused, as in the guest.

### 4.2 Identities

- Each side has a long-term key pair. The computer keeps an ECDSA P-256 key in `~/.config/quired/identity.key` (0600). Quire keeps its key in Android Keystore, non-exportable.
- Each side wraps its key in a self-signed X.509 certificate. Certificates are not checked against any CA. **A peer is identified only by the SHA-256 of its SubjectPublicKeyInfo (its pin).**
- Why P-256: Android Keystore and Go's `crypto/tls` both handle it natively, so neither side needs crypto outside its standard library.

### 4.3 The channel: TLS 1.3 with both pins

- Every connection is TLS 1.3 only, with mutual authentication: both sides present their certificates and prove they hold the key (TLS 1.3 `CertificateVerify`). ALPN is `quire-acp/1` for sessions and `quire-pair/1` for pairing (§4.4); a listener accepts only its own.
- **No resumption, in v1.** The computer issues no session tickets (Go `SessionTicketsDisabled: true`). TLS 1.3 resumes only from a ticket, and TLS 1.2 is refused, so no client can resume. Quire also keeps no client session cache: a fresh `SSLContext` per connection. Each of the two rules would prevent resumption on its own. Both are required, so that one mistake doesn't reopen it.
- **The pin check runs on every connection,** against the live list of paired peers, read when the connection is made (§4.5). There is no plaintext mode and no fallback.
  - **The computer (TLS server):** `tls.Config{MinVersion: tls.VersionTLS13, ClientAuth: tls.RequireAnyClientCert, SessionTicketsDisabled: true, NextProtos: ..., VerifyConnection: check}`. Go runs `VerifyConnection` on every connection, resumed ones included; `VerifyPeerCertificate` is skipped on resumption, so it is not used ([Go `crypto/tls` `Config`](https://pkg.go.dev/crypto/tls#Config), accessed 2026-10-18). `check` refuses a resumed connection (`DidResume`), a wrong ALPN, and a client whose pin is not in the live list.
  - **Quire (TLS client):** the TrustManager accepts any self-signed certificate. The pin check runs on the finished session (`SSLSocket.getSession().getPeerCertificates()`) for every connection, before the first ACP byte. A TrustManager is not consulted on resumption, so the check cannot live only there. The KeyManager uses the Keystore key.
- ACP's newline-delimited JSON runs inside, unchanged.
- **An unpaired client** is refused after the TLS handshake, with the same alert and timing as a bad certificate. `quired` logs the attempt with the peer's pin.

### 4.4 Pairing: a 6-digit code compared on both screens

Pairing is the one moment when neither side knows the other's pin. It uses short-authentication-string comparison with a commitment (SAS-MCA, the scheme behind Bluetooth's numeric comparison). It needs only what TLS already gives.

**Roles.** The computer is B, the TLS server. Quire is A, the TLS client. Every value below is computed by each side from its own view of its own TLS connection.

1. On the computer, the person runs `quired pair`. For 5 minutes it accepts **one** unpinned client, with ALPN `quire-pair/1`. It advertises `_quire._tcp` over mDNS on the listening address's network, with the computer's name and the first 4 bytes of its pin in the TXT record.
2. In Quire, the person chooses **Pair a computer** and picks the computer from the list, or types its address.
3. **The handshake must be complete first.** The two sides complete a TLS 1.3 handshake with their certificates; the pins are not checked yet. The handshake includes both `CertificateVerify` messages and both `Finished` messages, so each side has proved it holds the key behind its certificate. Neither side sends or accepts a pairing message on a connection whose handshake is not complete, or that was resumed (`DidResume`, or `SSLSession` reuse on Android).
4. **The transcript.** Each side builds the same canonical transcript `T` from its own view. Each field is a 2-byte big-endian length, then the bytes:

   ```text
   T = len‖"quire-pairing"  ‖  len‖0x01 (version)  ‖  len‖"quire-pair/1" (the ALPN)
     ‖ len‖"server" ‖ len‖pinB   (SHA-256 of the computer's SubjectPublicKeyInfo, from its TLS certificate)
     ‖ len‖"client" ‖ len‖pinA   (SHA-256 of Quire's SubjectPublicKeyInfo, from its TLS certificate)
   ```

   `pinB` and `pinA` are always in this order, server first. Each side takes its own pin from its own key, and the peer's pin from the certificate the peer proved in step 3.
5. **The exporter, bound to T.** `E = TLS-Exporter("EXPORTER-quire-pairing-v1", SHA-256(T), 32)` (Go `ConnectionState.ExportKeyingMaterial`; Android `android.net.ssl.SSLSockets.exportKeyingMaterial`). In TLS 1.3 the exporter secret is derived from the transcript up to the server's `Finished`, before the client's certificate ([RFC 8446 §7.1](https://www.rfc-editor.org/rfc/rfc8446.html#section-7.1), §7.5). So `E` alone binds the server's identity and this connection, but not Quire's. Quire's identity is bound through `T`: in the exporter's context, the commitment and the code.
6. **Nonces.** `Na` and `Nb` are 32 bytes each, from the platform's CSPRNG (Go `crypto/rand`, Android `SecureRandom`), new for each pairing.
7. **Messages,** inside the channel, as JSON lines with base64url values, in this order only:
   - **Commit, B → A:** `Cb = SHA-256("quire-commit-v1" ‖ SHA-256(T) ‖ E ‖ Nb)`.
   - **Nonce, A → B:** `Na`, sent only after `Cb` has arrived.
   - **Reveal, B → A:** `Nb`, sent only after `Na` has arrived. A recomputes `Cb` from its own `T` and `E` and stops if it differs.
8. **The code.** `h = SHA-256("quire-sas-v1" ‖ SHA-256(T) ‖ E ‖ Na ‖ Nb)`. The code is the first 8 bytes of `h`, read as a big-endian unsigned 64-bit integer, modulo 10^6, written as 6 decimal digits with leading zeros. 2^64 is not a multiple of 10^6, but the bias is below 10^-13, so each code has a probability of 10^-6.
9. **Both screens show the 6 digits.** The person confirms on both: Quire's dialog, and `quired pair`'s prompt.
10. Each side stores the other's pin only once both have confirmed and each has told the other so over the channel. Otherwise nothing is stored.

**One attempt per pairing.** A pairing window serves one attempt, whatever happens to it: a mismatch, a "No", a timeout, a disconnect or a malformed message each end it, and `quired pair` exits. The limit is global, not per address, so a disconnect can't be used to try again. In Quire, each **Pair a computer** is one attempt too. Another try needs the person to start pairing again on both sides.

#### Why it holds

An active attacker M in the middle can't relay one TLS connection through: it doesn't know the handshake keys. So it runs two: one with Quire, where it poses as the computer with its own key, and one with the computer, where it poses as Quire with its own key. The two connections have different exporters and different transcripts. For the person to see the same digits on both screens, M needs `code(T1, E1, Na, Nb') = code(T2, E2, Na', Nb)`. Here `Na'` and `Nb'` are the values M chose for each side, and `Na` and `Nb` are the real sides' random nonces.

- **M deals with Quire first.** M has to send Quire a commitment, and so fix `Nb'`, before Quire sends `Na`. Then M sends the computer some `Na'`, and only then does the computer reveal `Nb`. Quire's code is fixed once M has `Na`. The computer's code still depends on `Nb`, a random value M sees only after choosing `Na'`. So the two codes match with probability 10^-6.
- **M deals with the computer first.** M can finish with the computer and learn its code. It then has to commit to `Nb'` for Quire before it sees Quire's `Na`. The commitment is binding: M made it itself, so revealing a different `Nb'` afterwards means finding a SHA-256 collision. Quire's code then depends on a random `Na` that M couldn't choose, so again 10^-6.
- **Identity substitution.** Whatever certificates M presents, each side's `T` holds the pins actually proved on its own connection. The code covers `T`, so the digits the person confirms are about exactly the pins each side will store. M can't confirm one identity and get another stored. The digits match only by the 10^-6 chance above. The commitment covers `T` and `E` too, so a commitment from one connection is useless on another.
- **Replay and reflection.** `E` is new for each connection and the nonces are new for each pairing. The roles are fixed by the TLS roles and written into `T`, so neither side's messages can be sent back to it.
- **Offline guessing.** M gets no value it could test candidate codes against: the code depends on nonces that are committed or revealed only in order. Each pairing is one online try at 10^-6, which the person sees fail.

**Why not a code typed on the other screen.** A short code typed into Quire and used as a pre-shared key (Noise `NNpsk0`, or TLS-PSK) is open to offline guessing. An active attacker who poses as the computer once can test every code afterwards. A PAKE (SPAKE2, CPace) fixes that, but Go and Android would each need group arithmetic their standard libraries don't expose. SAS-MCA gives the same guarantee with the person's eyes and stock TLS.

### 4.5 Limits and revocation

- `quired pair` serves one pairing and then exits. A wrong confirmation, a mismatch or a timeout ends it.
- Unpaired connections are rate-limited: 5 per minute per address, with backoff.
- On the computer, `quired pair --list` and `quired pair --forget ID` manage pairings. Pins live in `~/.config/quired/paired.json` (0600). In Quire, **Settings › Quire › Paired computers › Forget** does the same.
- **Forgetting a device takes effect at once, on both sides:**
  - **On the computer:** `serve --listen` reads `paired.json` at every handshake (§4.3) and watches it. On any change, it closes every open connection whose peer pin is no longer listed, within a second. That includes connections started before the change.
  - **In Quire:** Forget closes the connection to that computer, and the next connection fails the pin check.
  - Nothing is resumed (§4.3), so no cached session or ticket can outlive a Forget on either side.
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

1. **A MITM simulation.** A relay between Quire's code and `quired pair` runs two TLS sessions and plays every strategy it can within the protocol: both message orders (Quire first, the computer first), its own certificates on either side or both, a commitment copied from the other connection, and a reflected message. Pairing must never complete with matching digits except by chance. That is checked statistically, with the code shortened to 2 digits for the test, where it should match about once in 100 tries.
2. **Unpaired or forgotten clients.** An unpaired client and a forgotten client are both refused after the handshake, with identical alert and timing, and nothing reaches `internal/serve`.
3. **No resumption, and revocation.** A test client that keeps a session cache, run against a test server built with tickets on:
   - after the computer forgets the client, the client is refused, whether it tries to resume or not (`VerifyConnection` sees resumed connections too);
   - after Quire forgets the computer, Quire refuses it, also on a resumed session;
   - the product server issues no ticket at all;
   - an open connection is closed within a second of either side's Forget.
4. **Proof of possession first.** A pairing message before the handshake completes, or on a resumed connection, ends the pairing.
5. **The code.** Fixed test vectors for `T`, `E`, the commitment and the code, the same in Go and Kotlin. The code's distribution over 10^6 random inputs shows no bias beyond chance. A disconnect, a malformed message or a timeout each use up the window.
6. **A changed pin.** Quire refuses to connect and says why.
7. **The pairing window.** It closes after one pairing, after 5 minutes, and after a mismatch.
8. **No plaintext.** No TLS version below 1.3, and no connection without the listener's own ALPN (`quire-acp/1` or `quire-pair/1`).
9. **The listening address.** A wildcard address is refused without `--listen-any`; mDNS stays on the chosen network.
10. **Rate limits** hold.
11. **No secrets in logs.** Neither side logs key material, exporters or nonces; pins are logged truncated.
12. **The Q1 contract still holds** over the TLS transport: the session-root rule, refused MCP servers, deny-by-default permission answers.

## 7. The review's answers (revision 1), and questions for revision 2

The Checker's answers to revision 1's questions (ANAL-218, 2026-10-18), and what changed:

1. **Is SAS-MCA over the exporter sound?** Not as specified: resumption skipped the pin check, and the exporter doesn't cover the client's certificate. Revised in §4.3 and §4.4.
2. **Digits.** Six are enough with one attempt per explicit pairing action, disconnects and aborts included, and a defined uniform decimal mapping. That is the "One attempt per pairing" rule and step 8 of §4.4: about 10^-6 per attempt.
3. **Interface or address.** A concrete local address is enough. A wildcard needs its own explicit choice, and discovery stays on the chosen network (§4.1).
4. **Root.** `~/Quire` is a sensible default, with the warning that it organizes folders and is no sandbox (§4.1).

For revision 2:

1. Is the construction in §4.4 sound as written, including "Why it holds"? That covers the transcript `T`, the exporter context `SHA-256(T)`, the commitment over `T`, `E` and `Nb`, the code over `T`, `E`, `Na` and `Nb`, and proof of possession before any pairing message.
2. Does §4.3 close resumption, given both rules (no tickets, no client cache) and the pin check on every connection? And are the revocation tests in §6 enough?

## Sources

- Vaudenay, "Secure Communications over Insecure Channels Based on Short Authenticated Strings", CRYPTO 2005 (SAS-MCA).
- Bluetooth Core Specification, Secure Simple Pairing, Numeric Comparison (the commitment and nonce order used in §4.4).
- RFC 8446 §7.1 (the exporter secret's place in the key schedule) and §7.5 (TLS 1.3 exporters); RFC 5705 (keying material exporters).
- Go `crypto/tls`: `Config.VerifyConnection`, `VerifyPeerCertificate`, `SessionTicketsDisabled`, `ConnectionState.ExportKeyingMaterial` (https://pkg.go.dev/crypto/tls, accessed 2026-10-18).
- Android `android.net.ssl.SSLSockets.exportKeyingMaterial` (https://developer.android.com/reference/android/net/ssl/SSLSockets, accessed 2026-10-18).
- RFC 9382 (SPAKE2) and draft-irtf-cfrg-cpace (CPace), the PAKE alternatives considered in §4.4.
