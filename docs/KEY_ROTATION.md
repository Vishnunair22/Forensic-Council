# SIGNING_KEY Rotation Policy

## Policy

The `SIGNING_KEY` in `.env` is used to generate ECDSA P-256 keys that sign all forensic reports and chain-of-custody entries. Compromise of this key allows an attacker to forge reports.

**Rotation schedule: annually, or immediately on suspected compromise.**

---

## Rotation Procedure

### 1. Generate a new key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Update `.env`

```bash
SIGNING_KEY=<new_value_from_step_1>
```

### 3. Restart the backend

```bash
docker compose -f infra/docker-compose.yml --env-file .env up -d --force-recreate backend
```

### 4. Verify

```bash
curl -s http://localhost:8000/health | python -m json.tool
# Should return "status": "healthy"
```

### 5. Re-sign existing reports (optional but recommended)

All reports signed with the old key remain valid â€” the signature is verified against the key that was active at signing time. However, for maximum audit integrity, re-sign critical reports:

```bash
# List reports signed with old key
psql $DATABASE_URL -c "SELECT report_id, signed_at FROM forensic_reports WHERE signing_key_fingerprint != '<new_fingerprint>' ORDER BY signed_at DESC LIMIT 50;"

# Re-sign via API (implement a /admin/resign endpoint if needed)
```

### 6. Archive the old key fingerprint

Record the old key fingerprint in your security audit log:

```
SIGNING_KEY rotated on 2026-03-30
Old fingerprint: <sha256_of_old_key>
New fingerprint: <sha256_of_new_key>
Reason: annual rotation
Authorized by: <admin_name>
```

---

## Emergency Rotation (Suspected Compromise)

If you suspect the `SIGNING_KEY` has been leaked:

1. Rotate immediately â€” do not wait for the annual schedule
2. Invalidate all active JWT tokens: `redis-cli FLUSHDB` (if Redis stores blacklists)
3. Audit all reports signed since the suspected compromise date
4. Notify stakeholders that reports signed between dates X and Y may need re-verification

---

## Automation

Add to your CI/CD or cron to check key age:

```bash
#!/bin/bash
# check_key_age.sh â€” run monthly via cron
KEY_FILE="/path/to/.env"
LAST_MODIFIED=$(stat -c %Y "$KEY_FILE" 2>/dev/null || stat -f %m "$KEY_FILE")
NOW=$(date +%s)
AGE_DAYS=$(( (NOW - LAST_MODIFIED) / 86400 ))

if [ "$AGE_DAYS" -gt 365 ]; then
  echo "WARNING: SIGNING_KEY is $AGE_DAYS days old. Rotate annually."
  # Send alert to your notification system
fi
```

