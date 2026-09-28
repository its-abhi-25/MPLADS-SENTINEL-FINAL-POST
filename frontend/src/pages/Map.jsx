import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, ChevronDown, ChevronUp, Layers, ArrowLeft, RotateCcw, Info, Target, MapPin, BarChart3, X } from 'lucide-react';
import { getMapData, getMapWorks, getMapFilters, getMps, getConstituencies, getGeoJSON, getGeographicCoverage, getConstituencyIntelligence } from '../services/api';
import LoadingState from '../components/LoadingState';
import ErrorState from '../components/ErrorState';
import { useHouse, HouseNotApplicable } from '../components/HouseToggle';
import { useTranslation } from '../i18n';
import { useLabels } from '../i18n/labels';

const MAP_CENTER = [20.5937, 78.9629];
const MAP_ZOOM = 5;

const PRIORITY_COLORS = {
  CRITICAL: '#a6291f',
  HIGH: '#c45a20',
  MODERATE: '#93630c',
  LOW: '#1c6e46',
};

// labelKey/descKey are i18n keys; `format` receives the locale-aware rupee
// formatter (labels.inr) as its second argument.
const METRIC_MODES = [
  { key: 'priority_rate', labelKey: 'map.priorityRate', descKey: 'map.metric.rate.desc', format: v => v != null ? v.toFixed(1) + '%' : '-' },
  { key: 'flagged_count', labelKey: 'map.metric.count', descKey: 'map.metric.count.desc', format: v => v != null ? String(v) : '-' },
  { key: 'average_risk', labelKey: 'map.metric.risk', descKey: 'map.metric.risk.desc', format: v => v != null ? v.toFixed(1) : '-' },
  { key: 'financial_exposure', labelKey: 'map.metric.exposure', descKey: 'map.metric.exposure.desc', format: (v, inr) => v != null ? inr(v) : '-' },
];

function getMetricValue(c, key) {
  if (!c) return null;
  switch (key) {
    case 'priority_rate': return c.flag_rate;
    case 'flagged_count': return c.flagged;
    case 'average_risk': return c.avg_risk_pct;
    case 'financial_exposure': return c.financial_exposure;
    default: return 0;
  }
}

function getColorForValue(value, metricKey) {
  if (value == null || isNaN(value)) return '#b0b8c8';
  switch (metricKey) {
    case 'priority_rate':
      if (value >= 15) return '#a6291f';
      if (value >= 10) return '#c45a20';
      if (value >= 5) return '#93630c';
      return '#1c6e46';
    case 'flagged_count':
      if (value >= 200) return '#a6291f';
      if (value >= 100) return '#c45a20';
      if (value >= 30) return '#93630c';
      return '#1c6e46';
    case 'average_risk':
      if (value >= 65) return '#a6291f';
      if (value >= 50) return '#c45a20';
      if (value >= 35) return '#93630c';
      return '#1c6e46';
    case 'financial_exposure':
      if (value >= 50000000) return '#a6291f';
      if (value >= 20000000) return '#c45a20';
      if (value >= 5000000) return '#93630c';
      return '#1c6e46';
    default: return '#b0b8c8';
  }
}

function getLegendItems(metricKey, t) {
  const noData = t('map.noData');
  const cr = t('common.unit.cr');
  switch (metricKey) {
    case 'priority_rate':
      return [
        { label: '\u226515%', color: '#a6291f' },
        { label: '10\u201315%', color: '#c45a20' },
        { label: '5\u201310%', color: '#93630c' },
        { label: '<5%', color: '#1c6e46' },
        { label: noData, color: '#b0b8c8' },
      ];
    case 'flagged_count':
      return [
        { label: '\u2265200', color: '#a6291f' },
        { label: '100\u2013200', color: '#c45a20' },
        { label: '30\u2013100', color: '#93630c' },
        { label: '<30', color: '#1c6e46' },
        { label: noData, color: '#b0b8c8' },
      ];
    case 'average_risk':
      return [
        { label: '\u226565', color: '#a6291f' },
        { label: '50\u201365', color: '#c45a20' },
        { label: '35\u201350', color: '#93630c' },
        { label: '<35', color: '#1c6e46' },
        { label: noData, color: '#b0b8c8' },
      ];
    case 'financial_exposure':
      return [
        { label: `\u226550 ${cr}`, color: '#a6291f' },
        { label: `20\u201350 ${cr}`, color: '#c45a20' },
        { label: `5\u201320 ${cr}`, color: '#93630c' },
        { label: `<5 ${cr}`, color: '#1c6e46' },
        { label: noData, color: '#b0b8c8' },
      ];
    default: return [];
  }
}

export default function MapPage() {
  const { t } = useTranslation();
  const labels = useLabels();
  const { house } = useHouse();
  const isRS = house === 'RS';
  // Leaflet popups are built as HTML strings when opened, outside React's
  // render cycle. They read the latest labels through this ref so a language
  // switch applies to the next popup without rebuilding any map layers.
  const labelsRef = useRef(labels);
  labelsRef.current = labels;
  const navigate = useNavigate();
  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const geoJsonLayerRef = useRef(null);
  const workMarkersRef = useRef(null);

  const [loading, setLoading] = useState(true);
  const [constituencyData, setConstituencyData] = useState([]);
  const [works, setWorks] = useState([]);
  const [geojsonData, setGeojsonData] = useState(null);
  const [coverage, setCoverage] = useState(null);
  const [filterOptions, setFilterOptions] = useState({});
  const [mapMetric, setMapMetric] = useState('priority_rate');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [searchInput, setSearchInput] = useState('');
  const [mpList, setMpList] = useState([]);
  const [constituencyList, setConstituencyList] = useState([]);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestHighlight, setSuggestHighlight] = useState(-1);
  const searchBoxRef = useRef(null);

  const [activeFilters, setActiveFilters] = useState({ state: '', priority: '', stage: '', search: '' });

  const [selectedConstituency, setSelectedConstituency] = useState(null);
  const [constituencyIntel, setConstituencyIntel] = useState(null);
  const [intelLoading, setIntelLoading] = useState(false);
  const [showWorkMarkers, setShowWorkMarkers] = useState(false);
  // Failed loads are kept per data source so each one is shown where its
  // data would have appeared -- never silently rendered as "no data".
  const [loadErrors, setLoadErrors] = useState({});
  const [reloadKey, setReloadKey] = useState(0);
  const setLoadError = useCallback((key, err) => {
    setLoadErrors(prev => {
      if (!err && !prev[key]) return prev;
      const next = { ...prev };
      if (err) next[key] = err; else delete next[key];
      return next;
    });
  }, []);

  const loadFilters = useCallback(() => {
    setLoadError('filters', null);
    getMapFilters().then(setFilterOptions).catch(e => setLoadError('filters', e));
  }, [setLoadError]);

  const loadLists = useCallback(() => {
    setLoadError('lists', null);
    Promise.all([getMps(), getConstituencies()]).then(([mps, cons]) => {
      setMpList(mps.mps || []);
      setConstituencyList((cons.constituencies || []).map(c => c.Constituency).filter(Boolean));
    }).catch(e => setLoadError('lists', e));
  }, [setLoadError]);

  useEffect(() => { loadFilters(); }, [loadFilters]);
  useEffect(() => { loadLists(); }, [loadLists]);

  useEffect(() => {
    setLoading(true);
    setSelectedConstituency(null);
    setConstituencyIntel(null);
    setShowWorkMarkers(false);
    setWorks([]);

    const params = {};
    if (activeFilters.state) params.state = activeFilters.state;
    if (activeFilters.priority) params.priority = activeFilters.priority;
    if (activeFilters.stage) params.stage = activeFilters.stage;
    if (activeFilters.search) params.search = activeFilters.search;

    setLoadError('data', null);
    setLoadError('boundaries', null);
    setLoadError('coverage', null);
    Promise.all([
      getMapData(params),
      getGeoJSON().catch((e) => { setLoadError('boundaries', e); return null; }),
      getGeographicCoverage().catch((e) => { setLoadError('coverage', e); return null; }),
    ]).then(([mapData, geojson, cov]) => {
      setConstituencyData(mapData);
      if (geojson) setGeojsonData(geojson);
      if (cov) setCoverage(cov);
      setLoading(false);
    }).catch((e) => {
      // Don't leave the previous filters' colours on the map under a failure.
      setConstituencyData([]);
      setLoadError('data', e);
      setLoading(false);
    });
  }, [activeFilters, reloadKey, setLoadError]);

  const retryMapData = useCallback(() => setReloadKey(k => k + 1), []);

  const loadConstituencyWorks = useCallback((state, constituency) => {
    setShowWorkMarkers(true);
    const params = { state, constituency };
    if (activeFilters.priority) params.priority = activeFilters.priority;
    if (activeFilters.stage) params.stage = activeFilters.stage;
    if (activeFilters.search) params.search = activeFilters.search;
    setLoadError('works', null);
    getMapWorks(params).then(data => {
      setWorks(data);
    }).catch((e) => { setWorks([]); setLoadError('works', e); });
  }, [activeFilters, setLoadError]);

  const selectConstituency = useCallback((state, constituency) => {
    // Constituency drill-down doesn't apply to Rajya Sabha; surface the
    // panel's explicit not-applicable notice instead of fetching nothing.
    if (isRS) {
      if (mapInstanceRef.current) mapInstanceRef.current.closePopup();
      setSidebarOpen(true);
      return;
    }
    setSelectedConstituency({ state, constituency });
    setIntelLoading(true);
    setShowWorkMarkers(true);

    setLoadError('intel', null);
    getConstituencyIntelligence(state, constituency).then(intel => {
      setConstituencyIntel(intel);
      setIntelLoading(false);
    }).catch((e) => {
      setConstituencyIntel(null);
      setLoadError('intel', e);
      setIntelLoading(false);
    });

    loadConstituencyWorks(state, constituency);

    if (mapInstanceRef.current) {
      const L = window.L;
      if (L && geoJsonLayerRef.current) {
        geoJsonLayerRef.current.eachLayer(layer => {
          if (layer.eachLayer) {
            layer.eachLayer(sub => {
              const props = sub.feature && sub.feature.properties;
              if (props && props.dataset_state === state && props.dataset_constituency === constituency) {
                if (sub.getBounds) {
                  mapInstanceRef.current.fitBounds(sub.getBounds(), { padding: [80, 80], maxZoom: 10 });
                }
              }
            });
          }
        });
      }
    }
  }, [loadConstituencyWorks, isRS]);

  const resetToNational = useCallback(() => {
    setSelectedConstituency(null);
    setConstituencyIntel(null);
    setShowWorkMarkers(false);
    setWorks([]);
    if (workMarkersRef.current) workMarkersRef.current.clearLayers();
    if (mapInstanceRef.current) {
      mapInstanceRef.current.setView(MAP_CENTER, MAP_ZOOM);
    }
  }, []);

  const handleFilterChange = useCallback((key, value) => {
    setActiveFilters(prev => ({ ...prev, [key]: value }));
  }, []);

  const clearFilters = useCallback(() => {
    setActiveFilters({ state: '', priority: '', stage: '', search: '' });
    setSearchInput('');
    setSuggestOpen(false);
    setSuggestHighlight(-1);
  }, []);

  const hasActiveFilters = Object.values(activeFilters).some(v => v !== '');

  const suggestions = useMemo(() => {
    const q = searchInput.trim().toLowerCase();
    if (q.length < 2) return [];
    const mpMatches = mpList.filter(n => n.toLowerCase().includes(q)).slice(0, 5).map(n => ({ type: 'MP', name: n }));
    const constMatches = constituencyList.filter(n => n.toLowerCase().includes(q)).slice(0, 5).map(n => ({ type: 'Constituency', name: n }));
    return [...mpMatches, ...constMatches].slice(0, 8);
  }, [searchInput, mpList, constituencyList]);

  useEffect(() => {
    const handleOutside = (e) => {
      const insideInput = searchBoxRef.current && searchBoxRef.current.contains(e.target);
      const insideDropdown = e.target.closest && e.target.closest('[data-map-search-suggestions]');
      if (!insideInput && !insideDropdown) setSuggestOpen(false);
    };
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, []);

  const selectSuggestion = (name) => {
    setSearchInput(name);
    setSuggestOpen(false);
    setSuggestHighlight(-1);
    setActiveFilters(prev => ({ ...prev, search: name }));
  };

  const handleSearchKeyDown = (e) => {
    if (!suggestOpen || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setSuggestHighlight(h => Math.min(h + 1, suggestions.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSuggestHighlight(h => Math.max(h - 1, 0)); }
    else if (e.key === 'Enter' && suggestHighlight >= 0) { e.preventDefault(); selectSuggestion(suggestions[suggestHighlight].name); }
    else if (e.key === 'Escape') { setSuggestOpen(false); }
  };

  useEffect(() => {
    const t = setTimeout(() => {
      setActiveFilters(prev => (prev.search === searchInput ? prev : { ...prev, search: searchInput }));
    }, 350);
    return () => clearTimeout(t);
  }, [searchInput]);

  useEffect(() => {
    window.__mapSelectConstituency = (state, constituency) => {
      selectConstituency(state, constituency);
    };
    return () => { delete window.__mapSelectConstituency; };
  }, [selectConstituency]);

  useEffect(() => {
    window.__mapNavigate = (path) => { navigate(path); };
    return () => { delete window.__mapNavigate; };
  }, [navigate]);

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;
    const L = window.L;
    if (!L) return;

    const map = L.map(mapRef.current, {
      center: MAP_CENTER,
      zoom: MAP_ZOOM,
      maxZoom: 18,
      minZoom: 3,
      zoomControl: false,
    });

    L.control.zoom({ position: 'topright' }).addTo(map);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 18,
    }).addTo(map);

    mapInstanceRef.current = map;
    geoJsonLayerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Leaflet's zoom buttons carry English title/aria-label by default; keep
  // them in the selected language (also re-applies on language change).
  useEffect(() => {
    const root = mapRef.current;
    if (!root) return;
    const zin = root.querySelector('.leaflet-control-zoom-in');
    const zout = root.querySelector('.leaflet-control-zoom-out');
    if (zin) { zin.title = t('map.zoomIn'); zin.setAttribute('aria-label', t('map.zoomIn')); }
    if (zout) { zout.title = t('map.zoomOut'); zout.setAttribute('aria-label', t('map.zoomOut')); }
  }, [t]);

  useEffect(() => {
    if (!mapInstanceRef.current || !geoJsonLayerRef.current) return;
    const L = window.L;
    if (!L || !geojsonData) return;

    const layer = geoJsonLayerRef.current;
    layer.clearLayers();

    const dataMap = {};
    constituencyData.forEach(c => {
      dataMap[c.State + '|' + c.Constituency] = c;
    });

    const geoFeatures = geojsonData.features || [];
    let allBounds = [];

    geoFeatures.forEach(feature => {
      const props = feature.properties || {};
      const state = props.dataset_state;
      const constituency = props.dataset_constituency;
      const key = state + '|' + constituency;
      const cData = dataMap[key];
      const metricValue = cData ? getMetricValue(cData, mapMetric) : null;
      const color = getColorForValue(metricValue, mapMetric);
      const isSelected = selectedConstituency && selectedConstituency.state === state && selectedConstituency.constituency === constituency;

      const geoLayer = L.geoJSON(feature, {
        style: function() {
          return {
            fillColor: color,
            weight: isSelected ? 3 : 1.5,
            opacity: 1,
            color: isSelected ? '#141c33' : 'rgba(255,255,255,0.7)',
            fillOpacity: isSelected ? 0.85 : 0.7,
          };
        },
        onEachFeature: function(feat, l) {
          if (!cData) return;
          const metricInfo = METRIC_MODES.find(m => m.key === mapMetric);
          const metricVal = getMetricValue(cData, mapMetric);

          // Evaluated when the popup opens (Leaflet accepts a function), so
          // the text always reflects the language selected at that moment.
          const buildPopupHtml = () => {
            const L10 = labelsRef.current;
            const tr = L10.t;
            const formatted = metricInfo ? metricInfo.format(metricVal, L10.inr) : (metricVal != null ? String(metricVal) : '-');
            return '<div style="font-family:IBM Plex Sans,sans-serif;min-width:220px;">' +
              '<div style="font-size:13px;font-weight:700;color:#141c33;margin-bottom:2px;">' + constituency + '</div>' +
              '<div style="font-size:11px;color:#454e64;margin-bottom:8px;">' + state + '</div>' +
              '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:11px;margin-bottom:8px;">' +
              '<div>' + tr('map.popup.works', { n: '<strong>' + cData.total + '</strong>' }) + '</div>' +
              '<div><strong>' + L10.inr(cData.total_amount) + '</strong></div>' +
              '<div style="color:#a6291f;">' + tr('map.popup.flagged', { n: '<strong>' + cData.flagged + '</strong>' }) + '</div>' +
              '<div>' + (cData.flag_rate != null
                ? tr('map.popup.rate', { pct: '<strong>' + cData.flag_rate + '</strong>' })
                : tr('map.priorityRate') + ': ' + tr('map.rateNA')) + '</div>' +
              '</div>' +
              '<div style="font-size:11px;color:#737d95;border-top:1px solid #dfe2ea;padding-top:6px;margin-bottom:6px;">' +
              '<strong>' + (metricInfo ? tr(metricInfo.labelKey) : '') + ':</strong> ' + formatted +
              '</div>' +
              '<button onclick="window.__mapSelectConstituency(\'' + state + '\',\'' + constituency.replace(/'/g, "\\'") + '\')" style="' +
              'width:100%;padding:6px 12px;background:#384a8a;color:white;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;">' +
              tr('map.popup.explore') + '</button></div>';
          };

          l.bindPopup(buildPopupHtml, { maxWidth: 280 });
          l.on('mouseover', function() { this.setStyle({ weight: 3, color: '#141c33', fillOpacity: 0.85 }); });
          l.on('mouseout', function() {
            const isStillSelected = selectedConstituency && selectedConstituency.state === state && selectedConstituency.constituency === constituency;
            geoLayer.resetStyle(this);
            if (isStillSelected) this.setStyle({ weight: 3, color: '#141c33', fillOpacity: 0.85 });
          });
        },
      });

      geoLayer.eachLayer(function(l) {
        if (l.getBounds) {
          const b = l.getBounds();
          if (b.isValid()) allBounds.push(b);
        }
      });

      layer.addLayer(geoLayer);
    });

    if (allBounds.length > 0 && !selectedConstituency) {
      let combined = allBounds[0];
      for (let i = 1; i < allBounds.length; i++) combined.extend(allBounds[i]);
      if (combined.isValid()) mapInstanceRef.current.fitBounds(combined, { padding: [30, 30] });
    }
  }, [constituencyData, geojsonData, mapMetric, selectedConstituency]);

  useEffect(() => {
    if (!mapInstanceRef.current) return;
    const L = window.L;
    if (!L) return;

    if (!workMarkersRef.current) {
      workMarkersRef.current = L.markerClusterGroup({ singleMarkerMode: true }).addTo(mapInstanceRef.current);
    }
    workMarkersRef.current.clearLayers();

    if (!showWorkMarkers || works.length === 0) return;

    const iconCache = {};
    function getDotIcon(color) {
      if (!iconCache[color]) {
        iconCache[color] = L.divIcon({
          html: '<div style="width:10px;height:10px;background:' + color + ';border-radius:50%;border:2px solid white;box-shadow:0 1px 3px rgba(0,0,0,0.3);"></div>',
          className: '',
          iconSize: [10, 10],
          iconAnchor: [5, 5],
        });
      }
      return iconCache[color];
    }

    works.forEach(function(work) {
      if (!work.latitude || !work.longitude) return;
      var priority = work.risk_level || work.priority || 'NOT_EVALUATED';
      var color = PRIORITY_COLORS[priority] || '#b0b8c8';
      var marker = L.marker([work.latitude, work.longitude], { icon: getDotIcon(color) });
      var riskScore = work.risk_score != null ? (work.risk_score * 100).toFixed(0) : '-';
      var buildPopupContent = function() {
        var L10 = labelsRef.current;
        var tr = L10.t;
        return '<div style="font-family:IBM Plex Sans,sans-serif;min-width:220px;max-width:300px;">' +
          '<div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">' +
          '<span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:10px;font-weight:600;background:' + color + '15;color:' + color + ';border:1px solid ' + color + '30;">' + String(L10.riskShort(priority)).toUpperCase() + '</span>' +
          '<span style="font-size:10px;color:#737d95;">' + tr('map.popup.risk', { score: riskScore }) + '</span></div>' +
          '<div style="font-size:13px;font-weight:600;color:#141c33;margin-bottom:4px;line-height:1.4;">' + (work.description || tr('common.noDescription')) + '</div>' +
          '<div style="font-size:11px;color:#454e64;margin-bottom:6px;">' +
          '<div><strong>' + tr('common.mp') + ':</strong> ' + work.mp + '</div>' +
          '<div><strong>' + tr('common.amount') + ':</strong> ' + L10.inr(work.amount) + ' | <strong>' + tr('common.stage') + ':</strong> ' + L10.stageUpper(work.stage) + '</div>' +
          '</div>' +
          '<div style="font-size:10px;color:#9aa2b6;margin-bottom:6px;">' + tr('map.popup.location') + ': ' +
          (work.location_level === 'CONSTITUENCY' ? tr('map.popup.locConst') : work.location_level === 'STATE' ? tr('map.popup.locState') : (work.location_level || tr('map.popup.locUnknown'))) + '</div>' +
          '<button onclick="window.__mapNavigate(\'/record/' + work.record_id + '\')" style="' +
          'width:100%;padding:6px 12px;background:#384a8a;color:white;border:none;border-radius:4px;font-size:11px;font-weight:600;cursor:pointer;">' +
          tr('map.popup.view') + '</button></div>';
      };
      marker.bindPopup(buildPopupContent, { maxWidth: 320 });
      marker.on('click', function() { setSelectedConstituencyData(work); });
      workMarkersRef.current.addLayer(marker);
    });
  }, [works, showWorkMarkers]);

  const [selectedWorkData, setSelectedWorkData] = useState(null);

  const nationalStats = useMemo(() => {
    const total = constituencyData.reduce((s, c) => s + c.total, 0);
    const critical = constituencyData.reduce((s, c) => s + c.critical, 0);
    const high = constituencyData.reduce((s, c) => s + c.high, 0);
    const moderate = constituencyData.reduce((s, c) => s + c.moderate, 0);
    const low = constituencyData.reduce((s, c) => s + c.low, 0);
    const totalAmount = constituencyData.reduce((s, c) => s + (c.total_amount || 0), 0);
    const flagged = critical + high;
    const priorityRate = total > 0 ? (flagged / total * 100).toFixed(1) : 0;
    return { total, critical, high, moderate, low, flagged, totalAmount, priorityRate };
  }, [constituencyData]);

  const legendItems = useMemo(() => getLegendItems(mapMetric, t), [mapMetric, t]);
  const currentMetricInfo = METRIC_MODES.find(m => m.key === mapMetric);

  return (
    <div className="map-shell">
      {sidebarOpen ? (
        <div className="map-floating-panel">
          <div className="map-panel-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h3>{t('map.title')}</h3>
              <p>{t('map.subtitle')}</p>
            </div>
            <button onClick={() => setSidebarOpen(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-on-dark-muted)', padding: 4, flexShrink: 0 }} aria-label={t('map.collapse')}>
              <ChevronDown size={16} />
            </button>
          </div>

          <div className="map-panel-body">
            {isRS && <HouseNotApplicable feature={t('house.na.mapDrilldown')} />}
            {loadErrors.data && <ErrorState compact what={t('map.what.data')} error={loadErrors.data} onRetry={retryMapData} />}
            {loadErrors.boundaries && <ErrorState compact what={t('map.what.boundaries')} error={loadErrors.boundaries} onRetry={retryMapData} />}
            {loadErrors.coverage && <ErrorState compact what={t('map.what.coverage')} error={loadErrors.coverage} onRetry={retryMapData} />}
            {loadErrors.filters && <ErrorState compact what={t('map.what.filters')} error={loadErrors.filters} onRetry={loadFilters} />}
            {loadErrors.lists && <ErrorState compact what={t('map.what.lists')} error={loadErrors.lists} onRetry={loadLists} />}
            {loadErrors.works && <ErrorState compact what={t('map.what.works')} error={loadErrors.works} />}
            {selectedConstituency && loadErrors.intel && (
              <ErrorState compact what={t('map.what.intel')} error={loadErrors.intel}
                onRetry={() => selectConstituency(selectedConstituency.state, selectedConstituency.constituency)} />
            )}
            {selectedConstituency && (
              <div style={{ marginBottom: 16 }}>
                <button onClick={resetToNational} style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'var(--indigo-subtle)', border: '1px solid var(--indigo-border)', borderRadius: 'var(--radius-md)', padding: '8px 12px', cursor: 'pointer', fontSize: 12, fontWeight: 600, color: 'var(--indigo-600)', width: '100%', justifyContent: 'center', marginBottom: 12 }}>
                  <RotateCcw size={13} /> {t('map.resetNational')}
                </button>
              </div>
            )}

            <div style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <Filter size={13} />
                <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--shell-800)', textTransform: 'uppercase', letterSpacing: 0.4 }}>{t('common.filters')}</span>
                {hasActiveFilters && (
                  <button onClick={clearFilters} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--gov-blue)', fontSize: 11, cursor: 'pointer', fontWeight: 600 }}>{t('common.clearAll')}</button>
                )}
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div className="toolbar-group">
                  <span className="toolbar-label">{t('common.state')}</span>
                  <select className="toolbar-select" style={{ width: '100%' }} value={activeFilters.state} onChange={(e) => handleFilterChange('state', e.target.value)}>
                    <option value="">{t('common.allStates')}</option>
                    {(filterOptions.states || []).map(s => <option key={s} value={s}>{labels.state(s)}</option>)}
                  </select>
                </div>
                <div className="toolbar-group">
                  <span className="toolbar-label">{t('common.riskLevel')}</span>
                  <select className="toolbar-select" style={{ width: '100%' }} value={activeFilters.priority} onChange={(e) => handleFilterChange('priority', e.target.value)}>
                    <option value="">{t('common.allRisk')}</option>
                    <option value="CRITICAL">{t('risk.critical')}</option>
                    <option value="HIGH">{t('risk.high')}</option>
                    <option value="MODERATE">{t('risk.moderate')}</option>
                    <option value="LOW">{t('risk.low')}</option>
                  </select>
                </div>
                <div className="toolbar-group">
                  <span className="toolbar-label">{t('common.stage')}</span>
                  <select className="toolbar-select" style={{ width: '100%' }} value={activeFilters.stage} onChange={(e) => handleFilterChange('stage', e.target.value)}>
                    <option value="">{t('common.allStages')}</option>
                    {(filterOptions.stages || []).map(s => <option key={s} value={s}>{labels.stageUpper(s)}</option>)}
                  </select>
                </div>
                <div className="toolbar-search" style={{ minWidth: 0 }} ref={searchBoxRef}>
                  <Search size={14} />
                  <input type="text" className="toolbar-input" style={{ width: '100%' }} placeholder={t('map.searchPlaceholder')} value={searchInput} onChange={(e) => { setSearchInput(e.target.value); setSuggestOpen(true); setSuggestHighlight(-1); }} onFocus={() => searchInput.trim().length >= 2 && setSuggestOpen(true)} onKeyDown={handleSearchKeyDown} autoComplete="off" />
                  {suggestOpen && suggestions.length > 0 && searchBoxRef.current && createPortal(
                    <div data-map-search-suggestions style={{ position: 'fixed', top: searchBoxRef.current.getBoundingClientRect().bottom + 4, left: searchBoxRef.current.getBoundingClientRect().left, width: searchBoxRef.current.getBoundingClientRect().width, background: '#fff', border: '1px solid var(--border-default)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-lg)', zIndex: 5000, maxHeight: 260, overflowY: 'auto' }}>
                      {suggestions.map((s, i) => (
                        <div key={s.type + '-' + s.name} onMouseEnter={() => setSuggestHighlight(i)} onClick={() => selectSuggestion(s.name)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '8px 12px', cursor: 'pointer', fontSize: 12.5, background: i === suggestHighlight ? 'var(--bg-hover)' : 'transparent', borderBottom: i < suggestions.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
                          <span style={{ color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
                          <span style={{ flexShrink: 0, fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.3, color: 'var(--text-faint)' }}>{s.type === 'MP' ? t('common.mp') : t('common.constituency')}</span>
                        </div>
                      ))}
                    </div>,
                    document.body
                  )}
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--shell-800)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 }}>{t('map.metricView')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {METRIC_MODES.map(m => (
                  <button key={m.key} onClick={() => setMapMetric(m.key)} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', background: mapMetric === m.key ? 'var(--indigo-subtle)' : 'transparent', border: mapMetric === m.key ? '1px solid var(--indigo-border)' : '1px solid transparent', borderRadius: 'var(--radius-md)', cursor: 'pointer', textAlign: 'left', transition: 'all 150ms ease' }}>
                    <BarChart3 size={13} style={{ color: mapMetric === m.key ? 'var(--indigo-600)' : 'var(--text-muted)', flexShrink: 0 }} />
                    <div>
                      <div style={{ fontSize: 11.5, fontWeight: 600, color: mapMetric === m.key ? 'var(--indigo-700)' : 'var(--text-secondary)' }}>{t(m.labelKey)}</div>
                      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{t(m.descKey)}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {/* Computed from the map data: when that failed to load, there
                are no figures to show (not zeros). */}
            {!loadErrors.data && (<>
            <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--shell-800)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 }}>
              {t('map.nationalSummary', { count: nationalStats.total.toLocaleString('en-IN') })}
            </div>
            <div className="map-stat-strip">
              <div className="map-stat-cell">
                <div className="n" style={{ color: 'var(--risk-high)' }}>{nationalStats.critical}</div>
                <div className="l">{t('dash.risk.critical')}</div>
              </div>
              <div className="map-stat-cell">
                <div className="n" style={{ color: '#c45a20' }}>{nationalStats.high}</div>
                <div className="l">{t('dash.risk.high')}</div>
              </div>
              <div className="map-stat-cell">
                <div className="n" style={{ color: 'var(--risk-review)' }}>{nationalStats.moderate}</div>
                <div className="l">{t('dash.risk.moderate')}</div>
              </div>
              <div className="map-stat-cell">
                <div className="n" style={{ color: 'var(--risk-low)' }}>{nationalStats.low}</div>
                <div className="l">{t('dash.risk.low')}</div>
              </div>
            </div>
            <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
              {t('map.summaryLine', { rate: nationalStats.priorityRate, amount: labels.inr(nationalStats.totalAmount) })}
            </div>
            </>)}

            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--shell-800)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>{t('map.legend')}</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {legendItems.map(({ label, color }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <div style={{ width: 14, height: 10, borderRadius: 2, background: color, border: '1px solid rgba(255,255,255,0.8)', boxShadow: '0 1px 2px rgba(0,0,0,0.15)' }} />
                    <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{label}</span>
                  </div>
                ))}
              </div>
            </div>

            {coverage && (
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 10, marginBottom: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--shell-800)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.4 }}>{t('map.coverage')}</div>
                <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                  <div>{t('map.coverageReal', { pct: coverage.real_boundary_pct })}</div>
                  <div>{t('map.coverageApprox', { pct: coverage.centroid_fallback_pct })}</div>
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.4, fontStyle: 'italic' }}>
                  {t('map.coverageNote')}
                </div>
              </div>
            )}

            {selectedConstituency && constituencyIntel && (
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 12, marginBottom: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--shell-800)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.4 }}>{t('map.intel')}</div>
                <div style={{ background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-light)', padding: '12px 14px' }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--navy-800)', marginBottom: 2 }}>{constituencyIntel.constituency}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 10 }}>{constituencyIntel.state}</div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: 11, marginBottom: 10 }}>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('dash.kpi.totalWorks')}:</span> <strong>{constituencyIntel.total_works}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('common.amount')}:</span> <strong>{labels.inr(constituencyIntel.total_amount)}</strong></div>
                    <div style={{ color: 'var(--risk-high)' }}><span style={{ color: 'var(--text-muted)' }}>{t('map.highCritical')}:</span> <strong>{constituencyIntel.flagged_count}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('map.priorityRate')}:</span> <strong>{constituencyIntel.priority_rate != null ? `${constituencyIntel.priority_rate}%` : t('map.rateNA')}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('map.avgRisk')}:</span> <strong>{constituencyIntel.average_risk != null ? constituencyIntel.average_risk : '—'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>{t('map.avgConfidence')}:</span> <strong>{constituencyIntel.average_confidence != null ? `${constituencyIntel.average_confidence}%` : '—'}</strong></div>
                    <div style={{ gridColumn: '1 / -1' }}><span style={{ color: 'var(--text-muted)' }}>{t('map.metric.exposure')}:</span> <strong>{labels.inr(constituencyIntel.financial_exposure)}</strong></div>
                  </div>

                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', borderTop: '1px solid var(--border-light)', paddingTop: 8, marginBottom: 8 }}>
                    <strong>{t('map.why')}</strong><br/>
                    {constituencyIntel.priority_rate == null
                      ? t('map.why.insufficient', { n: constituencyIntel.min_works_for_rate ?? 10 })
                      : constituencyIntel.priority_rate >= 10
                      ? t('map.why.high')
                      : constituencyIntel.priority_rate >= 5
                      ? t('map.why.mid')
                      : t('map.why.low')}
                    {' '}
                    {t('map.why.count', { flagged: constituencyIntel.flagged_count, total: constituencyIntel.total_works })}
                    {constituencyIntel.signal_summary && constituencyIntel.signal_summary.length > 1 && ` ${t('map.why.multi')}`}
                  </div>

                  {constituencyIntel.signal_summary && constituencyIntel.signal_summary.length > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.3 }}>{t('map.topSignals')}</div>
                      {constituencyIntel.signal_summary.slice(0, 4).map(s => (
                        <div key={s.signal} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: 'var(--text-secondary)', padding: '2px 0' }}>
                          <span>{labels.signal(s.signal)}</span>
                          <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{t('map.highN', { n: s.high_count })}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
                    <button onClick={() => {}} style={{ flex: 1, padding: '6px 10px', background: 'var(--indigo-600)', color: 'white', border: 'none', borderRadius: 'var(--radius-md)', fontSize: 10.5, fontWeight: 600, cursor: 'pointer', whiteSpace: 'nowrap' }}>
                      {showWorkMarkers ? t('map.worksShown', { n: works.length }) : t('map.viewPriority')}
                    </button>
                    <button onClick={resetToNational} style={{ padding: '6px 10px', background: 'var(--bg-subtle)', color: 'var(--text-secondary)', border: '1px solid var(--border-light)', borderRadius: 'var(--radius-md)', fontSize: 10.5, fontWeight: 600, cursor: 'pointer' }}>
                      {t('common.reset')}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {!selectedConstituency && !isRS && (
              <div style={{ borderTop: '1px solid var(--border-light)', paddingTop: 12 }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--shell-800)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.4 }}>
                  {t('map.howTo')}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                  {t('map.howToText')}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <button className="map-panel-collapse" onClick={() => setSidebarOpen(true)}>
          <Layers size={14} /> {t('map.filtersAnalysis')}
        </button>
      )}

      <div ref={mapRef} style={{ width: '100%', height: '100%' }} />

      {selectedConstituency && (
        <div style={{ position: 'absolute', top: 14, left: sidebarOpen ? 350 : 14, zIndex: 1001, display: 'flex', alignItems: 'center', gap: 6, background: 'var(--shell-900)', color: 'var(--text-on-dark)', padding: '8px 14px', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-lg)', fontSize: 12, fontWeight: 600 }}>
          <Target size={14} style={{ color: 'var(--seal-gold)' }} />
          {selectedConstituency.constituency}, {selectedConstituency.state}
          <button onClick={resetToNational} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-on-dark-muted)', padding: 2, marginLeft: 4 }} title={t('map.backNational')}>
            <X size={14} />
          </button>
        </div>
      )}

      {showWorkMarkers && works.length > 0 && (
        <div style={{ position: 'absolute', bottom: 48, right: 14, zIndex: 1001, display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(255,255,255,0.95)', border: '1px solid var(--border-light)', padding: '6px 12px', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-md)', fontSize: 11 }}>
          <MapPin size={12} style={{ color: 'var(--indigo-600)' }} />
          <span>{t('map.markersShown', { n: works.length })}</span>
          <button onClick={() => { setShowWorkMarkers(false); setWorks([]); if (workMarkersRef.current) workMarkersRef.current.clearLayers(); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }} title={t('map.hideMarkers')}>
            <X size={12} />
          </button>
        </div>
      )}

      {loading && (
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(255,255,255,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999 }}>
          <LoadingState message={t('map.loading')} />
        </div>
      )}

      <div style={{ position: 'absolute', bottom: 0, right: 0, background: 'rgba(255,255,255,0.8)', padding: '2px 6px', fontSize: 10, color: 'var(--text-muted)', zIndex: 999, borderRadius: '4px 0 0 0' }}>
        &copy; OpenStreetMap | Boundaries: datameet/maps (CC-BY-SA 2.5) | MPLADS Sentinel
      </div>

      <div style={{ position: 'absolute', bottom: 28, right: 0, background: 'rgba(255,255,255,0.9)', padding: '4px 8px', fontSize: 10, color: 'var(--text-muted)', zIndex: 999, borderTop: '1px solid var(--border-light)', maxWidth: 280, lineHeight: 1.4 }}>
        {t('map.gpsNote')}
      </div>
    </div>
  );
}
