# Security Policy

## Threat Model

`taiga-cli` is a lightweight, zero-dependency client-side CLI and AI agent skill. It runs locally on the user's machine to communicate with the Taiga.io REST API (or a self-hosted Taiga instance).

The threat model assumes:
- The local execution environment is trusted (the user's own workstation or container).
- The user holds legitimate credentials for their Taiga account.
- The CLI must not expose, forward, or leak credentials to any third-party hosts or unauthorized local users.

---

## Supported Versions

| Version | Supported |
| :--- | :--- |
| `0.1.x` | :white_check_mark: |
| `< 0.1.0` | :x: |

---

## Vulnerability Scope

### In-Scope (Eligible for Security Advisories)
- **Token or Credential Exfiltration:** Any path where Bearer tokens or passwords could be forwarded to unauthorized external domains (including cross-origin API calls or cross-domain HTTP redirect header leakage).
- **Insecure Transport:** Silent transmission of credentials over unencrypted HTTP without explicit user opt-in (`--insecure`).
- **Local File Permission Gaps:** Default cache or configuration directory creation with permissive modes that allow other unprivileged users on a shared multi-user machine to inspect cached tokens.
- **TLS/Certificate Verification Bypass:** Any unintentional degradation of system CA bundle validation or hostname verification.
- **Injection Flaws:** Vulnerabilities where malformed Taiga API responses could trigger unintended local code execution or file corruption.

### Out-of-Scope (Not Covered)
- **Compromised Local Machine:** If an attacker already has root/administrative access, is running processes under the same local UID with memory-inspection privileges, or has access via local malware, local token compromise is out of scope.
- **Server-Side Taiga Vulnerabilities:** Bugs, denial of service, or authentication flaws within the upstream Taiga.io server or self-hosted Taiga platform. Please report those to the [official Taiga project](https://taiga.io).
- **User-Specified Malicious Endpoints:** If a user explicitly configures `--url https://evil-server.com`, sending credentials to that configured endpoint is user-instructed behavior.
- **Brute Force & Rate Limiting:** Rate limiting is enforced by the upstream Taiga server, not by this local client.

---

## Reporting a Vulnerability

Please do **NOT** file public GitHub issues for security vulnerabilities.

### Preferred Method: GitHub Private Vulnerability Reporting
Submit a report via GitHub Security Advisories:
[https://github.com/aliepratama/taiga-cli/security/advisories/new](https://github.com/aliepratama/taiga-cli/security/advisories/new)

### Alternative Method: Direct Email
If you are unable to use GitHub Security Advisories, send an encrypted or plain report to:
- **Contact:** `me@aliepratama.com`
- **Subject:** `[SECURITY] taiga-cli vulnerability report`

Please include:
1. Steps to reproduce or a minimal proof of concept.
2. CLI version / git commit SHA.
3. Operating system and Python version.
4. Potential security impact.

---

## Response Timeline & SLA

- **Initial Response:** Within 48 hours of receipt.
- **Triage & Assessment:** Within 5 business days.
- **Fix & Advisory Release:** Coordinated disclosure with the reporter once a patch is verified.

---

## Coordinated Disclosure & Safe Harbor

We support responsible security research. We will not pursue legal action against researchers who:
- Give reasonable time to address the issue before public disclosure.
- Make a good-faith effort to avoid privacy violations, data destruction, and service interruption.
- Do not exploit a vulnerability beyond what is needed to prove its existence.
