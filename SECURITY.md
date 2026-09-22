# Security Policy

## Supported Versions

ByteRescue is currently an early-stage project. Security fixes are prioritized for the latest version on the `main` branch.

| Version | Supported |
| --- | --- |
| Latest `main` | Yes |
| Older development builds | Best effort |

## Reporting a Vulnerability

Please do **not** open a public GitHub issue for a suspected security vulnerability.

Instead, use GitHub's private vulnerability reporting feature when available, or contact the repository owner privately through GitHub.

Include:

- A clear description of the issue
- Affected version or commit
- Reproduction steps
- Expected and actual behavior
- Relevant logs or screenshots
- Any suggested mitigation

Please avoid including personal data, private files, disk images, credentials, or other sensitive information in a report.

## Data Safety

ByteRescue is intended for authorized storage analysis and recovery. Recovery operations can interact with sensitive user data. Always work on media you own or are authorized to examine.

When possible:

- Analyze a copy or disk image rather than the original media.
- Recover files to a different destination.
- Avoid unnecessary writes to the source device.
- Protect recovered data because it may contain sensitive information.

## Scope

This policy covers security issues in the ByteRescue source code, build configuration, release process, and official repository infrastructure.

Third-party Python packages should be reported to their respective maintainers when the issue originates outside ByteRescue.
