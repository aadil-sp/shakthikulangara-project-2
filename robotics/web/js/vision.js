// ArUco detection in the browser with js-aruco2 (vendor/aruco.js), loaded with
// OpenCV's DICT_4X4_50 codes so the printed markers are read exactly as the
// desktop app reads them. Corner order matches OpenCV (TL, TR, BR, BL).
import { DICT_4X4_50 } from "./dict.js";

const AR = window.AR;
AR.DICTIONARIES.ARUCO_4X4_50 = { nBits: 16, tau: 2, codeList: DICT_4X4_50 };

export class MarkerTracker {
  constructor() { this.detector = new AR.Detector({ dictionaryName: "ARUCO_4X4_50" }); }

  // imageData: ImageData of the frame. Returns { id: marker }.
  detect(imageData) {
    const out = {};
    for (const m of this.detector.detect(imageData)) {
      const p = m.corners;
      const cx = (p[0].x + p[1].x + p[2].x + p[3].x) / 4;
      const cy = (p[0].y + p[1].y + p[2].y + p[3].y) / 4;
      // Heading: centre -> middle of the top edge (TL-TR), as in the Python app
      const tx = (p[0].x + p[1].x) / 2, ty = (p[0].y + p[1].y) / 2;
      let side = 0;
      for (let i = 0; i < 4; i++) side += Math.hypot(p[i].x - p[(i + 1) % 4].x, p[i].y - p[(i + 1) % 4].y);
      out[m.id] = { id: m.id, x: cx, y: cy, theta: Math.atan2(ty - cy, tx - cx), side: side / 4, corners: p };
    }
    return out;
  }
}
