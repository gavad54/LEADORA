# Security Policy

## Supported scope
Security reports for the LEADORA MVP repository are welcome. Do not publish exploitable details or personal data in public issues. Contact the repository owner privately through GitHub's private vulnerability reporting feature if it is enabled.

## Current security limitations
- This is an MVP, not independently audited software.
- Account recovery, email verification, rate limiting, MFA, fine-grained roles, session revocation, and production monitoring are not implemented.
- The app uses a simple signed bearer token with a 12-hour expiry; it does not currently provide token revocation.
- SQLite storage requires durable, backed-up storage in a hosted deployment.
- Do not store sensitive or regulated personal, financial, health, or customer data until an independent security review is complete.

## Before production
1. Run dependency and static-analysis scans.
2. Review authentication, authorization, tenant isolation, input validation, and error handling.
3. Configure TLS, secret rotation, rate limits, monitoring, backups, and tested restore procedures.
4. Run a penetration test and privacy/legal review.
