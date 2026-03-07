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

## Alarm State Disarm Authentication

When the panel is in triggered alarm state, normal disarm commands via `insAree.xml` don't work. The integration uses a different authentication sequence specifically for this scenario.

### Dual Authentication Permutations

The integration uses two different authentication permutations based on the operation:

| Permutation | Array | Username | Purpose |
|-------------|-------|----------|---------|
| `PERMMANUAL_LOGIN` | `[2,7,6,1,4,5,8,3]` | `admin` | Normal login and arm/disarm commands |
| `PERMMANUAL_COMMAND` | `[7,1,6,2,8,4,3,5]` | `combivox` | Alarm state disarm via `reqProg.cgi` |

The authentication method automatically selects the correct permutation based on the username being used.

### reqProg.cgi Disarm Sequence

When the panel is in triggered state, the integration follows this multi-phase retry sequence:

#### Phase 1: req=255 (Initial authentication)

```
POST /reqProg.cgi?req=255
Response: RESEND → Recalculate hash, retry
Response: WAIT  → Save hash, move to Phase 2
Response: REDIRECT → Immediate success
```

- **RESEND**: Wrong PIN or panel busy → Recalculate hash and retry with `req=255`
- **WAIT**: Correct PIN but panel busy → Save current hash, move to Phase 2
- **REDIRECT**: Panel disarmed successfully

Max retries: 5 attempts with 0.5s delay between attempts.

#### Phase 2: req=0 (Disarm execution)

```
POST /reqProg.cgi?req=0
Response: WAIT → Retry with SAME hash
Response: REDIRECT → Success!
```

- **Important**: The hash from Phase 1 is **reused**, not recalculated
- **WAIT**: Panel still processing → Retry with same hash
- **REDIRECT**: Panel successfully disarmed

Max retries: 5 attempts with 0.2s delay between attempts.

### Complete Sequence Example

Based on PCAP analysis of the web interface behavior:

```
1. req=255 (hash A) → RESEND
2. req=255 (hash B) → WAIT
3. req=0   (hash B) → WAIT
4. req=0   (hash B) → REDIRECT ✅
```

### Request Format

**Endpoint:** `/reqProg.cgi?req=255` or `/reqProg.cgi?req=0`

**Payload:**
```
txt_zip=Basic={base64_auth}&hTxt=Basic={base64_auth}&ncc=6
```

**Headers:**
- `Content-Type: text/plain;charset=UTF-8`
- `Referer: http://{IP}:{PORT}/index.htm?id=10&req=0`
- `Cookie: {session_cookie}`

**Important notes:**
- Payload is sent as raw string (not URL-encoded)
- The `=` signs must remain as `=`, not `%3D`
- Base64 auth uses username `combivox` with `PERMMANUAL_COMMAND` permutation

### When This Sequence is Used

The integration automatically uses `reqProg.cgi` when:
- Panel state is `triggered` or `triggered_gsm_excluded`
- User attempts to disarm via UI or service

For normal disarm operations (panel NOT in alarm state), the integration uses the standard `insAree.xml` endpoint.

For more troubleshooting help, see the [Troubleshooting Guide](troubleshooting.md).
