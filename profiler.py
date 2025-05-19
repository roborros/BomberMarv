import time
import logging

Tstart = 0
Tend = 0
Tavg = 0

profiler_logfile = "profiler.log"
profiler_logger = logging.getLogger("profiler")
profiler_handler = logging.FileHandler(profiler_logfile, mode='a', encoding='utf-8')
profiler_formatter = logging.Formatter("%(asctime)s %(levelname)s %(threadName)s %(message)s")
profiler_handler.setFormatter(profiler_formatter)
if not profiler_logger.hasHandlers():
    profiler_logger.addHandler(profiler_handler)
profiler_logger.setLevel(logging.INFO)

def profile_start():
    global Tstart
    profiler_logger.info("Profiler started.")
    profiler_handler.flush()
    Tstart = time.perf_counter()

def profile_end():
    global Tend
    global Tstart
    global Tavg
    Tend = time.perf_counter() 
    Tdiff = (Tend - Tstart)*1000
    Tavg = (Tavg*30 + Tdiff)/31
    profiler_logger.info(f"Elapsed time: {Tdiff:.0f} ms    Average: {Tavg:.2f} ms")
    profiler_handler.flush()