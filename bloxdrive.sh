#!/bin/bash

export PYTHONPATH="$PWD/src:$PYTHONPATH"

MOUNT_DIR=$(python3 -c "import sys; sys.path.append('src'); import config; print(config.MOUNT_DIR)")

start() {
    # Try to unmount if there's a stale mount (fixes 'Transport endpoint is not connected' errors)
    fusermount -uz "$MOUNT_DIR" 2>/dev/null || true

    # Create mount directory if it doesn't exist
    mkdir -p "$MOUNT_DIR"
    
    # Run unified interactive setup check in foreground
    python3 -c "import sys; sys.path.append('src'); import auth_server; auth_server.ensure_setup()" || exit 1
    
    echo "Starting BloxDrive FUSE at $MOUNT_DIR..."
    # Run the FUSE mount in the background and redirect logs
    nohup python3 src/main.py mount "$MOUNT_DIR" > bloxdrive.log 2>&1 &
    
    # Save the Process ID so we can track it
    echo $! > bloxdrive.pid
    echo "BloxDrive started successfully in the background (PID: $(cat bloxdrive.pid))."
    echo "Logs are being written to bloxdrive.log"
}

stop() {
    echo "Stopping BloxDrive..."
    
    # Forcefully lazy-unmount
    fusermount -uz "$MOUNT_DIR" 2>/dev/null || true
    echo "Unmount signal sent to $MOUNT_DIR."

    # Kill the background process if it exists
    if [ -f bloxdrive.pid ]; then
        PID=$(cat bloxdrive.pid)
        if ps -p $PID > /dev/null; then
            kill $PID
            echo "Terminated BloxDrive FUSE process (PID: $PID)."
        fi
        rm bloxdrive.pid
    fi

    # Kill Web UI process if it exists
    if [ -f webui.pid ]; then
        WEB_PID=$(cat webui.pid)
        if ps -p $WEB_PID > /dev/null; then
            kill $WEB_PID
            echo "Terminated Web UI process (PID: $WEB_PID)."
        fi
        rm webui.pid
    fi
}

status() {
    if mountpoint -q "$MOUNT_DIR"; then
        echo "BloxDrive is MOUNTED at $MOUNT_DIR."
    else
        echo "BloxDrive is NOT mounted."
    fi
    
    if [ -f bloxdrive.pid ]; then
        PID=$(cat bloxdrive.pid)
        if ps -p $PID > /dev/null; then
            echo "Background process is RUNNING (PID: $PID)."
        else
            echo "Background process is DEAD but PID file exists."
        fi
    fi
}

auth() {
    echo "Forcing BloxDrive re-authentication..."
    python3 src/main.py auth
}

web() {
    start
    
    WEB_PORT=$(python3 -c "import sys; sys.path.append('src'); import config; print(config.WEB_PORT)")
    WEB_HOST=$(python3 -c "import sys; sys.path.append('src'); import config; print(config.WEB_HOST)")
    echo "Starting BloxDrive Web UI on port $WEB_PORT..."
    nohup python3 webfilemgr/app.py > webui.log 2>&1 &
    echo $! > webui.pid
    echo "Web UI started in background (PID: $(cat webui.pid)). Access it at http://$WEB_HOST:$WEB_PORT"
    
    if command -v xdg-open &> /dev/null; then
        xdg-open "http://localhost:$WEB_PORT" &> /dev/null &
    elif command -v open &> /dev/null; then
        open "http://localhost:$WEB_PORT" &> /dev/null &
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    status)
        status
        ;;
    restart)
        stop
        sleep 2
        start
        ;;
    auth)
        auth
        ;;
    web)
        web
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart|auth|web}"
        exit 1
        ;;
esac
