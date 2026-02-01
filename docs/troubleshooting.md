# Troubleshooting Guide

This guide covers common issues and their solutions.

## Connection Issues

### "Failed to connect" Error

**Symptoms:**
- Integration fails to connect during setup
- Entities show as "unavailable"
- Logs show connection timeout

**Possible causes:**
1. Incorrect IP address
2. Wrong HTTP port
3. Panel is powered off or disconnected
4. Network connectivity issues
5. Firewall blocking connection

**Solutions:**
1. **Verify IP address:**
   ```bash
   ping <PANEL_IP>
   ```

2. **Check web interface:**
   - Open browser to `http://<PANEL_IP>:<PORT>`
   - If you can't access it, the panel's web module may be disabled

3. **Verify port:**
   - Default is port `80`
   - Some panels use port `8080` or custom ports
   - Check your panel's configuration

4. **Test from Home Assistant:**
   - Go to **Developer Tools** → **Terminal**
   - Run: `curl -v http://<PANEL_IP>:<PORT>/login.cgi`

### Entities become unavailable after restart

**Symptoms:**
- All entities show "unavailable" after Home Assistant restart
- Connection works initially but fails after restart

**Possible cause:** Panel is offline at HA startup time

**Solution:** The integration now supports startup with cached configuration:
- Entities are created but show "unavailable" until connection succeeds
- Automatic retry in background
- Entities become available when panel comes back online

---

## Authentication Issues

### "Authentication failed" in logs

**Symptoms:**
- Logs show authentication errors
- Commands don't work (arm/disarm fail)
- Status may or may not work

**See:** [Authentication Documentation](authentication.md) for detailed authentication process.

**Solutions:**
1. **Verify PIN code:**
   - Check your master PIN code is correct
   - If code is < 6 digits, it's auto-padded: `1234` → `123400`
   - Ensure you're using the master code, not a user code

2. **Enable debug logging:**
   ```yaml
   logger:
     default: info
     logs:
       custom_components.combivox_web.auth: debug
   ```

3. **Check for "No cookie found" logs:**
   - May indicate panel is slow to respond
   - Network issues between HA and panel
   - Panel web interface not fully functional

### Cookie not found after authentication

**Symptoms:**
- Log: "No cookie found after authentication"
- Falls back to unauthenticated mode
- Some features may not work

**Workaround:** The integration will continue in unauthenticated mode:
- Basic status polling may work
- Commands will NOT work
- Reauthentication will be attempted automatically

**Solution:**
- Ensure panel's web interface is working properly
- Check for network issues
- Try increasing timeout in integration options (if available)

---

## Entity Creation Issues

### Zones/Areas not showing up

**Symptoms:**
- Integration connects successfully
- No zone or area entities created
- Logs show "Loaded configuration: X zones, Y areas" but no entities

**Important:** Only zones/areas **with configured names** in the panel are created as entities!

**Solutions:**
1. **Check panel configuration:**
   - Log into your panel's web interface
   - Verify zones/areas have names configured
   - Zones/areas without names are skipped

2. **Check cached config:**
   - Look at `/config/combivox_web/config_<IP>_<PORT>.json`
   - Verify zones/areas have `"zone_name"` or `"area_name"` fields
   - Empty names mean entities won't be created

3. **Enable debug logging:**
   ```yaml
   logger:
     default: info
     logs:
       custom_components.combivox_web: debug
   ```
   - Check logs for "Added zone sensor" or "Added area sensor" messages

### Macros/Scenarios not showing

**Symptoms:**
- Macro buttons not created
- Logs show "Loaded X macros" but no buttons

**Solution:** Same as zones/areas - macros must have names in the panel configuration.

**Check:**
1. Logs for "Parsed macro X: name" messages
2. Cached config file for "macros" section
3. Panel configuration to ensure macros have names

---

## Command Issues

### Areas not arming correctly

**Symptoms:**
- Arm command sent but areas don't arm
- Logs show command sent successfully

**Solutions:**
1. **Check area assignments:**
   - Go to **Settings** → **Devices & Services** → **Combivox Alarm Web** → **Configure**
   - Verify areas are selected for the arm mode you're using
   - Example: If arming "Away", check "Areas for Away Mode"

2. **Check logs:**
   - Look for "Areas armed:" messages
   - Verify the correct area IDs are listed

3. **Enable debug logging:**
   - Check the HTTP response from the panel
   - Look for XML parsing errors

4. **Verify area IDs:**
   - Area IDs must match the panel configuration
   - Check your panel's web interface to identify area numbers

### Disarming doesn't work as expected

**Symptoms:**
- Disarm command disarms all areas instead of selected ones
- Or disarm command doesn't work at all

**Solutions:**
1. **Review disarm behavior:**
   - Empty areas list = disarm ALL areas
   - Must specify areas to disarm selectively

2. **Check integration options:**
   - "Areas for Disarm Mode" determines default disarm behavior
   - Service can override this with specific areas

---

## Performance Issues

### High CPU usage

**Symptoms:**
- Home Assistant shows high CPU usage
- Logs show frequent polling

**Solutions:**
1. **Increase scan interval:**
   - Go to integration **Configure** options
   - Increase "Scan Interval" from default 5 seconds
   - Try 10-30 seconds
   - Minimum recommended: 3 seconds

2. **Reduce polling frequency:**
   - Default 5 seconds may be too fast for some systems
   - 10-15 seconds is usually sufficient

### Slow response time

**Symptoms:**
- Commands take a long time to execute
- Status updates are delayed

**Possible cause:** Panel response time, network latency

**Solutions:**
1. Check network latency between Home Assistant and panel
2. Consider increasing scan interval to reduce load
3. Check if panel is overloaded with requests

---

## Configuration Issues

### Options not saving/loading

**Symptoms:**
- Changes in integration options don't take effect
- Areas/macros don't update after saving options

**Solutions:**
1. **Check logs for "OPTIONS UPDATE LISTENER CALLED":**
   - This confirms options were detected

2. **Verify areas/macros changed:**
   - Integration reloads automatically when areas change
   - For scan interval changes, check for "polling interval updated" log

3. **Manually reload integration:**
   - Go to **Settings** → **Devices & Services**
   - Click **Configure** (without changing anything)
   - Click **Submit** to force reload

### Integration reload required

**Some changes require integration reload:**
- Changing area assignments (automatic reload)
- Adding/removing zones/areas/macros (automatic reload)
- Changing PIN code (manual reload recommended)

**To reload:**
1. Go to **Settings** → **Devices & Services**
2. Find **Combivox Alarm Web** integration
3. Click the three dots (⋮) → **Reload**

---

## Debug Logging

### Enable comprehensive debug logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.combivox_web: debug
    custom_components.combivox_web.auth: debug
    custom_components.combivox_web.base: debug
    custom_components.combivox_web.coordinator: debug
    custom_components.combivox_web.xml_parser: debug
```

### What you'll see with debug logging

**HTTP commands:**
- Full URLs being called
- Request headers (including cookies)
- Response status codes
- Response payloads

**XML parsing:**
- Raw XML content
- Parsed zone/area data
- Alarm memory detection

**Coordinator:**
- Polling timestamps
- Retry attempts
- Connection status changes

**Authentication:**
- Generated passwords
- Cookie retrieval status
- Session management

---

## Still having issues?

### Download Diagnostics

1. Go to **Settings** → **Devices & Services**
2. Find **Combivox Alarm Web** integration
3. Click the three dots (⋮) → **Download Diagnostics**

The diagnostic file includes:
- Connection info (IP, port, timeout)
- Current state (alarm state, armed areas, zones with alarm, GSM status)
- Full configuration (zones, areas, macros)
- Device info (model, firmware, serial)
- Live panel data (anomalies, alarm memory)

### Create GitHub Issue

When creating an issue, please include:

1. **Panel information:**
   - Panel model (e.g., Amica 64 GSM, Amica 128)
   - Web interface type (AmicaWeb, AmicaWeb Plus, SmartWeb)
   - Firmware version (if known)

2. **Configuration:**
   - Home Assistant version
   - Integration version (check in HACS)
   - Scan interval setting

3. **Diagnostic data:**
   - Download diagnostics file
   - Attach to GitHub issue (remove sensitive data like codes first)

4. **Debug logs:**
   - Enable debug logging
   - Reproduce the issue
   - Include relevant log excerpts

**GitHub Issues:** [Create an issue](https://github.com/stich86/ha-combivox-web/issues)
