from __future__ import annotations

import os
import pwd
import grp


def drop_privileges(user: str | None = None, group: str | None = None) -> None:
    if os.getuid() != 0:
        return
    if group:
        gid = grp.getgrnam(group).gr_gid
        os.setgid(gid)
    if user:
        uid = pwd.getpwnam(user).pw_uid
        os.setuid(uid)
