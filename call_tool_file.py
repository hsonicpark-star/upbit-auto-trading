import subprocess
import json
import sys
import os

def call_tool(connection, tool, args_file):
    with open(args_file, 'r', encoding='utf-8') as f:
        args = json.load(f)
        
    cmd = ["smithery.cmd", "tool", "call", connection, tool, json.dumps(args, ensure_ascii=False)]
    try:
        # Run and capture output as bytes
        result = subprocess.run(cmd, capture_output=True, check=False)
        
        # Try to decode stdout
        try:
            stdout_str = result.stdout.decode('utf-8')
        except UnicodeDecodeError:
            stdout_str = result.stdout.decode('cp949', errors='ignore')
            
        # Print to stdout with utf-8 encoding
        sys.stdout.buffer.write(stdout_str.encode('utf-8'))
        sys.stdout.buffer.flush()
        
        if result.stderr:
            try:
                stderr_str = result.stderr.decode('utf-8')
            except UnicodeDecodeError:
                stderr_str = result.stderr.decode('cp949', errors='ignore')
            sys.stderr.buffer.write(stderr_str.encode('utf-8'))
            sys.stderr.buffer.flush()
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python call_tool_file.py <tool> <args_json_file>")
        sys.exit(1)
    
    tool = sys.argv[1]
    args_file = sys.argv[2]
    call_tool("kis-code-assistant-mcp", tool, args_file)
