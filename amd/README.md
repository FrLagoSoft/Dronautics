# AMD display smoothing (ROCm + RIFE)

The drone's camera arrives at about 15 frames per second. `interp_server.py` runs on an
AMD GPU and uses **RIFE** (open-source, MIT-licensed, real-time video frame interpolation on
PyTorch) to generate the in-between frames, so the phone shows about **30 fps**.

**Display only.** The laptop's person detection and flight control use the real frames, never
generated ones: the AI sees honest data, the human sees smooth video.

```
Tello --video--> laptop --real frames--> YOLO + leash --> drone commands
                    \
                     --frames (15/s)--> AMD GPU: RIFE (ROCm) --smoothed 30/s--> phone
```

## 1. On the AMD machine (Linux with ROCm)

Check the GPU and that PyTorch is the ROCm build:

```bash
rocm-smi            # or: amd-smi
python3 -c "import torch; print(torch.__version__, torch.version.hip, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

`torch.version.hip` must print a version, and `cuda.is_available()` must be `True`.
(On ROCm, PyTorch keeps the `cuda` name for the AMD GPU, so the same code runs unchanged.)

Get RIFE and its weights:

```bash
git clone https://github.com/hzwer/Practical-RIFE.git
cd Practical-RIFE
wget https://huggingface.co/Bash2X/RIFE-Models/resolve/main/RIFE_v4.25.lite.zip
unzip RIFE_v4.25.lite.zip
```

Make sure `train_log/` ends up containing `flownet.pkl` and the model `.py` files
(`RIFE_HDv3.py`, `IFNet_HDv3.py`, ...). If the zip unpacked into its own folder, move those
files into `Practical-RIFE/train_log/`. The weights are the official Practical-RIFE release
(MIT), mirrored on Hugging Face.

Install the two small extras and start the service:

```bash
pip install opencv-python-headless numpy
cp /path/to/dronautics/amd/interp_server.py .
python3 interp_server.py --rife-dir . --multi 2
```

The first line it prints should say `RIFE ... on <AMD GPU name> [ROCm/HIP ...]`.
Port 8090 must be reachable from the laptop and the phone (open it in the cloud firewall).

## 2. On the laptop

In `laptop/config.py`:

```python
INTERP_URL = "http://<amd-machine-ip>:8090"
```

Check from the laptop: open `http://<amd-machine-ip>:8090/stats` in a browser.

The laptop needs internet while its Wi-Fi is on the Tello: plug the tablet in with
**USB tethering** (tablet on the venue Wi-Fi or cellular). That same cable is also the app's link.

## 3. On the phone

`http://<amd-machine-ip>:8090/` shows the smoothed stream with live stats
(GPU, backend, model, interpolation time, fps in and out). The app's video view can switch
between the raw stream (laptop) and the AMD-smoothed one.

## Testing without the AMD machine

The same script runs on any PyTorch GPU, so it can be tested on the laptop's NVIDIA card
(its stats then say `CUDA`, not `ROCm`). Without weights it falls back to a plain blend and
says so. For judging, run it on the AMD GPU so the stats show `ROCm/HIP`.
