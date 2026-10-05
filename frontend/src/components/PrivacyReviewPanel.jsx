import React, { useState } from 'react';
import { Card, Button, Form, Spinner, Alert } from 'react-bootstrap';
import { motion } from 'framer-motion';
import { ShieldLock, CheckCircle, XCircle, ArrowRight } from 'react-bootstrap-icons';
import { approvePrivacyActions } from '../services/mlApi';

/**
 * PrivacyReviewPanel — Human-in-the-Loop UI
 * 
 * Displays the privacy audit report (how many faces detected) and lets the user
 * toggle approve/skip for masking (blurring).
 */
const PrivacyReviewPanel = ({ project, onApproved }) => {
  const metadata = project?.metadata || {};
  const report = metadata?.privacy_report;
  const proposedActions = report?.proposed_actions || {};

  const [actionStates, setActionStates] = useState(() => {
    const initial = {};
    Object.keys(proposedActions).forEach(key => {
      initial[key] = proposedActions[key]?.recommended ?? true;
    });
    return initial;
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  if (!report) {
    return null;
  }

  const toggleAction = (key) => {
    setActionStates(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await approvePrivacyActions(project.id, actionStates);
      if (onApproved) onApproved();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSkipAll = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const allSkipped = {};
      Object.keys(proposedActions).forEach(k => { allSkipped[k] = false; });
      await approvePrivacyActions(project.id, allSkipped);
      if (onApproved) onApproved();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      <Card className="border-0 shadow-sm" style={{ 
        borderRadius: '16px', 
        overflow: 'hidden',
        border: '2px solid #059669'
      }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #059669 0%, #34d399 100%)',
          padding: '20px 24px',
          color: 'white'
        }}>
          <div className="d-flex align-items-center gap-2">
            <ShieldLock size={24} />
            <h6 className="mb-0 fw-bold">Privacy Review</h6>
          </div>
          <small style={{ opacity: 0.85 }}>
            Review detected PII (Personally Identifiable Information) and approve masking.
          </small>
        </div>

        <Card.Body className="p-4">
          {/* --- Audit Summary --- */}
          <div className="mb-4">
            <div className="d-flex flex-wrap gap-3 mb-3">
              <div className="text-center p-2 px-3" style={{ background: '#f3f4f6', borderRadius: '10px' }}>
                <div style={{ fontSize: '1.4em', fontWeight: '700', color: '#1f2937' }}>
                  {report.total_images}
                </div>
                <small className="text-muted">Total Images</small>
              </div>
              <div className="text-center p-2 px-3" style={{ 
                background: report.total_faces_detected > 0 ? '#fef2f2' : '#f0fdf4', 
                borderRadius: '10px' 
              }}>
                <div style={{ 
                  fontSize: '1.4em', fontWeight: '700', 
                  color: report.total_faces_detected > 0 ? '#dc2626' : '#16a34a' 
                }}>
                  {report.images_with_faces_count}
                </div>
                <small className="text-muted">Images with PII</small>
              </div>
              <div className="text-center p-2 px-3" style={{ 
                background: report.total_faces_detected > 0 ? '#fef2f2' : '#f0fdf4', 
                borderRadius: '10px' 
              }}>
                <div style={{ 
                  fontSize: '1.4em', fontWeight: '700', 
                  color: report.total_faces_detected > 0 ? '#dc2626' : '#16a34a' 
                }}>
                  {report.total_faces_detected}
                </div>
                <small className="text-muted">Faces Detected</small>
              </div>
            </div>
          </div>

          {/* --- Proposed Actions (toggles) --- */}
          {Object.keys(proposedActions).length > 0 && (
            <div className="mb-4">
              <h6 className="fw-bold mb-3" style={{ color: '#1f2937' }}>
                🛡️ Proposed Privacy Actions
              </h6>
              {Object.entries(proposedActions).map(([key, action]) => (
                <motion.div
                  key={key}
                  whileHover={{ scale: 1.01 }}
                  className="d-flex align-items-center justify-content-between p-3 mb-2"
                  style={{
                    background: actionStates[key] ? '#f0fdf4' : '#f9fafb',
                    borderRadius: '12px',
                    border: actionStates[key] ? '2px solid #86efac' : '2px solid #e5e7eb',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease'
                  }}
                  onClick={() => toggleAction(key)}
                >
                  <div className="d-flex align-items-center gap-3">
                    <ShieldLock size={18} className={actionStates[key] ? "text-success" : "text-muted"} />
                    <div>
                      <div className="fw-semibold" style={{ fontSize: '0.92em', color: '#1f2937' }}>
                        {key === 'blur_faces' ? 'Blur Detected Faces' : key}
                      </div>
                      <small className="text-muted">{action.description}</small>
                    </div>
                  </div>
                  <Form.Check 
                    type="switch"
                    checked={actionStates[key]}
                    onChange={() => toggleAction(key)}
                    onClick={(e) => e.stopPropagation()}
                    style={{ transform: 'scale(1.2)' }}
                  />
                </motion.div>
              ))}
            </div>
          )}

          {error && (
            <Alert variant="danger" className="py-2" style={{ borderRadius: '10px', fontSize: '0.88em' }}>
              <XCircle size={14} className="me-1" /> {error}
            </Alert>
          )}

          {/* --- Action Buttons --- */}
          <div className="d-flex gap-3 justify-content-end">
            <Button 
              variant="outline-secondary" 
              onClick={handleSkipAll}
              disabled={submitting}
              style={{ borderRadius: '10px', fontWeight: '600' }}
            >
              Skip Masking
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={submitting}
              style={{ 
                borderRadius: '10px', fontWeight: '600',
                background: 'linear-gradient(135deg, #059669 0%, #34d399 100%)',
                border: 'none',
                padding: '10px 24px'
              }}
            >
              {submitting ? (
                <>
                  <Spinner size="sm" className="me-2" />
                  Processing...
                </>
              ) : (
                <>
                  <CheckCircle size={16} className="me-2" />
                  Apply & Continue
                  <ArrowRight size={16} className="ms-2" />
                </>
              )}
            </Button>
          </div>
        </Card.Body>
      </Card>
    </motion.div>
  );
};

export default PrivacyReviewPanel;
