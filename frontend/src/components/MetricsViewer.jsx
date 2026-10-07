import React, { useState } from 'react';
import { Row, Col, Card, Modal, Button } from 'react-bootstrap';
import { ArrowsFullscreen } from 'react-bootstrap-icons';
import { 
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer,
  Legend
} from 'recharts';

const MetricsViewer = ({ project }) => {
  const [fullscreenChart, setFullscreenChart] = useState(null);
  
  const metadata = project.metadata || {};
  let metrics = metadata.metrics || metadata.evaluation_metrics || {};
  const featureImportance = metadata.feature_importance || {};
  
  // Backward compatibility for old PyTorch models where evaluation_metrics WAS the classification report
  if (metadata.evaluation_metrics && !metadata.metrics) {
    const macroAvg = metrics['macro avg'] || {};
    metrics = {
      accuracy: metrics.accuracy,
      precision: macroAvg.precision,
      recall: macroAvg.recall,
      f1_score: macroAvg['f1-score'],
      classification_report: metadata.evaluation_metrics
    };
  }
  
  if (!metrics || Object.keys(metrics).length === 0) {
    return <div className="text-center p-4 text-muted">No metrics available for this project yet.</div>;
  }
  
  // Format Feature Importance for Recharts
  const fiData = Object.entries(featureImportance)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10) // Top 10
    .map(([name, value]) => ({ name, value: Number(value.toFixed(4)) }));

  // Classification Report (for text/tabular/images)
  const classReport = metrics.classification_report || {};
  const classMetricsData = Object.keys(classReport)
    .filter(k => k !== 'accuracy' && k !== 'macro avg' && k !== 'weighted avg')
    .map(className => ({
      name: className,
      precision: classReport[className]?.precision || 0,
      recall: classReport[className]?.recall || 0,
      f1: classReport[className]?.['f1-score'] || 0
    }));

  return (
    <div className="mt-3">
      <Row className="g-3 mb-4">
        {/* Metric Cards */}
        {metrics.accuracy !== undefined && (
          <Col xs={6} md={3}>
            <Card className="text-center shadow-sm border-0 h-100" style={{ background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)' }}>
              <Card.Body>
                <div className="text-muted small mb-1 fw-bold">Accuracy</div>
                <h4 className="text-success mb-0">{(metrics.accuracy * 100).toFixed(1)}%</h4>
              </Card.Body>
            </Card>
          </Col>
        )}
        {metrics.f1_score !== undefined && (
          <Col xs={6} md={3}>
            <Card className="text-center shadow-sm border-0 h-100" style={{ background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)' }}>
              <Card.Body>
                <div className="text-muted small mb-1 fw-bold">F1 Score</div>
                <h4 className="text-primary mb-0">{(metrics.f1_score * 100).toFixed(1)}%</h4>
              </Card.Body>
            </Card>
          </Col>
        )}
        {metrics.precision !== undefined && (
          <Col xs={6} md={3}>
            <Card className="text-center shadow-sm border-0 h-100" style={{ background: 'linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%)' }}>
              <Card.Body>
                <div className="text-muted small mb-1 fw-bold">Precision</div>
                <h4 className="text-info mb-0">{(metrics.precision * 100).toFixed(1)}%</h4>
              </Card.Body>
            </Card>
          </Col>
        )}
        {metrics.recall !== undefined && (
          <Col xs={6} md={3}>
            <Card className="text-center shadow-sm border-0 h-100" style={{ background: 'linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%)' }}>
              <Card.Body>
                <div className="text-muted small mb-1 fw-bold">Recall</div>
                <h4 className="text-warning mb-0">{(metrics.recall * 100).toFixed(1)}%</h4>
              </Card.Body>
            </Card>
          </Col>
        )}
      </Row>

      {classMetricsData.length > 0 && (
        <Card className="shadow-sm border-0 mb-4" style={{ borderRadius: '16px' }}>
          <Card.Body className="p-4">
            <div className="d-flex justify-content-between align-items-center mb-4">
              <h6 className="fw-bold mb-0" style={{ color: '#374151' }}>📊 Per-Class Performance</h6>
              <Button variant="light" size="sm" onClick={() => setFullscreenChart('class')} className="d-flex align-items-center justify-content-center" style={{ width: '32px', height: '32px', borderRadius: '8px' }}>
                <ArrowsFullscreen size={14} />
              </Button>
            </div>
            <div style={{ height: '300px' }}>
              <ResponsiveContainer width="100%" height="100%">
                {classMetricsData.length > 10 ? (
                  <LineChart data={classMetricsData} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} angle={-45} textAnchor="end" />
                    <YAxis domain={[0, 1]} tick={{ fill: '#6b7280', fontSize: 12 }} />
                    <RechartsTooltip formatter={(value) => (value * 100).toFixed(1) + '%'} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
                    <Legend wrapperStyle={{ paddingTop: '20px' }} />
                    <Line type="monotone" dataKey="precision" stroke="#38bdf8" name="Precision" strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }} />
                    <Line type="monotone" dataKey="recall" stroke="#fbbf24" name="Recall" strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }} />
                    <Line type="monotone" dataKey="f1" stroke="#818cf8" name="F1 Score" strokeWidth={2} dot={{ r: 2 }} activeDot={{ r: 4 }} />
                  </LineChart>
                ) : (
                  <BarChart data={classMetricsData} margin={{ top: 5, right: 30, left: 20, bottom: 25 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 12 }} angle={-45} textAnchor="end" />
                    <YAxis domain={[0, 1]} tick={{ fill: '#6b7280', fontSize: 12 }} />
                    <RechartsTooltip formatter={(value) => (value * 100).toFixed(1) + '%'} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
                    <Legend wrapperStyle={{ paddingTop: '20px' }} />
                    <Bar dataKey="precision" fill="#38bdf8" name="Precision" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="recall" fill="#fbbf24" name="Recall" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="f1" fill="#818cf8" name="F1 Score" radius={[4, 4, 0, 0]} />
                  </BarChart>
                )}
              </ResponsiveContainer>
            </div>
          </Card.Body>
        </Card>
      )}

      {fiData.length > 0 && (
        <Card className="shadow-sm border-0 mb-4" style={{ borderRadius: '16px' }}>
          <Card.Body className="p-4">
            <div className="d-flex justify-content-between align-items-center mb-4">
              <h6 className="fw-bold mb-0" style={{ color: '#374151' }}>🎯 Top Feature Importance</h6>
              <Button variant="light" size="sm" onClick={() => setFullscreenChart('feature')} className="d-flex align-items-center justify-content-center" style={{ width: '32px', height: '32px', borderRadius: '8px' }}>
                <ArrowsFullscreen size={14} />
              </Button>
            </div>
            <div style={{ height: '350px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={fiData} layout="vertical" margin={{ top: 5, right: 30, left: 100, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 12 }} />
                  <YAxis type="category" dataKey="name" width={90} tick={{ fill: '#4b5563', fontSize: 12, fontWeight: 500 }} />
                  <RechartsTooltip cursor={{ fill: '#f3f4f6' }} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
                  <Bar dataKey="value" fill="#34d399" name="Importance" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </Card.Body>
        </Card>
      )}
      {/* Fullscreen Chart Modal */}
      <Modal show={!!fullscreenChart} onHide={() => setFullscreenChart(null)} fullscreen className="bg-light">
        <Modal.Header closeButton className="border-0">
          <Modal.Title className="fw-bold">
            {fullscreenChart === 'class' ? '📊 Per-Class Performance' : '🎯 Top Feature Importance'}
          </Modal.Title>
        </Modal.Header>
        <Modal.Body className="p-4 bg-white m-3" style={{ borderRadius: '16px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
          <div style={{ height: 'calc(100vh - 150px)', width: '100%' }}>
            {fullscreenChart === 'class' && (
              <ResponsiveContainer width="100%" height="100%">
                {classMetricsData.length > 10 ? (
                  <LineChart data={classMetricsData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 14 }} angle={-45} textAnchor="end" interval={0} />
                    <YAxis domain={[0, 1]} tick={{ fill: '#6b7280', fontSize: 14 }} />
                    <RechartsTooltip formatter={(value) => (value * 100).toFixed(1) + '%'} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
                    <Legend wrapperStyle={{ paddingTop: '40px', fontSize: '1.2em' }} />
                    <Line type="monotone" dataKey="precision" stroke="#38bdf8" name="Precision" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                    <Line type="monotone" dataKey="recall" stroke="#fbbf24" name="Recall" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                    <Line type="monotone" dataKey="f1" stroke="#818cf8" name="F1 Score" strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }} />
                  </LineChart>
                ) : (
                  <BarChart data={classMetricsData} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                    <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 14 }} angle={-45} textAnchor="end" interval={0} />
                    <YAxis domain={[0, 1]} tick={{ fill: '#6b7280', fontSize: 14 }} />
                    <RechartsTooltip formatter={(value) => (value * 100).toFixed(1) + '%'} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
                    <Legend wrapperStyle={{ paddingTop: '40px', fontSize: '1.2em' }} />
                    <Bar dataKey="precision" fill="#38bdf8" name="Precision" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="recall" fill="#fbbf24" name="Recall" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="f1" fill="#818cf8" name="F1 Score" radius={[4, 4, 0, 0]} />
                  </BarChart>
                )}
              </ResponsiveContainer>
            )}
            
            {fullscreenChart === 'feature' && (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={fiData} layout="vertical" margin={{ top: 20, right: 30, left: 150, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e5e7eb" />
                  <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 14 }} />
                  <YAxis type="category" dataKey="name" width={140} tick={{ fill: '#4b5563', fontSize: 14, fontWeight: 500 }} />
                  <RechartsTooltip cursor={{ fill: '#f3f4f6' }} contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }} />
                  <Bar dataKey="value" fill="#34d399" name="Importance" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </Modal.Body>
      </Modal>
    </div>
  );
};

export default MetricsViewer;
