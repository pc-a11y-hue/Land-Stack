/* Minimal stand-in for Leaflet 1.9.4, used ONLY by the browser tests (the sandbox cannot reach the CDN).
   It implements just the calls app.js makes and lets tests trigger map/polygon clicks. It does NOT render. */
(function () {
  const ll = p => Array.isArray(p) ? { lat: p[0], lng: p[1] } : p;
  class Bounds {
    constructor(pts) { this.pts = (pts || []).map(ll); }
    pad() { return this; }
    getCenter() { const n = this.pts.length || 1; return { lat: this.pts.reduce((a, p) => a + p.lat, 0) / n, lng: this.pts.reduce((a, p) => a + p.lng, 0) / n }; }
  }
  class Layer {
    addTo(t) { t.addLayer(this); return this; }
    on(ev, fn) { (this._h = this._h || {})[ev] = fn; return this; }
    fire(ev, e) { if (this._h && this._h[ev]) this._h[ev](e || {}); }
    bindTooltip() { return this; }
    setStyle(s) { this.style = Object.assign({}, this.style, s); return this; }
  }
  class Shape extends Layer {
    constructor(latlngs, opts) { super(); this.latlngs = latlngs; this.style = opts || {}; }
    getBounds() { return new Bounds(Array.isArray(this.latlngs) ? this.latlngs : [this.latlngs]); }
  }
  class Group extends Layer {
    constructor() { super(); this.layers = []; }
    addLayer(l) { if (!this.layers.includes(l)) this.layers.push(l); }
    clearLayers() { this.layers = []; }
    getBounds() { return new Bounds(this.layers.flatMap(l => l.getBounds().pts)); }
  }
  class Map extends Group {
    constructor(id) { super(); this.id = id; this.zoom = 5; this.handlers = {}; }
    setView(c, z) { this.center = c; this.zoom = z; return this; }
    on(ev, fn) { this.handlers[ev] = fn; return this; }
    getZoom() { return this.zoom; }
    hasLayer(l) { return this.layers.includes(l); }
    removeLayer(l) { this.layers = this.layers.filter(x => x !== l); }
    fitBounds(b) { this.lastFit = b; this.zoom = 17; if (this.handlers.zoomend) this.handlers.zoomend(); return this; }
    invalidateSize() { }
    click(lat, lng) { if (this.handlers.click) this.handlers.click({ latlng: { lat, lng } }); }   // test helper
  }
  const mk = C => (a, b) => new C(a, b);
  window.L = {
    map: id => new Map(id), tileLayer: () => new Layer(), layerGroup: () => new Group(),
    featureGroup: arr => { const g = new Group(); g.layers = arr || []; return g; },
    polygon: mk(Shape), polyline: mk(Shape), circle: mk(Shape), circleMarker: mk(Shape),
    marker: (p, o) => new Shape(p, o), divIcon: o => o, latLngBounds: a => new Bounds(a)
  };
})();
