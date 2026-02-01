# Authentication Documentation

The integration uses Combivox's proprietary authentication system to communicate with your alarm panel.

## Authentication Overview

The integration automatically handles authentication with your Combivox panel using the master PIN code configured during setup. Authentication is required for most operations including:

- Status monitoring
- Arm and disarm commands
- Zone bypass operations
- Macro/scenario execution
- Alarm memory clearing

## Configuration

### Master PIN Code

The integration requires your panel's **master PIN code** for authentication.

**Important:**
- Use the master code, not a user code
- The integration automatically handles code padding if your code is less than 6 digits
- Example: `1234` is automatically padded to `123400`

### Connection Requirements

For authentication to work properly, ensure:

1. **Panel is accessible**: The panel's web interface (AmicaWeb/SmartWeb) must be enabled
2. **Network connectivity**: Home Assistant must be able to reach the panel's IP address and port
3. **Correct credentials**: Verify your master PIN code is correct

## Troubleshooting Authentication

### "Authentication failed" in logs

**Possible causes:**
1. **Incorrect PIN code** - Verify your master PIN code
2. **Panel not accessible** - Check IP address and port
3. **Web interface disabled** - Ensure AmicaWeb/SmartWeb module is enabled on the panel
4. **Network issues** - Check connectivity between Home Assistant and the panel

**Solutions:**
- Verify the panel's web interface is accessible from a browser
- Double-check your master PIN code
- Check the logs for detailed authentication messages
- Ensure the panel is powered on and connected to the network

### Cookie not found

**Symptom:** Log shows "No cookie found after authentication"

**Causes:**
- Panel is slow to respond
- Panel returns HTML login page instead of setting cookie
- Network issues interrupting authentication

**What happens:**
- The integration falls back to unauthenticated mode
- Basic status polling may still work (unauthenticated)
- Commands (arm/disarm) will not work without authentication

**Solutions:**
- Ensure the panel's web interface works properly
- Check network connectivity between Home Assistant and panel
- Review authentication logs with debug logging enabled
- Try restarting the integration

### Enabling Debug Logging

To see detailed authentication logs:

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.combivox_web: debug
    custom_components.combivox_web.auth: debug
```

**Debug logs show:**
- Authentication attempts
- Response status codes
- Cookie retrieval status
- Connection errors

## Session Management

The integration automatically handles session management:

- **Automatic authentication**: Session is established when the integration starts
- **Session persistence**: The session is maintained for as long as the integration is running
- **Automatic reauthentication**: If the session expires, the integration automatically re-authenticates
- **Cleanup**: Session is properly closed when the integration is unloaded or removed

For more troubleshooting help, see the [Troubleshooting Guide](troubleshooting.md).
