import time
import logging

Tstart = 0
Tend = 0
Tavg = 0

def profile_start():
    global Tstart
    Tstart = time.perf_counter()

def profile_end():
    global Tend
    global Tstart
    global Tavg
    Tend = time.perf_counter() 
    Tdiff = (Tend - Tstart)*1000
    Tavg = (Tavg*30 + Tdiff)/31
    print(f"Elapsed time: {Tdiff:.0f} ms    Average: {Tavg:.2f} ms")
