import os

def parse_log(log_path: str) -> str:
    if not os.path.exists(log_path): return f"Error: {log_path} not found."
    with open(log_path, 'r') as f: lines = f.readlines()
    events = []
    for i, line in enumerate(lines):
        if "FAIL" in line or "Error" in line or "Assertion failed" in line:
            start, end = max(0, i - 2), min(len(lines), i + 3)
            events.append("".join(lines[start:end]))
    return "\n".join(events) if events else "No obvious failure keywords found."

def read_span(file_path: str, start_line: int, end_line: int) -> str:
    if not os.path.exists(file_path): return f"Error: {file_path} not found."
    with open(file_path, 'r') as f: lines = f.readlines()
    start, end = max(1, start_line), min(len(lines), end_line)
    return "\n".join([f"{i+1}: {lines[i].rstrip()}" for i in range(start - 1, end)])

def trace_signal(file_path: str, signal_name: str) -> str:
    """Returns only the lines in the Verilog file that interact with the target signal."""
    if not os.path.exists(file_path): 
        return f"Error: {file_path} not found."
        
    with open(file_path, 'r') as f: 
        lines = f.readlines()
        
    relevant_lines = []
    for i, line in enumerate(lines):
        # Basic substring match to find where the signal is used or assigned
        if signal_name in line:
            relevant_lines.append(f"{i+1}: {line.rstrip()}")
            
    return "\n".join(relevant_lines) if relevant_lines else f"No references to '{signal_name}' found."    
