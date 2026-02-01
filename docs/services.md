# Services Documentation

The integration provides custom services that can be called via **Developer Tools** → **Services** or used in automations and scripts.

## Available Services

### `combivox_web.arm_areas`

Arm specific areas of the alarm panel.

**Service Data:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `areas` | list | Yes | - | List of area IDs (1-8) to arm |
| `arm_mode` | string | No | `normal` | Arm mode: `normal`, `immediate`, or `forced` |

**Arm Modes:**
- **Normal**: Arming with exit delay (standard mode)
- **Immediate**: Arming without exit delay
- **Forced**: Bypass open zones and arm with delay

**Examples:**

Arm areas 1 and 2 with normal mode:
```yaml
service: combivox_web.arm_areas
data:
  areas: [1, 2]
  arm_mode: normal
```

Arm areas 1, 3, and 5 with forced mode:
```yaml
service: combivox_web.arm_areas
data:
  areas: [1, 3, 5]
  arm_mode: forced
```

---

### `combivox_web.disarm_areas`

Disarm specific areas of the alarm panel.

**Service Data:**
| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `areas` | list | No | `[1,2,3,4,5,6,7,8]` | List of area IDs (1-8) to disarm |

**Behavior:**
- **If areas are provided**: Only the selected areas will be disarmed
- **If areas is empty/null**: ALL areas will be disarmed (complete disarm)

This allows selective disarming - for example, keep the perimeter armed while disarming only interior areas.

**Examples:**

Disarm all areas (default):
```yaml
service: combivox_web.disarm_areas
```

Disarm specific areas (1, 2, 3):
```yaml
service: combivox_web.disarm_areas
data:
  areas: [1, 2, 3]
```

---

## Calling Services

### Via Developer Tools

1. Go to **Developer Tools** → **Services**
2. Select service: `combivox_web.arm_areas` or `combivox_web.disarm_areas`
3. Fill in the service data
4. Click **Call Service**

### Via Automation

```yaml
automation:
  - alias: "Arm Away at Night"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: combivox_web.arm_areas
        data:
          areas: [1, 2]
          arm_mode: normal
```

### Via Script

```yaml
arm_all_areas:
  alias: "Arm All Areas"
  sequence:
    - service: combivox_web.arm_areas
      data:
        areas: [1, 2, 3, 4, 5, 6, 7, 8]
        arm_mode: normal
```

---

## Area ID Reference

| Area ID | Description |
|---------|-------------|
| 1 | Area 1 |
| 2 | Area 2 |
| 3 | Area 3 |
| 4 | Area 4 |
| 5 | Area 5 |
| 6 | Area 6 |
| 7 | Area 7 |
| 8 | Area 8 |

> **Note:** Area IDs correspond to the physical areas configured on your Combivox panel. Check your panel configuration to identify which area ID matches which area name.
