"""Test-only portability helpers. External network access remains forbidden."""
import errno
import ipaddress
import socket
from contextlib import contextmanager
from unittest.mock import patch

_CONNECT = socket.socket.connect
_CONNECT_EX = socket.socket.connect_ex


def _local(sock, address):
    if sock.family not in (socket.AF_INET, socket.AF_INET6):
        return False
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except (ValueError, TypeError, IndexError):
        return False


def connect_local_only(sock, address):
    if not _local(sock, address):
        raise AssertionError('Test attempted an external socket connection')
    return _CONNECT(sock, address)


def connect_ex_local_only(sock, address):
    if not _local(sock, address):
        raise AssertionError('Test attempted an external socket connection')
    return _CONNECT_EX(sock, address)


@contextmanager
def local_sockets_only():
    with patch.object(socket.socket, 'connect', connect_local_only), \
         patch.object(socket.socket, 'connect_ex', connect_ex_local_only):
        yield


def symlink_or_skip(test, link, target, *, is_directory=False):
    try:
        link.symlink_to(target, target_is_directory=is_directory)
    except OSError as error:
        if error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS, errno.ENOTSUP) or getattr(error, 'winerror', None) == 1314:
            test.skipTest('Symlinks require system support and permission')
        raise
