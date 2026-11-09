import React from 'react';
import { Modal, Button, Badge, Row, Col, Card } from 'react-bootstrap';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Activity, Database, ShieldCheck, ShieldLock, 
  Cpu, BarChart, Server, Terminal, CodeSlash, InfoCircle
} from 'react-bootstrap-icons';

const AGENT_DATA = {
  planner: {
    title: 'Planner Agent',
    icon: <Activity size={32} />,
    color: '#8b5cf6',
    description: 'The master orchestrator of the AgentHive platform. It acts as the "brain", parsing your natural language goals and dynamically formulating the optimal execution strategy for the rest of the swarm. When you submit a prompt, the Planner evaluates the intent and dynamically provisions the other agents.',
    features: [
      'Natural Language Processing (NLP) of user intent via LLMs',
      'Dynamic Pipeline Routing (Images vs. Tabular vs. Text)',
      'Model Architecture Selection (e.g., ResNet18 vs. YOLOv8 vs. EfficientNet-B0 vs. MobileNetV2)',
      'Inter-Agent Task Delegation and orchestration',
      'AI Justification generation outlining the exact plan to the user'
    ],
    technical: 'Powered by the Gemini 3.5 Flash API for multi-step reasoning and semantic analysis. Operates over the Model Context Protocol (MCP) to seamlessly communicate context and schema across the Dockerized agent network.'
  },
  dataset: {
    title: 'Dataset Agent',
    icon: <Database size={32} />,
    color: '#3b82f6',
    description: 'The data ingestion and transformation specialist. It safely downloads, extracts, and validates raw data from remote sources (like Kaggle) or direct user uploads, transforming them into standardized machine learning formats.',
    features: [
      'Automated dataset extraction and flattening of nested zip archives',
      'Class and Folder normalizations (lowercasing, sanitizing filenames)',
      'Automatic Train/Val/Test stratification and ratio calculations',
      'Filesystem integrity checks and format validations',
      'Automatic integration with Google Cloud Storage (GCS) for remote blob persistence'
    ],
    technical: 'Uses Google Cloud Storage (GCS) for scalable blob storage and dynamic Python OS modules for file tree restructuring. It can execute Kaggle API commands natively to pull public datasets effortlessly.'
  },
  sanity: {
    title: 'Data Sanity Agent',
    icon: <ShieldCheck size={32} />,
    color: '#10b981',
    description: 'A Human-in-the-Loop auditor that aggressively scans your dataset for structural flaws, corruption, and imbalances before they poison your neural network. It proposes concrete fixes and waits for your explicit approval. It adapts its checks automatically based on whether the data is Images, Tabular (CSV), or Text.',
    features: [
      'Image Data: Corrupt image (magic bytes) and blurry image (Laplacian variance) detection',
      'Tabular Data: Missing value detection/imputation and duplicate row removal',
      'Tabular Data: Single-value (constant) column detection',
      'Text Data: Empty string detection and dataset length validation',
      'Class imbalance detection and synthetic oversampling/undersampling proposals',
      'Human-in-the-Loop approval workflows via interactive React dashboards'
    ],
    technical: 'Built natively with OpenCV and Pillow for rapid, parallelized tensor analysis of raw image bytes, and optimized CSV streaming parsers for memory-efficient tabular analysis without Pandas overhead.'
  },
  privacy: {
    title: 'Privacy Agent',
    icon: <ShieldLock size={32} />,
    color: '#f59e0b',
    description: 'Ensures strict compliance with data privacy regulations like GDPR and HIPAA. It autonomously scans datasets for Personally Identifiable Information (PII) and masks it before any model can memorize it.',
    features: [
      'High-accuracy Face detection and autonomous blurring',
      'License Plate detection and redaction in vehicle datasets',
      'Textual regex scrubbing for sensitive phone numbers and emails',
      'Complete Human-in-the-Loop override and review support',
      'Non-destructive metadata tagging for compliance auditing'
    ],
    technical: 'Utilizes highly optimized Haar Cascades, MTCNN (Multi-task Cascaded Convolutional Networks), and proprietary Deep Learning heuristics to guarantee privacy-preserving Machine Learning without destroying dataset features.'
  },
  training: {
    title: 'Trainer Agent',
    icon: <Cpu size={32} />,
    color: '#ef4444',
    description: 'The computational powerhouse. It provisions isolated Python environments and executes heavy Deep Learning and Machine Learning algorithms on GPUs, complete with live monitoring.',
    features: [
      'Dynamic PyTorch and Scikit-Learn training loops',
      'Real-time WebSocket and background-polling for live epoch logging',
      'Automatic Mixed Precision (AMP) and CUDA hardware acceleration',
      'Hyperparameter tuning, Learning Rate scheduling, and Dropout configuration',
      'Early stopping mechanisms to prevent model overfitting'
    ],
    technical: 'Employs AdamW optimizers, Cross-Entropy Loss functions, and native GPU-accelerated tensor computations via PyTorch 2.0. Supports dynamic architectures like ResNet, YOLOv8, EfficientNet, and MobileNet.'
  },
  evaluation: {
    title: 'Evaluation Agent',
    icon: <BarChart size={32} />,
    color: '#ec4899',
    description: 'The Explainable AI (XAI) auditor. It calculates comprehensive statistical metrics and generates visual rationale to eliminate the "black box" problem of modern Deep Learning.',
    features: [
      'Multi-metric evaluation (Accuracy, F1-Score, Precision, Recall, Validation Loss)',
      'Grad-CAM (Gradient-weighted Class Activation Mapping) visual heatmaps generation',
      'AI Justification Reports featuring natural language LLM analysis of the metrics',
      'Confusion Matrix generation and per-class performance breakdowns'
    ],
    technical: 'Leverages gradient-based localization (Grad-CAM) to project model activation layers directly onto the original source pixels, highlighting exactly what the convolution layers "looked at".'
  },
  deployment: {
    title: 'Deployment Agent',
    icon: <Server size={32} />,
    color: '#14b8a6',
    description: 'The operations and MLOps expert. Packages the final optimized model weights into a scalable, production-ready artifact that can be consumed by other applications or deployed to the cloud.',
    features: [
      'Generates scalable Docker Compose configurations for the final model',
      'Bundles inference APIs using high-performance FastAPI wrappers',
      'Model quantization and weight compression to reduce memory footprints',
      '1-Click Export functionality to download the entire inference stack'
    ],
    technical: 'Generates standardized containerization scripts (Dockerfiles) and RESTful OpenAPI endpoints for seamless, zero-downtime CI/CD integration.'
  }
};

const AgentDocumentationModal = ({ show, onHide, agentKey }) => {
  const data = AGENT_DATA[agentKey];

  if (!data) return null;

  return (
    <Modal show={show} onHide={onHide} size="lg" centered>
      <Modal.Header closeButton style={{ borderBottom: 'none', paddingBottom: 0 }}>
      </Modal.Header>
      <Modal.Body style={{ padding: '2rem' }}>
        <div className="text-center mb-4">
          <div
            style={{
              width: '80px',
              height: '80px',
              borderRadius: '50%',
              background: `linear-gradient(135deg, ${data.color}dd, ${data.color})`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              color: 'white',
              boxShadow: `0 10px 25px ${data.color}40`
            }}
          >
            {data.icon}
          </div>
          <h2 style={{ fontWeight: '700', color: '#1f2937', marginBottom: '8px' }}>
            {data.title}
          </h2>
          <Badge bg="light" text="dark" style={{ border: `1px solid ${data.color}`, color: data.color }}>
            Swarm Core Protocol
          </Badge>
        </div>

        <p style={{ fontSize: '1.1rem', color: '#4b5563', lineHeight: '1.6', textAlign: 'center', marginBottom: '2rem' }}>
          {data.description}
        </p>

        <Row className="g-4">
          <Col md={6}>
            <Card className="h-100 border-0 shadow-sm" style={{ borderRadius: '16px', background: '#f8fafc' }}>
              <Card.Body>
                <div className="d-flex align-items-center mb-3">
                  <Terminal size={20} color={data.color} className="me-2" />
                  <h5 style={{ margin: 0, fontWeight: '600', color: '#1e293b' }}>Key Capabilities</h5>
                </div>
                <ul style={{ paddingLeft: '1.2rem', color: '#475569', lineHeight: '1.8' }}>
                  {data.features.map((feature, i) => (
                    <li key={i}>{feature}</li>
                  ))}
                </ul>
              </Card.Body>
            </Card>
          </Col>
          <Col md={6}>
            <Card className="h-100 border-0 shadow-sm" style={{ borderRadius: '16px', background: '#f8fafc' }}>
              <Card.Body>
                <div className="d-flex align-items-center mb-3">
                  <CodeSlash size={20} color={data.color} className="me-2" />
                  <h5 style={{ margin: 0, fontWeight: '600', color: '#1e293b' }}>Technical Details</h5>
                </div>
                <p style={{ color: '#475569', lineHeight: '1.6', margin: 0 }}>
                  {data.technical}
                </p>
                <div className="mt-4 p-3 rounded" style={{ background: '#e2e8f0', fontSize: '0.85rem' }}>
                  <InfoCircle className="me-2" />
                  Integrated via Model Context Protocol (MCP) over isolated Docker runtimes.
                </div>
              </Card.Body>
            </Card>
          </Col>
        </Row>

      </Modal.Body>
      <Modal.Footer style={{ borderTop: 'none', justifyContent: 'center', paddingBottom: '2rem' }}>
        <Button variant="primary" onClick={onHide} style={{ background: data.color, border: 'none', padding: '10px 30px', borderRadius: '8px' }}>
          Close Documentation
        </Button>
      </Modal.Footer>
    </Modal>
  );
};

export default AgentDocumentationModal;
