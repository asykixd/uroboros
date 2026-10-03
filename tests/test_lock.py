import os

from uroboros.lock import InstanceLock


def test_second_instance_is_rejected(tmp_path):
    path = tmp_path / "uroboros.lock"
    first, second = InstanceLock(path), InstanceLock(path)
    assert first.acquire()
    assert not second.acquire()
    first.release()
    assert second.acquire()
    second.release()


def test_owner_pid_is_written(tmp_path):
    lock = InstanceLock(tmp_path / "uroboros.lock")
    assert lock.acquire()
    lock.release()
    assert lock.owner_pid() == str(os.getpid())
