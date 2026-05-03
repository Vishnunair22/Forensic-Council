import secrets, string

def hex64():
    return secrets.token_hex(32)

def alnum32():
    a = string.ascii_letters + string.digits
    return "".join(secrets.choice(a) for _ in range(32))

keys = {
    "SIGNING_KEY": hex64(),
    "JWT_SECRET_KEY": hex64(),
    "POSTGRES_PASSWORD": alnum32(),
    "REDIS_PASSWORD": alnum32(),
    "QDRANT_API_KEY": hex64(),
    "BOOTSTRAP_ADMIN_PASSWORD": alnum32(),
    "BOOTSTRAP_INVESTIGATOR_PASSWORD": alnum32(),
    "METRICS_SCRAPE_TOKEN": hex64(),
}
keys["DEMO_PASSWORD"] = keys["BOOTSTRAP_INVESTIGATOR_PASSWORD"]

for k, v in keys.items():
    print(f"{k}={v}")
