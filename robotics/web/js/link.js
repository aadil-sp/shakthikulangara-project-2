// Link to the car through the ESP32-C3 USB gateway, using the browser's Web
// Serial API (Chrome / Edge). Same text protocol as the desktop app:
//   PC -> gateway : "D,<left>,<right>\n"  "G,<cm>\n" (collision guard)  "B\n" (beep)
//   gateway -> PC : "T,<l>,<f>,<r>,<battery_v>[,<flags>,<car_rssi>,<gw_rssi>,<rtt_ms>,<pwm_l>,<pwm_r>]\n"
//                   "S,<car_ok>,<loss_pct>,<telemetry_hz>,<channel>\n"
export const F_GUARD = 1, F_FAULT_L = 2, F_FAULT_F = 4, F_FAULT_R = 8;
export const GATEWAY_VID = 0x303a;   // ESP32-C3 native USB

export const serialSupported = () => "serial" in navigator;

export class GatewayLink {
  constructor(onMessage) {
    this.onMessage = onMessage || (() => {});
    this.port = null;
    this.writer = null;
    this.telemetry = null;      // { sonar:[l,f,r], battery, flags, carRssi, gwRssi, rtt, pwm, stamp }
    this.status = null;         // { carOk, loss, hz, channel, stamp }
    this.closing = false;
  }

  get open() { return this.port !== null; }

  // Must be called from a click: the browser shows its port picker
  async choose(anyPort = false) {
    const filters = anyPort ? [] : [{ usbVendorId: GATEWAY_VID }];
    const port = await navigator.serial.requestPort({ filters });
    await this.connect(port);
  }

  // Reconnect to a gateway the user already allowed on an earlier visit
  async reconnect() {
    const ports = await navigator.serial.getPorts();
    const port = ports.find(p => p.getInfo().usbVendorId === GATEWAY_VID) || null;
    if (port) await this.connect(port);
    return !!port;
  }

  async connect(port) {
    await this.close();
    await port.open({ baudRate: 115200 });
    this.port = port;
    this.closing = false;
    this.writer = port.writable.getWriter();
    const info = port.getInfo();
    const isGateway = info.usbVendorId === GATEWAY_VID;
    this.onMessage(isGateway ? "Connected to the ESP32-C3 gateway"
      : "Connected to a USB serial port that is not the ESP32-C3 gateway (car's own cable?) - the car won't respond through it");
    this.readLoop(port);
  }

  async readLoop(port) {
    const decoder = new TextDecoder();
    let buf = "";
    while (port.readable && !this.closing) {
      const reader = port.readable.getReader();
      this.reader = reader;
      try {
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n")) >= 0) {
            this.handle(buf.slice(0, i).trim());
            buf = buf.slice(i + 1);
          }
          if (buf.length > 4096) buf = "";
        }
      } catch (e) {
        if (!this.closing) this.onMessage(`Gateway disconnected: ${e.message}`);
        break;
      } finally {
        reader.releaseLock();
      }
    }
    if (!this.closing) { this.port = null; this.writer = null; }
  }

  handle(line) {
    if (!line) return;
    if (line.startsWith("T,")) {
      const v = line.slice(2).split(",").map(Number);
      if (v.length < 4 || v.slice(0, 4).some(Number.isNaN)) return;
      this.telemetry = { sonar: [v[0], v[1], v[2]], battery: v[3], stamp: performance.now() / 1000,
        flags: 0, carRssi: null, gwRssi: null, rtt: null, pwm: null };
      if (v.length >= 10) Object.assign(this.telemetry, { flags: v[4], carRssi: v[5], gwRssi: v[6], rtt: v[7], pwm: [v[8], v[9]] });
    } else if (line.startsWith("S,")) {
      const [ok, loss, hz, ch] = line.slice(2).split(",");
      this.status = { carOk: ok === "1", loss: +loss, hz: +hz, channel: +ch, stamp: performance.now() / 1000 };
    } else {
      this.onMessage(`[gateway] ${line.replace(/^\[GATEWAY\]\s*/, "")}`);
    }
  }

  async write(text) {
    if (!this.writer) return;
    try { await this.writer.write(new TextEncoder().encode(text)); }
    catch (e) { this.onMessage(`Serial write failed: ${e.message}`); }
  }

  send(l, r) { return this.write(`D,${Math.round(l)},${Math.round(r)}\n`); }
  beep() { return this.write("B\n"); }
  setGuard(cm) { return this.write(`G,${Math.max(0, Math.min(100, Math.round(cm)))}\n`); }

  fresh(timeout = 1) {
    const t = this.telemetry;
    return t && performance.now() / 1000 - t.stamp < timeout ? t : null;
  }

  async close() {
    if (!this.port) return;
    this.closing = true;
    try { await this.send(0, 0); } catch (_) {}
    try { this.reader && (await this.reader.cancel()); } catch (_) {}
    try { this.writer && this.writer.releaseLock(); } catch (_) {}
    try { await this.port.close(); } catch (_) {}
    this.port = null; this.writer = null; this.telemetry = null; this.status = null;
  }
}
