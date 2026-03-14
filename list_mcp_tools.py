import subprocess
import sys
import json

def list_tools(connection):
    cmd = ["smithery.cmd", "tool", "list", connection, "--flat"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        for line in result.stdout.splitlines():
            try:
                data = json.loads(line)
                if data.get("type") == "tool":
                    print(f"Tool: {data.get('name')}")
            except:
                continue
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")

if __name__ == "__main__":
    list_tools("kis-code-assistant-mcp")
