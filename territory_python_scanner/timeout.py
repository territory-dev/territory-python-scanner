setup_fail_logged = False


def raise_te(*a):
    raise TimeoutError


def setup_timeout(t):
    global setup_fail_logged

    try:
        from signal import SIGALRM, alarm, signal

        signal(SIGALRM, raise_te)
        alarm(t)
    except Exception:
        if setup_fail_logged:
            return
        setup_fail_logged = True
        print('failed to setup timeout')


def clear_timeout():
    try:
        from signal import alarm
        alarm(0)
    except Exception:
        pass
