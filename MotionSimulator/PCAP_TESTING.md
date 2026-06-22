# PCAP Testing Guide

## Prerequisites — Add IP Aliases to Loopback

Required before running Safety or OnVIF pcaps. These IPs must exist on the loopback interface so the OS accepts traffic for them.

**macOS:**

```bash
sudo ifconfig lo0 alias 132.8.7.101
sudo ifconfig lo0 alias 132.8.7.102
sudo ifconfig lo0 alias 132.8.7.121
```

**Linux:**

```bash
sudo ip addr add 132.8.7.101/8 dev lo
sudo ip addr add 132.8.7.102/8 dev lo
sudo ip addr add 132.8.7.121/8 dev lo
```

> Aliases are lost on reboot. Re-run after restart.

---

## Safety — `safety_seq.pcap`

UDP — no listener required. Sends directly to the aliased IPs.

```bash
python3.12 replay_pcap.py safety_seq.pcap --port 1025
```

### Packets produced

**PBE (132.8.7.101):**
| Key | Description |
|---|---|
| `safety\|do3_fire1\|true` | Fire 1 |
| `safety\|do2_motion\|true` | Motion enable |
| `safety\|do4_led_fire_en\|true` | LED fire enable |

**SBE (132.8.7.102):**
| Key | Description |
|---|---|
| `safety\|do0_rld\|true` | Reload |
| `safety\|do1_rld_sfty\|true` | Reload safety |
| `safety\|do2_pwr\|true` | Power |
| `safety\|do4_fire2\|true` | Fire 2 |

---

## Motion — `motion_seq.pcap`

TCP — requires a listener on port 4949.

**Terminal 1 — start listener:**

macOS:

```bash
nc -l 127.0.0.1 4949
```

Linux:

```bash
nc -l -p 4949 127.0.0.1
```

**Terminal 2 — replay:**

```bash
python3.12 replay_pcap.py motion_seq.pcap --port 4949
```

### Packets produced

| Subscription key                       |
| -------------------------------------- |
| `motion\|mot_getloadposition\|true\|1` |
| `motion\|mot_getloadposition\|true\|2` |
| `motion\|mot_getloadposition\|true\|4` |
| `motion\|mot_getloadposition\|true\|5` |
| `motion\|mot_setspeedmode\|true\|1`    |
| `motion\|mot_setspeedmode\|true\|2`    |
| `motion\|mot_setspeedmode\|true\|4`    |
| `motion\|mot_setspeedmode\|true\|5`    |
| `motion\|mot_setacceleration\|true\|1` |
| `motion\|mot_setacceleration\|true\|2` |
| `motion\|mot_setacceleration\|true\|4` |
| `motion\|mot_setacceleration\|true\|5` |
| `motion\|mot_setspeed\|true\|1`        |
| `motion\|mot_setspeed\|true\|2`        |
| `motion\|mot_setspeed\|true\|4`        |
| `motion\|mot_setspeed\|true\|5`        |
| `motion\|mot_sendposition\|true\|1`    |
| `motion\|mot_sendposition\|true\|2`    |
| `motion\|mot_update\|true\|1`          |
| `motion\|mot_update\|true\|2`          |
| `motion\|mot_update\|true\|4`          |
| `motion\|mot_update\|true\|5`          |
| `motion\|com_sysstate\|true\|0`        |
| `motion\|com_isconnected\|true\|0`     |
| `motion\|dg_setsyncmode\|true\|0`      |
| `motion\|dg_issyncmode\|true\|0`       |
| `motion\|dg_isinnermode\|true\|0`      |

---

## Motion — `voltage_current.pcap`

TCP — same listener setup as motion_seq.

**Terminal 1 — start listener:**

macOS:

```bash
nc -l 127.0.0.1 4949
```

Linux:

```bash
nc -l -p 4949 127.0.0.1
```

**Terminal 2 — replay:**

```bash
python3.12 replay_pcap.py voltage_current.pcap --port 4949
```

### Packets produced

| Subscription key                             |
| -------------------------------------------- |
| `motion\|mot_getmotorspeed\|true\|1`         |
| `motion\|mot_getmotorspeed\|true\|2`         |
| `motion\|mot_getmotorspeed\|true\|4`         |
| `motion\|mot_getmotorspeed\|true\|5`         |
| `motion\|mot_getmotorvoltage\|true\|1`       |
| `motion\|mot_getmotorvoltage\|true\|2`       |
| `motion\|mot_getmotorvoltage\|true\|4`       |
| `motion\|mot_getmotorvoltage\|true\|5`       |
| `motion\|mot_getmotorcurrent\|true\|1`       |
| `motion\|mot_getmotorcurrent\|true\|2`       |
| `motion\|mot_getmotorcurrent\|true\|4`       |
| `motion\|mot_getmotorcurrent\|true\|5`       |
| `motion\|mot_getloadposition\|true\|1`       |
| `motion\|mot_getloadposition\|true\|2`       |
| `motion\|mot_getloadposition\|true\|4`       |
| `motion\|mot_getloadposition\|true\|5`       |
| `motion\|mot_axison\|true\|1`                |
| `motion\|mot_axison\|true\|2`                |
| `motion\|mot_axison\|true\|4`                |
| `motion\|mot_axison\|true\|5`                |
| `motion\|mot_axisoff\|true\|1`               |
| `motion\|mot_axisoff\|true\|2`               |
| `motion\|mot_axisoff\|true\|4`               |
| `motion\|mot_axisoff\|true\|5`               |
| `motion\|mot_isactiveswls\|true\|1`          |
| `motion\|mot_isactiveswls\|true\|2`          |
| `motion\|mot_isactiveswls\|true\|4`          |
| `motion\|mot_isactiveswls\|true\|5`          |
| `motion\|mot_merregister\|true\|1`           |
| `motion\|mot_merregister\|true\|2`           |
| `motion\|mot_merregister\|true\|4`           |
| `motion\|mot_derregister\|true\|1`           |
| `motion\|mot_derregister\|true\|2`           |
| `motion\|mot_derregister\|true\|4`           |
| `motion\|err_capturesystemregister\|true\|0` |
| `motion\|err_capturesystemregister\|true\|1` |
| `motion\|err_operationregister\|true\|1`     |
| `motion\|err_operationregister\|true\|2`     |
| `motion\|err_operationregister\|true\|4`     |
| `motion\|err_operationregister\|true\|5`     |
| `motion\|com_sysstate\|true\|0`              |
| `motion\|com_isconnected\|true\|0`           |
| `motion\|com_iskeepaliveon\|true\|0`         |
| `motion\|dg_issyncmode\|true\|0`             |
| `motion\|dg_isinnermode\|true\|0`            |
| `motion\|dg_isboresighten\|true\|0`          |
| `motion\|dg_iscapsnapready\|true\|0`         |
| `motion\|dg_getsafetystatus\|true\|0`        |
| `motion\|dg_getloadstatus\|true\|0`          |
| `motion\|dg_getnumbullets\|true\|0`          |
| `motion\|dg_getposdiff\|true\|1`             |
| `motion\|dg_getposdiff\|true\|2`             |
| `motion\|dg_getboresightoffset\|true\|1`     |
| `motion\|dg_getboresightoffset\|true\|2`     |
| `motion\|dg_getboresightoffset\|true\|4`     |

---

## OnVIF — `onvif_IR.pcap` / `onvif_LRF.pcap`

TCP — requires a listener on port 8080 at `132.8.7.121` (alias must be set first).

**Terminal 1 — start listener:**

macOS:

```bash
nc -l 132.8.7.121 8080
```

Linux:

```bash
nc -l -p 8080 132.8.7.121
```

**Terminal 2 — replay:**

```bash
python3.12 replay_pcap.py onvif_IR.pcap --host 132.8.7.121 --port 8080
# or
python3.12 replay_pcap.py onvif_LRF.pcap --host 132.8.7.121 --port 8080
```

### Packets produced

| File             | Subscription key       | Description                    |
| ---------------- | ---------------------- | ------------------------------ |
| `onvif_IR.pcap`  | `onvif\|fov_sts\|true` | FOV status (zoom value)        |
| `onvif_LRF.pcap` | `onvif\|lrf_sts\|true` | LRF status (range measurement) |

---

## Notes

- Subscribe from the frontend **before** starting the replay — the backend only broadcasts to clients registered at the moment the packet is processed.
- Packets with `value = 1.0` carry no numeric payload (trigger/ack only) — safe to ignore in graph displays.
- Safety packets go directly to the correct destination IP from the pcap — no host override needed.
