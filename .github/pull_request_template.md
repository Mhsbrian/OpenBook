Describe the behavior changed and the validation performed.

## Release handoff

Complete this for image-affecting work; otherwise state `No image impact` and why.
The AnyBook release coordinator maintains the queue in Multica ANAL-232.

- Source issue:
- Track and target (Ruby / AOSP / shared / unknown):
- Full source commit and dependencies:
- Changes intended for release:
- Pinned inputs for the release (artifact and SHA-256 each):
- Tests run on exactly those bytes, and the `anybook-handoff/1` file listing them:
- Remaining limitations:
- Boot / layout / data / recovery / installer-pin impact:
- Development image, if built: parent image identity, artifact hash and test status:

Do not build a production candidate, payload or stick image here, or rehearse the laptop update:
the release does those once and cites matching checks from this handoff (`docs/release-control.md`,
"Test once").
- Release disposition: awaiting intake / queued / deferred / included in a named plan:

A PR, development image or “in review” status is not a release approval.
The coordinator records a numbered release plan and separate build/device-write
approvals. See `docs/release-control.md`. Never include private images or owner data.
