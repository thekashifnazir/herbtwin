// The photo's own location, read in the browser so the home page can say "Using your
// photo's location" before anything is sent. Display only: the server reads it again
// (where.exif_gps), and a place typed or chosen on the page beats it (where.resolve_location).
// JPEG (APP1 "Exif") and PNG (an eXIf chunk), the two types the form accepts. Anything it
// can't read gives null, never an error. tests/test_photo_gps_js.py holds it to exif_gps.
(() => {
  const tiffStart = (v) => {
    if (v.byteLength > 4 && v.getUint16(0) === 0xffd8) {  // JPEG: the segments before the image data
      let o = 2;
      while (o + 10 <= v.byteLength) {
        const marker = v.getUint16(o);
        if ((marker & 0xff00) !== 0xff00 || marker === 0xffda) return null;
        if (marker === 0xffe1 && v.getUint32(o + 4) === 0x45786966) return o + 10;  // "Exif\0\0"
        o += 2 + v.getUint16(o + 2);
      }
      return null;
    }
    if (v.byteLength > 8 && v.getUint32(0) === 0x89504e47) {  // PNG: the chunks, to IEND
      let o = 8;  // eXIf should come before IDAT, but Pillow (the server) finds it after too
      while (o + 8 <= v.byteLength) {
        const type = v.getUint32(o + 4);
        if (type === 0x65584966) return o + 8;  // "eXIf"
        if (type === 0x49454e44) return null;  // "IEND"
        o += 12 + v.getUint32(o);
      }
    }
    return null;
  };

  const photoGps = (buffer) => {
    try {
      const v = new DataView(buffer);
      const tiff = tiffStart(v);
      if (tiff === null) return null;
      const le = v.getUint16(tiff) === 0x4949;  // "II" little-endian, "MM" big
      const u16 = (o) => v.getUint16(tiff + o, le), u32 = (o) => v.getUint32(tiff + o, le);
      const entry = (ifd, tag) => {
        for (let i = 0, n = u16(ifd); i < n; i++) if (u16(ifd + 2 + i * 12) === tag) return ifd + 2 + i * 12;
        return null;
      };
      const pointer = entry(u32(4), 0x8825);  // IFD0's GPS IFD
      if (pointer === null) return null;
      const gps = u32(pointer + 8);
      const ref = (tag) => {
        const e = entry(gps, tag);
        return e === null ? "" : String.fromCharCode(v.getUint8(tiff + e + 8)).toUpperCase();
      };
      const degrees = (tag) => {  // three RATIONALs: degrees, minutes, seconds
        const e = entry(gps, tag);
        if (e === null || u16(e + 2) !== 5 || u32(e + 4) !== 3) return null;
        let sum = 0;
        for (let i = 0, at = u32(e + 8); i < 3; i++) {
          const den = u32(at + i * 8 + 4);
          if (!den) return null;
          sum += u32(at + i * 8) / den / 60 ** i;
        }
        return sum;
      };
      const lat = degrees(2), lon = degrees(4);
      if (lat === null || lon === null) return null;
      const y = ref(1) === "S" ? -lat : lat, x = ref(3) === "W" ? -lon : lon;
      return Math.abs(y) <= 90 && Math.abs(x) <= 180 ? [y, x] : null;
    } catch {
      return null;  // cut short or malformed: no location, as the server would say
    }
  };

  if (typeof module !== "undefined") module.exports = photoGps;  // the parity test
  else window.herbtwinPhotoGps = photoGps;
})();
