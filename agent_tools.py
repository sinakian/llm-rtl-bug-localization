import os
import re


def parse_log(log_path: str) -> str:
    """Extract the failing assertion + testbench line, and derive the FAILURE STAGE.
    The testbench checks reset -> fill -> readback in order and dies at the first failure,
    so the stage is a strong, explainable prior for the bug class."""
    if not os.path.exists(log_path):
        return f"Error: {log_path} not found."
    with open(log_path, "r") as f:
        text = f.read()

    assert_msg = ""
    tb_line = None
    for line in text.splitlines():
        if "AssertionError:" in line:
            assert_msg = line.split("AssertionError:", 1)[-1].strip()
        m = re.search(r'test_fifo\.py", line (\d+)', line)
        if m:
            tb_line = int(m.group(1))

    a = assert_msg.lower()
    if "empty" in a or "after reset" in a:
        stage = "RESET stage -- the empty flag is wrong immediately after reset"
        classes = "wrong_reset"
    elif "full" in a or "after 8 writes" in a:
        stage = "FILL stage -- the full flag never asserts after the FIFO is filled"
        classes = "off_by_one (full-flag comparison), or operator_flip on a write-side pointer/counter"
    elif "read" in a or "data_out" in a:
        stage = "READBACK stage -- a read returned the wrong data"
        classes = "stuck_at (data_out driven by a constant) OR operator_flip (a read/write pointer uses the wrong operator)"
    else:
        stage = "UNKNOWN stage"
        classes = "operator_flip, off_by_one, stuck_at, or wrong_reset"

    return (
        f"FAILING ASSERTION: {assert_msg or 'not found'}\n"
        f"TESTBENCH LINE: test_fifo.py:{tb_line if tb_line else '?'}\n"
        f"FAILURE STAGE: {stage}\n"
        f"CANDIDATE CLASSES (prior): {classes}"
    )


def read_span(file_path: str, start_line: int, end_line: int) -> str:
    if not os.path.exists(file_path):
        return f"Error: {file_path} not found."
    with open(file_path, "r") as f:
        lines = f.readlines()
    start, end = max(1, start_line), min(len(lines), end_line)
    return "\n".join([f"{i+1}: {lines[i].rstrip()}" for i in range(start - 1, end)])


def trace_signal(file_path: str, signal_name: str) -> str:
    if not os.path.exists(file_path):
        return f"Error: {file_path} not found."
    with open(file_path, "r") as f:
        lines = f.readlines()
    relevant = [f"{i+1}: {ln.rstrip()}" for i, ln in enumerate(lines) if signal_name in ln]
    return "\n".join(relevant) if relevant else f"No references to '{signal_name}' found."


def recursive_trace(file_path: str, initial_signal: str, depth: int = 2) -> str:
    if not os.path.exists(file_path):
        return f"Error: {file_path} not found."
    with open(file_path, "r") as f:
        lines = f.readlines()
    ignore = {"assign", "wire", "reg", "always", "posedge", "negedge", "clk", "rst", "if",
              "else", "begin", "end", "module", "endmodule", "input", "output", "parameter",
              "DEPTH", "WIDTH"}
    signals = {initial_signal}
    traced = set()
    for d in range(depth):
        new = set()
        for i, line in enumerate(lines):
            if any(re.search(rf"\b{s}\b", line) for s in signals):
                traced.add((i + 1, line.rstrip()))
                if d < depth - 1:
                    for w in set(re.findall(r"[a-zA-Z_]\w*", line)):
                        if w not in ignore and w not in signals:
                            new.add(w)
        signals.update(new)
    ordered = sorted(traced, key=lambda x: x[0])
    return "\n".join(f"{n}: {t}" for n, t in ordered) if ordered else f"No references to '{initial_signal}' found."


def ast_trace_signal(file_path: str, signal_name: str, top_module: str = "fifo") -> str:
    """Deterministic dataflow: find the source line(s) where a signal is ASSIGNED.

    Note: pyverilog's dataflow nodes do not reliably expose source line numbers across
    versions, so instead of its AST we use a targeted regex over the source that matches
    the signal on the left-hand side of an assignment ( '<=', '=', or 'assign ... ='  ).
    This is version-independent and returns exact line numbers for the line backstop."""
    if not os.path.exists(file_path):
        return f"Error: {file_path} not found."

    # Match: optional 'assign', the signal (with optional bit/index select), then <= or =
    # (but not ==). Anchored to the start of the statement so RHS uses don't match.
    pat = re.compile(
        rf"^\s*(assign\s+)?{re.escape(signal_name)}\s*(\[[^\]]*\])?\s*(<=|=)(?!=)"
    )

    hits = []
    with open(file_path, "r") as f:
        for i, line in enumerate(f, start=1):
            if pat.search(line):
                hits.append(f"Line {i}: {line.strip()}")

    if not hits:
        return f"No assignment to '{signal_name}' found."
    return "\n".join(hits)