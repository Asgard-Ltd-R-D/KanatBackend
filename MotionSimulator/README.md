# Motion Simulator

A TCP-based motion control simulator that provides realistic motion axis simulation and laser range finder (LRF) functionality for testing motion control systems.

## Overview

The Motion Simulator consists of three main components:

- **Motion Server** (`motion_simulator.py`) - TCP server that simulates motion control hardware
- **UI Client** (`ui_client.py`) - Tkinter-based GUI for controlling and monitoring the simulator
- **Protocol** (`protocol.py`) - Shared communication protocol definitions

## Features

- **Motion Axis Simulation**: Simulates a single motion axis with position, speed, and acceleration control
- **Laser Range Finder**: Simulates LRF functionality with configurable range values
- **Real-time Monitoring**: Live position and speed updates via GUI
- **TCP Communication**: Standardized packet-based protocol for reliable communication
- **Multi-client Support**: Server can handle multiple concurrent connections

## Prerequisites

### System Requirements

- Python 3.6 or higher
- macOS (for lo0 interface setup)
- Tkinter (usually included with Python)

### Network Setup

Before running the simulator, you need to configure the loopback interface with the required IP addresses:

#### 1. Add IP addresses to lo0 interface

```bash
# Add server IP (motion simulator)
sudo ifconfig lo0 alias 132.8.7.125

# Add client IP (UI client)
sudo ifconfig lo0 alias 132.8.7.1
```

#### 2. Verify IP addresses are configured

```bash
# Check that both IPs are configured
ifconfig lo0 | grep "132.8.7"
```

You should see both IP addresses listed. If you need to remove them later:

```bash
# Remove IP addresses (if needed)
sudo ifconfig lo0 -alias 132.8.7.125
sudo ifconfig lo0 -alias 132.8.7.1
```

## Installation

1. **Clone or download** the MotionSimulator folder to your local machine

2. **Navigate to the MotionSimulator directory**:

   ```bash
   cd MotionSimulator
   ```

3. **No additional dependencies required** - uses only Python standard library modules

## Usage

### Starting the Motion Server

1. **Open a terminal** and navigate to the MotionSimulator directory

2. **Run the motion server**:

   ```bash
   python3 motion_simulator.py
   ```

   You should see output like:

   ```
   [Server] Motion Simulator v1.1.0 (2025-10-20) listening on 132.8.7.125:4949...
   ```

3. **Keep this terminal open** - the server will continue running and display connection logs

### Starting the UI Client

1. **Open a new terminal** and navigate to the MotionSimulator directory

2. **Run the UI client**:

   ```bash
   python3 ui_client.py
   ```

3. **The GUI window will open** with the following sections:
   - **Connection**: Connect/Disconnect button and status
   - **Axis 1 Status**: Real-time position and speed display
   - **Laser Range Finder**: Current range display and set range controls
   - **Motion Commands**: Position, speed, and acceleration controls

### Using the UI Client

1. **Connect to Server**:

   - Click the "Connect" button
   - Status should change to "Connected to 132.8.7.125:4949"
   - Position and speed will start updating automatically

2. **Control Motion**:

   - Enter target position in the "Target Position" field
   - Set desired "Max Speed" and "Acceleration" values
   - Click "Send Absolute Move" for absolute positioning
   - Click "Send Relative Move" for relative positioning

3. **Control LRF**:

   - Enter desired range in the "Set Range (m)" field
   - Click "Set" to update the simulated LRF range
   - Current range is displayed in real-time

4. **Monitor Status**:
   - Position and speed update automatically every 30ms
   - LRF range updates in real-time
   - Connection status is shown at the top

## Protocol Details

The simulator uses a custom TCP protocol with the following characteristics:

- **Port**: 4949
- **Packet Format**: Start bytes (0x50, 0x54) + Length + GroupID + AxisID + Opcode + Data + Checksum
- **Supported Opcodes**:
  - `MOT_GetLoadPosition` (0x0109) - Get current position
  - `MOT_GetMotorSpeed` (0x010A) - Get current speed
  - `MOT_SetPositionAbsolute` (0x0139) - Set absolute target position
  - `MOT_SetPositionRelative` (0x0138) - Set relative target position
  - `MOT_SetSpeed` (0x0131) - Set maximum speed
  - `MOT_SetAcceleration` (0x0130) - Set acceleration
  - `LRF_GetRange` (0x0301) - Get LRF range
  - `LRF_SetRange` (0x0300) - Set LRF range
  - `COM_Connect` (0x0702) - Connection handshake

## Simulation Physics

The motion simulation uses simplified physics:

- **Update Rate**: 10ms (100 Hz)
- **Movement**: Linear interpolation to target position
- **Speed Control**: Constant speed movement (acceleration not fully implemented)
- **Position Tolerance**: 0.01 units for "in position" detection

## Troubleshooting

### Connection Issues

1. **"Failed to connect" error**:

   - Verify IP addresses are configured on lo0 interface
   - Check that motion server is running
   - Ensure no firewall is blocking port 4949

2. **"Connection lost" during operation**:
   - Check server terminal for error messages
   - Restart both server and client
   - Verify network configuration

### GUI Issues

1. **UI not responding**:

   - Check if server is still running
   - Try disconnecting and reconnecting
   - Restart the UI client

2. **Values not updating**:
   - Verify connection status
   - Check server logs for errors
   - Ensure polling is active (should happen automatically)

## File Structure

```
MotionSimulator/
├── README.md              # This file
├── motion_simulator.py    # TCP server (motion simulation)
├── ui_client.py          # GUI client application
└── protocol.py           # Communication protocol definitions
```

## Version History

- **v1.1.0** (2025-10-20): Added LRF simulation support
- **v1.0.4** (2025-10-20): Corrected packet parsing logic

## Development Notes

- The simulator is designed for testing motion control systems
- Physics simulation is simplified for demonstration purposes
- Protocol is compatible with standard motion control opcodes
- Multi-client support allows testing with multiple control applications

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Verify network configuration
3. Check server logs for error messages
4. Ensure all prerequisites are met
