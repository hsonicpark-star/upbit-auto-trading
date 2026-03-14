import subprocess
import json
import sys

def call_tool(connection, tool, args):
    cmd = ["smithery.cmd", "tool", "call", connection, tool, json.dumps(args, ensure_ascii=False)]
    try:
        # We need to capture the output carefully
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
        stdout, stderr = process.communicate()
        
        # Try to decode as utf-8
        try:
            output_str = stdout.decode('utf-8')
        except UnicodeDecodeError:
            output_str = stdout.decode('cp949', errors='ignore')
            
        print(output_str)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python call_tool_raw.py <tool> <args_json>")
        sys.exit(1)
    
    tool = sys.argv[1]
    args = json.loads(sys.argv[2])
    call_tool("kis-code-assistant-mcp", tool, args)
