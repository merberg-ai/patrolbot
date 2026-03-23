<div align="center">
  <img src="https://img.icons8.com/color/96/000000/robot-3.png" alt="patrolbot logo" width="100"/>
  <h1>patrolbot 🤖 (v1.0)</h1>
  <p><em>Autonomous patrol system for Raspberry Pi robotics.</em> 🚗💨</p>

[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-lightgrey.svg)](https://flask.palletsprojects.com/)
[![Hardware](https://img.shields.io/badge/Hardware-Adeept_PiCar-orange.svg)](https://www.adeept.com/)
[![Status](https://img.shields.io/badge/Status-Phase1--Stable-green.svg)]()

</div>

<br />

`patrolbot` is a **focused autonomous patrol system** for the **Adeept PiCar platform**, streamlined into a single purpose:

> **Drive, patrol, avoid obstacles, and stay alive.**

Version **1.0 (Phase 1)** is the foundation build — a cleaned, patrol-only runtime with all unnecessary subsystems removed.

---

# 🎯 Project Scope (v1.0)

This version is intentionally **minimal and focused**:

* Autonomous forward patrol
* Ultrasonic-based obstacle avoidance
* Basic reverse + turn escape behavior
* Live telemetry + camera feed
* Mobile-friendly web UI

🚫 Removed:

* Gamepad / controller support
* Bluetooth stack
* Object tracking / YOLO
* Manual driving UI
* RGB lighting UI
* Multi-mode robot features

This is no longer a “robot playground.”
It’s a **dedicated patrol system**.

---

# ✨ Features (Phase 1)

## 🤖 Autonomous Patrol

* Continuous forward movement
* Front ultrasonic obstacle detection
* Automatic stop → reverse → turn → resume
* Simple, predictable behavior loop

## 🧠 Patrol Engine (v1)

* State-driven patrol logic
* Obstacle-triggered escape routines
* Camera pan sweep support (optional)
* Designed for future expansion (memory, smarter routing)

## 📡 Telemetry

* Battery voltage and percentage
* Ultrasonic distance
* Motor and steering state
* Patrol state + current action

## 🎥 Camera

* Live MJPEG stream via `picamera2`
* Pan/tilt servo control (internal use)
* Ready for future vision features

## 🖥️ Web UI

Minimal, mobile-friendly interface:

| Page         | Description                                  |
| ------------ | -------------------------------------------- |
| **Patrol**   | Main control panel + live camera + telemetry |
| **Settings** | Configurable patrol parameters               |
| **System**   | Diagnostics, logs, system control            |

---

# ⚙️ Patrol Behavior (v1)

Basic loop:

```
FORWARD →
  obstacle detected →
    STOP →
    REVERSE →
    TURN →
    RESUME
```

Simple. Reliable. No overthinking (yet).

---

# 🛠️ Hardware Requirements

* **Raspberry Pi** (Pi 4 or Pi 5 recommended)
* **Adeept PiCar Kit** or compatible:

  * Motor driver
  * Steering servo
  * Camera pan/tilt servos
  * **HC-SR04 ultrasonic sensor (front required)**

Optional (future use):

* Rear ultrasonic sensor

---

# 🚀 Installation

```bash
git clone https://github.com/yourusername/patrolbot.git
cd patrolbot/install
sudo ./install.sh
```

The installer will:

* Set up Python virtual environment
* Install dependencies
* Configure system packages
* Register `patrolbot.service`

---

# 🎮 Usage

Open in browser:

```
http://<raspberry-pi-ip>:8080/
```

---

## 🔧 Service Control

```bash
# Status
sudo systemctl status patrolbot --no-pager -l

# Restart
sudo systemctl restart patrolbot

# Stop
sudo systemctl stop patrolbot

# Logs
journalctl -u patrolbot -f
```

---

# 📂 Project Structure

```
patrolbot/
├── app.py
├── patrolbot/
│   ├── api/            # REST API (patrol, status, settings)
│   ├── hardware/       # Motors, camera, ultrasonic, etc.
│   ├── services/
│   │   ├── patrol.py   # 🧠 patrol engine (core logic)
│   │   ├── telemetry.py
│   │   ├── startup.py
│   │   └── safety.py
│   ├── webui/
│   │   ├── templates/
│   │   │   ├── patrol.html
│   │   │   ├── settings.html
│   │   │   └── system.html
│   │   └── static/
│   ├── config.py
│   └── state.py
├── config/
│   ├── default.yaml
│   └── runtime.yaml
└── install/
```

---

# 🔧 Configuration

All defaults:

```
config/default.yaml
```

Runtime overrides:

```
config/runtime.yaml
```

Reset config:

```bash
rm config/runtime.yaml
sudo systemctl restart patrolbot
```

---

# ⚠️ Current Limitations (Phase 1)

* No obstacle memory (can get stuck in loops)
* No rear sensor logic yet (planned)
* No intelligent pathing
* No vision-based decisions
* No remote/manual override

This is a **stable foundation**, not the final system.

---

# 🧭 Roadmap

## Phase 2

* Improved obstacle avoidance
* Reverse safety checks
* Turn logic improvements
* Patrol controls (start/pause/stop)

## Phase 3

* Obstacle memory (anti-loop behavior)
* Smarter navigation decisions
* Configurable patrol modes

## Phase 4+

* Camera-assisted navigation
* Person detection / following (optional mode)
* SLAM / mapping (long-term)

---

# 🤝 Contributing

PRs welcome. Ideas welcome. Chaos welcome.

---

<div align="center">
  <i>Built for robots that wander… and survive.</i>
</div>
