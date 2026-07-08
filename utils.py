import json
import os
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path


getcontext().prec = 28


def D(value):
    return Decimal(str(value))


def q_down(value, increment):
    inc = D(increment)
    if inc <= 0:
        return D(value)
    return (D(value) / inc).to_integral_value(rounding=ROUND_DOWN) * inc


def dstr(value):
    return format(D(value).normalize(), "f")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def load_env(path=".env"):
    env_path = Path(path)
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))

