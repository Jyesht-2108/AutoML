import React, { useState, useEffect } from 'react';
import { Card, Badge, Alert, Button, Spinner, Row, Col } from 'react-bootstrap';
import { motion } from 'framer-motion';
import { 
  Robot, Magic, CheckCircle, ShieldCheck, Cpu,
  ArrowClockwise, LightningCharge, ExclamationTriangle,
  GraphUp, ListCheck, Bullseye
} from 'react-bootstrap-icons';
import { getAIInsights } from '../services/mlApi';

/**
 * JustificationReport — AI-Powered XAI Dashboard
 * 
 * Fetches LLM-generated insights that analyze the full pipeline context:
 * metrics, agent logs, training config, sanity/privacy reports.
 * Displays verdict, strengths/weaknesses, and retrain suggestions.
 */
const JustificationReport = ({ metadata, projectId }) => {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Static audit trail data from metadata
  const plannerRationale = metadata?.planner_rationale || "No specific planner rationale provided.";
  const sanityResults = metadata?.sanity_fix_results || {};
  const privacyResults = metadata?.privacy_fix_results || {};
  const hasSanity = Object.keys(sanityResults).length > 0;
  const hasPrivacy = Object.keys(privacyResults).length > 0;

  useEffect(() => {
    if (metadata?.ai_insights) {
      setInsights(metadata.ai_insights);
    }
  }, [metadata?.ai_insights]);

  const fetchInsights = async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getAIInsights(projectId);
      setInsights(res.data.insights);
    } catch (err) {
      setError(err.response?.data?.details || err.message || 'Failed to generate insights');
    } finally {
      setLoading(false);
    }
  };

  const verdictConfig = {
    deploy: { color: '#10b981', bg: 'linear-gradient(135deg, #ecfdf5, #d1fae5)', icon: <CheckCircle size={28} />, label: '✅ Ready to Deploy' },
    retrain: { color: '#f59e0b', bg: 'linear-gradient(135deg, #fffbeb, #fef3c7)', icon: <ArrowClockwise size={28} />, label: '🔄 Retrain Recommended' },
    investigate: { color: '#ef4444', bg: 'linear-gradient(135deg, #fef2f2, #fee2e2)', icon: <ExclamationTriangle size={28} />, label: '🔍 Needs Investigation' },
  };

  if (!metadata) return <Alert variant="info">No metadata available yet.</Alert>;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <Card className="border-0 shadow-sm" style={{ borderRadius: '16px', overflow: 'hidden', background: '#f8fafc' }}>
        <div style={{
          background: 'linear-gradient(135deg, #4f46e5 0%, #818cf8 100%)',
          padding: '20px 24px',
          color: 'white'
        }}>
          <div className="d-flex align-items-center gap-2">
            <Robot size={24} />
            <h6 className="mb-0 fw-bold">AI Decision Justification & Insights</h6>
          </div>
          <small style={{ opacity: 0.85 }}>
            Transparent audit trail + LLM-powered analysis of your entire ML pipeline
          </small>
        </div>

        <Card.Body className="p-4">

          {/* === Section 1: AI-Powered Insights === */}
          <div className="mb-4 p-3" style={{ background: 'linear-gradient(135deg, #ede9fe, #ddd6fe)', borderRadius: '12px', border: '1px solid #c4b5fd' }}>
            <div className="d-flex justify-content-between align-items-center mb-2">
              <h6 className="fw-bold mb-0 d-flex align-items-center gap-2" style={{ color: '#5b21b6' }}>
                <LightningCharge size={18} /> AI Expert Analysis
              </h6>
              <Button
                variant={insights ? "outline-secondary" : "primary"}
                size="sm"
                onClick={fetchInsights}
                disabled={loading}
                style={{ borderRadius: '8px', fontWeight: '600' }}
              >
                {loading ? (
                  <><Spinner animation="border" size="sm" className="me-1" /> Analyzing...</>
                ) : insights ? (
                  <><ArrowClockwise size={14} className="me-1" /> Re-analyze</>
                ) : (
                  <><Magic size={14} className="me-1" /> Generate AI Insights</>
                )}
              </Button>
            </div>
            <small style={{ color: '#6d28d9' }}>
              The AI reviews your full pipeline — metrics, logs, config, sanity & privacy reports — and gives expert recommendations.
            </small>
          </div>

          {error && <Alert variant="danger" className="mb-4">{error}</Alert>}

          {insights && (
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
            >
              {/* Verdict Banner */}
              {(() => {
                const v = verdictConfig[insights.overall_verdict] || verdictConfig.investigate;
                return (
                  <div className="mb-4 p-4" style={{ background: v.bg, borderRadius: '14px', border: `2px solid ${v.color}30` }}>
                    <div className="d-flex align-items-center gap-3 mb-2">
                      <div style={{ color: v.color }}>{v.icon}</div>
                      <div>
                        <h5 className="mb-0 fw-bold" style={{ color: v.color }}>{v.label}</h5>
                        <Badge bg="light" text="dark" className="mt-1" style={{ fontSize: '0.75em' }}>
                          Confidence: {insights.confidence_in_verdict?.toUpperCase()}
                        </Badge>
                      </div>
                    </div>
                    <p className="mb-0 mt-2" style={{ color: '#374151', fontSize: '0.95em', lineHeight: '1.6' }}>
                      {insights.summary}
                    </p>
                  </div>
                );
              })()}

              {/* Analysis Cards */}
              <Row className="g-3 mb-4">
                <Col md={4}>
                  <Card className="border-0 shadow-sm h-100" style={{ borderRadius: '12px' }}>
                    <Card.Body className="p-3">
                      <h6 className="fw-bold d-flex align-items-center gap-2 mb-3" style={{ color: '#2563eb' }}>
                        <GraphUp size={16} /> Metrics Analysis
                      </h6>
                      <p style={{ fontSize: '0.9em', color: '#475569', lineHeight: '1.6' }}>
                        {insights.metrics_analysis}
                      </p>
                    </Card.Body>
                  </Card>
                </Col>
                <Col md={4}>
                  <Card className="border-0 shadow-sm h-100" style={{ borderRadius: '12px' }}>
                    <Card.Body className="p-3">
                      <h6 className="fw-bold d-flex align-items-center gap-2 mb-3" style={{ color: '#059669' }}>
                        <ShieldCheck size={16} /> Data Quality
                      </h6>
                      <p style={{ fontSize: '0.9em', color: '#475569', lineHeight: '1.6' }}>
                        {insights.data_quality_analysis}
                      </p>
                    </Card.Body>
                  </Card>
                </Col>
                <Col md={4}>
                  <Card className="border-0 shadow-sm h-100" style={{ borderRadius: '12px' }}>
                    <Card.Body className="p-3">
                      <h6 className="fw-bold d-flex align-items-center gap-2 mb-3" style={{ color: '#d97706' }}>
                        <Cpu size={16} /> Training Analysis
                      </h6>
                      <p style={{ fontSize: '0.9em', color: '#475569', lineHeight: '1.6' }}>
                        {insights.training_analysis}
                      </p>
                    </Card.Body>
                  </Card>
                </Col>
              </Row>

              {/* Strengths & Weaknesses */}
              <Row className="g-3 mb-4">
                <Col md={6}>
                  <Card className="border-0 shadow-sm h-100" style={{ borderRadius: '12px', borderLeft: '4px solid #10b981' }}>
                    <Card.Body className="p-3">
                      <h6 className="fw-bold text-success mb-3">💪 Strengths</h6>
                      {insights.strengths?.length > 0 ? (
                        <ul className="mb-0" style={{ fontSize: '0.9em', color: '#334155', paddingLeft: '18px' }}>
                          {insights.strengths.map((s, i) => <li key={i} className="mb-1">{s}</li>)}
                        </ul>
                      ) : <span className="text-muted small">No specific strengths identified.</span>}
                    </Card.Body>
                  </Card>
                </Col>
                <Col md={6}>
                  <Card className="border-0 shadow-sm h-100" style={{ borderRadius: '12px', borderLeft: '4px solid #ef4444' }}>
                    <Card.Body className="p-3">
                      <h6 className="fw-bold text-danger mb-3">⚠️ Weaknesses</h6>
                      {insights.weaknesses?.length > 0 ? (
                        <ul className="mb-0" style={{ fontSize: '0.9em', color: '#334155', paddingLeft: '18px' }}>
                          {insights.weaknesses.map((w, i) => <li key={i} className="mb-1">{w}</li>)}
                        </ul>
                      ) : <span className="text-muted small">No weaknesses identified.</span>}
                    </Card.Body>
                  </Card>
                </Col>
              </Row>

              {/* Retrain Suggestions */}
              {insights.retrain_suggestions && Object.keys(insights.retrain_suggestions).length > 0 && (
                <Card className="border-0 shadow-sm mb-4" style={{ borderRadius: '12px', borderLeft: '4px solid #8b5cf6' }}>
                  <Card.Body className="p-3">
                    <h6 className="fw-bold mb-3 d-flex align-items-center gap-2" style={{ color: '#7c3aed' }}>
                      <Bullseye size={16} /> Retrain Suggestions
                    </h6>
                    {insights.retrain_suggestions.reasoning && (
                      <p style={{ fontSize: '0.9em', color: '#475569', fontStyle: 'italic', marginBottom: '12px' }}>
                        "{insights.retrain_suggestions.reasoning}"
                      </p>
                    )}
                    <div className="d-flex flex-wrap gap-2">
                      {insights.retrain_suggestions.preferred_model && (
                        <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #c4b5fd', fontSize: '0.85em' }}>
                          🏗️ Model: <strong>{insights.retrain_suggestions.preferred_model}</strong>
                        </Badge>
                      )}
                      {insights.retrain_suggestions.epochs && (
                        <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #c4b5fd', fontSize: '0.85em' }}>
                          🔁 Epochs: <strong>{insights.retrain_suggestions.epochs}</strong>
                        </Badge>
                      )}
                      {insights.retrain_suggestions.learning_rate && (
                        <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #c4b5fd', fontSize: '0.85em' }}>
                          📐 LR: <strong>{insights.retrain_suggestions.learning_rate}</strong>
                        </Badge>
                      )}
                      {insights.retrain_suggestions.batch_size && (
                        <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #c4b5fd', fontSize: '0.85em' }}>
                          📦 Batch: <strong>{insights.retrain_suggestions.batch_size}</strong>
                        </Badge>
                      )}
                    </div>
                  </Card.Body>
                </Card>
              )}

              {/* Next Steps */}
              {insights.next_steps?.length > 0 && (
                <Card className="border-0 shadow-sm mb-4" style={{ borderRadius: '12px', borderLeft: '4px solid #0ea5e9' }}>
                  <Card.Body className="p-3">
                    <h6 className="fw-bold mb-3 d-flex align-items-center gap-2" style={{ color: '#0284c7' }}>
                      <ListCheck size={16} /> Recommended Next Steps
                    </h6>
                    <ol className="mb-0" style={{ fontSize: '0.9em', color: '#334155', paddingLeft: '18px' }}>
                      {insights.next_steps.map((step, i) => <li key={i} className="mb-1">{step}</li>)}
                    </ol>
                  </Card.Body>
                </Card>
              )}
            </motion.div>
          )}

          <hr className="my-4" />

          {/* === Section 2: Static Audit Trail === */}
          <h6 className="fw-bold mb-3" style={{ color: '#6b7280' }}>📋 Pipeline Audit Trail</h6>

          {/* Planner Strategy */}
          <div className="mb-4">
            <h6 className="d-flex align-items-center gap-2 fw-bold text-primary mb-3">
              <Magic size={18} /> 1. AI Planner Strategy
            </h6>
            <div className="p-3 bg-white" style={{ borderRadius: '12px', border: '1px solid #e2e8f0', color: '#334155', fontSize: '0.95em', fontStyle: 'italic' }}>
              "{plannerRationale}"
            </div>
          </div>

          {/* Sanity Audits */}
          <div className="mb-4">
            <h6 className="d-flex align-items-center gap-2 fw-bold text-success mb-3">
              <CheckCircle size={18} /> 2. Data Sanity Audits & Fixes
            </h6>
            <div className="p-3 bg-white" style={{ borderRadius: '12px', border: '1px solid #e2e8f0' }}>
              {hasSanity ? (
                <ul className="mb-0" style={{ color: '#334155', fontSize: '0.95em' }}>
                  {Object.entries(sanityResults).map(([key, value]) => (
                    <li key={key} className="mb-1"><strong>{key}:</strong> {typeof value === 'object' ? JSON.stringify(value) : String(value)}</li>
                  ))}
                </ul>
              ) : (
                <span className="text-muted" style={{ fontSize: '0.9em' }}>No data sanity actions were taken.</span>
              )}
            </div>
          </div>

          {/* Privacy Audits */}
          <div className="mb-4">
            <h6 className="d-flex align-items-center gap-2 fw-bold text-info mb-3">
              <ShieldCheck size={18} /> 3. Privacy Audits & Masking
            </h6>
            <div className="p-3 bg-white" style={{ borderRadius: '12px', border: '1px solid #e2e8f0' }}>
              {hasPrivacy ? (
                <ul className="mb-0" style={{ color: '#334155', fontSize: '0.95em' }}>
                  {Object.entries(privacyResults).map(([key, value]) => (
                    <li key={key} className="mb-1"><strong>{key}:</strong> {typeof value === 'object' ? JSON.stringify(value) : String(value)}</li>
                  ))}
                </ul>
              ) : (
                <span className="text-muted" style={{ fontSize: '0.9em' }}>No privacy masking was applied.</span>
              )}
            </div>
          </div>

          {/* Final Training Config */}
          <div className="mb-2">
            <h6 className="d-flex align-items-center gap-2 fw-bold text-secondary mb-3">
              <Cpu size={18} /> 4. Final Training Configuration
            </h6>
            <div className="p-3 bg-white d-flex flex-wrap gap-3" style={{ borderRadius: '12px', border: '1px solid #e2e8f0' }}>
              <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #cbd5e1' }}>
                <span className="text-muted me-2">Architecture:</span> 
                {metadata.preferred_model || "N/A"}
              </Badge>
              <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #cbd5e1' }}>
                <span className="text-muted me-2">Epochs:</span> 
                {metadata.epochs || "N/A"}
              </Badge>
              <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #cbd5e1' }}>
                <span className="text-muted me-2">Learning Rate:</span> 
                {metadata.learning_rate || "N/A"}
              </Badge>
              <Badge bg="light" text="dark" className="p-2 px-3" style={{ border: '1px solid #cbd5e1' }}>
                <span className="text-muted me-2">Batch Size:</span> 
                {metadata.batch_size || "N/A"}
              </Badge>
            </div>
          </div>

          {/* Grad-CAM Explainable AI */}
          {metadata.gradcam_preview_url && (
            <div className="mb-2 mt-4">
              <h6 className="d-flex align-items-center gap-2 fw-bold text-danger mb-3">
                <Magic size={18} /> 5. Explainable AI (Grad-CAM)
              </h6>
              <div className="p-3 bg-white" style={{ borderRadius: '12px', border: '1px solid #e2e8f0' }}>
                <p className="text-muted small mb-3">
                  These visual heatmaps show exactly which regions of the image the AI model looked at to make its decision. Red areas indicate high importance.
                </p>
                <img 
                  src={metadata.gradcam_preview_url.startsWith('http') 
                    ? metadata.gradcam_preview_url 
                    : `https://storage.googleapis.com/${metadata.gradcam_preview_url.replace('gs://', '')}`}
                  alt="Grad-CAM Heatmaps"
                  style={{ width: '100%', borderRadius: '8px', border: '1px solid #e2e8f0' }}
                />
              </div>
            </div>
          )}

        </Card.Body>
      </Card>
    </motion.div>
  );
};

export default JustificationReport;
