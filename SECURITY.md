# Security Policy

## Supported versions

Only the latest release on `main` receives security fixes.

## Reporting

Use GitHub’s private **Report a vulnerability** flow. Do not open public issues
for suspected credential leaks, authentication bypasses, or order-forgery bugs.
We will acknowledge reports within 5 business days and target coordinated
disclosure within 90 days.

The gateway supports API-key authentication, but it must still run on a private
network or behind an authenticated reverse proxy/mTLS boundary. Credential
leaks, authentication bypasses, and forged trading actions are in scope.
