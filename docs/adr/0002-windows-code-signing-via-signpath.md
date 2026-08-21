Status: Accepted

# 0002. Windows code signing via SignPath Foundation

## Context

The unsigned Windows NSIS installer produced by the release pipeline (see ADR
0001) triggers a Microsoft SmartScreen "unknown publisher" warning on first
run, which had generated a real user complaint. A commercial Authenticode
certificate (EV or OV) that would suppress this warning costs money annually,
which is not viable for a solo-maintainer open source project with no
revenue. macOS signing/notarization is explicitly out of scope for this
project per the maintainer's decision (Apple's platform is not a priority for
them), and Linux has no equivalent problem: there is no OS-level gatekeeper
(nothing like SmartScreen or Gatekeeper) that blocks unsigned Linux binaries.
This decision is therefore scoped to Windows only.

## Options

- **Commercial Authenticode certificate (EV or OV)**: solves the SmartScreen
  warning directly and is the most conventional path, but costs real money
  every year with no free tier, which a solo-maintainer hobby project cannot
  sustain.
- **Azure Trusted Signing**: a cloud/subscription-based Microsoft signing
  service. Would also solve the warning, but is a paid, ongoing cloud
  subscription cost, same blocker as a commercial cert.
- **SignPath Foundation** (chosen): provides free Authenticode signing for
  qualifying open source projects (OSI-approved license, actively maintained,
  already publicly released). Requires submitting an application for
  approval, enabling MFA on both SignPath and GitHub accounts, and publishing
  a "Code Signing Policy" disclosure in the project's README naming the
  Authors, Reviewers, and Approvers roles required by SignPath's program
  terms. No monetary cost, but has an approval gate and an ongoing
  process/disclosure obligation.
- **Ship unsigned, rely on checksums and GPG-signed tags only**: gives a
  technical user a way to verify integrity, but does not suppress the
  SmartScreen warning for the actual complaint that triggered this decision,
  so it does not solve the problem being addressed.

## Decision

Apply to the SignPath Foundation program for free Windows Authenticode
signing. The `build-windows` job in `.github/workflows/release.yml` was wired
to call `signpath/github-action-submit-signing-request@v2` twice: once to
sign the PyInstaller-produced `FlowSnip.exe` before it is bundled into the
installer, and again to sign the final NSIS installer wrapper
(`FlowSnip-<version>-windows-setup.exe`) after `makensis` builds it. Both
calls are gated on a `release-signing` SignPath signing policy and read
`SIGNPATH_API_TOKEN` from repository secrets and `SIGNPATH_ORGANIZATION_ID`
from repository variables. The required Code Signing Policy disclosure was
published in `README.md`, listing Rajesh Subramanian as Author, Reviewer, and
Approver, plus a statement that FlowSnip does not transfer personal data to
SignPath as part of signing.

## Consequences

- Signing is presently non-functional in CI until the SignPath Foundation
  application is approved and the `SIGNPATH_API_TOKEN` secret and
  `SIGNPATH_ORGANIZATION_ID` variable are configured on the GitHub repository.
  Until then, the signing steps in `build-windows` fail closed (the job
  errors out) rather than silently skipping signing; this is intentional so
  that an unsigned release artifact is never published without the failure
  being visible.
- Because this is a solo-maintainer project, the same person fills the
  Author, Reviewer, and Approver roles that SignPath's program terms require
  to be distinct named roles; this is disclosed as-is in the README rather
  than worked around.
- macOS and Linux artifacts remain unsigned by design under this decision's
  scope, not by oversight: macOS signing/notarization is a separate,
  already-tracked follow-up (per ADR 0001), and Linux has no signing gate to
  solve.
- Once SignPath approval and credentials are in place, every tagged release
  build will produce a signed `FlowSnip.exe` and a signed NSIS installer with
  no further workflow changes required.
