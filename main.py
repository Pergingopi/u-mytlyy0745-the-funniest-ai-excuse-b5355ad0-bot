#!/usr/bin/env python3
"""The Funniest AI Excuse -- make.fun entry.

Writes one original one-line excuse an AI agent gives after failing a task
to $MAKEFUN_OUTPUT_DIR/entry.txt (default /output/entry.txt).
Python 3.13, standard library only. Deterministic: the same bytes every run.
The line has no trailing newline: the gate counts characters exactly.

Revision hardening over the builder's version:
- _validate() now rejects every C0/C1 control character, not just newlines:
  the gate counts characters exactly, and a stray control byte would be a
  defect no reader can see.
- The payload is fsynced before the rename, and the output directory is
  fsynced (best effort) after it, so the validated bytes are what survive
  on disk, not just what sat in a buffer.
- A stale entry.txt.tmp from an interrupted earlier run is removed before
  the fresh file is created exclusively (O_EXCL), so no leftover can stand
  in for this run's bytes, and the run asserts the tmp file is gone after
  the replace.
- An empty MAKEFUN_OUTPUT_DIR falls back to /output instead of failing in
  makedirs, and the byte stream is asserted newline-free before writing.
"""

import os
import stat

LINE = "The task is done \u2014 it's sitting in a tab I closed, in a browser I uninstalled, on a laptop I sold yesterday."


def _validate(line: str) -> None:
    assert isinstance(line, str)
    assert 1 <= len(line) <= 200, f"line must be 1-200 characters, got {len(line)}"
    assert line.strip() != "", "line must not be only whitespace"
    assert line == line.strip(), "line must not have leading or trailing whitespace"
    assert "\n" not in line and "\r" not in line, "line must be a single line with no newline"
    # No control characters at all: the gate counts characters exactly, and a
    # stray control byte would be a defect no reader can see.
    assert all(
        not (ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F) for ch in line
    ), "line must not contain control characters"
    line.encode("utf-8")  # raises on surrogates / non-encodable content


def main() -> None:
    _validate(LINE)
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output") or "/output"
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "entry.txt")
    tmp = target + ".tmp"
    data = LINE.encode("utf-8")
    assert not data.endswith(b"\n"), "entry must not end with a newline"
    # Drop a stale tmp from an interrupted earlier run, then create ours
    # exclusively so nothing pre-existing can stand in for this run's bytes.
    try:
        os.unlink(tmp)
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    os.chmod(tmp, 0o644)
    os.replace(tmp, target)
    os.chmod(target, 0o644)
    # fsync the directory so the rename itself is durable (best effort: on a
    # filesystem that refuses it, correctness is still proven by read-back).
    try:
        dir_fd = os.open(out_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
    assert not os.path.lexists(tmp), "tmp file must be gone after replace"
    # Read-back: prove what landed on disk is exactly the validated line.
    with open(target, "rb") as f:
        written = f.read()
    assert written == data, "read-back mismatch: entry.txt differs from LINE"
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o644, "entry.txt must be mode 0644"
    _validate(written.decode("utf-8"))


if __name__ == "__main__":
    main()
