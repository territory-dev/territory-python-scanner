def raise_te(*a):
    raise TimeoutError


def setup_timeout(t):
    try:
        from signal import SIGALRM, alarm, signal

        signal(SIGALRM, raise_te)
        alarm(t)
    except Exception:
        print('failed to setup timeout')


def clear_timeout():
    try:
        from signal import alarm
        alarm(0)
    except Exception:
        pass
