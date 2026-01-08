# USB tethering helper (Linux) — Python

This is a **computer-side** helper for using your phone’s **built-in USB tethering** on Linux.

It does **not** bypass carrier restrictions, and it does **not** work unless your phone exposes a USB network interface (RNDIS/ECM/NCM).

## What you do on the phone (no phone app needed)

- **Android**: Settings → Network & Internet (or Connections) → **Hotspot & tethering** → **USB tethering** → ON  
  (USB debugging is *not* required.)
- **iPhone**: Settings → Personal Hotspot → **Allow Others to Join** → connect USB → trust computer  
  (Linux support depends on the USB mode/driver; many iPhones require drivers/tools not available by default.)

## What you do on Linux

Install a DHCP client if you don’t have one:

```bash
sudo apt-get update
sudo apt-get install -y isc-dhcp-client
```

Run:

```bash
sudo python3 usb_tether.py --watch --status
```

If you want to see which interface was detected:

```bash
python3 usb_tether.py --list
```

If your interface isn’t `usb0` (sometimes it’s `enx...`), specify it:

```bash
sudo python3 usb_tether.py --iface enx001122334455 --status
```

## Why this can’t be “PDANet with no installs anywhere”

To share a phone’s cellular data to a computer, **either**:

- the phone must provide **native USB tethering** (what this tool automates on Linux), **or**
- the phone must run a **companion app** that creates a VPN/proxy/tunnel (PDANet-style).

There’s no way for a Python program on the computer alone to access the phone’s carrier data without one of those two.

