from pathlib import Path
import time

base = None
for p in Path("/sys/class/hwmon").glob("hwmon*/name"):
    if p.read_text().strip() == "aht10":
        base = p.parent
        break
assert base, "AHT hwmon device not found"

t_file = base/"temp1_input"
h_file = base/"humidity1_input"

for _ in range(5):
    t = int(t_file.read_text())/1000.0
    h = int(h_file.read_text())/1000.0
    print(f"T={t:.3f} °C  RH={h:.3f} %")
    time.sleep(1)