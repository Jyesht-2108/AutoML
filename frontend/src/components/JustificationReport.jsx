import React from 'react';
import { Card, Badge, Alert } from 'react-bootstrap';
import { motion } from 'framer-motion';
import { Robot, Magic, CheckCircle, ShieldCheck, Cpu } from 'react-bootstrap-icons';

/**
 * JustificationReport — UI component for AI Transparency
 * 
 * Displays the rationale behind AI decisions (Planner, Sanity, Privacy, Training)
 * extracted directly from project.metadata.
 */
const JustificationReport = ({ metadata }) => {
  if (!metadata) return <Alert variant="info">No metadata available yet.</Alert>;

  const plannerRationale = metadata.planner_rationale || "No specific planner rationale provided.";
  const sanityResults = metadata.sanity_fix_results || {};
  const privacyResults = metadata.privacy_fix_results || {};
  
  const hasSanity = Object.keys(sanityResults).length > 0;
  const hasPrivacy = Object.keys(privacyResults).length > 0;

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
            <h6 className="mb-0 fw-bold">AI Decision Justification & Audit Trail</h6>
          </div>
          <small style={{ opacity: 0.85 }}>
            Transparent log of exactly why the AI made specific choices and what it changed.
          </small>
        </div>

        <Card.Body className="p-4">
          
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
                    <li key={key} className="mb-1"><strong>{key}:</strong> {value}</li>
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
                    <li key={key} className="mb-1"><strong>{key}:</strong> {value}</li>
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
