# Reviewer Mode

This project provides a reviewer-friendly Docker mode for the public SoftwareX/Zenodo artifact.

## Purpose

The public archive must be runnable without private SMTP credentials. In reviewer mode, the registration email-verification flow is replaced by a fixed local verification code.

## Default Docker Behavior

Reviewer mode is enabled by default in `docker-compose.yml`:

```env
REVIEWER_MODE=true
REVIEWER_VERIFICATION_CODE=000000
```

Start the complete stack from the repository root:

```bash
docker compose up --build
```

Then open:

- Frontend: `http://localhost:5174`
- Backend API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

## Registration Steps

1. Open `http://localhost:5174`.
2. Switch to the registration tab.
3. Enter a username, email address, and password.
4. Click the verification-code send button.
5. Enter this fixed reviewer verification code:

```text
000000
```

6. Submit the registration form.

The registration page also displays a reviewer-mode note beside the verification-code field.

## SMTP Mode

To test the real email flow instead of reviewer mode:

```env
REVIEWER_MODE=false
```

Then provide valid local SMTP variables in `.env`:

```env
SMTP_HOST=
SMTP_PORT=465
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_USE_SSL=true
```

Do not commit real SMTP credentials to the public package.
