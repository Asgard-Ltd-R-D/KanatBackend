# Motion Simulator

A TCP-based motion control simulator that provides realistic motion axis simulation and laser range finder (LRF) functionality for testing motion control systems.

## Overview

The Motion Simulator consists of three main components:

- **Motion Server** (`motion_simulator.py`) - TCP server that simulates motion control hardware
- **UI Client** (`ui_client.py`) - Tkinter-based GUI for controlling and monitoring the simulator
- **Protocol** (`protocol.py`) - Shared communication protocol definitions

## Features

- **Motion Axis Simulation**: Simulates multiple motion axes (1, 2, 4, 5) with position, speed, and acceleration control
- **Laser Range Finder**: Simulates LRF functionality with configurable range values
- **Safety/Fire Control**: UDP-based fire command simulation with cyclic transmission
- **Real-time Monitoring**: Live position, speed, voltage, current, and error status updates via GUI
- **Mode Control**: System-wide sync/unsync and inner/outer mode control
- **Ballistic Offset**: Configurable ballistic offset for axes 1 and 2
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
#IP Safety 1
sudo ifconfig lo0 alias 132.8.7.101

#IP Safety 2
sudo ifconfig lo0 alias 132.8.7.102
```

#### 2. Verify IP addresses are configured

```bash
# Check that both IPs are configured
ifconfig lo0 | grep "132.8.7"
```

You should see both IP addresses listed. If you need to remove them later:

```bash
# Remove IP addresses (if needed)
sudo ifconfig lo0 -alias 132.8.7.101
sudo ifconfig lo0 -alias 132.8.7.102
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
   [Server] Motion Simulator v1.6.0 (2025-10-26) listening on 127.0.0.1:4949 (TCP)...
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
   - **Fire Control**: UDP-based fire command controls (FIRE1_CMD, FIRE2_CMD)
   - **Laser Range Finder**: Current range display and set range controls
   - **Mode Control**: System-wide sync/unsync and inner/outer mode controls
   - **Motion Commands**: Position, speed, and acceleration controls
   - **Axis Control**: Individual axis ON/OFF/RESET controls
   - **Ballistic Offset**: Configurable ballistic offset for axes 1 and 2
   - **All Axis Status**: Real-time monitoring for all simulated axes (1, 2, 4, 5)

### Using the UI Client

1. **Connect to Server**:

   - Click the "Connect" button
   - Status should change to "Connected to 132.8.7.125:4949"
   - Position and speed will start updating automatically

2. **Control Motion**:

   - Select target axis from the dropdown (1, 2, 4, or 5)
   - Enter target position in the "Target Position" field
   - Set desired "Max Speed" and "Acceleration" values
   - Click "Send Absolute Move" for absolute positioning
   - Click "Send Relative Move" for relative positioning

3. **Control Axes**:

   - Use "Axis ON" to enable the selected axis
   - Use "Axis OFF" to disable the selected axis
   - Use "Axis RESET" to clear faults on the selected axis

4. **Control LRF**:

   - Enter desired range in the "Set Range (m)" field
   - Click "Set" to update the simulated LRF range
   - Current range is displayed in real-time

5. **Control System Modes**:

   - Select "SYNC" or "UNSYNC" for system-wide mode
   - In UNSYNC mode, choose "INNER" or "OUTER" sub-mode
   - Mode changes affect all axes simultaneously

6. **Control Fire Commands** (Safety Domain):

   - Click "FIRE1_CMD (START)" to begin cyclic UDP fire commands to 132.8.7.101:1025
   - Click "FIRE2_CMD (START)" to begin cyclic UDP fire commands to 132.8.7.102:1025
   - Commands are sent at 10ms intervals while active
   - Click "STOP" to halt fire command transmission

7. **Control Ballistic Offset**:

   - Enter offset value in the "Set Offset" field
   - Click "Send Offset" to apply ballistic offset (axes 1 and 2 only)
   - Current offset is displayed in the axis status panels

8. **Monitor Status**:
   - Position, speed, voltage, current, and error status update automatically every 30ms
   - LRF range updates in real-time
   - Connection status is shown at the top
   - All four axes (1, 2, 4, 5) are monitored simultaneously

## Protocol Details

The simulator uses a custom TCP protocol with the following characteristics:

- **Port**: 4949
- **Packet Format**: Start bytes (0x50, 0x54) + Length + GroupID + AxisID + Opcode + Data + Checksum
- **Supported Opcodes**:
  - **Motion Control (0x01xx)**:
    - `MOT_GetLoadPosition` (0x0109) - Get current position
    - `MOT_GetMotorSpeed` (0x010A) - Get current speed
    - `MOT_GetMotorVoltage` (0x0107) - Get motor voltage
    - `MOT_GetMotorCurrent` (0x0106) - Get motor current
    - `MOT_SetPositionAbsolute` (0x0139) - Set absolute target position
    - `MOT_SetPositionRelative` (0x0138) - Set relative target position
    - `MOT_SetSpeed` (0x0131) - Set maximum speed
    - `MOT_SetAcceleration` (0x0130) - Set acceleration
    - `MOT_SetPositionMode` (0x013B) - Set position control mode
    - `MOT_Update` (0x0134) - Start motion execution
    - `MOT_AxisOn` (0x013C) - Enable axis
    - `MOT_AxisOff` (0x013D) - Disable axis
    - `MOT_AxisReset` (0x013E) - Reset axis faults
  - **Laser Range Finder (0x03xx)**:
    - `LRF_GetRange` (0x0301) - Get LRF range
    - `LRF_SetRange` (0x0300) - Set LRF range
  - **Communication (0x07xx)**:
    - `COM_Connect` (0x0702) - Connection handshake
  - **Error Handling (0x0Exx)**:
    - `ERR_CaptureMotorErrorRegister` (0x0E0B) - Get axis error status (CMER)
  - **Dual Gimbal/Mode Control (0x0Fxx)**:
    - `DG_SetSyncMode` (0x0FA0) - Set system sync/unsync mode
    - `DG_SetInnerMode` (0x0FA1) - Set inner/outer mode (unsync only)
    - `DG_SetBallisticOffset` (0x0FBD) - Set ballistic offset (axes 1,2)
    - `DG_GetBallisticOffset` (0x0FBE) - Get ballistic offset (axes 1,2)

## Safety Domain (UDP Fire Commands)

The simulator includes UDP-based fire command functionality for safety system testing:

- **Fire Command Ports**: 1025 (both FIRE1 and FIRE2)
- **Target IP Addresses**:
  - FIRE1: 132.8.7.101:1025
  - FIRE2: 132.8.7.102:1025
- **Transmission Rate**: 10ms intervals (100 Hz)
- **Packet Format**: Fixed 20-byte binary payload
- **Command Types**:
  - `FIRE1_CMD`: Cyclic fire command to safety system 1
  - `FIRE2_CMD`: Cyclic fire command to safety system 2

The UDP fire commands operate independently of the TCP motion control protocol and are designed for testing safety system integration.

## Simulation Physics

The motion simulation uses simplified physics:

- **Update Rate**: 10ms (100 Hz)
- **Simulated Axes**: 1, 2, 4, 5 (4 total axes)
- **Movement**: Linear interpolation to target position
- **Speed Control**: Constant speed movement (acceleration not fully implemented)
- **Position Tolerance**: 0.01 units for "in position" detection
- **Error Simulation**: Simulated voltage, current, and error conditions
- **Status Monitoring**: Real-time CMER (Capture Motor Error Register) status

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

- **v1.6.0** (2025-10-26): Added parallel UDP Fire listeners and comprehensive multi-axis support
- **v1.1.0** (2025-10-20): Added LRF simulation support
- **v1.0.4** (2025-10-20): Corrected packet parsing logic

## Development Notes

- The simulator is designed for testing motion control systems and safety integration
- Physics simulation is simplified for demonstration purposes
- Protocol is compatible with standard motion control opcodes
- Multi-client support allows testing with multiple control applications
- UDP fire commands provide safety system testing capabilities
- Supports multiple motion axes with individual control and monitoring
- Real-time error status monitoring via CMER register

## Support

For issues or questions:

1. Check the troubleshooting section above
2. Verify network configuration
3. Check server logs for error messages
4. Ensure all prerequisites are met
