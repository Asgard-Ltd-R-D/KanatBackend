/* extension.js
 *
 * Native GNOME Shell panel indicator that shows the status of a TCP port.
 * Green = port reachable (online), Red = port unreachable (offline).
 *
 * Default: checks localhost:10900 (dotnet prod).
 */

const { Gio, GLib, St } = imports.gi;
const Main = imports.ui.main;
const PanelMenu = imports.ui.panelMenu;
const PopupMenu = imports.ui.popupMenu;

// Config – adjust if needed
const HOST = '127.0.0.1';
const PORT = 10900;
const INTERVAL_SECONDS = 5; // polling interval

let indicator = null;
let timeoutId = null;

class DotnetPortStatusIndicator extends PanelMenu.Button {
    constructor() {
        super(0.0, 'Dotnet Port Status');

        // Icon container
        this._icon = new St.Icon({
            icon_name: 'network-error-symbolic',
            style_class: 'system-status-icon'
        });
        this.add_child(this._icon);

        // Popup menu text
        this._statusItem = new PopupMenu.PopupMenuItem('Checking...', { reactive: false });
        this.menu.addMenuItem(this._statusItem);

        // First update
        this._updateStatus();
    }

    _setStatus(online) {
        if (online) {
            // Green-style icon (OK)
            this._icon.icon_name = 'emblem-ok-symbolic';
            this._statusItem.label.text = `Online: ${HOST}:${PORT}`;
        } else {
            // Red-style / error icon
            this._icon.icon_name = 'network-error-symbolic';
            this._statusItem.label.text = `Offline: ${HOST}:${PORT}`;
        }
    }

    _checkPortAsync(callback) {
        let client = new Gio.SocketClient();
        client.timeout = 2; // seconds

        // Avoid warnings if host is not resolvable
        try {
            client.connect_to_host_async(
                `${HOST}:${PORT}`,
                PORT,
                null,
                (obj, res) => {
                    try {
                        let connection = obj.connect_to_host_finish(res);
                        if (connection) {
                            connection.close(null);
                            callback(true);
                        } else {
                            callback(false);
                        }
                    } catch (e) {
                        callback(false);
                    }
                }
            );
        } catch (e) {
            callback(false);
        }
    }

    _updateStatus() {
        this._checkPortAsync((online) => {
            this._setStatus(online);
        });
    }

    start() {
        // Poll periodically
        if (timeoutId !== null)
            GLib.Source.remove(timeoutId);

        timeoutId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT,
            INTERVAL_SECONDS,
            () => {
                this._updateStatus();
                return true; // keep repeating
            }
        );

        // Immediate check
        this._updateStatus();
    }

    stop() {
        if (timeoutId !== null) {
            GLib.Source.remove(timeoutId);
            timeoutId = null;
        }
    }
}

// GNOME Shell extension entry points
function init() {
    // Nothing special to init
}

function enable() {
    indicator = new DotnetPortStatusIndicator();

    // Add to top bar (right side, like Wi-Fi / battery)
    Main.panel.addToStatusArea('dotnet-port-status', indicator);
    indicator.start();
}

function disable() {
    if (indicator) {
        indicator.stop();
        indicator.destroy();
        indicator = null;
    }
}
