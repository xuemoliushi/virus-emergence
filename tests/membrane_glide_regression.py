"""Compatibility entry: the former glide card has been replaced by infection relay."""
from infection_relay_regression import CASES, FIXTURE, ROOT, SETUP, GROWTH_SETUP, EXTRA, LuaRuntime, run

if __name__ == '__main__':
    raise SystemExit(0 if run() else 1)
