import React, { useState } from 'react';
import { Card, Button, Spinner, Alert } from 'react-bootstrap';
import { CheckCircle, ArrowCounterclockwise } from 'react-bootstrap-icons';
import mlApi from '../services/mlApi';
import MetricsViewer from './MetricsViewer';

const EvaluationReviewPanel = ({ project, onApproved }) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleDecision = async (decision) => {
    setIsSubmitting(true);
    setError(null);
    try {
      let newStatus = 'pending_deployment';
      if (decision === 'retrain') {
        newStatus = 'pending_training_config';
      }

      await mlApi.patch(`/api/ml/projects/${project.id}/status`, {
        status: newStatus
      });

      onApproved(newStatus); // Triggers a UI refresh
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to submit decision');
      setIsSubmitting(false);
    }
  };

  return (
    <Card className="border-0 shadow-sm" style={{ borderRadius: '16px', background: '#f8fafc' }}>
      <Card.Body className="p-4">
        <h5 className="fw-bold mb-3" style={{ color: '#1f2937' }}>📈 Evaluation Review</h5>
        <p className="text-muted mb-4">
          The Trainer Agent has completed training and evaluation! Review the model's performance metrics below. 
          If you are satisfied with the results, you can proceed to deployment. If the accuracy is lower than expected, 
          you can send it back to adjust hyperparameters or choose a different algorithm.
        </p>

        {error && <Alert variant="danger">{error}</Alert>}

        <Card className="border-0 shadow-sm mb-4">
          <Card.Body>
            <MetricsViewer project={project} />
          </Card.Body>
        </Card>

        <div className="d-flex gap-3 mt-4">
          <Button
            variant="outline-secondary"
            onClick={() => handleDecision('retrain')}
            disabled={isSubmitting}
            className="flex-grow-1 py-3"
            style={{ borderRadius: '12px', fontWeight: '600' }}
          >
            {isSubmitting ? (
              <Spinner animation="border" size="sm" />
            ) : (
              <>
                <ArrowCounterclockwise size={20} className="me-2" />
                Adjust Config & Retrain
              </>
            )}
          </Button>

          <Button
            variant="success"
            onClick={() => handleDecision('deploy')}
            disabled={isSubmitting}
            className="flex-grow-1 py-3"
            style={{ borderRadius: '12px', fontWeight: '600' }}
          >
            {isSubmitting ? (
              <Spinner animation="border" size="sm" />
            ) : (
              <>
                <CheckCircle size={20} className="me-2" />
                Satisfied — Deploy Model
              </>
            )}
          </Button>
        </div>
      </Card.Body>
    </Card>
  );
};

export default EvaluationReviewPanel;
