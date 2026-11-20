"""Block every outgoing connection in a seeded test's child process.

On Windows, a new asyncio event loop builds its self-pipe with socket.socketpair(), which connects two of
its own sockets over the loopback address. On macOS and Linux socketpair() needs no connect. That one call
is let through, and nothing else.
"""
import socket


def deny_network(message):
    def denied(*args, **kwargs):
        raise RuntimeError(message)

    real_connect, real_socketpair = socket.socket.connect, socket.socketpair

    def socketpair(*args, **kwargs):
        socket.socket.connect = real_connect
        try:
            return real_socketpair(*args, **kwargs)
        finally:
            socket.socket.connect = denied

    socket.socket.connect = denied
    socket.socketpair = socketpair
