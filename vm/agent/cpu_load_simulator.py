import threading, time, math

def cpu_load(duration=60):
    print("Simulating CPU load for", duration, "seconds...")
    end = time.time() + duration
    while time.time() < end:
        math.sqrt(12345.6789)
    print("Load simulation complete.")

if __name__ == "__main__":
    threads = [threading.Thread(target=cpu_load, args=(60,)) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()

