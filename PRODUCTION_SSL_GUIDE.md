# EduMi2 Production SSL Setup Guide (Option A — Let's Encrypt)

This guide walks you through deploying **Let's Encrypt SSL Certificates** for `eclass.dei.ac.in` on your Ubuntu server.

Using Let's Encrypt ensures:
- **Zero "Not Secure" browser warnings** across all devices (Windows, Android, iOS, macOS, Linux).
- **Fully functional Incognito Mode** with no blank screens or blocked WebSocket/camera streams.
- **Automatic Certificate Renewal** without manual maintenance.

---

## Prerequisites

1. **Public IP & DNS Routing**: Ensure `eclass.dei.ac.in` and `www.eclass.dei.ac.in` point to your Ubuntu server's public IP address in DNS.
2. **Open Firewall Ports**: Ensure ports `80` (HTTP) and `443` (HTTPS) are publicly accessible.

---

## Method 1: Automatic Setup via `deploy.sh` (Recommended)

When deploying or updating your application on Ubuntu, pass the `--letsencrypt` flag to `deploy.sh`:

```bash
sudo bash deploy.sh --domain eclass.dei.ac.in --email admin@dei.ac.in --letsencrypt
```

### What this automatically does:
1. Installs `certbot` and `python3-certbot-nginx`.
2. Issues a trusted SSL/TLS certificate for `eclass.dei.ac.in` and `www.eclass.dei.ac.in`.
3. Copies fullchain and private key files into `./certs/edumi.crt` and `./certs/edumi.key`.
4. Hardens `.env` with secure HTTPS settings:
   - `SECURE_SSL_REDIRECT=True`
   - `SESSION_COOKIE_SECURE=True`
   - `CSRF_COOKIE_SECURE=True`
5. Sets up auto-renewal via `certbot.timer` and registers Nginx auto-reload hooks.

---

## Method 2: Standalone SSL Provisioner Script

If your application is already deployed and you only want to install or renew Let's Encrypt SSL certificates:

```bash
sudo bash scripts/setup_letsencrypt.sh --domain eclass.dei.ac.in --email admin@dei.ac.in
```

---

## Verifying SSL & Incognito Mode

### 1. Verify Certificate Trust
Open your browser and visit:
```text
https://eclass.dei.ac.in
```
Look for the **green padlock / Secure** indicator next to the URL. Click the padlock to view certificate details issued by **Let's Encrypt Authority**.

### 2. Verify Incognito Mode
1. Open a **New Incognito Window** (`Ctrl + Shift + N` or `Cmd + Shift + N`).
2. Visit `https://eclass.dei.ac.in`.
3. Verify that the homepage, login form, LiveKit video streams, and camera feeds load without any SSL bypass prompts or blank pages.

---

## Maintenance & Testing Auto-Renewal

Let's Encrypt certificates are valid for 90 days. EduMi2 automatically enables `certbot.timer` to renew certificates 30 days before expiration.

To manually test the auto-renewal process at any time:
```bash
sudo certbot renew --dry-run
```

To check certificate expiration status:
```bash
sudo certbot certificates
```
