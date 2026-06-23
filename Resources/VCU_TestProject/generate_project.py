#!/usr/bin/env python3
"""
VCU Test Project Generator
==========================
Generates a LARGE, multi-component, multi-release embedded C codebase plus all
the side artefacts that Architecture Validator Pro consumes, so the whole app
can be exercised (and stress-tested) without any proprietary firmware:

  * releases/<REL>/src/<component>/<module>.{c,h}   — a full C source tree per release
  * releases/<REL>/architecture_ports.csv / .xlsx   — Rhapsody-style port export
  * releases/<REL>/requirements.csv / .xlsx         — requirement traces
  * Test Case Design/<Component>_Test_Case_Design.md
  * CHANGELOG.md / README.md

The codebase models a simplified automotive **Vehicle Control Unit (VCU)** with
several software components (each = one Rhapsody "model"): Body Control,
Powertrain, Battery Management, Thermal Management, Chassis Control,
Diagnostics, Comm Gateway and Charging Control. Components, modules, functions,
struct fields and signatures EVOLVE across five releases (R1.0 .. R5.0) so the
change-log / baseline / diff features have real deltas to chew on.

Design constraints (so it compiles to a single ARM ET_REL ELF with DWARF):
  * Every symbol (public + static + global) is namespaced -> no collisions when
    all translation units are amalgamated into one compile unit.
  * Only <stdint.h> (clang freestanding) is used; no libc calls.
  * Each .c includes "vcu_all.h" which declares every struct/enum/prototype, so
    inter-module calls (the call graph) resolve at compile time.

Run with the project venv python (needs openpyxl for the .xlsx exports):
    .venv/bin/python ForTesting/VCU_TestProject/generate_project.py

The companion build_all.sh compiles one ELF per release.
"""
import os
import csv
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

# Release indices 0..4 map to these public names.
RELEASES = ["R1.0", "R2.0", "R3.0", "R4.0", "R5.0"]

# ---------------------------------------------------------------------------
# SCALE knob — bump this to make every release bigger (more signal accessors
# per module => more functions / larger ELF). 1 => ~900-1400 funcs in R5;
# 3 => several thousand. Override with env VCU_SCALE.
# ---------------------------------------------------------------------------
SCALE = int(os.environ.get("VCU_SCALE", "1"))


# ---------------------------------------------------------------------------
# Component / module specification
# ---------------------------------------------------------------------------
# Each module is a dict. `intro`/`retire` are release indices controlling when a
# module exists. `cals` are calibration scalars (get/set accessors). `signals`
# are measured inputs (read accessors). `req_base` seeds requirement IDs.
# ---------------------------------------------------------------------------

COMPONENTS = [
    dict(model="BodyControl", prefix="Bcm", iface_base="If_BCM", req="BCM", intro=0, dir="body_control",
         summary="Body Control Module: exterior/interior lighting, doors, wipers, windows and mirrors.",
         modules=[
             dict(base="lighting",  cals=["MaxCurrentMa", "DimRatePctS", "FadeMs"],     signals=["Switch", "BusVoltage", "AmbientLux"]),
             dict(base="doors",     cals=["LockTimeoutMs", "AjarDebounce"],             signals=["LatchState", "HandlePull", "LockBtn"]),
             dict(base="wipers",    cals=["IntervalMs", "ParkOffsetDeg", "SpeedHigh"],  signals=["RainLevel", "ParkSwitch", "MotorLoad"]),
             dict(base="windows",   cals=["MaxDuty", "PinchThreshMa", "AutoStopMm"],    signals=["HallPos", "Current", "UpBtn", "DownBtn"]),
             dict(base="mirrors",   cals=["FoldAngle", "HeatPwm"],                      signals=["FoldSwitch", "TiltPot"]),
             dict(base="ambient",   cals=["Brightness", "ColorTemp"],                   signals=["DoorOpen", "Dimmer"], intro=3),
         ]),
    dict(model="Powertrain", prefix="Pwt", iface_base="If_PWT", req="PWT", intro=0, dir="powertrain",
         summary="Powertrain coordinator: torque arbitration, throttle, gear selection and cruise.",
         modules=[
             dict(base="torque",    cals=["MaxTorqueNm", "RateLimitNmS", "RegenGain"],  signals=["PedalPct", "WheelSpeed", "MotorRpm"]),
             dict(base="throttle",  cals=["DeadbandPct", "GainNum", "GainDen"],         signals=["PedalRaw", "TpsA", "TpsB"]),
             dict(base="gearbox",   cals=["ShiftDelayMs", "KickdownPct"],               signals=["LeverPos", "OutputRpm", "OilTemp"]),
             dict(base="cruise",    cals=["MaxSetKph", "RampKphS"],                     signals=["SetBtn", "CancelBtn", "VehSpeed"]),
             dict(base="launch",    cals=["LaunchRpm", "SlipTarget"],                   signals=["ClutchPos", "Traction"], intro=3),
         ]),
    dict(model="BatteryMgmt", prefix="Bms", iface_base="If_BMS", req="BMS", intro=0, dir="battery_mgmt",
         summary="Battery Management System: cell monitoring, state of charge, balancing and contactor control.",
         modules=[
             dict(base="cellmon",   cals=["OverVoltMv", "UnderVoltMv", "SampleMs"],     signals=["CellMv", "PackCurrent", "CellTemp"]),
             dict(base="soc",       cals=["NomCapacityAh", "CoulombGain"],              signals=["PackVoltage", "PackCurrent", "PackTemp"]),
             dict(base="balancing", cals=["BalanceDeltaMv", "BalanceMs"],               signals=["MaxCellMv", "MinCellMv"]),
             dict(base="contactor", cals=["PrechargeMs", "WeldDebounce"],               signals=["MainAux", "PrechargeAux", "BusVolt"]),
             dict(base="thermrunaway", cals=["RunawayDtC", "RunawayWindowMs"],          signals=["DtDtC", "GasSensor"], intro=2),
         ]),
    dict(model="ThermalMgmt", prefix="Thm", iface_base="If_THM", req="THM", intro=0, dir="thermal_mgmt",
         summary="Thermal Management: coolant loops, HVAC, pump and fan control.",
         modules=[
             dict(base="coolant",   cals=["TargetC", "HysteresisC", "PumpMinPct"],      signals=["InletC", "OutletC", "FlowLpm"]),
             dict(base="hvac",      cals=["CabinTargetC", "BlowerMax"],                 signals=["CabinC", "EvapC", "SolarLux"]),
             dict(base="pump",      cals=["MaxRpm", "RampRpmS"],                        signals=["FeedbackRpm", "PressureKpa"]),
             dict(base="fan",       cals=["OnThreshC", "OffThreshC"],                   signals=["RadiatorC", "FanRpm"]),
         ]),
    dict(model="ChassisControl", prefix="Chs", iface_base="If_CHS", req="CHS", intro=1, dir="chassis_control",
         summary="Chassis Control (introduced R2.0): ABS, traction, steering assist and suspension.",
         modules=[
             dict(base="abs",       cals=["SlipThreshPct", "PulseMs"],                  signals=["WheelFL", "WheelFR", "WheelRL", "WheelRR"]),
             dict(base="traction",  cals=["TcSlipPct", "TorqueCutNm"],                  signals=["DriveSlip", "Yaw"]),
             dict(base="steering",  cals=["AssistGain", "ReturnGain"],                  signals=["TorqueSensor", "SteerAngle", "Speed"]),
             dict(base="suspension", cals=["DampSoft", "DampHard"],                     signals=["HeightFL", "HeightFR", "AccelZ"], intro=3),
         ]),
    dict(model="Diagnostics", prefix="Diag", iface_base="If_DIAG", req="DIAG", intro=0, dir="diagnostics",
         summary="Diagnostics: DTC management, freeze frames, UDS services and monitors.",
         modules=[
             dict(base="dtc",       cals=["AgingThreshold", "ConfirmCycles"],           signals=["FaultBits", "IgnCycle"]),
             dict(base="freezeframe", cals=["FrameDepth", "SnapshotMask"],              signals=["RpmSnap", "SpeedSnap"]),
             dict(base="uds",       cals=["P2TimeoutMs", "S3TimeoutMs"],                signals=["RxPending", "SessionType"]),
             dict(base="monitor",   cals=["MisfireThresh", "CatTempLimit"],             signals=["O2Sensor", "MisfireCount"]),
             dict(base="security",  cals=["SeedMask", "DelayMs"],                       signals=["AttemptCount", "Unlocked"], intro=2),
         ]),
    dict(model="CommGateway", prefix="Com", iface_base="If_COM", req="COM", intro=0, dir="comm_gateway",
         summary="Communication Gateway: CAN/LIN routing, signal mapping and bus monitoring.",
         modules=[
             dict(base="canrouter", cals=["BusLoadLimit", "RouteTableLen"],             signals=["RxId", "RxDlc", "BusOff"]),
             dict(base="linmaster", cals=["ScheduleMs", "BreakBits"],                   signals=["LinPid", "LinErr"]),
             dict(base="signaldb",  cals=["TimeoutMs", "DefaultValue"],                 signals=["RawA", "RawB", "RawC"]),
             dict(base="netmon",    cals=["WakeTimeoutMs", "SleepDelayMs"],             signals=["BusActivity", "WakeLine"]),
         ]),
    dict(model="ChargingCtrl", prefix="Chg", iface_base="If_CHG", req="CHG", intro=2, dir="charging_ctrl",
         summary="Charging Control (introduced R3.0): AC/DC charging state machine, control pilot and metering.",
         modules=[
             dict(base="acdc",      cals=["MaxAmpsAc", "MaxAmpsDc"],                     signals=["PlugState", "GridVolt", "PilotPwm"]),
             dict(base="sequencer", cals=["StateTimeoutMs", "RetryLimit"],              signals=["ContactorAux", "InsulationMohm"]),
             dict(base="pilot",     cals=["DutyToAmps", "ProxResistor"],                signals=["CpVolt", "PpVolt"]),
             dict(base="metering",  cals=["EnergyScale", "TariffId"],                   signals=["DcCurrent", "DcVolt"]),
         ]),
]


# ---------------------------------------------------------------------------
# Per-release evolution rules (applied on top of the base spec)
# ---------------------------------------------------------------------------

def module_exists(comp, mod, r):
    """Is this module present in release index r?"""
    if r < comp["intro"]:
        return False
    if r < mod.get("intro", 0):
        return False
    if mod.get("retire") is not None and r >= mod["retire"]:
        return False
    return True


def signal_list(mod, r):
    """Signals grow per release -> 'added function' diffs and ELF growth."""
    base = list(mod["signals"])
    extra = r + (SCALE - 1) * 2  # more aux signals as releases advance / scale up
    for i in range(extra):
        base.append("Aux%02d" % (i + 1))
    return base


def cal_list(mod, r):
    base = list(mod["cals"])
    # one extra calibration appears from R3.0 onward
    if r >= 2:
        base.append("TrimOffset")
    if r >= 4:
        base.append("LimpFactor")
    return base


def state_fields(mod, r):
    """State struct fields; some are ADDED at later releases (modified-struct diffs)."""
    fields = [
        ("uint8_t", "phase", "current %s phase" % mod["base"]),
        ("uint16_t", "value", "primary processed value"),
        ("uint16_t", "raw", "last raw sample"),
        ("uint8_t", "valid", "1 = signal path healthy"),
    ]
    if r >= 1:
        fields.append(("uint16_t", "fault_count", "accumulated fault counter (added R2.0)"))
    if r >= 3:
        fields.append(("uint32_t", "uptime_ticks", "ticks since init (added R4.0)"))
        fields.append(("int16_t", "trim", "applied trim offset (added R4.0)"))
    return fields


# ---------------------------------------------------------------------------
# Symbol-name helpers (everything namespaced for single-TU amalgamation)
# ---------------------------------------------------------------------------

def pub(comp, mod, leaf):
    # e.g. Bcm_Lighting_Init
    return "%s_%s_%s" % (comp["prefix"], mod["base"].capitalize(), leaf)


def stat(comp, mod, leaf):
    # e.g. bcm_lighting_clamp_u16  (lowercase -> kept by the function filter)
    return "%s_%s_%s" % (comp["prefix"].lower(), mod["base"], leaf)


def gvar(comp, mod, leaf):
    return "g_%s_%s_%s" % (comp["prefix"].lower(), mod["base"], leaf)


def cfg_type(comp, mod):
    return "%s_%s_Config_t" % (comp["prefix"], mod["base"].capitalize())


def state_type(comp, mod):
    return "%s_%s_State_t" % (comp["prefix"], mod["base"].capitalize())


def phase_enum(comp, mod):
    return "%s_%s_Phase_t" % (comp["prefix"], mod["base"].capitalize())


# ---------------------------------------------------------------------------
# C emission
# ---------------------------------------------------------------------------

def emit_header(comp, mod, r):
    P = comp["prefix"]
    B = mod["base"]
    guard = ("VCU_%s_%s_H" % (P, B)).upper()
    cals = cal_list(mod, r)
    L = []
    L.append("#ifndef %s" % guard)
    L.append("#define %s" % guard)
    L.append("")
    L.append("#include <stdint.h>")
    L.append("")
    L.append("/* %s :: %s module (release %s)" % (comp["model"], B, RELEASES[r]))
    L.append(" * %s */" % comp["summary"])
    L.append("")
    # Phase enum
    L.append("typedef enum {")
    L.append("    %s_OFF = 0," % stat(comp, mod, "p").upper())
    L.append("    %s_INIT," % stat(comp, mod, "p").upper())
    L.append("    %s_RUN," % stat(comp, mod, "p").upper())
    L.append("    %s_FAULT," % stat(comp, mod, "p").upper())
    L.append("    %s_LIMP" % stat(comp, mod, "p").upper())
    L.append("} %s;" % phase_enum(comp, mod))
    L.append("")
    # Config struct (one field per calibration)
    L.append("/* REQ-%s-%s0: %s configuration shall be calibratable. */"
             % (comp["req"], mod["base"][:3].upper(), B))
    L.append("typedef struct {")
    for c in cals:
        L.append("    uint16_t %s;" % _snake(c))
    L.append("} %s;" % cfg_type(comp, mod))
    L.append("")
    # State struct
    L.append("/* REQ-%s-%s1: %s runtime state shall be observable. */"
             % (comp["req"], mod["base"][:3].upper(), B))
    L.append("typedef struct {")
    for t, n, desc in state_fields(mod, r):
        L.append("    %-9s %-14s /* %s */" % (t, n + ";", desc))
    L.append("} %s;" % state_type(comp, mod))
    L.append("")
    # Public prototypes
    for fn in public_functions(comp, mod, r):
        L.append("%s;" % fn["decl"])
    L.append("")
    L.append("#endif /* %s */" % guard)
    L.append("")
    return "\n".join(L)


def _snake(camel):
    out = []
    for i, ch in enumerate(camel):
        if ch.isupper() and i > 0:
            out.append("_")
        out.append(ch.lower())
    return "".join(out)


def public_functions(comp, mod, r):
    """Return a list of public function descriptors present in release r.

    Each descriptor: {name, decl, ret, params, body, req, op}
    The list order is stable so diffs are clean.
    """
    P = comp["prefix"]
    fns = []
    cals = cal_list(mod, r)
    sigs = signal_list(mod, r)
    reqbase = mod["base"][:3].upper()

    # --- Init -----------------------------------------------------------
    name = pub(comp, mod, "Init")
    body = [
        "    if (cfg != 0) {",
        "        %s = *cfg;" % gvar(comp, mod, "cfg"),
        "    }",
        "    %s.phase = %s_INIT;" % (gvar(comp, mod, "state"), stat(comp, mod, "p").upper()),
        "    %s.valid = 1u;" % gvar(comp, mod, "state"),
        "    %s.fault_count = 0u;" % gvar(comp, mod, "state") if r >= 1 else "    /* no fault counter pre-R2.0 */",
        "    %s();" % stat(comp, mod, "reset"),
    ]
    fns.append(dict(
        name=name, ret="void",
        params=[("const %s *" % cfg_type(comp, mod), "cfg")],
        decl="void %s(const %s *cfg)" % (name, cfg_type(comp, mod)),
        body=body, req="REQ-%s-%s2" % (comp["req"], reqbase),
        op=name))

    # --- Calibration accessors -----------------------------------------
    for ci, c in enumerate(cals):
        gname = pub(comp, mod, "Get" + c)
        fns.append(dict(
            name=gname, ret="uint16_t", params=[],
            decl="uint16_t %s(void)" % gname,
            body=["    return %s.%s;" % (gvar(comp, mod, "cfg"), _snake(c))],
            req="REQ-%s-%s3" % (comp["req"], reqbase), op=gname))

        sname = pub(comp, mod, "Set" + c)
        # Signature change: the FIRST calibration setter gains a 'ramp' param at R4.0+
        if ci == 0 and r >= 3:
            fns.append(dict(
                name=sname, ret="void",
                params=[("uint16_t", "v"), ("uint8_t", "ramp")],
                decl="void %s(uint16_t v, uint8_t ramp)" % sname,
                body=[
                    "    uint16_t lim = %s(v, %s.%s);" % (stat(comp, mod, "clamp_u16"), gvar(comp, mod, "cfg"), _snake(c)),
                    "    (void)ramp; /* ramp profile reserved */",
                    "    %s.%s = lim;" % (gvar(comp, mod, "cfg"), _snake(c)),
                ],
                req="REQ-%s-%s3" % (comp["req"], reqbase), op=sname))
        else:
            fns.append(dict(
                name=sname, ret="void", params=[("uint16_t", "v")],
                decl="void %s(uint16_t v)" % sname,
                body=["    %s.%s = %s(v, 0xFFFFu);" % (gvar(comp, mod, "cfg"), _snake(c), stat(comp, mod, "clamp_u16"))],
                req="REQ-%s-%s3" % (comp["req"], reqbase), op=sname))

    # --- Signal readers -------------------------------------------------
    for si, s in enumerate(sigs):
        rname = pub(comp, mod, "Read" + s)
        fns.append(dict(
            name=rname, ret="uint16_t", params=[],
            decl="uint16_t %s(void)" % rname,
            body=[
                "    uint16_t raw = %s[%d];" % (gvar(comp, mod, "inputs"), si),
                "    uint16_t out = %s(raw);" % stat(comp, mod, "scale"),
                "    %s.raw = raw;" % gvar(comp, mod, "state"),
                "    return out;",
            ],
            req="REQ-%s-%s4" % (comp["req"], reqbase), op=rname))

    # --- Compute (uses several helpers) --------------------------------
    cname = pub(comp, mod, "Compute")
    cbody = [
        "    uint16_t a = %s();" % pub(comp, mod, "Read" + sigs[0]),
        "    uint16_t b = %s(a, %s.%s);" % (stat(comp, mod, "lpf"), gvar(comp, mod, "state"), "value"),
        "    uint16_t c = %s(b, %s.%s);" % (stat(comp, mod, "clamp_u16"), gvar(comp, mod, "cfg"), _snake(cals[0])),
        "    %s.value = c;" % gvar(comp, mod, "state"),
        "    return c;",
    ]
    fns.append(dict(
        name=cname, ret="uint16_t", params=[],
        decl="uint16_t %s(void)" % cname, body=cbody,
        req="REQ-%s-%s5" % (comp["req"], reqbase), op=cname))

    # --- SelfTest (ADDED at R3.0) --------------------------------------
    if r >= 2:
        tname = pub(comp, mod, "SelfTest")
        fns.append(dict(
            name=tname, ret="uint8_t", params=[],
            decl="uint8_t %s(void)" % tname,
            body=[
                "    uint8_t crc = %s((const uint8_t *)&%s, (uint8_t)sizeof(%s));"
                % (stat(comp, mod, "crc8"), gvar(comp, mod, "cfg"), cfg_type(comp, mod)),
                "    %s.valid = (crc != 0u) ? 1u : 0u;" % gvar(comp, mod, "state"),
                "    return %s.valid;" % gvar(comp, mod, "state"),
            ],
            req="REQ-%s-%s6" % (comp["req"], reqbase), op=tname))

    # --- LegacyReset (REMOVED after R1.0) ------------------------------
    if r == 0:
        lname = pub(comp, mod, "LegacyReset")
        fns.append(dict(
            name=lname, ret="void", params=[],
            decl="void %s(void)" % lname,
            body=[
                "    /* REQ-%s-%s9: deprecated legacy reset, removed in R2.0. */" % (comp["req"], reqbase),
                "    %s.phase = %s_OFF;" % (gvar(comp, mod, "state"), stat(comp, mod, "p").upper()),
            ],
            req="REQ-%s-%s9" % (comp["req"], reqbase), op=lname))

    # --- Step / hub (body GROWS at R3.0: calls SelfTest) ---------------
    sname = pub(comp, mod, "Step")
    sbody = [
        "    %s.phase = %s_RUN;" % (gvar(comp, mod, "state"), stat(comp, mod, "p").upper()),
        "    (void)%s();" % pub(comp, mod, "Compute"),
    ]
    if r >= 1:
        sbody.append("    if (%s.value > %s.%s) {" % (gvar(comp, mod, "state"), gvar(comp, mod, "cfg"), _snake(cals[0])))
        sbody.append("        %s.fault_count++;" % gvar(comp, mod, "state"))
        sbody.append("        %s.phase = %s_FAULT;" % (gvar(comp, mod, "state"), stat(comp, mod, "p").upper()))
        sbody.append("    }")
    if r >= 2:
        sbody.append("    if (%s() == 0u) {" % pub(comp, mod, "SelfTest"))
        sbody.append("        %s.phase = %s_LIMP;" % (gvar(comp, mod, "state"), stat(comp, mod, "p").upper()))
        sbody.append("    }")
    if r >= 3:
        sbody.append("    %s.uptime_ticks++;" % gvar(comp, mod, "state"))
    fns.append(dict(
        name=sname, ret="void", params=[],
        decl="void %s(void)" % sname, body=sbody,
        req="REQ-%s-%s7" % (comp["req"], reqbase), op=sname))

    # --- GetState ------------------------------------------------------
    gsname = pub(comp, mod, "GetState")
    fns.append(dict(
        name=gsname, ret="const %s *" % state_type(comp, mod), params=[],
        decl="const %s *%s(void)" % (state_type(comp, mod), gsname),
        body=["    return &%s;" % gvar(comp, mod, "state")],
        req="REQ-%s-%s1" % (comp["req"], reqbase), op=gsname))

    return fns


def static_functions(comp, mod, r):
    """The internal helper layer (file-local) used by the public functions —
    these are the leaf/intermediate nodes of the source call graph."""
    return [
        dict(name=stat(comp, mod, "clamp_u16"),
             decl="static uint16_t %s(uint16_t v, uint16_t hi)" % stat(comp, mod, "clamp_u16"),
             body=["    return (v > hi) ? hi : v;"]),
        dict(name=stat(comp, mod, "scale"),
             decl="static uint16_t %s(uint16_t raw)" % stat(comp, mod, "scale"),
             body=[
                 "    uint32_t s = ((uint32_t)raw * 1000u) >> 10;",
                 "    return (uint16_t)(s & 0xFFFFu);",
             ]),
        dict(name=stat(comp, mod, "lpf"),
             decl="static uint16_t %s(uint16_t x, uint16_t prev)" % stat(comp, mod, "lpf"),
             body=[
                 "    /* first-order IIR low-pass: y = (3*prev + x) / 4 */",
                 "    return (uint16_t)(((uint32_t)prev * 3u + x) >> 2);",
             ]),
        dict(name=stat(comp, mod, "crc8"),
             decl="static uint8_t %s(const uint8_t *p, uint8_t n)" % stat(comp, mod, "crc8"),
             body=[
                 "    uint8_t crc = 0xFFu;",
                 "    uint8_t i;",
                 "    for (i = 0u; i < n; i++) {",
                 "        crc = (uint8_t)(crc ^ p[i]);",
                 "        crc = (uint8_t)((crc << 1) ^ ((crc & 0x80u) ? 0x1Du : 0u));",
                 "    }",
                 "    return crc;",
             ]),
        dict(name=stat(comp, mod, "reset"),
             decl="static void %s(void)" % stat(comp, mod, "reset"),
             body=[
                 "    %s.value = 0u;" % gvar(comp, mod, "state"),
                 "    %s.raw = 0u;" % gvar(comp, mod, "state"),
             ]),
    ]


def emit_source(comp, mod, r):
    P = comp["prefix"]
    B = mod["base"]
    cals = cal_list(mod, r)
    sigs = signal_list(mod, r)
    L = []
    L.append('#include "vcu_all.h"')
    L.append("")
    L.append("/* ============================================================")
    L.append(" * %s :: %s   (release %s)" % (comp["model"], B, RELEASES[r]))
    L.append(" * %s" % comp["summary"])
    L.append(" * ============================================================ */")
    L.append("")
    # Globals
    L.append("static %s %s;" % (cfg_type(comp, mod), gvar(comp, mod, "cfg")))
    L.append("static %s %s;" % (state_type(comp, mod), gvar(comp, mod, "state")))
    L.append("static uint16_t %s[%d];" % (gvar(comp, mod, "inputs"), max(8, len(sigs))))
    L.append("")
    # Static prototypes (forward declarations so order is irrelevant)
    for sf in static_functions(comp, mod, r):
        L.append("%s;" % sf["decl"])
    L.append("")
    # Static definitions
    for sf in static_functions(comp, mod, r):
        L.append(sf["decl"])
        L.append("{")
        L.extend(sf["body"])
        L.append("}")
        L.append("")
    # Public definitions
    for fn in public_functions(comp, mod, r):
        if fn.get("req"):
            L.append("/* %s */" % fn["req"])
        L.append(fn["decl"])
        L.append("{")
        L.extend(fn["body"])
        L.append("}")
        L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Top-level VCU scheduler (the application call-graph hub)
# ---------------------------------------------------------------------------

def emit_scheduler(r):
    """vcu_main.c: the top-level scheduler that calls every component's modules —
    forms the application-level call graph hub for the code map."""
    L = []
    L.append('#include "vcu_all.h"')
    L.append("")
    L.append("/* VCU top-level scheduler (release %s)." % RELEASES[r])
    L.append(" * Calls each present component/module Step() once per cycle. */")
    L.append("")
    L.append("static uint32_t g_vcu_tick;")
    L.append("")
    # Per-component cyclic dispatcher
    for comp in COMPONENTS:
        if r < comp["intro"]:
            continue
        fn = "Vcu_%s_Cyclic" % comp["prefix"]
        L.append("void %s(void)" % fn)
        L.append("{")
        for mod in comp["modules"]:
            if module_exists(comp, mod, r):
                L.append("    %s();" % pub(comp, mod, "Step"))
        L.append("}")
        L.append("")
    # Init-all
    L.append("void Vcu_InitAll(void)")
    L.append("{")
    for comp in COMPONENTS:
        if r < comp["intro"]:
            continue
        for mod in comp["modules"]:
            if module_exists(comp, mod, r):
                L.append("    %s(0);" % pub(comp, mod, "Init"))
    L.append("}")
    L.append("")
    # Cyclic-all (10ms task)
    L.append("/* REQ-VCU-040: the 10ms task shall service every active component. */")
    L.append("void Vcu_Cyclic10ms(void)")
    L.append("{")
    L.append("    g_vcu_tick++;")
    for comp in COMPONENTS:
        if r < comp["intro"]:
            continue
        L.append("    Vcu_%s_Cyclic();" % comp["prefix"])
    L.append("}")
    L.append("")
    L.append("uint32_t Vcu_GetTick(void)")
    L.append("{")
    L.append("    return g_vcu_tick;")
    L.append("}")
    L.append("")
    return "\n".join(L)


def emit_all_header(r):
    """vcu_all.h aggregates every module header + scheduler prototypes."""
    L = []
    L.append("#ifndef VCU_ALL_H")
    L.append("#define VCU_ALL_H")
    L.append("")
    L.append("#include <stdint.h>")
    L.append("")
    for comp in COMPONENTS:
        if r < comp["intro"]:
            continue
        for mod in comp["modules"]:
            if module_exists(comp, mod, r):
                L.append('#include "%s/%s.h"' % (comp["dir"], mod["base"]))
    L.append("")
    L.append("/* top-level scheduler */")
    for comp in COMPONENTS:
        if r < comp["intro"]:
            continue
        L.append("void Vcu_%s_Cyclic(void);" % comp["prefix"])
    L.append("void Vcu_InitAll(void);")
    L.append("void Vcu_Cyclic10ms(void);")
    L.append("uint32_t Vcu_GetTick(void);")
    L.append("")
    L.append("#endif /* VCU_ALL_H */")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Side artefacts
# ---------------------------------------------------------------------------

def all_operations(comp, r):
    """All public operation (port) descriptors for one component in release r."""
    ops = []
    for mod in comp["modules"]:
        if not module_exists(comp, mod, r):
            continue
        for fn in public_functions(comp, mod, r):
            ops.append((mod, fn))
    return ops


def write_arch_ports_csv(path, comp_list, r):
    rows = []
    for comp in comp_list:
        if r < comp["intro"]:
            continue
        for mod, fn in all_operations(comp, r):
            port = "p_%s_%s" % (mod["base"], _leaf_of(fn["op"]))
            full = ("Components::P_SW_Components::%s::P10_SW_Arch_Public::%s.%s"
                    % (comp["model"], mod["base"], port))
            iface = "%s_%s" % (comp["iface_base"], mod["base"].capitalize())
            direction = "provided"
            dtype = fn["ret"].replace("const ", "").replace(" *", "*").strip()
            rows.append([port, full, iface, fn["op"], direction, dtype])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(["Port Name", "Full path name", "Required Interface", "Operations", "Direction", "Return Type"])
        w.writerows(rows)
    return len(rows)


def _leaf_of(name):
    # strip the "Prefix_Module_" namespace -> operation leaf
    parts = name.split("_", 2)
    return parts[2] if len(parts) >= 3 else name


def write_requirements_csv(path, comp_list, r):
    rows = []
    rows.append(["REQ-VCU-040", "The 10 ms task shall service every active component each cycle."])
    rows.append(["REQ-VCU-001", "Every software component shall expose an Init and a cyclic Step entry point."])
    for comp in comp_list:
        if r < comp["intro"]:
            continue
        for mod in comp["modules"]:
            if not module_exists(comp, mod, r):
                continue
            rb = mod["base"][:3].upper()
            base = comp["req"]
            rows.append(["REQ-%s-%s0" % (base, rb), "%s %s configuration shall be calibratable." % (comp["model"], mod["base"])])
            rows.append(["REQ-%s-%s1" % (base, rb), "%s %s runtime state shall be observable." % (comp["model"], mod["base"])])
            rows.append(["REQ-%s-%s4" % (base, rb), "%s %s input signals shall be scaled before use." % (comp["model"], mod["base"])])
            rows.append(["REQ-%s-%s5" % (base, rb), "%s %s shall compute a filtered, clamped output." % (comp["model"], mod["base"])])
            rows.append(["REQ-%s-%s7" % (base, rb), "%s %s Step shall update phase and latch faults." % (comp["model"], mod["base"])])
            if r >= 2:
                rows.append(["REQ-%s-%s6" % (base, rb), "%s %s shall provide a self-test returning health." % (comp["model"], mod["base"])])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ID", "Description"])
        w.writerows(rows)
    return len(rows)


def csv_to_xlsx(csv_path, xlsx_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            ws.append(row)
    wb.save(xlsx_path)


# ---------------------------------------------------------------------------
# Test case design docs (one per component, against the final release)
# ---------------------------------------------------------------------------

def write_test_design(path, comp, r):
    L = []
    L.append("# Test Case Design - %s" % comp["model"])
    L.append("")
    L.append("High-level test cases for the **%s** architecture model. %s" % (comp["model"], comp["summary"]))
    L.append("")
    L.append("---")
    tc = 1
    for mod in comp["modules"]:
        if not module_exists(comp, mod, r):
            continue
        rb = mod["base"][:3].upper()
        L.append("## Test Case: TC.%03d - %s init & cyclic" % (tc, mod["base"]))
        L.append("")
        L.append("**Given** the ECU has powered on")
        L.append("**When** `%s` then `%s` are called" % (pub(comp, mod, "Init"), pub(comp, mod, "Step")))
        L.append("**Then** the phase becomes RUN and `value` is a filtered, clamped sample (REQ-%s-%s7)" % (comp["req"], rb))
        L.append("")
        L.append("### Low Level Test Case Design")
        L.append("*(Paste the low-level test cases generated by the AI tab here)*")
        L.append("")
        L.append("---")
        tc += 1
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate():
    rel_root = os.path.join(HERE, "releases")
    if os.path.isdir(rel_root):
        shutil.rmtree(rel_root)
    os.makedirs(rel_root)

    stats = []
    for r, rel in enumerate(RELEASES):
        rdir = os.path.join(rel_root, rel)
        srcdir = os.path.join(rdir, "src")
        os.makedirs(srcdir)

        n_funcs = 0
        n_files = 0
        # vcu_all.h
        with open(os.path.join(srcdir, "vcu_all.h"), "w", encoding="utf-8") as f:
            f.write(emit_all_header(r))
        # scheduler
        with open(os.path.join(srcdir, "vcu_main.c"), "w", encoding="utf-8") as f:
            f.write(emit_scheduler(r))
        n_files += 1

        for comp in COMPONENTS:
            if r < comp["intro"]:
                continue
            cdir = os.path.join(srcdir, comp["dir"])
            os.makedirs(cdir, exist_ok=True)
            for mod in comp["modules"]:
                if not module_exists(comp, mod, r):
                    continue
                with open(os.path.join(cdir, mod["base"] + ".h"), "w", encoding="utf-8") as f:
                    f.write(emit_header(comp, mod, r))
                with open(os.path.join(cdir, mod["base"] + ".c"), "w", encoding="utf-8") as f:
                    f.write(emit_source(comp, mod, r))
                n_funcs += len(public_functions(comp, mod, r)) + len(static_functions(comp, mod, r))
                n_files += 2

        # Side artefacts per release
        ports_csv = os.path.join(rdir, "architecture_ports.csv")
        n_ports = write_arch_ports_csv(ports_csv, COMPONENTS, r)
        csv_to_xlsx(ports_csv, os.path.join(rdir, "architecture_ports.xlsx"))

        req_csv = os.path.join(rdir, "requirements.csv")
        n_reqs = write_requirements_csv(req_csv, COMPONENTS, r)
        csv_to_xlsx(req_csv, os.path.join(rdir, "requirements.xlsx"))

        n_comp = sum(1 for c in COMPONENTS if r >= c["intro"])
        stats.append(dict(rel=rel, files=n_files, funcs=n_funcs, ports=n_ports,
                          reqs=n_reqs, comps=n_comp))
        print("  %-5s  components=%d  src_files=%-4d  functions~%-5d  ports=%-4d  reqs=%d"
              % (rel, n_comp, n_files, n_funcs, n_ports, n_reqs))

    # Test case design (against final release)
    td = os.path.join(HERE, "Test Case Design")
    if os.path.isdir(td):
        shutil.rmtree(td)
    os.makedirs(td)
    last = len(RELEASES) - 1
    for comp in COMPONENTS:
        write_test_design(os.path.join(td, "%s_Test_Case_Design.md" % comp["model"]), comp, last)

    write_changelog(os.path.join(HERE, "CHANGELOG.md"), stats)
    write_readme(os.path.join(HERE, "README.md"), stats)
    print("Done. Test Case Design + CHANGELOG.md + README.md written.")
    return stats


def write_changelog(path, stats):
    L = ["# VCU Test Project — Release Change Log", ""]
    L.append("Five releases with real, tool-visible deltas (added/removed/modified functions,")
    L.append("added struct fields, signature changes, new modules and new components).")
    L.append("")
    L.append("| Release | Components | Src files | ~Functions | Arch ports | Requirements |")
    L.append("|---------|-----------|-----------|-----------|-----------|--------------|")
    for s in stats:
        L.append("| %s | %d | %d | ~%d | %d | %d |" % (s["rel"], s["comps"], s["files"], s["funcs"], s["ports"], s["reqs"]))
    L.append("")
    deltas = [
        ("R1.0", ["Baseline: 6 components (BodyControl, Powertrain, BatteryMgmt, ThermalMgmt, Diagnostics, CommGateway).",
                  "Each module ships `*_LegacyReset` (deprecated) — these are REMOVED in R2.0.",
                  "State struct has 4 fields (phase/value/raw/valid)."]),
        ("R2.0", ["**New component:** ChassisControl (ABS, traction, steering).",
                  "**Removed:** every `*_LegacyReset` function.",
                  "**Modified struct:** all `*_State_t` gain `fault_count` (REQ *xx1).",
                  "**Modified function:** every `*_Step` now latches a fault when value exceeds the cal limit.",
                  "More `ReadAux*` signal accessors per module (auto growth)."]),
        ("R3.0", ["**New component:** ChargingCtrl (AC/DC sequencer, pilot, metering).",
                  "**New modules:** BatteryMgmt::thermrunaway, Diagnostics::security.",
                  "**Added function:** every module gains `*_SelfTest`; `*_Step` now calls it and can enter LIMP.",
                  "**Added calibration:** `TrimOffset` accessor pair across all modules."]),
        ("R4.0", ["**New modules:** BodyControl::ambient, Powertrain::launch, ChassisControl::suspension.",
                  "**Modified struct:** `*_State_t` gain `uptime_ticks` + `trim`.",
                  "**Signature change:** the first calibration setter of each module gains a `ramp` parameter.",
                  "`*_Step` now advances `uptime_ticks`."]),
        ("R5.0", ["**Added calibration:** `LimpFactor` accessor pair across all modules.",
                  "Largest signal-accessor surface (peak function count) — the stress-test release.",
                  "All eight components active simultaneously."]),
    ]
    for rel, items in deltas:
        L.append("## %s" % rel)
        for it in items:
            L.append("- %s" % it)
        L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def write_readme(path, stats):
    last = stats[-1]
    L = []
    L.append("# VCU Test Project — large multi-release embedded C corpus")
    L.append("")
    L.append("A synthetic but realistic automotive **Vehicle Control Unit (VCU)** firmware built")
    L.append("specifically to exercise and **stress-test Architecture Validator Pro** end-to-end")
    L.append("without any proprietary embedded code. It is deliberately bigger and more complex")
    L.append("than the bundled `AI_Demo_WindowLift` demo: **8 software components, %d releases,**" % len(RELEASES))
    L.append("**~%d functions and %d architecture ports in the largest release.**" % (last["funcs"], last["ports"]))
    L.append("")
    L.append("## Layout")
    L.append("```")
    L.append("VCU_TestProject/")
    L.append("  generate_project.py     # regenerates everything (this is the source of truth)")
    L.append("  build_all.sh            # compiles one ARM ELF (with DWARF) per release")
    L.append("  patch_debug_relocs.py   # build-time DWARF reloc fixup (ET_REL, see demo)")
    L.append("  CHANGELOG.md            # the inter-release deltas, narrated")
    L.append("  Test Case Design/       # one HLT doc per component")
    L.append("  releases/")
    for s in stats:
        L.append("    %s/" % s["rel"])
        L.append("      src/                  # full multi-file C tree (%d components)" % s["comps"])
        L.append("      vcu_%s.elf            # ARM ELF w/ DWARF (after build_all.sh)" % s["rel"])
        L.append("      architecture_ports.csv / .xlsx")
        L.append("      requirements.csv / .xlsx")
    L.append("```")
    L.append("")
    L.append("## How to drive every feature")
    L.append("1. **New Project** → save it → set a master password.")
    L.append("2. **Releases:** create one release per `releases/RX.Y` folder; **Load New ELF** →")
    L.append("   that release's `vcu_RX.Y.elf`.")
    L.append("3. **Architecture import:** import `architecture_ports.csv` (or `.xlsx`). Each")
    L.append("   component is a separate **model**; the `Operations` column holds real exported")
    L.append("   function names, so symbol matching resolves at score 100.")
    L.append("4. **Code Map / AI:** point the source at that release's `src/` folder.")
    L.append("5. **Change Log:** Compute Release Diffs between two releases' `src/` folders to")
    L.append("   see added/removed/modified functions, struct-field and signature changes")
    L.append("   (see `CHANGELOG.md` for what to expect).")
    L.append("6. **Requirements / Test Design:** import `requirements.csv`; use the")
    L.append("   `Test Case Design/` docs in the AI Test Generation tab.")
    L.append("")
    L.append("## Rebuilding")
    L.append("```")
    L.append("# regenerate sources + exports (needs venv for openpyxl)")
    L.append(".venv/bin/python ForTesting/VCU_TestProject/generate_project.py")
    L.append("# bigger: VCU_SCALE=3 .venv/bin/python ForTesting/VCU_TestProject/generate_project.py")
    L.append("# compile the ELFs (needs clang w/ arm-none-eabi target)")
    L.append("PYTHON=.venv/bin/python ForTesting/VCU_TestProject/build_all.sh")
    L.append("```")
    L.append("")
    L.append("## Notes on the ELF (same fixup as the demo)")
    L.append("No standalone ARM linker is available on the build host, so each release's")
    L.append("translation units are amalgamated into one compile unit and emitted as a single")
    L.append("**relocatable** ARM ELF (`ET_REL`) with DWARF. `patch_debug_relocs.py` pre-applies")
    L.append("the DWARF debug relocations so both the native Rust parser and the pyelftools")
    L.append("fallback read identical, correct symbols / params / structs / globals. This is a")
    L.append("fixture build step only — not part of the shipped app.")
    L.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    print("Generating VCU test project (SCALE=%d)..." % SCALE)
    generate()
