"""ESP32-S3 board definition and placement presets."""

from src.circuit import Circuit


def build_esp32s3() -> Circuit:
    """ESP32-S3 Dev Board (NodeMCU-style) with USB-C, LDO, ESD, LEDs, buttons."""
    c = Circuit("ESP32-S3 DevKit")

    # Simulation-only: voltage source representing USB host 5V supply
    c.add_component(kind="voltage_source", pins={"+": "VBUS", "-": "GND"},
                    ref="VUSB", value="5", unit="V", simulation_only=True)

    # USB-C connector (power + native USB)
    c.add_connector(
        kind="usb_c",
        pins={
            "GND_A1": "GND", "VBUS_A": "VBUS", "CC1": "USB_CC1",
            "DP_A": "USB_DP_A", "DN_A": "USB_DN_A", "GND_A12": "GND",
            "GND_B1": "GND", "VBUS_B": "VBUS", "CC2": "USB_CC2",
            "DP_B": "USB_DP_B", "DN_B": "USB_DN_B", "GND_B12": "GND",
            "SHIELD1": "GND", "SHIELD2": "GND",
            "SHIELD3": "GND", "SHIELD4": "GND",
        },
        ref="J1", value="USB-C",
    )

    # CC pull-downs (5.1k to GND for UFP/sink detection)
    c.add_resistor("USB_CC1", "GND", "5.1k", ref="R1")
    c.add_resistor("USB_CC2", "GND", "5.1k", ref="R2")

    # USB series resistors (22R on D+/D-)
    c.add_resistor("USB_DP_A", "USB_DP", "22", ref="R3")
    c.add_resistor("USB_DN_A", "USB_DN", "22", ref="R4")

    # VBUS decoupling + Schottky reverse protection
    c.add_diode("VBUS", "5V", ref="D1", model="1N5819")
    c.add_capacitor("5V", "GND", "10u", ref="C1")

    # USB ESD protection (USBLC6-2SC6)
    c.add_ic(
        kind="usblc6",
        pins={
            "IO1_A": "USB_DP",
            "GND": "GND",
            "IO2_A": "USB_DN",
            "IO2_B": "ESP_DN",
            "VBUS": "5V",
            "IO1_B": "ESP_DP",
        },
        ref="U3", value="USBLC6-2SC6",
    )

    # AMS1117-3.3 LDO
    c.add_ic(
        kind="ams1117",
        pins={"VIN": "5V", "VOUT": "3V3", "GND": "GND"},
        ref="U2", value="AMS1117-3.3",
    )

    # Power conditioning
    c.add_capacitor("5V", "GND", "22u", ref="C2")
    c.add_capacitor("5V", "GND", "100n", ref="C3")
    c.add_capacitor("3V3", "GND", "22u", ref="C4")
    c.add_capacitor("3V3", "GND", "100n", ref="C5")

    # ESP32 decoupling
    c.add_capacitor("3V3", "GND", "10u", ref="C6")
    c.add_capacitor("3V3", "GND", "100n", ref="C7")

    # Reset / boot
    c.add_resistor("3V3", "ESP_EN", "10k", ref="R5")
    c.add_capacitor("ESP_EN", "GND", "1u", ref="C8")
    c.add_switch("ESP_EN", "GND", ref="SW2")
    c.add_switch("ESP_IO0", "GND", ref="SW1")

    # LEDs
    c.add_resistor("3V3", "LED1_A", "1k", ref="R6")
    c.add_led("LED1_A", "GND", ref="LED1")
    c.add_resistor("ESP_IO38", "LED2_A", "1k", ref="R7")
    c.add_led("LED2_A", "GND", ref="LED2")

    # ESP32-S3-WROOM-1-N8R8 module
    c.add_ic(
        kind="esp32s3",
        pins={
            "1": "GND",
            "2": "3V3",
            "3": "ESP_EN",
            "4": "ESP_IO4",
            "5": "ESP_IO5",
            "6": "ESP_IO6",
            "7": "ESP_IO7",
            "8": "ESP_IO15",
            "9": "ESP_IO16",
            "10": "ESP_IO17",
            "11": "ESP_IO18",
            "12": "ESP_IO8",
            "13": "ESP_IO3",
            "14": "ESP_IO46",
            "15": "ESP_IO9",
            "16": "ESP_IO10",
            "17": "ESP_IO11",
            "18": "ESP_IO12",
            "19": "ESP_IO13",
            "20": "ESP_IO14",
            "21": "ESP_IO21",
            "22": "ESP_IO47",
            "23": "ESP_IO48",
            "24": "ESP_IO45",
            "25": "ESP_IO0",
            "26": "ESP_IO35",
            "27": "ESP_IO36",
            "28": "ESP_IO37",
            "29": "ESP_IO38",
            "30": "ESP_IO39",
            "31": "ESP_IO40",
            "32": "ESP_IO41",
            "33": "ESP_IO42",
            "34": "ESP_IO44",
            "35": "ESP_IO43",
            "36": "ESP_IO2",
            "37": "ESP_IO1",
            "38": "GND",
            "39": "GND",
            "GND": "GND",
        },
        ref="U1", value="ESP32-S3-WROOM-1-N8R8",
    )

    # 2x20 headers for breadboard-friendly layout
    j2_nets = [
        "3V3", "ESP_EN",
        "ESP_IO4", "ESP_IO5", "ESP_IO6", "ESP_IO7",
        "ESP_IO15", "ESP_IO16", "ESP_IO17", "ESP_IO18",
        "ESP_IO8", "ESP_IO3", "ESP_IO46",
        "ESP_IO9", "ESP_IO10", "ESP_IO11", "ESP_IO12",
        "ESP_IO13", "ESP_IO14", "GND",
    ]
    c.add_connector(
        kind="pin_header_20",
        pins={str(i + 1): net for i, net in enumerate(j2_nets)},
        ref="J2", value="1x20",
    )

    j3_nets = [
        "GND", "ESP_IO43", "ESP_IO44",
        "ESP_IO1", "ESP_IO2", "ESP_IO42", "ESP_IO41",
        "ESP_IO40", "ESP_IO39", "ESP_IO38",
        "ESP_IO48", "ESP_IO47", "ESP_IO21",
        "ESP_DP", "ESP_DN",
        "ESP_IO45", "ESP_IO0",
        "5V", "5V", "GND",
    ]
    c.add_connector(
        kind="pin_header_20",
        pins={str(i + 1): net for i, net in enumerate(j3_nets)},
        ref="J3", value="1x20",
    )

    return c


def esp32s3_placement() -> dict[str, tuple[float, float]]:
    """NodeMCU-style custom placement map for ESP32-S3 board."""
    cx = 135.0
    return {
        "J1": (cx, 75.0),
        "U3": (cx - 5, 80.0),
        "R1": (cx + 6, 78.0),
        "R2": (cx + 9, 78.0),
        "R3": (cx - 3, 83.0),
        "R4": (cx + 3, 83.0),
        "D1": (cx + 7, 83.0),
        "C1": (cx + 10, 83.0),
        "U2": (cx - 8, 88.0),
        "C2": (cx - 4, 90.0),
        "C3": (cx, 90.0),
        "C4": (cx + 4, 90.0),
        "C5": (cx + 8, 90.0),
        "U1": (cx, 108.0),
        "C6": (cx - 8, 95.0),
        "C7": (cx + 8, 95.0),
        "R5": (cx - 10, 100.0),
        "C8": (cx - 10, 104.0),
        "SW2": (cx - 12, 108.0),
        "SW1": (cx - 12, 114.0),
        "R6": (cx + 10, 100.0),
        "LED1": (cx + 12, 100.0),
        "R7": (cx + 10, 104.0),
        "LED2": (cx + 12, 104.0),
        "J2": (cx - 12.7, 108.0),
        "J3": (cx + 12.7, 108.0),
    }
