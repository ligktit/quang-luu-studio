"""Quick test: run recorder_worker as subprocess for 3 seconds."""
import subprocess, sys, os, time, tempfile

temp_wav = os.path.join(tempfile.gettempdir(), "test_rec.wav")
stop_flag = os.path.join(tempfile.gettempdir(), "test_rec_flag.tmp")

with open(stop_flag, 'w') as f:
    f.write("recording")

worker = os.path.join(os.path.dirname(__file__), "recorder_worker.py")
proc = subprocess.Popen(
    [sys.executable, worker, temp_wav, stop_flag],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
)

print("Started subprocess, recording for 3 seconds...")
time.sleep(3)

os.remove(stop_flag)
proc.wait(timeout=5)

print("STDOUT:", proc.stdout.read())
print("STDERR:", proc.stderr.read())

if os.path.exists(temp_wav):
    size = os.path.getsize(temp_wav)
    print(f"WAV file: {temp_wav} ({size} bytes)")
else:
    print("No WAV file created!")
