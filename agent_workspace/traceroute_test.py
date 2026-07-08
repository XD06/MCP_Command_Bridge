import subprocess
import sys

# Windows: tracert
cmd = "tracert"
# Use -d to avoid DNS resolution, -h 30 for max hops
result = subprocess.run([cmd, "-d", "-h", "30", "8.8.8.8"], capture_output=True, text=True, timeout=60)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[:500])
