"""Sonde rapide : lit la temp CPU via LibreHardwareMonitor (doit tourner en admin)."""
import os

BASE = os.path.dirname(os.path.abspath(__file__))
import clr
clr.AddReference(os.path.join(BASE, "libs", "LibreHardwareMonitorLib.dll"))
from LibreHardwareMonitor.Hardware import Computer

c = Computer()
c.IsCpuEnabled = True
c.IsGpuEnabled = False
c.IsMemoryEnabled = False
c.IsMotherboardEnabled = False
c.IsStorageEnabled = False
c.IsNetworkEnabled = False
c.IsBatteryEnabled = False
c.Open()
for hw in c.Hardware:
    hw.Update()
    print("CPU:", hw.Name)
    for s in hw.Sensors:
        if str(s.SensorType) == "Temperature" and s.Value is not None:
            print(f"  {s.Name} = {float(s.Value):.1f} C")
c.Close()
