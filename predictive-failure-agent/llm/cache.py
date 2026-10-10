import hashlib
import json


def cache_key(model, evidence, settings):
    return hashlib.sha256(json.dumps({"schema_version": 1, "model": model, "evidence": evidence, "settings": settings}, sort_keys=True).encode()).hexdigest()
