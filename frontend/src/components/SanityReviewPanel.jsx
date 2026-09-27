import React, { useState } from 'react';
import { Card, Badge, Button, Form, Spinner, Alert } from 'react-bootstrap';
import { motion } from 'framer-motion';
import { 
  ShieldCheck, 
  Trash, 
  Images, 
  FolderSymlink, 
  PlusCircle,
  CheckCircle,
  ExclamationTriangle,
  XCircle,
  ArrowRight
} from 'react-bootstrap-icons';
import { approveSanityActions } from '../services/mlApi';

/**
 * SanityReviewPanel — Human-in-the-Loop UI
 * 
 * Displays the sanity audit report and lets the user toggle
 * approve/skip for each proposed fix action, then submit.
 */
const SanityReviewPanel = ({ project, onApproved }) => {
  const metadata = project?.metadata || {};
  const report = metadata?.sanity_report;
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
      await approveSanityActions(project.id, actionStates);
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
      await approveSanityActions(project.id, allSkipped);
      if (onApproved) onApproved();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to submit');
    } finally {
      setSubmitting(false);
    }
  };

  const actionIcons = {
    remove_corrupt: <Trash size={18} className="text-danger" />,
    remove_blurry: <Images size={18} className="text-warning" />,
    auto_split: <FolderSymlink size={18} className="text-info" />,
    augment_balance: <PlusCircle size={18} className="text-success" />,
  };

  const actionLabels = {
    remove_corrupt: 'Remove Corrupt Images',
    remove_blurry: 'Remove Blurry Images',
    auto_split: 'Auto-Create Train/Val/Test Splits',
    augment_balance: 'Augment Minority Classes',
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
        border: '2px solid #8b5cf6'
      }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
          padding: '20px 24px',
          color: 'white'
        }}>
          <div className="d-flex align-items-center gap-2">
            <ShieldCheck size={24} />
            <h6 className="mb-0 fw-bold">Data Sanity Review</h6>
          </div>
          <small style={{ opacity: 0.85 }}>
            Review the audit results and approve fixes before training begins
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
                <small className="text-muted">Images</small>
              </div>
              <div className="text-center p-2 px-3" style={{ background: '#f3f4f6', borderRadius: '10px' }}>
                <div style={{ fontSize: '1.4em', fontWeight: '700', color: '#1f2937' }}>
                  {report.num_classes}
                </div>
                <small className="text-muted">Classes</small>
              </div>
              <div className="text-center p-2 px-3" style={{ 
                background: report.corrupt_count > 0 ? '#fef2f2' : '#f0fdf4', 
                borderRadius: '10px' 
              }}>
                <div style={{ 
                  fontSize: '1.4em', fontWeight: '700', 
                  color: report.corrupt_count > 0 ? '#dc2626' : '#16a34a' 
                }}>
                  {report.corrupt_count}
                </div>
                <small className="text-muted">Corrupt</small>
              </div>
              <div className="text-center p-2 px-3" style={{ 
                background: report.blurry_count > 0 ? '#fffbeb' : '#f0fdf4', 
                borderRadius: '10px' 
              }}>
                <div style={{ 
                  fontSize: '1.4em', fontWeight: '700', 
                  color: report.blurry_count > 0 ? '#d97706' : '#16a34a' 
                }}>
                  {report.blurry_count}
                </div>
                <small className="text-muted">Blurry</small>
              </div>
              {report.avg_resolution && (
                <div className="text-center p-2 px-3" style={{ background: '#f3f4f6', borderRadius: '10px' }}>
                  <div style={{ fontSize: '1.4em', fontWeight: '700', color: '#1f2937' }}>
                    {report.avg_resolution}
                  </div>
                  <small className="text-muted">Avg Res</small>
                </div>
              )}
              <div className="text-center p-2 px-3" style={{ 
                background: report.has_splits ? '#f0fdf4' : '#fffbeb', 
                borderRadius: '10px' 
              }}>
                <div style={{ 
                  fontSize: '1.4em', fontWeight: '700', 
                  color: report.has_splits ? '#16a34a' : '#d97706' 
                }}>
                  {report.has_splits ? '✓' : '✗'}
                </div>
                <small className="text-muted">Splits</small>
              </div>
            </div>

            {/* Warnings */}
            {report.warnings?.length > 0 && (
              <Alert variant="warning" className="py-2 px-3" style={{ borderRadius: '10px', fontSize: '0.88em' }}>
                <ExclamationTriangle size={14} className="me-1" />
                <strong>Warnings:</strong>
                <ul className="mb-0 mt-1 ps-3">
                  {report.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </Alert>
            )}

            {/* Class Distribution (compact) */}
            {report.class_distribution && Object.keys(report.class_distribution).length > 0 && (
              <div className="mb-3">
                <small className="text-muted d-block mb-2 fw-bold">Class Distribution</small>
                <div className="d-flex flex-wrap gap-1">
                  {Object.entries(report.class_distribution)
                    .sort(([,a], [,b]) => b - a)
                    .slice(0, 15)
                    .map(([cls, count]) => (
                      <Badge key={cls} bg="light" text="dark" 
                        style={{ fontSize: '0.78em', border: '1px solid #e5e7eb' }}>
                        {cls}: {count}
                      </Badge>
                    ))}
                  {Object.keys(report.class_distribution).length > 15 && (
                    <Badge bg="secondary" style={{ fontSize: '0.78em' }}>
                      +{Object.keys(report.class_distribution).length - 15} more
                    </Badge>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* --- Proposed Actions (toggles) --- */}
          {Object.keys(proposedActions).length > 0 && (
            <div className="mb-4">
              <h6 className="fw-bold mb-3" style={{ color: '#1f2937' }}>
                🔧 Proposed Fixes
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
                    {actionIcons[key] || <ShieldCheck size={18} />}
                    <div>
                      <div className="fw-semibold" style={{ fontSize: '0.92em', color: '#1f2937' }}>
                        {actionLabels[key] || key}
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
              Skip All & Train
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={submitting}
              style={{ 
                borderRadius: '10px', fontWeight: '600',
                background: 'linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)',
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

export default SanityReviewPanel;
