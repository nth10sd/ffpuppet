# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import os

from psutil import AccessDenied, NoSuchProcess

from .helpers import get_processes

__author__ = "Tyson Smith"
__credits__ = ["Tyson Smith"]


class Check(object):
    """
    Check base class
    """
    name = None

    def __init__(self):
        self.message = None


    def check(self):
        """
        Implement a check that returns True when the abort conditions are met.
        """
        raise NotImplementedError("check() needs to be implemented!")


    def dump_log(self, dst_fp):
        if self.message is not None:
            dst_fp.write(self.message.encode("utf-8", "ignore"))


class CheckLogContents(Check):
    """
    CheckLogContents will search through the browser logs for a token.
    """
    buf_limit = 0x20000  # 128KB
    name = "log_contents"
    def __init__(self, log_files, search_tokens):
        assert log_files, "log_files is empty"
        assert search_tokens, "search_tokens is empty"
        super(CheckLogContents, self).__init__()
        self.logs = list()
        for log_file in log_files:
            self.logs.append({"fname": log_file, "line_buf": "", "offset": 0})
        self.tokens = search_tokens


    def check(self):
        for log in self.logs:
            try:
                # check if file has new data
                if os.stat(log["fname"]).st_size <= log["offset"]:
                    continue
                # collect new data
                with open(log["fname"], "r") as scan_fp:
                    scan_fp.seek(log["offset"], os.SEEK_SET)
                    data = scan_fp.read(self.buf_limit)
                    log["offset"] = scan_fp.tell()
            except (IOError, OSError):
                # log does not exist
                continue
            # prepend chunk of previously read line to data
            if log["line_buf"]:
                if len(log["line_buf"]) > self.buf_limit:
                    # trim if we are getting huge lines
                    log["line_buf"] = log["line_buf"][self.buf_limit * -1:]
                data = "".join([log["line_buf"], data])
            for token in self.tokens:
                match = token.search(data)
                if match:
                    self.message = "TOKEN_LOCATED: %s\n" % match.group()
                    return True
            try:
                log["line_buf"] = data.rsplit("\n", 1)[1]
            except IndexError:
                log["line_buf"] = data
        return False


class CheckLogSize(Check):
    """
    CheckLogSize will check the total file size of the browser logs.
    """
    name = "log_size"
    def __init__(self, limit, stderr_file, stdout_file):
        super(CheckLogSize, self).__init__()
        self.limit = limit
        self.stderr_file = stderr_file
        self.stdout_file = stdout_file


    def check(self):
        err_size = os.stat(self.stderr_file).st_size
        out_size = os.stat(self.stdout_file).st_size
        total_size = err_size + out_size
        if total_size > self.limit:
            self.message = "".join([
                "LOG_SIZE_LIMIT_EXCEEDED: %s\n" % format(total_size, ","),
                "Limit: %s (%dMB)\n" % (format(self.limit, ","), self.limit/1048576),
                "stderr log: %s (%dMB)\n" % (format(err_size, ","), err_size/1048576),
                "stdout log: %s (%dMB)\n" % (format(out_size, ","), out_size/1048576)])
        return self.message is not None


class CheckMemoryUsage(Check):
    """
    CheckMemoryUsage used limit the about of memory used by the browser process.
    """
    name = "memory_usage"
    def __init__(self, pid, limit):
        super(CheckMemoryUsage, self).__init__()
        self.limit = limit
        self.pid = pid


    def check(self):
        """
        Use psutil to check the amount of memory in use by the process with the
        matching self.pid.
        """
        procs = get_processes(self.pid)
        proc_info = list()
        total_usage = 0
        for proc in procs:
            try:
                cur_rss = proc.memory_info().rss
                total_usage += cur_rss
                proc_info.append((proc.pid, cur_rss))
            except (AccessDenied, NoSuchProcess):
                pass
        if total_usage >= self.limit:
            msg = [
                "MEMORY_LIMIT_EXCEEDED: %s\n" % format(total_usage, ","),
                "Limit: %s (%dMB)\n" % (format(self.limit, ","), self.limit/1048576),
                "Parent PID: %d\n" % self.pid]
            for pid, usage in proc_info:
                msg.append("-> PID %6d: %s\n" % (pid, format(usage, "14,")))
            self.message = "".join(msg)
        return self.message is not None
