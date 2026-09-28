import React from 'react';
import { Shield, AlertTriangle, Search, Link2, BarChart3, FileText, ArrowDown } from 'lucide-react';
import { useTranslation } from '../i18n';

const STEP_COLORS = [
  'var(--info)', 'var(--info)', 'var(--info)', 'var(--info)',
  'var(--risk-review)',
  'var(--risk-high)', 'var(--risk-high)', 'var(--risk-high)', 'var(--risk-high)', 'var(--risk-high)',
  'var(--success)',
];

const SIGNALS = [
  { icon: <BarChart3 size={16} />, nameKey: 'sig.cost', descKey: 'meth.sig.cost.d', weight: '25%' },
  { icon: <Search size={16} />, nameKey: 'sig.similarity', descKey: 'meth.sig.similarity.d', weight: '20%' },
  { icon: <Link2 size={16} />, nameKey: 'sig.mpConcentration', descKey: 'meth.sig.mpConcentration.d', weight: '10%' },
  { icon: <Link2 size={16} />, nameKey: 'sig.constituencyPattern', descKey: 'meth.sig.constituencyPattern.d', weight: '10%' },
  { icon: <AlertTriangle size={16} />, nameKey: 'sig.temporal', descKey: 'meth.sig.temporal.d', weight: '10%' },
  { icon: <FileText size={16} />, nameKey: 'sig.stage', descKey: 'meth.sig.stage.d', weight: '10%' },
  { icon: <AlertTriangle size={16} />, nameKey: 'sig.pattern', descKey: 'meth.sig.pattern.d', weight: '15%' },
];

const LIMITATION_COUNT = 7;
const EVIDENCE_STEP_COUNT = 11;

export default function Methodology() {
  const { t } = useTranslation();

  return (
    <div>
      <div className="page-header">
        <h2>{t('nav.methodology')}</h2>
        <p className="subtitle">{t('meth.subtitle')}</p>
      </div>

      {/* Core Principle */}
      <div className="card" style={{ marginBottom: 16, borderLeft: '4px solid var(--gov-blue)', background: 'var(--gov-blue-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
          <Shield size={24} style={{ color: 'var(--gov-blue)' }} />
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: 'var(--navy)' }}>{t('meth.principle')}</h3>
          </div>
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          {t('meth.principleBody')}
        </p>
      </div>

      {/* Processing Pipeline */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3>{t('meth.pipeline')}</h3>
        </div>
        <div>
          {STEP_COLORS.map((color, i) => {
            const step = i + 1;
            return (
              <div key={step}>
                <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%',
                    background: color, color: '#fff',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, fontWeight: 600, flexShrink: 0
                  }}>{step}</div>
                  <div style={{ flex: 1, paddingTop: 4 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)' }}>{t(`meth.step${step}.t`)}</div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{t(`meth.step${step}.d`)}</div>
                  </div>
                </div>
                {i < STEP_COLORS.length - 1 && (
                  <div className="pipeline-arrow" style={{ marginLeft: 15 }}>
                    <ArrowDown size={16} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Anomaly Signals */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3>{t('common.analyticalSignals')}</h3>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 14 }}>
          {SIGNALS.map(({ icon, nameKey, descKey, weight }) => (
            <div key={nameKey} style={{
              background: 'var(--bg-subtle)',
              padding: 16,
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--border-light)',
              borderLeft: '3px solid var(--gov-blue)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                {icon}
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--navy)' }}>{t(nameKey)}</span>
                <span style={{ fontSize: 10, color: 'var(--text-muted)', marginLeft: 'auto', background: 'var(--bg-muted)', padding: '2px 6px', borderRadius: 'var(--radius-sm)' }}>
                  {t('meth.weight', { w: weight })}
                </span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>{t(descKey)}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Risk vs Confidence */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3>{t('meth.rvc')}</h3>
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          <p style={{ marginBottom: 8 }}><strong>{t('common.riskScore')}</strong> {t('meth.rvc.riskText')}</p>
          <p style={{ marginBottom: 8 }}><strong>{t('meth.rvc.confLabel')}</strong> {t('meth.rvc.confText')}</p>
          <p style={{ marginBottom: 8 }}>{t('meth.rvc.note')}</p>
          <p>
            {t('meth.rvc.bands')}{' '}
            <strong>{t('dash.risk.low').toUpperCase()}</strong> (0-39), <strong>{t('dash.risk.moderate').toUpperCase()}</strong> (40-64), <strong>{t('dash.risk.high').toUpperCase()}</strong> (65-84), <strong>{t('dash.risk.critical').toUpperCase()}</strong> (85-100). {t('meth.rvc.criticalNote')}
          </p>
        </div>
      </div>

      {/* Evidence Model */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-header">
          <h3>{t('meth.evidence')}</h3>
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.8 }}>
          <p style={{ marginBottom: 12 }}>{t('meth.evidenceIntro')}</p>
          <div style={{
            background: 'var(--bg-subtle)',
            padding: 16,
            borderRadius: 'var(--radius-md)',
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: 12,
            lineHeight: 2,
            border: '1px solid var(--border-light)'
          }}>
            {Array.from({ length: EVIDENCE_STEP_COUNT }, (_, i) => (
              <React.Fragment key={i}>
                {i === 0 ? null : <>&nbsp;&nbsp;&darr; </>}
                {t(`meth.ev.${i + 1}`)}
                {i < EVIDENCE_STEP_COUNT - 1 && <br />}
              </React.Fragment>
            ))}
          </div>
        </div>
      </div>

      {/* Important Limitations */}
      <div className="card" style={{ borderLeft: '4px solid var(--risk-review)', background: 'var(--risk-review-bg)' }}>
        <div className="card-header" style={{ borderBottom: 'none', paddingBottom: 0 }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--navy)' }}>
            <AlertTriangle size={16} style={{ color: 'var(--risk-review)' }} />
            {t('meth.limits')}
          </h3>
        </div>
        <ul style={{ fontSize: 13, color: 'var(--text-secondary)', paddingLeft: 20, lineHeight: 1.8 }}>
          {Array.from({ length: LIMITATION_COUNT }, (_, i) => (
            <li key={i}>{t(`meth.lim.${i + 1}`)}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
