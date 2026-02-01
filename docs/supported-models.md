# Supported Models

This page lists tested and confirmed compatible Combivox alarm panel models.

## Tested Models

| Model | Web Interface | Panel Firmware | Web Interface Firmware | Tester | Status | Notes |
|-------|--------------|----------------|------------------------|---------|--------|-------|
| Amica 64 GSM | AmicaWeb | 2.2 | 2.5/2.5 | @stich86 | ✅ Working | Full functionality confirmed |
| Amica 64 GSM | AmicaWeb Plus | 5.5 | 3/2.3 | @Ale76xx | ✅ Working | Full functionality confirmed |


## Expected Compatibility

The integration should work with any Combivox panel supporting:

- **AmicaWeb** or **AmicaWeb Plus** web interface
- **SmartWeb** web interface
- HTTP/XML communication protocol
- Status polling via `/status9.xml`
- Command execution via `/insAree.xml`, `/execBypass.xml`, `/execChangeImp.xml`

### Potentially Compatible Models

The following models are likely to work but have not been tested:

- Amica series
- Elisa series 
- Any panel with the AmicaWeb/SmartWeb module enabled (not tested with SmartWeb Video Plus)

> **Note:** If your model is not listed, please test and report!

## Report Your Model

Help us improve this integration by reporting your panel model!

### How to Report

1. **Find your model:**
   - Check your panel documentation
   - Or find it in the web interface: System Info → Model
   - Or check the `sensor.combivox_model` entity in Home Assistant

2. **Test functionality:**
   - Does status monitoring work?
   - Can you arm/disarm?
   - Are zones and areas detected?
   - Do macros/scenarios work?
   - Any issues encountered?

3. **Create a GitHub issue** or **comment on existing issue:**
   - Title: "Model Support: [Your Model Name]"
   - Include:
     - Model name (e.g., Amica 64 LTE, Amica 128)
     - Web interface type (AmicaWeb, AmicaWeb Plus, SmartWeb)
     - Panel firmware version (if known)
     - Web interface firmware version (if known)
     - Testing results: What works / what doesn't
     - Any issues or unexpected behavior

4. **Optional:**
   - Download diagnostics (Settings → Devices & Services → Download Diagnostics)
   - Share diagnostic info (remove sensitive codes first!)

## Contribution Guidelines

When reporting your model, please be thorough:

**Required Information:**
- ✅ Panel model name
- ✅ Web interface type
- ✅ Panel firmware version
- ✅ Web interface firmware version
- ✅ Testing results (works/partially works/doesn't work)

**Helpful Information:**
- 📸 Screenshot of model info from web interface
- 🔧 Panel firmware version
- 🌐 Web interface firmware version
- 📊 Number of zones/areas/macros configured
- ⚠️ Any bugs or unexpected behavior discovered
- 💡 Suggestions for improvements

**What to Test:**

1. **Basic functionality:**
   - [ ] Integration connects successfully
   - [ ] Zone entities created
   - [ ] Area entities created
   - [ ] System status sensor works
   - [ ] Model sensor shows correct model

2. **Alarm control:**
   - [ ] Can arm away
   - [ ] Can arm home
   - [ ] Can arm night
   - [ ] Can disarm
   - [ ] Arm modes work (normal/immediate/forced)

3. **Zones:**
   - [ ] Zone status updates correctly
   - [ ] Zone bypass buttons work
   - [ ] Alarm memory detected

4. **Advanced features:**
   - [ ] Macros/scenarios work
   - [ ] GSM sensors work (if applicable)
   - [ ] Clear alarm memory works

## Known Issues

### AmicaWeb vs SmartWeb

- **AmicaWeb**: Original web interface, fully supported
- **AmicaWeb Plus**: Enhanced version, fully supported
- **SmartWeb**: Newer web interface, should work but needs testing

### GSM Functionality

GSM monitoring features require:
- Panel with GSM module enabled
- Valid SIM card with network subscription
- GSM functionality configured in panel

GSM sensors may show "unknown" if:
- GSM module is not installed
- SIM card is not inserted
- No network subscription

## Future Testing Needed

The following scenarios need testing:

1. **Large configurations:**
   - Panels with 32+ zones
   - All 8 areas configured
   - Multiple macros/scenarios

2. **Edge cases:**
   - Zones with special characters in names
   - Very long zone/area names
   - Rapid arm/disarm cycles

3. **Network scenarios:**
   - High latency networks
   - Intermittent connectivity
   - Panel behind VPN
   - Remote panel over internet

## Acknowledgments

Thank you to everyone who tests and reports their panel models. Your feedback helps improve this integration for everyone!
