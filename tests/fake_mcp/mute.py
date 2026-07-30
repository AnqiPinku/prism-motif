"""mute 假 server：读 stdin 但对一切保持沉默——initialize 永远等不到应答。"""
import sys

for _ in sys.stdin:
    pass
