"""Shared config + DB connection."""
import os, pathlib
import psycopg

ROOT = pathlib.Path(__file__).resolve().parent.parent

def _load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env

ENV = _load_env()
APOLLO_KEY        = ENV["APOLLO_API_KEY"]
APOLLO_MASTER_KEY = ENV["APOLLO_MASTER_KEY"]
ANTHROPIC_KEY = ENV["ANTHROPIC_API_KEY"]
PGDSN         = ENV["PGDSN"]

# Models: Opus for the token-heavy research pass, Fable for the email write.
MODEL_RESEARCH = "claude-opus-5"
MODEL_WRITE    = "claude-fable-5"

SCORE_THRESHOLD = 70   # must match sql/001_schema.sql v_sendable

def db():
    return psycopg.connect(PGDSN, autocommit=True)
