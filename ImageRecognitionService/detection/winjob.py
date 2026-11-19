"""Windows jobs, for the Detection Service's supervisor (supervisor.py).

A job is a group of processes Windows can kill together. The supervisor puts
each service it starts in a job of its own that is set to kill everything in it
when its last handle closes, which is when the supervisor ends, however it ends.
Ending a job by hand (`end_job`) kills the service and everything it started,
even the Run processes a service that has already gone left behind.
"""
import ctypes
import logging

log = logging.getLogger("detection.supervisor")

CREATE_SUSPENDED = 0x00000004
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def create_job():
    """A Windows job that kills every process in it when its last handle closes,
    which is when the supervisor ends, however: a stop, a crash, a kill from the
    Task Manager. Without it the service it started would live on, holding its
    port and the GPU, and the next supervisor's service could not start."""
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class _Extended(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", _Basic), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
    info = _Extended()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
                                            ctypes.byref(info), ctypes.sizeof(info)):
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject failed")
    return job


def die_with_me(process):
    """Puts a just-started, still suspended `process` in a job of its own that
    dies with the supervisor, so does everything it starts after (the service's
    Run processes). Answers the job, or None when Windows refused: logged, not
    raised, since the service runs either way, only unguarded against the
    supervisor's death. One job for each service, so `end_job` can kill what
    an old service left behind without touching the next one's."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    from ctypes import wintypes
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    job = None
    try:
        job = create_job()
        if not kernel32.AssignProcessToJobObject(job, int(process._handle)):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
        return job
    except OSError as e:
        if job:
            end_job(job)
        log.warning("The Detection Service will keep running if the supervisor is killed (Windows refused "
                    "the guard: %s)", e)
        return None


def end_job(job):
    """Kills every process in `job`, and closes it."""
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.TerminateJobObject(job, 1)
    kernel32.CloseHandle(job)


def resume(process):
    """A process started with CREATE_SUSPENDED, let go."""
    ctypes.WinDLL("ntdll").NtResumeProcess(ctypes.c_void_p(int(process._handle)))
