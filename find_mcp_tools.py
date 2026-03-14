import subprocess
import sys
import json

def find_tools(connection, query):
    cmd = ["smithery.cmd", "tool", "find", connection, query]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python find_mcp_tools.py <query>")
        sys.exit(1)
    find_tools("kis-code-assistant-mcp", sys.argv[1])
