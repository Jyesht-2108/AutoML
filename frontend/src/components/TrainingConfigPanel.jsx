import React, { useState } from 'react';
import { Card, Form, Button, Spinner, Alert } from 'react-bootstrap';
import { motion } from 'framer-motion';
import { Cpu, CheckCircle, ArrowRight, XCircle } from 'react-bootstrap-icons';
import { saveTrainingConfig } from '../services/mlApi';

/**
 * TrainingConfigPanel — Human-in-the-Loop UI
 * 
 * Lets the user review and override the Planner Agent's suggested
 * training configuration (model, epochs, lr, batch size) before training.
 */
const TrainingConfigPanel = ({ project, onConfigSaved }) => {
  const metadata = project?.metadata || {};
  
  // Use planner's suggestions as defaults, fallback to hardcoded defaults
  const [config, setConfig] = useState({
    model: metadata.preferred_model || 'resnet18',
    epochs: metadata.epochs || 10,
    learning_rate: metadata.learning_rate || 0.001,
    batch_size: metadata.batch_size || 32,
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const SUPPORTED_MODELS = [
    { value: 'resnet18', label: 'ResNet-18 (Fast, Baseline)' },
    { value: 'resnet34', label: 'ResNet-34 (Balanced)' },
    { value: 'resnet50', label: 'ResNet-50 (High Accuracy, Slower)' },
    { value: 'mobilenet_v2', label: 'MobileNet V2 (Lightweight, Mobile)' },
    { value: 'efficientnet_b0', label: 'EfficientNet-B0 (Modern, Efficient)' }
  ];

  const handleChange = (e) => {
    const { name, value, type } = e.target;
    setConfig(prev => ({
      ...prev,
      [name]: type === 'number' ? Number(value) : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await saveTrainingConfig(project.id, config);
      if (onConfigSaved) onConfigSaved();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to save config');
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
        border: '2px solid #3b82f6'
      }}>
        {/* Header */}
        <div style={{
          background: 'linear-gradient(135deg, #2563eb 0%, #60a5fa 100%)',
          padding: '20px 24px',
          color: 'white'
        }}>
          <div className="d-flex align-items-center gap-2">
            <Cpu size={24} />
            <h6 className="mb-0 fw-bold">Training Configuration</h6>
          </div>
          <small style={{ opacity: 0.85 }}>
            Review or override the AI-suggested training parameters
          </small>
        </div>

        <Card.Body className="p-4">
          <Form onSubmit={handleSubmit}>
            <div className="mb-4">
              <Form.Group className="mb-3">
                <Form.Label className="fw-semibold text-muted">Model Architecture</Form.Label>
                <Form.Select 
                  name="model" 
                  value={config.model} 
                  onChange={handleChange}
                  style={{ borderRadius: '10px', padding: '10px 15px' }}
                >
                  {SUPPORTED_MODELS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </Form.Select>
                <Form.Text className="text-muted ms-1">
                  The neural network architecture to train.
                </Form.Text>
              </Form.Group>

              <div className="row">
                <div className="col-md-4">
                  <Form.Group className="mb-3">
                    <Form.Label className="fw-semibold text-muted">Epochs</Form.Label>
                    <Form.Control 
                      type="number" 
                      name="epochs" 
                      value={config.epochs} 
                      onChange={handleChange}
                      min="1"
                      max="100"
                      style={{ borderRadius: '10px', padding: '10px 15px' }}
                    />
                    <Form.Text className="text-muted ms-1">
                      Full passes over data.
                    </Form.Text>
                  </Form.Group>
                </div>
                
                <div className="col-md-4">
                  <Form.Group className="mb-3">
                    <Form.Label className="fw-semibold text-muted">Learning Rate</Form.Label>
                    <Form.Control 
                      type="number" 
                      name="learning_rate" 
                      value={config.learning_rate} 
                      onChange={handleChange}
                      step="0.0001"
                      min="0.0001"
                      max="0.1"
                      style={{ borderRadius: '10px', padding: '10px 15px' }}
                    />
                    <Form.Text className="text-muted ms-1">
                      Step size for optimizer.
                    </Form.Text>
                  </Form.Group>
                </div>

                <div className="col-md-4">
                  <Form.Group className="mb-3">
                    <Form.Label className="fw-semibold text-muted">Batch Size</Form.Label>
                    <Form.Select 
                      name="batch_size" 
                      value={config.batch_size} 
                      onChange={handleChange}
                      style={{ borderRadius: '10px', padding: '10px 15px' }}
                    >
                      <option value="8">8</option>
                      <option value="16">16</option>
                      <option value="32">32 (Default)</option>
                      <option value="64">64</option>
                      <option value="128">128</option>
                    </Form.Select>
                    <Form.Text className="text-muted ms-1">
                      Images per training step.
                    </Form.Text>
                  </Form.Group>
                </div>
              </div>
            </div>

            {error && (
              <Alert variant="danger" className="py-2" style={{ borderRadius: '10px', fontSize: '0.88em' }}>
                <XCircle size={14} className="me-1" /> {error}
              </Alert>
            )}

            <div className="d-flex justify-content-end">
              <Button
                type="submit"
                disabled={submitting}
                style={{ 
                  borderRadius: '10px', fontWeight: '600',
                  background: 'linear-gradient(135deg, #2563eb 0%, #60a5fa 100%)',
                  border: 'none',
                  padding: '10px 24px'
                }}
              >
                {submitting ? (
                  <>
                    <Spinner size="sm" className="me-2" />
                    Saving...
                  </>
                ) : (
                  <>
                    <CheckCircle size={16} className="me-2" />
                    Start Training
                    <ArrowRight size={16} className="ms-2" />
                  </>
                )}
              </Button>
            </div>
          </Form>
        </Card.Body>
      </Card>
    </motion.div>
  );
};

export default TrainingConfigPanel;
