"""SecureWise scanning engines package.

Each engine tries a real tool via subprocess when available on PATH, and
falls back to a lightweight, still-meaningful, in-process engine when the
real tool is not installed. See README for which tools are available in a
given environment.
"""
