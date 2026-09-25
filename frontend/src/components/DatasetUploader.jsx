import React, { useState, useRef, useCallback } from 'react';
import { Card, Form, Button, ProgressBar, Badge, Alert, Row, Col, Spinner } from 'react-bootstrap';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CloudUpload,
  FileEarmarkZip,
  XCircle,
  CheckCircleFill,
  ExclamationTriangleFill,
  Cpu,
  Folder2Open,
  ArrowRepeat,
  Trash
} from 'react-bootstrap-icons';
import { uploadCustomDataset } from '../services/mlApi';

const MAX_FILE_SIZE_MB = 500;
const ALLOWED_EXTENSIONS = ['.zip', '.tar.gz', '.rar'];

const DatasetUploader = ({ user, onProjectCreated }) => {
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState(null); // 'success' | 'error'
  const [uploadMessage, setUploadMessage] = useState('');
  const [projectId, setProjectId] = useState(null);
  const [validationError, setValidationError] = useState('');

  const [projectName, setProjectName] = useState('');
  const [taskType, setTaskType] = useState('image_classification');
  const [preferredModel, setPreferredModel] = useState('resnet18');
  const [description, setDescription] = useState('');

  const fileInputRef = useRef(null);

  const validateFile = (f) => {
    if (!f) return 'No file selected';

    const name = f.name.toLowerCase();
    const isValidExt = ALLOWED_EXTENSIONS.some(ext => name.endsWith(ext));
    if (!isValidExt) {
      return `Invalid file type. Allowed: ${ALLOWED_EXTENSIONS.join(', ')}`;
    }

    const sizeMB = f.size / (1024 * 1024);
    if (sizeMB > MAX_FILE_SIZE_MB) {
      return `File too large (${sizeMB.toFixed(1)}MB). Maximum is ${MAX_FILE_SIZE_MB}MB.`;
    }

    return '';
  };

  const handleFile = useCallback((f) => {
    const error = validateFile(f);
    if (error) {
      setValidationError(error);
      setFile(null);
      return;
    }
    setValidationError('');
    setFile(f);
    setUploadStatus(null);
    setUploadMessage('');

    // Auto-generate project name from filename if empty
    if (!projectName) {
      const baseName = f.name.replace(/\.(zip|tar\.gz|rar)$/i, '').replace(/[_-]/g, ' ');
      setProjectName(baseName.charAt(0).toUpperCase() + baseName.slice(1));
    }
  }, [projectName]);

  const handleDrag = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  }, [handleFile]);

  const handleInputChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFile(e.target.files[0]);
    }
  };

  const handleRemoveFile = () => {
    setFile(null);
    setValidationError('');
    setUploadStatus(null);
    setUploadMessage('');
    setProjectId(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleUpload = async (e) => {
    e.preventDefault();

    if (!file || !projectName.trim()) return;

    setUploading(true);
    setUploadProgress(0);
    setUploadStatus(null);
    setUploadMessage('');

    const formData = new FormData();
    formData.append('dataset', file);
    formData.append('project_name', projectName.trim());
    formData.append('task_type', taskType);
    formData.append('preferred_model', preferredModel);
    formData.append('description', description.trim());

    try {
      const response = await uploadCustomDataset(formData, (progressEvent) => {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
        setUploadProgress(percent);
      });

      setUploadStatus('success');
      setUploadMessage(response.data.message || 'Dataset uploaded and project created successfully!');
      setProjectId(response.data.projectId);

      if (onProjectCreated) {
        onProjectCreated();
      }
    } catch (error) {
      console.error('Upload error:', error);
      setUploadStatus('error');
      setUploadMessage(
        error.response?.data?.error ||
        error.response?.data?.details ||
        'Failed to upload dataset. Please try again.'
      );
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setProjectName('');
    setTaskType('image_classification');
    setPreferredModel('resnet18');
    setDescription('');
    setUploadStatus(null);
    setUploadMessage('');
    setUploadProgress(0);
    setProjectId(null);
    setValidationError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const formatFileSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
    >
      <Card className="border-0 shadow-sm" style={{ borderRadius: '20px', overflow: 'hidden' }}>
        {/* Header */}
        <Card.Header
          className="border-0 text-white"
          style={{
            background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%)',
            padding: '28px 32px'
          }}
        >
          <div className="d-flex align-items-center gap-3">
            <div
              style={{
                width: '48px',
                height: '48px',
                borderRadius: '14px',
                background: 'rgba(255,255,255,0.2)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backdropFilter: 'blur(10px)'
              }}
            >
              <CloudUpload size={24} />
            </div>
            <div>
              <h5 className="mb-1 fw-bold">Upload Custom Dataset</h5>
              <p className="mb-0" style={{ opacity: 0.85, fontSize: '0.9em' }}>
                Upload your own dataset for quick model training & evaluation
              </p>
            </div>
          </div>
        </Card.Header>

        <Card.Body className="p-4">
          {/* Success state */}
          <AnimatePresence>
            {uploadStatus === 'success' && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
              >
                <Alert
                  variant="success"
                  className="border-0 mb-4"
                  style={{
                    background: 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)',
                    borderRadius: '16px',
                    padding: '24px'
                  }}
                >
                  <div className="d-flex align-items-start gap-3">
                    <CheckCircleFill size={28} className="text-success flex-shrink-0 mt-1" />
                    <div>
                      <h6 className="fw-bold text-success mb-2">Upload Successful!</h6>
                      <p className="mb-2" style={{ color: '#065f46' }}>{uploadMessage}</p>
                      {projectId && (
                        <Badge bg="success" className="me-2" style={{ fontSize: '0.85em' }}>
                          Project ID: {projectId.slice(0, 8)}...
                        </Badge>
                      )}
                      <Badge
                        bg="info"
                        style={{ fontSize: '0.85em' }}
                      >
                        Status: Training Queued
                      </Badge>
                      <div className="mt-3">
                        <Button
                          size="sm"
                          variant="outline-success"
                          onClick={handleReset}
                          style={{ borderRadius: '10px', fontWeight: '600' }}
                        >
                          <CloudUpload className="me-2" size={14} />
                          Upload Another Dataset
                        </Button>
                      </div>
                    </div>
                  </div>
                </Alert>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error state */}
          <AnimatePresence>
            {uploadStatus === 'error' && (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
              >
                <Alert
                  variant="danger"
                  className="border-0 mb-4"
                  style={{
                    background: 'linear-gradient(135deg, #fef2f2 0%, #fecaca 100%)',
                    borderRadius: '16px',
                    padding: '24px'
                  }}
                >
                  <div className="d-flex align-items-start gap-3">
                    <ExclamationTriangleFill size={24} className="text-danger flex-shrink-0 mt-1" />
                    <div>
                      <h6 className="fw-bold text-danger mb-1">Upload Failed</h6>
                      <p className="mb-0" style={{ color: '#991b1b' }}>{uploadMessage}</p>
                    </div>
                  </div>
                </Alert>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Upload Form — hidden after success */}
          {uploadStatus !== 'success' && (
            <Form onSubmit={handleUpload}>
              <Row className="g-4">
                {/* Left Column — File Drop Zone */}
                <Col xs={12} lg={5}>
                  <div
                    onDragEnter={handleDrag}
                    onDragLeave={handleDrag}
                    onDragOver={handleDrag}
                    onDrop={handleDrop}
                    onClick={() => !file && fileInputRef.current?.click()}
                    style={{
                      border: `2px dashed ${dragActive ? '#6366f1' : validationError ? '#ef4444' : file ? '#10b981' : '#d1d5db'}`,
                      borderRadius: '16px',
                      padding: file ? '24px' : '48px 24px',
                      textAlign: 'center',
                      cursor: file ? 'default' : 'pointer',
                      background: dragActive
                        ? 'linear-gradient(135deg, #eef2ff 0%, #e0e7ff 100%)'
                        : file
                          ? 'linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%)'
                          : '#fafafa',
                      transition: 'all 0.3s ease',
                      minHeight: '220px',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      justifyContent: 'center'
                    }}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".zip,.tar.gz,.rar"
                      onChange={handleInputChange}
                      style={{ display: 'none' }}
                    />

                    {!file ? (
                      <motion.div
                        animate={{ y: dragActive ? -5 : 0 }}
                        transition={{ duration: 0.2 }}
                      >
                        <CloudUpload
                          size={48}
                          style={{
                            color: dragActive ? '#6366f1' : '#9ca3af',
                            marginBottom: '16px'
                          }}
                        />
                        <p className="fw-semibold mb-1" style={{ color: '#374151' }}>
                          {dragActive ? 'Drop your dataset here!' : 'Drag & drop your dataset'}
                        </p>
                        <p className="mb-2" style={{ color: '#9ca3af', fontSize: '0.9em' }}>
                          or click to browse files
                        </p>
                        <div className="d-flex gap-2 justify-content-center flex-wrap">
                          {ALLOWED_EXTENSIONS.map(ext => (
                            <Badge
                              key={ext}
                              bg="light"
                              text="dark"
                              style={{
                                fontSize: '0.75em',
                                padding: '4px 10px',
                                borderRadius: '8px',
                                border: '1px solid #e5e7eb'
                              }}
                            >
                              {ext}
                            </Badge>
                          ))}
                        </div>
                        <p className="mt-2 mb-0" style={{ color: '#9ca3af', fontSize: '0.8em' }}>
                          Max size: {MAX_FILE_SIZE_MB}MB
                        </p>
                      </motion.div>
                    ) : (
                      <motion.div
                        initial={{ opacity: 0, scale: 0.9 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="w-100"
                      >
                        <div className="d-flex align-items-center gap-3">
                          <div
                            style={{
                              width: '52px',
                              height: '52px',
                              borderRadius: '14px',
                              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0
                            }}
                          >
                            <FileEarmarkZip size={24} className="text-white" />
                          </div>
                          <div className="text-start flex-grow-1" style={{ minWidth: 0 }}>
                            <p
                              className="fw-semibold mb-0"
                              style={{
                                color: '#1f2937',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}
                            >
                              {file.name}
                            </p>
                            <p className="mb-0" style={{ color: '#6b7280', fontSize: '0.85em' }}>
                              {formatFileSize(file.size)}
                            </p>
                          </div>
                          <Button
                            variant="link"
                            onClick={(e) => { e.stopPropagation(); handleRemoveFile(); }}
                            style={{ color: '#ef4444', padding: '4px' }}
                            disabled={uploading}
                          >
                            <Trash size={18} />
                          </Button>
                        </div>
                      </motion.div>
                    )}
                  </div>

                  {validationError && (
                    <motion.div
                      initial={{ opacity: 0, y: -5 }}
                      animate={{ opacity: 1, y: 0 }}
                    >
                      <Alert
                        variant="danger"
                        className="mt-2 mb-0 py-2 px-3 border-0"
                        style={{ borderRadius: '10px', fontSize: '0.85em' }}
                      >
                        <ExclamationTriangleFill className="me-2" size={14} />
                        {validationError}
                      </Alert>
                    </motion.div>
                  )}

                  {/* Dataset structure hint */}
                  <div
                    className="mt-3 p-3"
                    style={{
                      background: '#f0f9ff',
                      borderRadius: '12px',
                      border: '1px solid #bae6fd',
                      fontSize: '0.82em'
                    }}
                  >
                    <p className="fw-semibold mb-2" style={{ color: '#0369a1' }}>
                      <Folder2Open className="me-2" size={14} />
                      Expected folder structure:
                    </p>
                    <pre
                      className="mb-0"
                      style={{
                        color: '#0c4a6e',
                        fontSize: '0.9em',
                        lineHeight: '1.6',
                        background: 'transparent',
                        border: 'none',
                        padding: 0,
                        margin: 0
                      }}
                    >
{`dataset.zip/
├── train/
│   ├── class_1/  (images...)
│   └── class_2/  (images...)
└── val/
    ├── class_1/  (images...)
    └── class_2/  (images...)`}
                    </pre>
                  </div>
                </Col>

                {/* Right Column — Project Config */}
                <Col xs={12} lg={7}>
                  <div
                    className="p-4"
                    style={{
                      background: '#f9fafb',
                      borderRadius: '16px',
                      border: '1px solid #f3f4f6',
                      height: '100%'
                    }}
                  >
                    <h6 className="fw-bold mb-3" style={{ color: '#374151' }}>
                      <Cpu className="me-2" size={16} />
                      Project Configuration
                    </h6>

                    <Form.Group className="mb-3">
                      <Form.Label className="fw-semibold" style={{ fontSize: '0.9em', color: '#4b5563' }}>
                        Project Name *
                      </Form.Label>
                      <Form.Control
                        type="text"
                        placeholder="e.g., Cat vs Dog Classifier"
                        value={projectName}
                        onChange={(e) => setProjectName(e.target.value)}
                        required
                        disabled={uploading}
                        style={{
                          borderRadius: '10px',
                          border: '2px solid #e5e7eb',
                          padding: '10px 14px'
                        }}
                      />
                    </Form.Group>

                    <Form.Group className="mb-3">
                      <Form.Label className="fw-semibold" style={{ fontSize: '0.9em', color: '#4b5563' }}>
                        Description
                      </Form.Label>
                      <Form.Control
                        as="textarea"
                        rows={2}
                        placeholder="Brief description of your dataset and goal..."
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        disabled={uploading}
                        style={{
                          borderRadius: '10px',
                          border: '2px solid #e5e7eb',
                          padding: '10px 14px',
                          resize: 'none'
                        }}
                      />
                    </Form.Group>

                    <Row className="g-3 mb-3">
                      <Col xs={12} sm={6}>
                        <Form.Group>
                          <Form.Label className="fw-semibold" style={{ fontSize: '0.9em', color: '#4b5563' }}>
                            Task Type
                          </Form.Label>
                          <Form.Select
                            value={taskType}
                            onChange={(e) => setTaskType(e.target.value)}
                            disabled={uploading}
                            style={{
                              borderRadius: '10px',
                              border: '2px solid #e5e7eb',
                              padding: '10px 14px'
                            }}
                          >
                            <option value="image_classification">Image Classification</option>
                          </Form.Select>
                        </Form.Group>
                      </Col>
                      <Col xs={12} sm={6}>
                        <Form.Group>
                          <Form.Label className="fw-semibold" style={{ fontSize: '0.9em', color: '#4b5563' }}>
                            Model Architecture
                          </Form.Label>
                          <Form.Select
                            value={preferredModel}
                            onChange={(e) => setPreferredModel(e.target.value)}
                            disabled={uploading}
                            style={{
                              borderRadius: '10px',
                              border: '2px solid #e5e7eb',
                              padding: '10px 14px'
                            }}
                          >
                            <option value="resnet18">ResNet-18 (Fast)</option>
                            <option value="resnet34">ResNet-34 (Balanced)</option>
                            <option value="resnet50">ResNet-50 (Accurate)</option>
                            <option value="mobilenet_v2">MobileNet V2 (Lightweight)</option>
                            <option value="efficientnet_b0">EfficientNet-B0 (Efficient)</option>
                          </Form.Select>
                        </Form.Group>
                      </Col>
                    </Row>

                    {/* Upload progress */}
                    <AnimatePresence>
                      {uploading && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="mb-3"
                        >
                          <div
                            className="p-3"
                            style={{
                              background: 'white',
                              borderRadius: '12px',
                              border: '1px solid #e5e7eb'
                            }}
                          >
                            <div className="d-flex justify-content-between mb-2">
                              <span className="fw-semibold" style={{ fontSize: '0.85em', color: '#4b5563' }}>
                                <Spinner animation="border" size="sm" className="me-2" />
                                {uploadProgress < 100 ? 'Uploading dataset...' : 'Creating project & processing...'}
                              </span>
                              <span className="fw-bold" style={{ fontSize: '0.85em', color: '#6366f1' }}>
                                {uploadProgress}%
                              </span>
                            </div>
                            <ProgressBar
                              now={uploadProgress}
                              animated
                              striped
                              style={{
                                height: '8px',
                                borderRadius: '4px',
                                background: '#e5e7eb'
                              }}
                              variant="primary"
                            />
                            <p className="mt-2 mb-0" style={{ color: '#9ca3af', fontSize: '0.8em' }}>
                              {uploadProgress < 100
                                ? 'Uploading to cloud storage...'
                                : 'Setting up project and queuing for training...'}
                            </p>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {/* Submit button */}
                    <Button
                      type="submit"
                      disabled={!file || !projectName.trim() || uploading || uploadStatus === 'success'}
                      className="w-100"
                      style={{
                        background: !file || !projectName.trim() || uploading
                          ? '#d1d5db'
                          : 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%)',
                        border: 'none',
                        borderRadius: '12px',
                        padding: '14px',
                        fontWeight: '700',
                        fontSize: '1em',
                        letterSpacing: '0.3px',
                        boxShadow: !file || !projectName.trim() || uploading
                          ? 'none'
                          : '0 4px 15px rgba(99, 102, 241, 0.4)',
                        transition: 'all 0.3s ease'
                      }}
                    >
                      {uploading ? (
                        <>
                          <ArrowRepeat className="me-2 spin-animation" size={18} />
                          Processing...
                        </>
                      ) : (
                        <>
                          <CloudUpload className="me-2" size={18} />
                          Upload & Start Training
                        </>
                      )}
                    </Button>
                  </div>
                </Col>
              </Row>
            </Form>
          )}
        </Card.Body>
      </Card>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        .spin-animation {
          animation: spin 1s linear infinite;
        }
      `}</style>
    </motion.div>
  );
};

export default DatasetUploader;
