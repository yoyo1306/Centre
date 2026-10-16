"""Dump complet : tous les hardwares + subhardwares, 3 passes d'Update, toutes les sondes Temperature."""
import os
import time

BASE = os.path.dirname(os.path.abspath(__file__))
import clr
clr.AddReference(os.path.join(BASE, "libs", "LibreHardwareMonitorLib.dll"))
from LibreHardwareMonitor.Hardware import Computer

c = Computer()
c.IsCpuEnabled = True
c.IsGpuEnabled = True
c.IsMemoryEnabled = True
c.IsMotherboardEnabled = True
c.IsStorageEnabled = False
c.IsNetworkEnabled = False
c.IsBatteryEnabled = False
c.Open()


def show(hw, prefix=""):
    print(f"{prefix}HW {hw.HardwareType} | {hw.Name}")
    for s in hw.Sensors:
        if str(s.SensorType) == "Temperature":
            v = s.Value
            print(f"{prefix}   TEMP {s.Name} = {('%.1f' % float(v)) if v is not None else 'None'}")


for i in range(3):
    print(f"===== passe {i} =====")
    for hw in c.Hardware:
        hw.Update()
        for sh in hw.SubHardware:
            sh.Update()
        show(hw)
        for sh in hw.SubHardware:
            show(sh, prefix="  sub ")
    time.sleep(1)
c.Close()
